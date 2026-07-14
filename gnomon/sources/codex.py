import ast
import json
import os
import re

from gnomon.sources._util import _texts
from gnomon.config import parse_ts
from gnomon.taxonomy import WRITE_TOOLS, _canon_tool, _canon_input, is_substantive_tool


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


class _UnsupportedJsPayload(ValueError):
    """The compositor payload is not in the conservative literal subset we parse."""


def _js_skip_ws(text, index):
    while index < len(text) and text[index].isspace():
        index += 1
    return index


_JS_MAX_DEPTH = 64


def _js_literal(text, index, variables=None, _depth=0):
    """Parse the small, data-only JS subset used by Codex compositor calls.

    This intentionally rejects expressions, template interpolation, functions, and
    unknown identifiers. Returning no tool is safer than inventing telemetry from an
    executable language we do not evaluate.
    """
    if _depth > _JS_MAX_DEPTH:
        raise _UnsupportedJsPayload()
    variables = variables or {}
    index = _js_skip_ws(text, index)
    if index >= len(text):
        raise _UnsupportedJsPayload()
    ch = text[index]
    if ch in "\"'":
        quote = ch
        end = index + 1
        escaped = False
        while end < len(text):
            current = text[end]
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == quote:
                token = text[index:end + 1]
                try:
                    return ast.literal_eval(token), end + 1
                except Exception as exc:
                    raise _UnsupportedJsPayload() from exc
            end += 1
        raise _UnsupportedJsPayload()
    if ch == "`":
        raise _UnsupportedJsPayload()
    if ch == "{":
        out = {}
        index = _js_skip_ws(text, index + 1)
        while index < len(text) and text[index] != "}":
            if text[index] in "\"'":
                key, index = _js_literal(text, index, variables, _depth + 1)
            else:
                match = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", text[index:])
                if not match:
                    raise _UnsupportedJsPayload()
                key = match.group(0)
                index += len(key)
            index = _js_skip_ws(text, index)
            if index >= len(text) or text[index] != ":":
                raise _UnsupportedJsPayload()
            value, index = _js_literal(text, index + 1, variables, _depth + 1)
            out[str(key)] = value
            index = _js_skip_ws(text, index)
            if index < len(text) and text[index] == ",":
                index = _js_skip_ws(text, index + 1)
                continue
            if index >= len(text) or text[index] != "}":
                raise _UnsupportedJsPayload()
        if index >= len(text):
            raise _UnsupportedJsPayload()
        return out, index + 1
    if ch == "[":
        out = []
        index = _js_skip_ws(text, index + 1)
        while index < len(text) and text[index] != "]":
            value, index = _js_literal(text, index, variables, _depth + 1)
            out.append(value)
            index = _js_skip_ws(text, index)
            if index < len(text) and text[index] == ",":
                index = _js_skip_ws(text, index + 1)
                continue
            if index >= len(text) or text[index] != "]":
                raise _UnsupportedJsPayload()
        if index >= len(text):
            raise _UnsupportedJsPayload()
        return out, index + 1
    number = re.match(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", text[index:])
    if number:
        token = number.group(0)
        return (float(token) if any(c in token for c in ".eE") else int(token)), index + len(token)
    ident = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", text[index:])
    if ident:
        name = ident.group(0)
        if name in variables:
            return variables[name], index + len(name)
        if name in {"true", "false", "null"}:
            return {"true": True, "false": False, "null": None}[name], index + len(name)
    raise _UnsupportedJsPayload()


def _js_code_mask(text):
    """Blank strings/comments while preserving offsets for code-only regex scans."""
    masked = list(text)
    index = 0
    while index < len(text):
        if text[index] in "\"'`":
            quote = text[index]
            masked[index] = " "
            index += 1
            escaped = False
            while index < len(text):
                current = text[index]
                masked[index] = " "
                index += 1
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    break
            continue
        if text.startswith("//", index):
            while index < len(text) and text[index] not in "\r\n":
                masked[index] = " "
                index += 1
            continue
        if text.startswith("/*", index):
            masked[index:index + 2] = [" ", " "]
            index += 2
            while index < len(text) and not text.startswith("*/", index):
                masked[index] = " "
                index += 1
            if index < len(text):
                masked[index:index + 2] = [" ", " "]
                index += 2
            continue
        index += 1
    return "".join(masked)


def _codex_exec_tools(script):
    """Recover literal nested tool payloads from a modern Codex exec compositor."""
    code = _js_code_mask(script)
    variables = {}
    for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=", code):
        try:
            value, _ = _js_literal(script, match.end(), variables)
        except _UnsupportedJsPayload:
            continue
        variables[match.group(1)] = value

    recovered = []
    for match in re.finditer(r"\btools\.([A-Za-z0-9_]+)\s*\(", code):
        nested_name = match.group(1)
        try:
            value, end = _js_literal(script, match.end(), variables)
            end = _js_skip_ws(script, end)
            if end >= len(script) or script[end] != ")":
                continue
        except _UnsupportedJsPayload:
            continue
        if nested_name == "apply_patch" and isinstance(value, str):
            recovered.extend(("Edit", {"new_string": new_s, "old_string": old_s,
                                        "file_path": path})
                             for new_s, old_s, path in _patch_files(value))
            continue
        if not isinstance(value, dict):
            continue
        if nested_name.startswith("mcp__"):
            recovered.append((nested_name, value))
            continue
        recovered.append(_codex_tool({"type": "function_call", "name": nested_name,
                                      "arguments": json.dumps(value)}))
    return recovered


def _codex_tool(p):
    """Map a Codex tool/function call to a Claude-shaped (name, input) tool_use."""
    pt = p.get("type")
    if pt == "web_search_call":
        return "WebSearch", {}
    name = p.get("name") or pt or "tool"
    # custom_tool_call carries data in payload.input rather than arguments.  Modern
    # Codex wraps shell/MCP calls in the `exec` compositor, so recover the nested
    # canonical tool instead of treating every compositor call as unknown.
    if pt == "custom_tool_call" and name == "apply_patch":
        raw_patch = p.get("input") or ""
        new_s, old_s, fpath = _patch_churn(raw_patch)
        return "Edit", {"new_string": new_s, "old_string": old_s, "file_path": fpath}
    if pt == "custom_tool_call" and name == "exec":
        script = str(p.get("input") or "")
        nested = _codex_exec_tools(script)
        if nested:
            return nested[0]
        return "exec", {}
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
    if str(name).lower().replace("-", "_").rsplit(".", 1)[-1] in {
            "spawn_agent", "delegate", "dispatch_agent", "followup_task", "send_input"}:
        return "Agent", args
    if pt == "local_shell_call" or name in ("exec_command", "shell", "local_shell", "bash"):
        command = args.get("cmd") or args.get("command") or p.get("action") or ""
        if isinstance(command, list):
            command = " && ".join(str(part) for part in command)
        elif not isinstance(command, str):
            command = str(command)
        return "Bash", {"command": command}
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
        with open(fp, "r", errors="replace") as handle:
            for line in handle:
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
    call_outputs = {}
    for ev in rows:
        payload = ev.get("payload") or {}
        if (ev.get("type") == "response_item"
                and payload.get("type") == "function_call_output"
                and payload.get("call_id")):
            output = payload.get("output")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except Exception:
                    output = None
            if isinstance(output, dict):
                call_outputs[payload["call_id"]] = output

    sid = os.path.basename(fp).split(".")[0]
    cwd = None
    parent_tid = None            # parent_thread_id when this session was spawned as a subagent
    agent_path = None            # stable collaboration identity for reused child threads
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
                    agent_path = spawn.get("agent_path") or agent_path
        elif ev.get("type") == "response_item" and p.get("type") == "function_call":
            try:
                a = json.loads(p.get("arguments") or "{}")
                cwd = cwd or (a.get("workdir") if isinstance(a, dict) else None)
            except Exception:
                pass
    base = {"sessionId": sid, "cwd": cwd}

    if parent_tid:
        # A reused Codex thread can contain multiple turns. Attribute tools and
        # lifecycle to the exact turn_context.turn_id instead of letting any old
        # task_complete/turn_aborted contaminate the whole child file.
        turns = {}
        current_turn = None
        missing_turn_identity = False
        for ev in rows:
            payload = ev.get("payload") or {}
            if ev.get("type") == "turn_context":
                current_turn = payload.get("turn_id")
                if current_turn:
                    turn = turns.setdefault(current_turn, {
                        "model": None, "timestamp": ev.get("timestamp"),
                        "substantive_calls": 0, "writes": 0,
                        "lifecycle": None, "ambiguous_lifecycle": False,
                    })
                    turn["model"] = payload.get("model") or turn["model"]
                else:
                    missing_turn_identity = True
                continue
            if ev.get("type") == "event_msg" and payload.get("type") in {
                    "task_complete", "turn_aborted"}:
                turn_id = payload.get("turn_id")
                if not turn_id:
                    missing_turn_identity = True
                    continue
                turn = turns.setdefault(turn_id, {
                    "model": None, "timestamp": ev.get("timestamp"),
                    "substantive_calls": 0, "writes": 0,
                    "lifecycle": None, "ambiguous_lifecycle": False,
                })
                lifecycle = "completed" if payload.get("type") == "task_complete" else "aborted"
                if turn["lifecycle"] not in (None, lifecycle):
                    turn["ambiguous_lifecycle"] = True
                turn["lifecycle"] = lifecycle
                continue
            if ev.get("type") != "response_item" or not current_turn:
                continue
            pt = payload.get("type")
            if pt not in {"function_call", "local_shell_call", "custom_tool_call",
                          "web_search_call"}:
                continue
            if pt == "custom_tool_call" and payload.get("name") == "exec":
                tools = _codex_exec_tools(str(payload.get("input") or ""))
                if not tools:
                    tools = [_codex_tool(payload)]
            else:
                tools = [_codex_tool(payload)]
            turn = turns[current_turn]
            for name, _ in tools:
                if is_substantive_tool(name):
                    turn["substantive_calls"] += 1
                if name in WRITE_TOOLS:
                    turn["writes"] += 1

        for turn_id, turn in turns.items():
            lifecycle_known = bool(turn["lifecycle"] and not turn["ambiguous_lifecycle"])
            yield {**base, "type": "routing_link",
                   "timestamp": turn.get("timestamp") or child_ts,
                   "routing": {"provider": "openai", "parent_session": parent_tid,
                               "child_session": sid, "turn_id": turn_id,
                               "delegation_identity": agent_path or sid,
                               "child_model": turn.get("model"),
                               "completed": turn["lifecycle"] == "completed"
                                            and lifecycle_known,
                               "aborted": turn["lifecycle"] == "aborted"
                                          and lifecycle_known,
                               "lifecycle_known": lifecycle_known,
                               "substantive_calls": turn["substantive_calls"],
                               "writes": turn["writes"]}}
        if missing_turn_identity or not turns:
            yield {**base, "type": "routing_link", "timestamp": child_ts,
                   "routing": {"provider": "openai", "parent_session": parent_tid,
                               "child_session": sid, "turn_id": None,
                               "delegation_identity": agent_path or sid,
                               "child_model": None, "completed": False,
                               "aborted": False, "lifecycle_known": False,
                               "substantive_calls": 0, "writes": 0}}

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
                nested_tools = (_codex_exec_tools(str(p.get("input") or ""))
                                if pt == "custom_tool_call" and p.get("name") == "exec"
                                else [_codex_tool(p)])
                for name, inp in nested_tools or [("exec", {})]:
                    if name == "Agent":
                        inp = dict(inp)
                        result = call_outputs.get(p.get("call_id")) or {}
                        identity = (result.get("agent_id") or result.get("task_name")
                                    or inp.get("target") or inp.get("task_name"))
                        if identity:
                            inp["_routing_identity"] = identity
                        if result.get("submission_id"):
                            inp["_routing_turn_id"] = result["submission_id"]
                    yield {**base, "type": "assistant", "timestamp": ts,
                           "message": {"role": "assistant", "model": model,
                                       "content": [{"type": "tool_use", "name": name,
                                                    "input": inp}]}}
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
