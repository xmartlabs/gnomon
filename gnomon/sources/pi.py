import json
import os

from gnomon.sources._util import _texts, _iso_ms
from gnomon.taxonomy import _canon_tool, _canon_input


def _pi_blocks(content):
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
            blocks.append({"type": "thinking", "thinking": part.get("thinking") or part.get("text") or ""})
        elif pt in ("toolCall", "tool_use"):
            name = _canon_tool(part.get("name"))
            inp = part.get("arguments") or part.get("input") or {}
            blocks.append({"type": "tool_use", "name": name, "input": _canon_input(name, inp)})
        elif pt == "tool_result":
            blocks.append({"type": "tool_result", "is_error": bool(part.get("is_error") or part.get("isError"))})
    return blocks


def _pi_events(fp):
    sid, cwd = os.path.basename(fp).split(".")[0], None
    try:
        rows = [json.loads(line) for line in open(fp, "r", errors="replace") if line.strip()]
    except Exception:
        return
    for obj in rows:
        if isinstance(obj, dict) and obj.get("type") == "session":
            sid = obj.get("id") or sid
            cwd = obj.get("cwd") or cwd
            break
    base = {"sessionId": sid, "cwd": cwd}
    for obj in rows:
        if not isinstance(obj, dict) or obj.get("type") != "message":
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        role = msg.get("role")
        ts = obj.get("timestamp") or _iso_ms(msg.get("timestamp"))
        if role == "user":
            text = _texts(msg.get("content"))
            if text:
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": text}}
        elif role == "assistant":
            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": msg.get("model"),
                               "content": _pi_blocks(msg.get("content"))}}
        elif role == "toolResult":
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user",
                               "content": [{"type": "tool_result", "is_error": bool(msg.get("isError"))}]}}
