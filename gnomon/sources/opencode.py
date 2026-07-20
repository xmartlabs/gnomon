import json
import os
import glob
import sqlite3
from collections import defaultdict

from gnomon.sources._util import _iso_ms
import gnomon.sources.discovery as discovery
from gnomon.taxonomy import _canon_tool, _canon_input


def _json_dict(raw):
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        obj = json.loads(raw)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _opencode_session_events(sid, cwd, messages, parts_by_message):
    base = {"sessionId": sid, "cwd": cwd}
    for m in messages:
        mid = m.get("id")
        ts = _iso_ms((m.get("time") or {}).get("created"))
        parts = list(parts_by_message.get(str(mid), []))
        parts.sort(key=lambda p: ((p.get("time") or {}).get("start") or 0, p.get("id") or ""))
        if m.get("role") == "user":
            texts = [p.get("text") for p in parts if p.get("type") == "text" and p.get("text")]
            if not texts:
                summ = m.get("summary") if isinstance(m.get("summary"), dict) else {}
                texts = [x for x in (summ.get("title"), summ.get("body")) if x]
            if texts:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": "\n".join(texts)}}
        elif m.get("role") == "assistant":
            blocks, tool_results = [], []
            for p in parts:
                pt = p.get("type")
                if pt == "text" and p.get("text"):
                    blocks.append({"type": "text", "text": p.get("text", "")})
                elif pt == "reasoning":
                    blocks.append({"type": "thinking", "thinking": p.get("text", "")})
                elif pt == "tool":
                    st = p.get("state") if isinstance(p.get("state"), dict) else {}
                    name = _canon_tool(p.get("tool"))
                    inp = _canon_input(name, st.get("input") if isinstance(st.get("input"), dict) else {})
                    blocks.append({"type": "tool_use", "name": name, "input": inp})
                    is_err = st.get("status") not in (None, "completed") or bool(st.get("error"))
                    tool_results.append({"type": "tool_result", "is_error": is_err})
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": m.get("modelID"), "content": blocks}}
            if tool_results:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": tool_results}}


def _opencode_events(fp):
    try:
        sess = json.load(open(fp, "r", errors="replace"))
    except Exception:
        return
    if not isinstance(sess, dict):
        return
    sid = sess.get("id") or os.path.basename(fp).split(".")[0]
    cwd = sess.get("directory")
    msg_dir = os.path.join(discovery.OPENCODE_DIR, "storage", "message", sid)
    part_root = os.path.join(discovery.OPENCODE_DIR, "storage", "part")
    messages = []
    for mp in sorted(glob.glob(os.path.join(msg_dir, "*.json"))):
        try:
            m = json.load(open(mp, "r", errors="replace"))
        except Exception:
            continue
        if isinstance(m, dict):
            messages.append(m)
    messages.sort(key=lambda m: (m.get("time") or {}).get("created") or 0)
    parts_by_message = defaultdict(list)
    for mid in [m.get("id") for m in messages if m.get("id")]:
        for pp in sorted(glob.glob(os.path.join(part_root, str(mid), "*.json"))):
            try:
                p = json.load(open(pp, "r", errors="replace"))
            except Exception:
                continue
            if isinstance(p, dict):
                parts_by_message[str(mid)].append(p)
    yield from _opencode_session_events(sid, cwd, messages, parts_by_message)


def _opencode_sqlite_events(db_path):
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except Exception:
        return
    try:
        sessions = conn.execute(
            "SELECT id, directory, time_created FROM session ORDER BY time_created, id"
        ).fetchall()
        for sess in sessions:
            sid = sess["id"]
            messages, parts_by_message = [], defaultdict(list)
            for row in conn.execute(
                "SELECT id, data FROM message WHERE session_id = ? ORDER BY time_created, id",
                (sid,),
            ):
                msg = _json_dict(row["data"])
                if msg:
                    msg.setdefault("id", row["id"])
                    messages.append(msg)
            for row in conn.execute(
                "SELECT message_id, id, data FROM part WHERE session_id = ? "
                "ORDER BY time_created, id",
                (sid,),
            ):
                part = _json_dict(row["data"])
                if part:
                    part.setdefault("id", row["id"])
                    parts_by_message[str(row["message_id"])].append(part)
            yield from _opencode_session_events(
                sid, sess["directory"], messages, parts_by_message)
    except sqlite3.Error:
        return
    finally:
        conn.close()
