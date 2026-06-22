import json
import os
import glob

from gnomon.sources._util import _iso_ms
from gnomon.sources.discovery import OPENCODE_DIR
from gnomon.taxonomy import _canon_tool, _canon_input


def _opencode_events(fp):
    try:
        sess = json.load(open(fp, "r", errors="replace"))
    except Exception:
        return
    if not isinstance(sess, dict):
        return
    sid = sess.get("id") or os.path.basename(fp).split(".")[0]
    cwd = sess.get("directory")
    msg_dir = os.path.join(OPENCODE_DIR, "storage", "message", sid)
    part_root = os.path.join(OPENCODE_DIR, "storage", "part")
    messages = []
    for mp in sorted(glob.glob(os.path.join(msg_dir, "*.json"))):
        try:
            m = json.load(open(mp, "r", errors="replace"))
        except Exception:
            continue
        if isinstance(m, dict):
            messages.append(m)
    messages.sort(key=lambda m: (m.get("time") or {}).get("created") or 0)
    base = {"sessionId": sid, "cwd": cwd}
    for m in messages:
        mid = m.get("id")
        ts = _iso_ms((m.get("time") or {}).get("created"))
        parts = []
        for pp in sorted(glob.glob(os.path.join(part_root, str(mid), "*.json"))):
            try:
                p = json.load(open(pp, "r", errors="replace"))
            except Exception:
                continue
            if isinstance(p, dict):
                parts.append(p)
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
