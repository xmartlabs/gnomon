import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime

from gnomon.sources._util import _texts, _iso_ms
from gnomon.config import strip_injections, parse_ts, line_count
from gnomon.taxonomy import _canon_tool, _canon_input
from gnomon.sources.discovery import CURSOR_DIR, CURSOR_DB


_CURSOR_TOOL_MAP = {
    "run_terminal_command_v2": "Bash", "run_terminal_cmd": "Bash",
    "read_file_v2": "Read", "read_file": "Read",
    "edit_file_v2": "Edit", "edit_file": "Edit", "search_replace": "Edit",
    "str_replace": "Edit", "apply_patch": "Edit",
    "delete_file": "Edit", "delete": "Edit", "write_file": "Write",
    "glob_file_search": "Glob", "list_dir_v2": "Glob", "list_dir": "Glob",
    "ripgrep_raw_search": "Grep", "semantic_search_full": "Grep",
    "semantic_search": "Grep", "rg": "Grep",
    "web_search": "WebSearch", "web_fetch": "WebFetch",
    "task_v2": "Agent", "subagent": "Agent", "todo_write": "TodoWrite",
    "create_plan": "EnterPlanMode", "ask_question": "AskUserQuestion",
    "read_lints": "Read", "edit_notebook": "NotebookEdit",
    "await_shell": "BashOutput", "await": "BashOutput",
    # Cursor's plan/step-tracking tools ~ Claude's TodoWrite (mirrors codex.py mapping
    # of `update_plan` -> TodoWrite). Counted as planning, not noise.
    "update_current_step": "TodoWrite", "update_todo": "TodoWrite",
    "update_todos": "TodoWrite",
}

_CURSOR_PATCH_FILE_RE = re.compile(r"^\*{3}\s*(?:Update|Add|Create|Delete)\s+File:\s*(.+)$", re.M)


def _cursor_project_cwd(project_slug):
    """Best-effort reverse of Cursor's project folder slug -> workspace path.

    Cursor flattens the absolute path into a slug joining segments with '-', but folder
    names themselves contain '-' too (`Users-mirland-Projects-carp-health-flutter`), so a
    blind `replace('-', '/')` invents a non-existent path (`.../carp/health/flutter`) and
    git churn silently reads 0. The ambiguity is real, so we resolve it against the disk:
    descend through path segments that actually exist as directories, then treat whatever
    is left as the leaf folder name (dashes preserved). Numeric / temp slugs that don't map
    to a home path return None."""
    if not project_slug:
        return None
    norm = project_slug.replace("\\", "/").strip("/")
    # Only home-anchored slugs map to a real workspace; numeric ids / var-folders / etc. don't.
    head = norm.split("-", 1)[0].split("/", 1)[0]
    if head not in ("Users", "home"):
        return None
    tokens = norm.replace("/", "-").split("-")
    path = ""
    i = 0
    # Descend while each next token is a real directory at this level.
    while i < len(tokens):
        cand = (path + "/" + tokens[i]) if path else ("/" + tokens[i])
        if os.path.isdir(cand):
            path = cand
            i += 1
        else:
            break
    # Remaining tokens form the leaf folder name, with its internal dashes restored.
    if i < len(tokens):
        leaf = "-".join(tokens[i:])
        path = (path + "/" + leaf) if path else ("/" + leaf)
    if path and os.path.isdir(path):
        return path
    # Nothing on disk matched (history copied/mounted, repo since deleted): fall back to
    # the naive '-'->'/' reconstruction so the workspace still gets a label, even though
    # git churn won't find a repo there.
    return "/" + norm.replace("-", "/")


def _cursor_jsonl_meta(fp):
    """Return (sessionId, cwd, is_sidechain) from an agent-transcripts path.
    Subagent transcripts (.../​<session>/subagents/<id>.jsonl) attribute to the PARENT
    session id, mirroring Claude's sidechains-share-the-session semantics."""
    norm = fp.replace("\\", "/")
    sid = os.path.basename(fp).rsplit(".", 1)[0]
    is_sidechain = "/subagents/" in norm
    cwd = None
    parts = norm.split("/agent-transcripts/")
    if len(parts) == 2:
        proj = parts[0].rstrip("/").split("/")[-1]
        cwd = _cursor_project_cwd(proj)
        if is_sidechain:
            sid = parts[1].split("/")[0] or sid
    return sid, cwd, is_sidechain


_CURSOR_WRAPPER_RE = re.compile(
    r"<(attached_files|image_files|manually_attached_skills|available_skills|agent_skills|"
    r"external_links|code_selection|recently_viewed_files|open_and_recently_viewed_files|"
    r"linter_errors|system_notification|system_reminder|additional_data|user_info|"
    r"current_file|cursor_position|edit_history|timestamp)>.*?</\1>", re.S | re.I)


def _cursor_clean_prompt(text):
    if not text:
        return ""
    # The human-typed turn lives inside <user_query>...</user_query>; everything around it
    # is injected context. When the tag is present, keep ONLY its contents.
    found = re.findall(r"<user_query>(.*?)</user_query>", text, flags=re.S | re.I)
    if found:
        text = "\n".join(found)
    else:
        text = _CURSOR_WRAPPER_RE.sub("", text)
    return strip_injections(text).strip()


def _cursor_tool_key(name):
    """snake_case a Cursor tool name ('StrReplace' -> 'str_replace') for map lookup."""
    n = str(name or "tool")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", n).lower().replace("-", "_")


def _cursor_mcp_name(key):
    """Canonicalize a Cursor MCP tool key ('mcp_figma_get_design_context') to
    'mcp__<server>__<tool>' so the server is one bucket, not one-per-tool. The raw name
    flattens server+tool with single separators, so '__'.split downstream used to read the
    whole tail as a distinct 'server' and inflate mcp_servers_distinct."""
    rest = key[len("mcp"):].lstrip("_")
    parts = [p for p in rest.split("_") if p]
    if len(parts) >= 2:
        return f"mcp__{parts[0]}__{'_'.join(parts[1:])}"
    if len(parts) == 1:
        return f"mcp__cursor__{parts[0]}"
    return "mcp__cursor__tool"


def _cursor_tool_name(name):
    n = str(name or "tool")
    key = _cursor_tool_key(n)
    if n.startswith("mcp__"):
        return n
    if key == "mcp" or key.startswith("mcp_"):
        return _cursor_mcp_name(key)
    mapped = _CURSOR_TOOL_MAP.get(key)
    if mapped:
        return mapped
    # Fall back to the NORMALIZED key, not the raw name, so casing variants of an
    # unmapped tool ('UpdateCurrentStep' / 'updateCurrentStep') collapse to one entry.
    return _canon_tool(key)


def _cursor_tool_input(raw_name, raw):
    key = _cursor_tool_key(raw_name)
    if isinstance(raw, str):
        if key == "apply_patch":
            # ApplyPatch carries the raw patch text, not JSON -- count it like Codex's
            # apply_patch (patch lines as added churn; diff markers over-count a bit).
            m = _CURSOR_PATCH_FILE_RE.search(raw)
            raw = {"new_string": raw, "old_string": "",
                   "file_path": m.group(1).strip() if m else ""}
        else:
            try:
                raw = json.loads(raw or "{}")
            except Exception:
                raw = {"raw": raw}
    if not isinstance(raw, dict):
        raw = {}
    cname = _cursor_tool_name(raw_name)
    inp = dict(raw)
    if cname == "Bash":
        inp.setdefault("command", inp.get("command") or "")
    elif cname in ("Read", "Write", "Edit", "MultiEdit"):
        fp = (inp.get("targetFile") or inp.get("file_path") or inp.get("path")
              or inp.get("filePath") or inp.get("relativeWorkspacePath"))
        if fp:
            inp["file_path"] = fp
        if cname == "Edit":
            inp.setdefault("new_string", inp.get("codeEdit") or inp.get("code")
                            or inp.get("new_string") or "")
            inp.setdefault("old_string", inp.get("old_string") or inp.get("oldString") or "")
        if cname == "Write":
            inp.setdefault("content", inp.get("contents") or inp.get("code") or "")
    return _canon_input(cname, inp)


def _cursor_tool(raw_name, raw_input):
    """Resolve a Cursor tool call to (canonical name, normalized input).
    CallMcpTool is special: the real MCP tool lives in the input (server/toolName),
    so it's renamed mcp__<server>__<tool> to count as an MCP call, not a native one."""
    inp = _cursor_tool_input(raw_name, raw_input)
    if _cursor_tool_key(raw_name) == "call_mcp_tool":
        server = str(inp.get("server") or "server")
        tool = str(inp.get("toolName") or inp.get("tool_name") or "tool")
        return f"mcp__{server}__{tool}", inp
    return _cursor_tool_name(raw_name), inp


def _cursor_jsonl_blocks(content):
    blocks = []
    if isinstance(content, str):
        if content:
            blocks.append({"type": "text", "text": content})
        return blocks
    if not isinstance(content, list):
        return blocks
    for part in content:
        if not isinstance(part, dict):
            continue
        pt = part.get("type")
        if pt == "text" and part.get("text"):
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif pt == "thinking":
            blocks.append({"type": "thinking",
                            "thinking": part.get("thinking") or part.get("text") or ""})
        elif pt in ("tool_use", "toolCall"):
            raw_inp = part.get("input") or part.get("arguments") or {}
            name, inp = _cursor_tool(part.get("name"), raw_inp)
            blocks.append({"type": "tool_use", "name": name, "input": inp})
        elif pt == "tool_result":
            blocks.append({"type": "tool_result",
                           "is_error": bool(part.get("is_error") or part.get("isError"))})
    return blocks


def _cursor_jsonl_events(fp):
    sid, cwd, is_sidechain = _cursor_jsonl_meta(fp)
    base = {"sessionId": sid, "cwd": cwd}
    if is_sidechain:
        base["isSidechain"] = True
    # Real Cursor JSONL carries NO per-event timestamps (the SQLite copy of the same
    # session does -- and is preferred). For JSONL-only sessions, stamp the FIRST event
    # with the file mtime so the session still lands on the calendar / time window,
    # without flooding the hour histogram with thousands of identical fake timestamps.
    mtime_iso = None
    try:
        mtime_iso = datetime.fromtimestamp(os.path.getmtime(fp)).astimezone().isoformat()
    except Exception:
        pass
    first = True
    try:
        fh = open(fp, "r", errors="replace")
    except Exception:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                yield {"__bad__": True}
                continue
            if not isinstance(obj, dict):
                yield {"__bad__": True}
                continue
            role = obj.get("role")
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
            ts = obj.get("timestamp") or msg.get("timestamp")
            # Stamp EVERY timestampless event with the file mtime -- not just the first --
            # so monthly/backfill date-window runs don't drop later prompts/tool calls of
            # a JSONL-only Cursor session (the window gate skips dt-None events). The first
            # event is the session's representative point and feeds the hour/weekday
            # histograms; later mtime-stamped events are flagged synthetic so they're
            # excluded from those histograms (avoiding a fake spike in one bucket) while
            # still being counted as prompts/tool calls inside the window.
            synth_ts = False
            if ts is None:
                ts = mtime_iso
                synth_ts = not first
            content = msg.get("content")
            if role == "user":
                text = _cursor_clean_prompt(_texts(content))
                if text:
                    first = False
                    yield {**base, "type": "user", "timestamp": ts, "__synth_ts__": synth_ts,
                           "message": {"role": "user", "content": text}}
            elif role == "assistant":
                blocks = _cursor_jsonl_blocks(content)
                tool_results = [b for b in blocks if b.get("type") == "tool_result"]
                blocks = [b for b in blocks if b.get("type") != "tool_result"]
                if blocks:
                    first = False
                    yield {**base, "type": "assistant", "timestamp": ts, "__synth_ts__": synth_ts,
                           "message": {"role": "assistant", "model": msg.get("model"),
                                       "content": blocks}}
                if tool_results:
                    yield {**base, "type": "user", "timestamp": ts, "__synth_ts__": synth_ts,
                           "message": {"role": "user", "content": tool_results}}
            elif role is None and obj.get("type") == "turn_ended":
                # status-only marker line; a failed turn is the closest thing the JSONL
                # format has to an API error signal ("aborted" = user stop, not an error)
                if str(obj.get("status") or "").lower() in ("error", "failed"):
                    yield {**base, "type": "system", "timestamp": ts, "__synth_ts__": synth_ts,
                           "isApiErrorMessage": True}


def _cursor_bubble_blocks(bubble):
    blocks = []
    text = bubble.get("text") or ""
    if text:
        blocks.append({"type": "text", "text": text})
    for tb in bubble.get("allThinkingBlocks") or []:
        if isinstance(tb, dict):
            t = tb.get("text") or tb.get("thinking") or ""
            if t:
                blocks.append({"type": "thinking", "thinking": t})
        elif isinstance(tb, str) and tb:
            blocks.append({"type": "thinking", "thinking": tb})
    tfd = bubble.get("toolFormerData")
    tool_meta = None
    if isinstance(tfd, dict) and tfd.get("name"):
        name, inp = _cursor_tool(tfd.get("name"), tfd.get("params"))
        blocks.append({"type": "tool_use", "name": name, "input": inp})
        st = str(tfd.get("status") or "completed").lower()
        if st in ("error", "failed"):
            tool_meta = True
        elif st in ("completed", "success", "done"):
            tool_meta = False
        # cancelled / aborted / interrupted: user stopped it -- neither success nor error
    return blocks, tool_meta


def _cursor_open_sqlite(db_path):
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        return None


def _cursor_jsonl_edit_inputs(fp):
    """Per-tool FIFO queues of churn-bearing inputs (Edit/Write/MultiEdit) from a
    session's JSONL twin. The SQLite copy of the same session stores only the edited
    file's path in its tool params -- the old/new strings live ONLY in the JSONL -- so
    the SQLite reader pops these to backfill churn, pairing nth Edit with nth Edit."""
    queues = defaultdict(list)
    for ev in _cursor_jsonl_events(fp):
        msg = ev.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if (isinstance(b, dict) and b.get("type") == "tool_use"
                    and b.get("name") in ("Edit", "Write", "MultiEdit")):
                queues[b["name"]].append(b.get("input") or {})
    return queues


def _cursor_sqlite_events(db_path, twins=None):
    conn = _cursor_open_sqlite(db_path)
    if conn is None:
        return
    twins = twins or {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
        ).fetchall()
    except Exception:
        conn.close()
        return
    for key, val in rows:
        composer_id = key.split(":", 1)[-1]
        try:
            meta = json.loads(val)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        headers = meta.get("fullConversationHeadersOnly") or []
        if not headers:
            continue
        # cwd comes from the JSONL twin's project slug -- the DB stores no workspace path
        twin = twins.get(composer_id) or {}
        base = {"sessionId": composer_id, "cwd": twin.get("cwd")}
        # The real model lives on the session, not the bubble: composerData carries
        # modelConfig.modelName (e.g. "claude-4.5-sonnet-thinking", "gemini-3-pro",
        # "default"). Per-bubble `model` is always None on disk, so without this the
        # whole source reads as model-less and AQ Model mix collapses to 0.
        session_model = (meta.get("modelConfig") or {}).get("modelName")
        edit_queues = _cursor_jsonl_edit_inputs(twin["jsonl"]) if twin.get("jsonl") else None
        for hdr in headers:
            if not isinstance(hdr, dict):
                continue
            bubble_id = hdr.get("bubbleId")
            if not bubble_id:
                continue
            bkey = f"bubbleId:{composer_id}:{bubble_id}"
            try:
                brow = conn.execute(
                    "SELECT value FROM cursorDiskKV WHERE key = ?", (bkey,)
                ).fetchone()
            except Exception:
                continue
            if not brow:
                continue
            try:
                bubble = json.loads(brow[0])
            except Exception:
                continue
            if not isinstance(bubble, dict):
                continue
            ts = bubble.get("createdAt")
            btype = hdr.get("type")
            if btype is None:
                btype = bubble.get("type")
            blocks, tool_err = _cursor_bubble_blocks(bubble)
            if edit_queues:
                for b in blocks:
                    if (b.get("type") == "tool_use" and b.get("name") in edit_queues
                            and not (b["input"].get("new_string") or b["input"].get("content")
                                     or b["input"].get("edits"))):
                        for k, v in edit_queues[b["name"]].pop(0).items():
                            if not b["input"].get(k):   # fill missing AND ""-normalized keys
                                b["input"][k] = v
                        if not edit_queues[b["name"]]:
                            del edit_queues[b["name"]]
            if btype == 1:
                text = _texts(blocks) or bubble.get("text") or ""
                if text:
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user", "content": text}}
            elif btype == 2:
                # Attach Cursor tokenCount to same assistant event instead of creating
                # a separate usage-only turn. Ignore empty token payloads.
                tok_count = bubble.get("tokenCount")
                msg = {"role": "assistant"}
                if session_model:
                    msg["model"] = session_model
                usage = None
                if isinstance(tok_count, dict):
                    input_tok = int(tok_count.get("inputTokens") or 0)
                    output_tok = int(tok_count.get("outputTokens") or 0)
                    if input_tok > 0 or output_tok > 0:
                        # Keep the real model if we have one; only fall back to "cursor"
                        # so tokens are still attributed to *something* in by_model.
                        msg.setdefault("model", "cursor")
                        usage = {
                            "input_tokens": input_tok,
                            "output_tokens": output_tok,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                        }
                        msg["usage"] = usage
                if blocks:
                    msg["content"] = blocks
                    yield {**base, "type": "assistant", "timestamp": ts,
                           "message": msg}
                elif usage:
                    # Blocks-empty but has tokens: emit usage-only event (with empty content)
                    msg["content"] = []
                    yield {**base, "type": "assistant", "timestamp": ts,
                           "message": msg}
                if tool_err is not None:
                    yield {**base, "type": "user", "timestamp": ts,
                           "message": {"role": "user",
                                       "content": [{"type": "tool_result",
                                                    "is_error": bool(tool_err)}]}}
    conn.close()


def _cursor_dedup(sources):
    """Prefer the SQLite copy of a Cursor session over its JSONL transcript.

    The same modern session exists in BOTH places with complementary data: SQLite
    bubbles carry per-event timestamps and tool error statuses (JSONL has neither),
    while the JSONL carries full tool inputs -- edit old/new strings the SQLite params
    omit -- and the workspace path (via the project folder slug). So JSONL files whose
    session id is already a composer in state.vscdb are dropped from the event stream,
    and a twin map {sessionId: {"cwd", "jsonl"}} is forwarded to the SQLite reader,
    which backfills cwd and churn-bearing edit inputs from the twin.
    Subagent sidechains exist only as JSONL and are always kept.
    Returns (filtered sources, twin map)."""
    if not any(fmt == "cursor-jsonl" for _, _, fmt in sources):
        return sources, {}
    sqlite_ids = _cursor_sqlite_composer_ids(CURSOR_DB)
    twins = {}
    out = []
    for entry in sources:
        src, fp, fmt = entry
        if fmt != "cursor-jsonl":
            out.append(entry)
            continue
        sid, cwd, is_sidechain = _cursor_jsonl_meta(fp)
        if is_sidechain or sid not in sqlite_ids:
            out.append(entry)
        else:
            twins[sid] = {"cwd": cwd, "jsonl": fp}
    return out, twins


def _cursor_sqlite_composer_ids(db_path):
    """Composer (session) UUIDs present in state.vscdb; empty set if unreadable."""
    if not db_path or not os.path.isfile(db_path):
        return set()
    conn = _cursor_open_sqlite(db_path)
    if conn is None:
        return set()
    try:
        rows = conn.execute(
            "SELECT key FROM cursorDiskKV WHERE key LIKE 'composerData:%'").fetchall()
        return {k.split(":", 1)[-1] for (k,) in rows}
    except Exception:
        return set()
    finally:
        conn.close()
