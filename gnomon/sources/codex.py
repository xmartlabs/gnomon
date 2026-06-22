import json
import os

from gnomon.sources._util import _texts
from gnomon.config import parse_ts
from gnomon.taxonomy import _canon_tool, _canon_input


def _patch_files(text):
    """Parse a *** Begin/End Patch block into PER-FILE churn.

    Returns a list of (new_string, old_string, file_path) -- one entry per
    *** Update/Add/Delete File directive -- so a single apply_patch touching
    several files is attributed to each file separately (not flattened onto the
    first).  Counts '+' lines as additions and '-' lines as deletions, skipping
    header markers (+++, ---, *** , @@) and context lines.  Delete File carries
    no content (churn captured via git_churn instead).
    """
    files = []
    cur = None  # {"path": str, "add": [..], "del": [..]}
    in_patch = False
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        if line == "*** Begin Patch":
            in_patch = True
            continue
        if line == "*** End Patch":
            break
        if not in_patch:
            continue
        # file directive -> start a new file section
        if line.startswith("*** "):
            # rename: re-attribute the current file section to its destination path so
            # churn / iteration depth land on the new path, not the stale original.
            if line.startswith("*** Move to: ") and cur is not None:
                cur["path"] = line[len("*** Move to: "):]
                continue
            for directive in ("Update File: ", "Add File: ", "Delete File: "):
                if line.startswith("*** " + directive):
                    if cur is not None:
                        files.append(cur)
                    cur = {"path": line[len("*** " + directive):], "add": [], "del": []}
                    break
            continue
        if cur is None:
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue  # unified-diff file headers, not content
        if line.startswith("+"):
            cur["add"].append(line[1:])
        elif line.startswith("-"):
            cur["del"].append(line[1:])
        # context lines (no prefix) are ignored for churn
    if cur is not None:
        files.append(cur)
    out = []
    for f in files:
        new_s = "\n".join(f["add"]) + ("\n" if f["add"] else "")
        old_s = "\n".join(f["del"]) + ("\n" if f["del"] else "")
        out.append((new_s, old_s, f["path"]))
    return out


def _patch_churn(text):
    """Single-file convenience wrapper over _patch_files: returns the FIRST file's
    (new_string, old_string, file_path), or empties when the patch has no files.
    Multi-file patches should use _patch_files directly (see _codex_events)."""
    files = _patch_files(text)
    return files[0] if files else ("", "", "")


def _codex_mcp_name(namespace, tool):
    """Build a canonical `mcp__<server>__<tool>` name from a Codex namespaced MCP
    call (short `name` + `namespace` like "mcp__supabase_bot__" or
    "mcp__codex_apps__gmail").

    The server segment is taken verbatim from the namespace. NOTE: the namespace
    form may spell a server with underscores where the already-prefixed `name`
    form uses hyphens (e.g. "supabase_bot" vs "supabase-bot"); that difference is
    not reconciled here (underscore<->hyphen is not safely reversible -- many servers
    use underscores legitimately). mcp_calls counting is exact regardless; only
    mcp_servers_distinct may occasionally split one server across the two
    spellings."""
    body = namespace[len("mcp__"):].rstrip("_")
    server_path = "__".join(s for s in body.split("__") if s)
    tool = (str(tool or "")).lstrip("_") or "tool"
    return f"mcp__{server_path}__{tool}" if server_path else f"mcp__{tool}"


def _codex_tool(p):
    """Map a Codex tool/function call to a Claude-shaped (name, input) tool_use."""
    pt = p.get("type")
    if pt == "web_search_call":
        return "WebSearch", {}
    name = p.get("name") or pt or "tool"
    # custom_tool_call (real apply_patch) carries the patch in payload.input, not arguments
    if pt == "custom_tool_call" and name == "apply_patch":
        raw_patch = p.get("input") or ""
        new_s, old_s, fpath = _patch_churn(raw_patch)
        return "Edit", {"new_string": new_s, "old_string": old_s, "file_path": fpath}
    try:
        args = json.loads(p.get("arguments") or "{}")
    except Exception:
        args = {}
    if not isinstance(args, dict):
        args = {}
    # MCP calls: either the name is already prefixed (mcp__server__tool -- kept as-is)
    # or it's a short name under an mcp__ namespace (reclassified here so it counts as
    # MCP, not native). Checked before the builtin-name branches so an MCP tool named
    # like a builtin (e.g. "create_file") isn't mis-mapped to Edit.
    if isinstance(name, str) and name.startswith("mcp__"):
        return name, args
    ns = p.get("namespace")
    if isinstance(ns, str) and ns.startswith("mcp__"):
        return _codex_mcp_name(ns, name), args
    if pt == "local_shell_call" or name in ("exec_command", "shell", "local_shell", "bash"):
        return "Bash", {"command": args.get("cmd") or args.get("command") or str(p.get("action") or "")}
    if name in ("apply_patch", "patch", "edit_file", "write_file", "create_file"):
        return "Edit", {"new_string": args.get("patch") or args.get("content") or "",
                        "old_string": "", "file_path": args.get("path") or args.get("file") or ""}
    if name == "update_plan":          # Codex's plan tool ~ Claude's TodoWrite
        return "TodoWrite", args
    if name == "write_stdin":          # input to a running shell ~ BashOutput interaction
        return "BashOutput", {}
    return name, args


def _codex_is_injected(text):
    """True for Codex tooling wrappers (environment context, project instructions, turn
    notices, and the boot 'whats 2+2?' probe) that are sent as `user` messages but are
    NOT human prompts. Real task wrappers like <task> are NOT injected."""
    if not text:
        return False
    s = text.lstrip()
    if s.startswith(("<environment_context", "<user_instructions", "<turn_aborted")):
        return True
    if s.startswith("# AGENTS.md instructions for"):
        return True
    if s.rstrip().lower() in ("whats 2+2?", "what's 2+2?", "whats 2 + 2?"):
        return True
    return False


def _codex_events(fp):
    rows = []
    try:
        for line in open(fp, "r", errors="replace"):
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except Exception:
        return
    sid = os.path.basename(fp).split(".")[0]
    cwd = None
    parent_tid = None            # parent_thread_id when this session was spawned as a subagent
    child_ts = None              # representative timestamp of THIS (child) session
    for ev in rows:                       # first pass: session id + working dir + subagent parent
        p = ev.get("payload") or {}
        # Remember a usable child timestamp so the synthetic fan-out Agent event can be
        # stamped (undated events are dropped by every windowed run). Prefer the earliest.
        _ets = ev.get("timestamp")
        if _ets and child_ts is None:
            child_ts = _ets
        if ev.get("type") == "session_meta":
            sid = p.get("id") or sid
            cwd = p.get("cwd") or cwd
            # thread_spawn means this session was launched as a delegate.
            src = p.get("source")
            if isinstance(src, dict):
                sub = src.get("subagent") or {}
                spawn = sub.get("thread_spawn") if isinstance(sub, dict) else None
                if isinstance(spawn, dict) and spawn:
                    parent_tid = spawn.get("parent_thread_id") or parent_tid
        elif ev.get("type") == "response_item" and p.get("type") == "function_call":
            try:
                a = json.loads(p.get("arguments") or "{}")
                cwd = cwd or (a.get("workdir") if isinstance(a, dict) else None)
            except Exception:
                pass
    base = {"sessionId": sid, "cwd": cwd}

    # Fan-out belongs to orchestrating session, not worker. Spawn metadata only exists
    # on child session, so emit a synthetic Agent event keyed to parent session id.
    # If parent is outside analyzed window this can create a small fan-out-only
    # placeholder session, which is still better than undercounting delegation.
    if parent_tid:
        yield {"sessionId": parent_tid, "cwd": None, "type": "assistant", "timestamp": child_ts,
               "message": {"role": "assistant", "model": None,
                           "content": [{"type": "tool_use", "name": "Agent",
                                        "input": {"subagent_type": "codex-subagent"}}]}}

    model = None
    # token_count carries cumulative total_token_usage. In mixed-model sessions we
    # snapshot totals on each model switch and credit the delta to the prior active
    # model. We also bucket each delta by the calendar month of the token event that
    # produced it, so a thread spanning a month boundary books its tokens in the
    # right months instead of dumping them all in the session's last month.
    _TOK_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
    model_tok = {}                   # (model, monthKey) -> {field: tokens}
    bucket_ts = {}                   # (model, monthKey) -> last token ts seen in that bucket
    base_total = {f: 0 for f in _TOK_FIELDS}   # cumulative at the last flush
    cur_total = None                 # latest cumulative snapshot
    cur_month = None                 # monthKey of the latest cumulative snapshot
    last_token_ts = None             # raw ts of the latest cumulative snapshot

    def _month_of(ts):
        dt = parse_ts(ts)
        return dt.strftime("%Y-%m") if dt is not None else None

    def _flush_model(mdl):
        # Credit the delta accumulated since the last flush to (model, month) of the
        # most recent snapshot, then advance the baseline.
        if mdl is None or cur_total is None:
            return
        key = (mdl, cur_month)
        acc = model_tok.setdefault(key, {f: 0 for f in _TOK_FIELDS})
        for f in _TOK_FIELDS:
            acc[f] += max(cur_total[f] - base_total[f], 0)
        if last_token_ts is not None:
            bucket_ts[key] = last_token_ts
        for f in _TOK_FIELDS:
            base_total[f] = cur_total[f]

    for ev in rows:
        # the active model lives in turn_context (e.g. "gpt-5.4"), not on the
        # response items -- track it as we stream so assistant turns carry it and
        # Codex usage shows up in the Model mix instead of reading as model-less
        if ev.get("type") == "turn_context":
            new_model = (ev.get("payload") or {}).get("model") or model
            if new_model != model:
                _flush_model(model)   # close out the previous model's delta
                model = new_model
            continue
        # token_count arrives as event_msg, not response_item.
        if ev.get("type") == "event_msg":
            p_em = ev.get("payload") or {}
            if p_em.get("type") == "token_count":
                info = p_em.get("info") or {}
                ttu = info.get("total_token_usage")
                if isinstance(ttu, dict) and ttu.get("total_tokens"):
                    new_month = _month_of(ev.get("timestamp"))
                    # When the running total crosses into a new calendar month, flush the
                    # delta accrued so far to the prior month before adopting the new one.
                    if cur_total is not None and new_month != cur_month:
                        _flush_model(model)
                    cur_total = {f: int(ttu.get(f) or 0) for f in _TOK_FIELDS}
                    cur_month = new_month
                    last_token_ts = ev.get("timestamp")
            continue
        if ev.get("type") != "response_item":
            continue
        ts = ev.get("timestamp")
        p = ev.get("payload") or {}
        pt = p.get("type")
        if pt == "message":
            role = p.get("role")
            text = _texts(p.get("content"))
            if role == "user" and text and not _codex_is_injected(text):
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
            elif role == "assistant":
                yield {**base, "type": "assistant", "timestamp": ts,
                       "message": {"role": "assistant", "model": model,
                                   "content": [{"type": "text", "text": text}] if text else []}}
            # developer/system messages are tooling, not human prompts -> skipped
        elif pt == "reasoning":
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": model,
                               "content": [{"type": "thinking",
                                            "thinking": _texts(p.get("content")) or p.get("summary") or ""}]}}
        elif pt in ("function_call", "local_shell_call", "custom_tool_call", "web_search_call"):
            # One apply_patch can touch several files. Emit one Edit per file so
            # churn and iteration depth are attributed correctly.
            if pt == "custom_tool_call" and p.get("name") == "apply_patch":
                for new_s, old_s, fpath in _patch_files(p.get("input") or ""):
                    yield {**base, "type": "assistant", "timestamp": ts,
                           "message": {"role": "assistant", "model": model,
                                       "content": [{"type": "tool_use", "name": "Edit",
                                                    "input": {"new_string": new_s, "old_string": old_s,
                                                              "file_path": fpath}}]}}
            else:
                name, inp = _codex_tool(p)
                yield {**base, "type": "assistant", "timestamp": ts,
                       "message": {"role": "assistant", "model": model,
                                   "content": [{"type": "tool_use", "name": name, "input": inp}]}}
        elif pt == "function_call_output":
            out = p.get("output")
            is_err = isinstance(out, dict) and out.get("success") is False
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": bool(is_err)}]}}

    # Close out final model delta, then emit one synthetic usage event per
    # (model, month) so mixed-model sessions split correctly in model mix AND
    # month-spanning threads attribute tokens to the right calendar month. Each
    # event is stamped with a timestamp inside its month (the last token ts seen
    # there) so the main loop buckets it correctly. Map Codex fields to Claude shape:
    #   input  = input_tokens - cached_input_tokens  (non-cached portion)
    #   cache_read = cached_input_tokens
    #   output = output_tokens + reasoning_output_tokens
    _flush_model(model)
    for (mdl, _mkey), acc in model_tok.items():
        if not mdl or not any(acc.values()):
            continue
        cached = acc["cached_input_tokens"]
        usage = {
            "input_tokens": max(acc["input_tokens"] - cached, 0),
            "output_tokens": acc["output_tokens"] + acc["reasoning_output_tokens"],
            "cache_read_input_tokens": cached,
            "cache_creation_input_tokens": 0,
        }
        ts = bucket_ts.get((mdl, _mkey), last_token_ts)
        yield {**base, "type": "assistant", "timestamp": ts,
               "__codex_usage__": True,
               "message": {"role": "assistant", "model": mdl, "usage": usage, "content": []}}
