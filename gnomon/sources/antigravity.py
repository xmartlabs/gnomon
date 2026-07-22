"""Google Antigravity source parser.

Antigravity stores each CLI agent conversation ("trajectory"/"cascade") as a SQLite file
under ``~/.gemini/antigravity-cli/conversations/<uuid>.db``. The ``steps`` table holds one
row per step with a protobuf-encoded ``step_payload`` BLOB and no ``.proto`` shipped on
disk, so we decode the wire format directly (stdlib only -- see ``_pb_fields``) and map the
field numbers observed in real transcripts onto the Claude-shaped event dict the rest of
gnomon consumes.

Step field map, reverse-engineered from real CLI transcripts (validated across both local
conversation DBs):

  envelope:      {1: step_type, 4: status, 5: meta{1: created{1:sec,2:nano}, 9: usage}}
  step_type 14:  user prompt           text at 19.2
  step_type 15:  assistant turn        text at 20.1; tool call at 20.7 {2:name, 3:args_json};
                                        token usage at 5.9 {2:input, 3:output, 5:cache_read}
  step_type 17:  tool/model error      -> errored tool_result
  step_type 5/7/8/9/21/23/33: tool result/observation -> success tool_result
  step_type 98/101/132: meta/heartbeat -> skipped

Per-step model id lives in the ``gen_metadata`` table (idx aligned with ``steps.idx``).

The IDE stores trajectories as encrypted ``*.pb`` files (custom scheme, key in Keychain),
so full IDE step data is not decodable here; ``antigravity_summary`` reads the unencrypted
trajectory index from the IDE ``state.vscdb`` for a volume/time-only summary.
"""

import os
import re
import json
import sqlite3
from datetime import datetime

from gnomon.sources.discovery import ANTIGRAVITY_DB
from gnomon.taxonomy import _canon_tool, _canon_input, _norm_path_seps, _SKILL_MD_RX


# --- stdlib protobuf wire-format decoder (no .proto, no dependency) -----------------

def _pb_varint(buf, i):
    val = shift = 0
    while i < len(buf):
        b = buf[i]; i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7
    raise ValueError("truncated varint")


def _pb_fields(buf):
    """Decode one protobuf message into [(field_no, wire_type, value)]. Raises on
    malformed input -- callers treat any raise as 'not a message'."""
    i, out = 0, []
    while i < len(buf):
        key, i = _pb_varint(buf, i)
        f, w = key >> 3, key & 7
        if f == 0:
            raise ValueError("field 0")
        if w == 0:
            v, i = _pb_varint(buf, i)
        elif w == 1:
            v, i = buf[i:i + 8], i + 8
        elif w == 2:
            ln, i = _pb_varint(buf, i)
            if i + ln > len(buf):
                raise ValueError("truncated bytes")
            v, i = buf[i:i + ln], i + ln
        elif w == 5:
            v, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"wire type {w}")
        out.append((f, w, v))
    return out


def _msg(buf):
    """Wire fields as {field_no: [values]} -- last-wins is fine for our scalar reads."""
    out = {}
    for f, _w, v in _pb_fields(buf):
        out.setdefault(f, []).append(v)
    return out


def _sub(msg, f):
    """Decode the length-delimited field ``f`` as a nested message ({} on miss/failure)."""
    vals = msg.get(f)
    if not vals or not isinstance(vals[-1], (bytes, bytearray)):
        return {}
    try:
        return _msg(vals[-1])
    except Exception:
        return {}


def _str(msg, f):
    """Field ``f`` as text, or None."""
    vals = msg.get(f)
    if not vals:
        return None
    v = vals[-1]
    return v.decode("utf-8", "replace") if isinstance(v, (bytes, bytearray)) else v


def _int(msg, f):
    vals = msg.get(f)
    return int(vals[-1]) if vals and isinstance(vals[-1], int) else 0


_UUID_RX = re.compile(rb"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MODEL_RX = re.compile(rb"(gemini-[0-9][\w.\-]*|claude-[\w.\-]+|gpt-[\w.\-]+)")


# --- CLI conversation parser --------------------------------------------------------

# Antigravity/Windsurf tool names -> Claude-style canonical taxonomy.
_AG_TOOL = {
    "list_dir": "Glob",
    "view_file": "Read", "read_file": "Read",
    "run_command": "Bash",
    "grep_search": "Grep",
    "write_to_file": "Write",
    "replace_file_content": "Edit", "edit_file": "Edit",
    "multi_replace_file_content": "MultiEdit",
    "search_web": "WebSearch",
    "read_url_content": "WebFetch",
    "invoke_subagent": "Agent",
    "manage_task": "TodoWrite",
}

_STEP_USER = 14
_STEP_ASSISTANT = 15
_STEP_ERROR = 17
_RESULT_TYPES = frozenset({5, 7, 8, 9, 21, 23, 33})   # tool observations / results (success)


def _step_ts(meta):
    """ISO timestamp from a step's meta block (field 5), created time at 5.1{1:sec,2:nano}."""
    created = _sub(meta, 1)
    sec = _int(created, 1)
    if not sec:
        return None
    try:
        return datetime.fromtimestamp(sec + _int(created, 2) / 1e9).astimezone().isoformat()
    except Exception:
        return None


def _step_usage(meta):
    """Token usage from meta.9: 2=non-cached input, 3=output, 5=cache-read."""
    u = _sub(meta, 9)
    inp, out, cache = _int(u, 2), _int(u, 3), _int(u, 5)
    if not (inp or out or cache):
        return None
    return {"input_tokens": inp, "output_tokens": out,
            "cache_read_input_tokens": cache, "cache_creation_input_tokens": 0}


def _ag_mcp_name(name):
    """Antigravity names MCP tools `server::tool`; gnomon counts MCP by the `mcp__server__tool`
    convention. Translate so MCP calls register as mcp_calls + a distinct server. Non-MCP names
    pass through unchanged."""
    if isinstance(name, str) and "::" in name:
        server, _, tool = name.partition("::")
        return f"mcp__{server}__{tool}" if server else name
    return name


def _skill_from_path(path):
    """Skill name if `path` reads a `skills/<name>/SKILL.md` (skill load), else None. Skips
    vendored trees so a `node_modules/.../skills/x/SKILL.md` isn't miscredited as a skill use.

    Paths reaching here come either from a `file://` URI (already forward-slashed) or raw
    from the Windsurf SQLite keys, which on Windows are backslashed -- normalize so both
    the skill match and the vendored-tree guards fire either way."""
    p = _norm_path_seps(path)
    if "/node_modules/" in p or "/vendor/" in p or "/.git/" in p:
        return None
    m = _SKILL_MD_RX.search(p)
    return m.group(1) if m else None


def _ag_args(raw):
    """Tool args arrive as a JSON string with Windsurf CamelCase keys; parse and alias the
    keys gnomon's _canon_input understands (file_path / command / content / query)."""
    try:
        d = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        d = {}
    if not isinstance(d, dict):
        return {}
    out = dict(d)
    for src, dst in (("AbsolutePath", "file_path"), ("TargetFile", "file_path"),
                     ("CommandLine", "command"), ("CodeContent", "content"),
                     ("Query", "query")):
        if src in d and dst not in out:
            out[dst] = d[src]
    return out


def _conversation_cwd(con):
    """Working directory from trajectory_metadata_blob field 1.1 (file:// URI)."""
    try:
        row = con.execute("select data from trajectory_metadata_blob limit 1").fetchone()
        if row and row[0]:
            uri = _str(_sub(_msg(row[0]), 1), 1)
            if isinstance(uri, str) and uri.startswith("file://"):
                return uri[len("file://"):]
    except Exception:
        pass
    return None


def _models_by_idx(con):
    """Map steps.idx -> model id from the gen_metadata blobs (idx aligned with steps)."""
    models = {}
    try:
        for idx, data in con.execute("select idx, data from gen_metadata"):
            if data:
                mm = _MODEL_RX.findall(data)
                if mm:
                    models[idx] = mm[0].decode()
    except Exception:
        pass
    return models


def _antigravity_cli_events(fp):
    """Yield Claude-shaped event dicts from one Antigravity CLI conversation DB."""
    try:
        con = sqlite3.connect(f"file:{fp}?mode=ro&immutable=1", uri=True)
    except Exception:
        return
    try:
        base = {"sessionId": os.path.basename(fp).split(".")[0], "cwd": _conversation_cwd(con)}
        models = _models_by_idx(con)
        try:
            rows = con.execute("select idx, step_type, step_payload from steps "
                               "where step_payload is not null order by idx").fetchall()
        except Exception:
            return
    finally:
        con.close()

    last_model = None
    for idx, st, blob in rows:
        try:
            m = _msg(blob)
        except Exception:
            yield {"__bad__": True}
            continue
        ts = _step_ts(_sub(m, 5))
        if st == _STEP_USER:
            txt = _str(_sub(m, 19), 2)
            if txt:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": txt}}
        elif st == _STEP_ASSISTANT:
            a = _sub(m, 20)
            content = []
            text = _str(a, 1)
            if text:
                content.append({"type": "text", "text": text})
            tool = _sub(a, 7)
            raw_name = _str(tool, 2)
            skill = None
            if raw_name:
                # MCP tools are `server::tool` -> mcp__server__tool (so they count as MCP);
                # otherwise canonicalize the Antigravity/Windsurf builtin name.
                mcp = _ag_mcp_name(raw_name)
                cname = mcp if mcp.startswith("mcp__") else _AG_TOOL.get(raw_name, _canon_tool(raw_name))
                inp = _canon_input(cname, _ag_args(_str(tool, 3)))
                content.append({"type": "tool_use", "name": cname, "input": inp})
                if cname == "Read":              # reading skills/<name>/SKILL.md = a skill load
                    skill = _skill_from_path(inp.get("file_path") or "")
            # gen_metadata only stamps generation steps; carry the last-seen model forward
            # so non-generation assistant turns aren't left model-less in the mix.
            if models.get(idx):
                last_model = models[idx]
            usage = _step_usage(_sub(m, 5))
            # skip empty turns (no text, no tool, no usage) so they don't inflate turn/model counts
            if content or usage:
                msg = {"role": "assistant", "model": last_model, "content": content}
                if usage:
                    msg["usage"] = usage
                ev = {**base, "type": "assistant", "timestamp": ts, "message": msg}
                if skill:
                    ev["attributionSkill"] = skill
                yield ev
        elif st == _STEP_ERROR:
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": True}]}}
        elif st in _RESULT_TYPES:
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": False}]}}
        # meta steps (98/101/132/…) carry no scoring signal -> skipped


# --- IDE export orchestration (query a running Antigravity language server) ----------
#
# The IDE's transcripts are encrypted; the only sanctioned way to read them is the running
# language server, which decrypts and serves them over a local JSON API. gnomon discovers the
# process itself (pgrep + cmdline csrf + lsof ports), then calls GetCascadeTrajectorySteps per
# conversation with stdlib only (no external dependency). Best-effort: every failure returns
# None and the run continues without the IDE. Gated upstream on antigravity_summary() (only runs
# when the IDE was actually used and its dates fall in the window).

_ANTIGRAVITY_APP = "/Applications/Antigravity IDE.app"
_ANTIGRAVITY_APP_FALLBACK = "/Applications/Antigravity.app"


def _antigravity_app_path():
    if os.path.isdir(_ANTIGRAVITY_APP):
        return _ANTIGRAVITY_APP
    if os.path.isdir(_ANTIGRAVITY_APP_FALLBACK):
        return _ANTIGRAVITY_APP_FALLBACK
    return None


def _discover_language_servers():
    """Return [(port, csrf), …] for ALL running Antigravity language servers. Antigravity runs
    one language server per open workspace, each serving only THAT workspace's conversations, so
    we must query every one to see all IDE history."""
    import subprocess
    out = []
    try:
        pids = subprocess.run(["pgrep", "-f", "language_server"],
                              capture_output=True, text=True, timeout=10).stdout.split()
    except Exception:
        return out
    for pid in pids:
        try:
            args = subprocess.run(["ps", "-p", pid, "-o", "args="],
                                  capture_output=True, text=True, timeout=10).stdout
        except Exception:
            continue
        m = re.search(r"--csrf_token\s+(\S+)", args)
        if not m:
            continue
        csrf = m.group(1)
        try:
            lsof = subprocess.run(["lsof", "-p", pid, "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
                                  capture_output=True, text=True, timeout=10).stdout
        except Exception:
            continue
        for port in dict.fromkeys(int(pm.group(1)) for pm in re.finditer(r":(\d+)\s+\(LISTEN\)", lsof)):
            if _ls_api_ok(port, csrf):
                out.append((port, csrf))
                break   # one working API port per process is enough
    return out


def _discover_language_server():
    """First running language server as (port, csrf), or (None, None)."""
    servers = _discover_language_servers()
    return servers[0] if servers else (None, None)


def _ls_api_ok(port, csrf):
    """True if the LanguageServer API answers on this port (GetAllCascadeTrajectories).

    TLS verification is intentionally disabled: this is a loopback (127.0.0.1) call to the
    user's OWN Antigravity language server, which serves a self-signed cert with no CA to
    trust. There is no network hop to MITM (same machine, same user, own process), and the
    official client connects the same way. Scope is strictly localhost."""
    import ssl as _ssl
    import urllib.request
    url = (f"https://localhost:{port}/exa.language_server_pb.LanguageServerService/"
           "GetAllCascadeTrajectories")
    ctx = _ssl._create_unverified_context()  # localhost self-signed LS cert (see docstring)
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={"X-Codeium-Csrf-Token": csrf,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def ide_window_overlaps(summary, since_dt, until_dt):
    """True if the IDE conversation date range [first, last] overlaps the active time window.
    Used to skip launching the IDE when no IDE history can fall in --since/--until. Unknown
    bounds are treated as open (don't skip on missing data). `summary` is antigravity_summary()."""
    from gnomon.config import parse_ts
    if not summary:
        return False
    if not since_dt and not until_dt:
        return True
    first = parse_ts(summary.get("first")) if summary.get("first") else None
    last = parse_ts(summary.get("last")) if summary.get("last") else None
    if until_dt and first and first >= until_dt:
        return False
    if since_dt and last and last < since_dt:
        return False
    return True


def _ls_post(port, csrf, method, body):
    """POST to the LanguageServer JSON API, return the parsed dict (or None). Localhost-only,
    self-signed cert (see _ls_api_ok docstring for why TLS verification is off)."""
    import ssl as _ssl
    import json as _json
    import urllib.request
    url = f"https://localhost:{port}/exa.language_server_pb.LanguageServerService/{method}"
    ctx = _ssl._create_unverified_context()  # localhost self-signed LS cert
    req = urllib.request.Request(url, data=_json.dumps(body).encode(), method="POST",
                                 headers={"X-Codeium-Csrf-Token": csrf,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            return _json.loads(r.read().decode())
    except Exception:
        return None


_UUID_ANY_RX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _ide_cascade_ids():
    """IDE conversation UUIDs from the `.pb` filenames on disk."""
    ids = set()
    for d in (os.path.expanduser("~/.gemini/antigravity-ide/conversations"),
              os.path.expanduser("~/.gemini/antigravity/conversations")):
        if os.path.isdir(d):
            ids |= {n[:-3] for n in os.listdir(d) if n.endswith(".pb")}
    return ids


def _ide_cascade_map(servers):
    """{cascade_id: (port, csrf) | None} — map each conversation to the server that indexes it
    (from each server's GetAllCascadeTrajectories), so it's fetched once from its owner instead
    of probed against every server. `.pb`-only ids whose owner isn't indexed map to None
    (try all servers as a fallback)."""
    import json as _json
    owner = {}
    for port, csrf in servers:
        resp = _ls_post(port, csrf, "GetAllCascadeTrajectories", {})
        if resp:
            for cid in set(_UUID_ANY_RX.findall(_json.dumps(resp))):
                owner.setdefault(cid, (port, csrf))
    for cid in _ide_cascade_ids():
        owner.setdefault(cid, None)
    return owner


def export_antigravity_ide(out_dir, launch=True, wait_secs=20, log=print):
    """Best-effort: pull the IDE's conversation steps from the running language server and
    write them to a combined JSON (`[{cascade_id, steps:[...]}]`), returning its path (or
    None). No external dependency — talks to the local API with stdlib. Steps: verify app
    installed -> ensure language server up (optionally launch + poll) -> discover port/csrf
    -> for each cascade, GetCascadeTrajectorySteps -> write."""
    import os as _os
    import json as _json
    import subprocess
    import time as _time
    app_path = _antigravity_app_path()
    if not app_path:
        log("  Antigravity IDE not installed (skipping IDE)")
        return None

    servers = _discover_language_servers()
    if not servers and launch:
        log("  launching Antigravity to read IDE history...")
        try:
            subprocess.run(["open", app_path], timeout=15)
        except Exception:
            pass
        deadline = _time.time() + wait_secs
        while _time.time() < deadline and not servers:
            _time.sleep(2)
            servers = _discover_language_servers()
    if not servers:
        log("  could not reach the Antigravity language server (open the IDE with a workspace) -- skipping IDE")
        return None

    # Fetch each cascade once from the server that owns it (per-workspace); ids with no known
    # owner fall back to trying every server. One conversation per id (dedupe).
    convs = []
    for cid, srv in _ide_cascade_map(servers).items():
        for port, csrf in ([srv] if srv else servers):
            resp = _ls_post(port, csrf, "GetCascadeTrajectorySteps",
                            {"cascadeId": cid, "startIndex": 0, "endIndex": 100010})
            steps = (resp or {}).get("steps") or []
            if steps:
                convs.append({"cascade_id": cid, "steps": steps})
                break

    _os.makedirs(out_dir, exist_ok=True)
    path = _os.path.join(out_dir, "ide_steps_export.json")
    # Remove a previous run's export FIRST so a failed/empty refresh can't fold stale history.
    try:
        _os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    if not convs:
        log("  Antigravity language server returned no IDE steps -- skipping IDE")
        return None
    try:
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump(convs, fh)
    except OSError as e:
        log(f"  could not write IDE export: {e} -- skipping IDE")
        return None
    return path


# --- IDE step parser (CORTEX JSON from the language server) --------------------------
#
# Step `type` -> handling. The language server returns rich named-JSON steps with real
# per-step timestamps (metadata.createdAt). Model is masked (MODEL_PLACEHOLDER_*) and token
# counts aren't reliably present, so those stay unset (workstream 3 keeps them from
# penalizing). Tool intent appears twice — announced in PLANNER_RESPONSE.toolCalls AND
# executed in the dedicated *_ACTION/RUN_COMMAND/VIEW_*/etc steps — so we emit tool_use from
# the EXECUTION steps only (richer: real args, exit codes) and take thinking/text from
# PLANNER_RESPONSE/NOTIFY_USER, avoiding double counting.

_CORTEX_READ = frozenset({"CORTEX_STEP_TYPE_VIEW_FILE", "CORTEX_STEP_TYPE_VIEW_FILE_OUTLINE",
                          "CORTEX_STEP_TYPE_VIEW_CODE_ITEM"})
# steps that carry no scoring signal (status pings, task markers, injected context, ephemeral)
_CORTEX_SKIP = frozenset({"CORTEX_STEP_TYPE_COMMAND_STATUS", "CORTEX_STEP_TYPE_TASK_BOUNDARY",
                          "CORTEX_STEP_TYPE_CONVERSATION_HISTORY", "CORTEX_STEP_TYPE_EPHEMERAL_MESSAGE"})


def _uri_path(uri):
    if isinstance(uri, str) and uri.startswith("file://"):
        return uri[len("file://"):]
    return uri if isinstance(uri, str) else ""


def _antigravity_ide_export_events(fp):
    """Yield Claude-shaped events from the combined IDE step export written by
    export_antigravity_ide (`[{cascade_id, steps:[CORTEX step JSON]}]`). Real per-step
    timestamps; model/tokens unavailable (masked by the server)."""
    import json as _json
    try:
        with open(fp, "r", errors="replace") as fh:
            convs = _json.load(fh)
    except Exception:
        return
    if not isinstance(convs, list):
        return
    for conv in convs:
        if not isinstance(conv, dict):
            continue
        cid = conv.get("cascade_id")
        steps = conv.get("steps") or []
        base = {"sessionId": cid or "antigravity-ide", "cwd": _ide_steps_cwd(steps)}
        for s in steps:
            yield from _cortex_step_events(s, base)


def _cortex_step_events(s, base):
    if not isinstance(s, dict):
        return
    t = s.get("type")
    if t in _CORTEX_SKIP:
        return
    ts = (s.get("metadata") or {}).get("createdAt")

    def asst(blocks):
        return {**base, "type": "assistant", "timestamp": ts,
                "message": {"role": "assistant", "model": None, "content": blocks}}

    def tool(name, inp):
        return asst([{"type": "tool_use", "name": name, "input": _canon_input(name, inp)}])

    if t == "CORTEX_STEP_TYPE_USER_INPUT":
        items = (s.get("userInput") or {}).get("items") or []
        text = "\n".join(i.get("text", "") for i in items if isinstance(i, dict) and i.get("text"))
        if text.strip():
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user", "content": text}}
    elif t == "CORTEX_STEP_TYPE_PLANNER_RESPONSE":
        # Thinking only. Tool calls (builtins AND MCP) are emitted from their dedicated execution
        # steps (CODE_ACTION / RUN_COMMAND / VIEW_* / MCP_TOOL / …); emitting them here too would
        # double-count.
        thinking = (s.get("plannerResponse") or {}).get("thinking")
        if thinking:
            yield asst([{"type": "thinking", "thinking": thinking}])
    elif t == "CORTEX_STEP_TYPE_NOTIFY_USER":
        msg = (s.get("notifyUser") or {}).get("notificationContent")
        if msg:
            yield asst([{"type": "text", "text": msg}])
    elif t == "CORTEX_STEP_TYPE_CODE_ACTION":
        spec = (s.get("codeAction") or {}).get("actionSpec") or {}
        # createFile -> Write, anything else (edit/replace) -> Edit
        is_create = "createFile" in spec
        inner = spec.get("createFile") or spec.get("editFile") or next(iter(spec.values()), {}) or {}
        path = _uri_path(inner.get("absolutePathUri") or inner.get("absoluteUri") or "")
        content = inner.get("instruction") or inner.get("codeContent") or inner.get("content") or ""
        yield tool("Write" if is_create else "Edit",
                   {"file_path": path, "content": content} if is_create
                   else {"file_path": path, "new_string": content, "old_string": ""})
    elif t == "CORTEX_STEP_TYPE_RUN_COMMAND":
        rc = s.get("runCommand") or {}
        yield tool("Bash", {"command": rc.get("commandLine") or rc.get("proposedCommandLine") or ""})
        code = rc.get("exitCode")
        if isinstance(code, int) and code != 0:
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user", "content": [{"type": "tool_result", "is_error": True}]}}
    elif t in _CORTEX_READ:
        v = s.get("viewFile") or s.get("viewFileOutline") or s.get("viewCodeItem") or {}
        path = _uri_path(v.get("absolutePathUri") or v.get("absoluteUri") or "")
        ev = tool("Read", {"file_path": path})
        skill = _skill_from_path(path)        # reading skills/<name>/SKILL.md = a skill load
        if skill:
            ev["attributionSkill"] = skill
        yield ev
    elif t == "CORTEX_STEP_TYPE_MCP_TOOL":
        mt = s.get("mcpTool") or {}
        tc = mt.get("toolCall") or {}
        server, name = mt.get("serverName") or "", tc.get("name") or ""
        cn = f"mcp__{server}__{name}" if server else _ag_mcp_name(name)
        yield tool(cn, _ag_args(tc.get("argumentsJson")))
        if "ERROR" in str(s.get("status") or ""):
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user", "content": [{"type": "tool_result", "is_error": True}]}}
    elif t == "CORTEX_STEP_TYPE_LIST_DIRECTORY":
        yield tool("Glob", {})
    elif t in ("CORTEX_STEP_TYPE_GREP_SEARCH", "CORTEX_STEP_TYPE_FIND"):
        g = s.get("grepSearch") or s.get("find") or {}
        yield tool("Grep", {"query": g.get("query") or g.get("pattern") or ""})
    elif t == "CORTEX_STEP_TYPE_ERROR_MESSAGE":
        yield {**base, "type": "user", "timestamp": ts,
               "message": {"role": "user", "content": [{"type": "tool_result", "is_error": True}]}}


def _ide_steps_cwd(steps):
    """Best-effort cwd: first real-workspace file path in the steps, skipping ~/.gemini artifacts."""
    for s in steps:
        if not isinstance(s, dict):
            continue
        # include every code_action variant (createFile, editFile, replace…) so edit-only
        # sessions still yield a cwd, not just file views / commands / new files.
        spec = (s.get("codeAction") or {}).get("actionSpec") or {}
        blocks = [s.get("viewFile"), s.get("runCommand"), *spec.values()]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            cand = block.get("cwd") or _uri_path(block.get("absolutePathUri") or block.get("absoluteUri") or "")
            if cand and "/.gemini/" not in _norm_path_seps(cand):
                return cand if block.get("cwd") else os.path.dirname(cand)
    return None


# --- IDE summary (volume/time only; full IDE steps are encrypted) -------------------

_ANTIGRAVITY_SUMMARY_KEYS = (
    "antigravityUnifiedStateSync.trajectorySummaries",
    "jetskiStateSync.agentManagerInitState",
)


def _antigravity_summary_from_buf(buf):
    tmin = tmax = None

    def _scan_ts(b, depth=0):
        nonlocal tmin, tmax
        if depth > 6:
            return
        for _f, w, v in _pb_fields(b):
            if w == 0 and 1.3e9 < v < 2.2e9:        # plausible unix seconds
                ts = datetime.fromtimestamp(v).astimezone()
                tmin = ts if tmin is None or ts < tmin else tmin
                tmax = ts if tmax is None or ts > tmax else tmax
            elif w == 2:
                try:
                    _scan_ts(v, depth + 1)
                except Exception:
                    pass

    convs = 0

    def _has_uuid(fields):
        return any(g == 1 and gw == 2 and _UUID_RX.match(gv)
                   for g, gw, gv in fields)

    for f, w, root in _pb_fields(buf):
        if f != 1 or w != 2:
            continue
        try:
            children = _pb_fields(root)
        except Exception:
            continue
        # Newer Antigravity IDE stores conversation records directly as repeated field 1.
        if _has_uuid(children):
            convs += 1
            _scan_ts(root)
            continue
        # Older storage wrapped conversation records one level deeper.
        for cf, cw, cv in children:
            if cf != 1 or cw != 2:
                continue
            try:
                inner = _pb_fields(cv)
            except Exception:
                continue
            # a conversation record leads with its uuid as field 1
            if _has_uuid(inner):
                convs += 1
                _scan_ts(cv)
    if not convs:
        return None
    return {"conversations": convs,
            "first": tmin.isoformat() if tmin else None,
            "last": tmax.isoformat() if tmax else None}


def antigravity_summary():
    """Best-effort read of Antigravity IDE conversation metadata from the unencrypted
    trajectory index in state.vscdb. Returns {"conversations": n, "first": iso,
    "last": iso} or None. Fully local, read-only. The full per-step IDE transcripts live
    in encrypted *.pb files and are not decoded here."""
    if not os.path.exists(ANTIGRAVITY_DB):
        return None
    try:
        import base64
        con = sqlite3.connect(f"file:{ANTIGRAVITY_DB}?mode=ro&immutable=1", uri=True)
        try:
            for key in _ANTIGRAVITY_SUMMARY_KEYS:
                row = con.execute("SELECT value FROM ItemTable WHERE key=?", (key,)).fetchone()
                if not row or not row[0]:
                    continue
                raw = row[0]
                buf = base64.b64decode(raw if isinstance(raw, (bytes, bytearray)) else str(raw))
                summary = _antigravity_summary_from_buf(buf)
                if summary:
                    return summary
        finally:
            con.close()
        return None
    except Exception:
        return None
