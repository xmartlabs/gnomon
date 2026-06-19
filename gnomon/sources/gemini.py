import json
import os

from gnomon.sources._util import _texts
from gnomon.taxonomy import _canon_tool, _canon_input


def _gemini_events(fp):
    try:
        d = json.load(open(fp, "r", errors="replace"))
    except Exception:
        return
    if not isinstance(d, dict):
        return
    sid = d.get("sessionId") or os.path.basename(fp)

    # Scan once for cwd: prefer dir_path args, then file_path dirname, then
    # a "Directory: /abs" line in run_shell_command output.
    cwd = None
    try:
        for m in d.get("messages") or []:
            if not isinstance(m, dict):
                continue
            for tc in m.get("toolCalls") or []:
                if not isinstance(tc, dict):
                    continue
                args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                dp = args.get("dir_path") or ""
                if isinstance(dp, str) and dp.startswith("/"):
                    cwd = dp
                    break
                fp_arg = args.get("file_path") or ""
                if isinstance(fp_arg, str) and fp_arg.startswith("/"):
                    cwd = os.path.dirname(fp_arg)
                    break
                # try to parse "Directory: /abs" from run_shell_command output
                try:
                    resp = (tc.get("result") or [{}])[0]
                    out = (resp.get("functionResponse") or {}).get("response", {}).get("output", "") or ""
                    for line in str(out).splitlines():
                        if line.startswith("Directory:"):
                            candidate = line.split(":", 1)[1].strip()
                            if candidate.startswith("/") and candidate != "(root)":
                                cwd = candidate
                                break
                except Exception:
                    pass
                if cwd:
                    break
            if cwd:
                break
    except Exception:
        cwd = None

    base = {"sessionId": sid, "cwd": cwd}

    for m in d.get("messages") or []:
        if not isinstance(m, dict):
            continue
        ts = m.get("timestamp")
        role = m.get("type") or m.get("role")
        content = m.get("content")
        text = _texts(content)

        if role == "user" and text:
            yield {**base, "type": "user", "timestamp": ts,
                   "message": {"role": "user", "content": text}}

        elif role in ("gemini", "model", "assistant"):
            blocks = []

            # thinking blocks
            for th in m.get("thoughts") or []:
                if not isinstance(th, dict):
                    continue
                subj = th.get("subject") or ""
                desc = th.get("description") or ""
                thinking_text = (subj + ": " + desc).strip(": ") if subj else desc
                if thinking_text:
                    blocks.append({"type": "thinking", "thinking": thinking_text})

            # text block
            if text:
                blocks.append({"type": "text", "text": text})

            # tool_use blocks from toolCalls
            tool_calls = m.get("toolCalls") or []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                raw_name = tc.get("name") or "tool"
                canon = _canon_tool(raw_name)
                args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                blocks.append({"type": "tool_use", "name": canon,
                                "input": _canon_input(raw_name, args)})

            # token usage translation
            tok = m.get("tokens") if isinstance(m.get("tokens"), dict) else {}
            usage = {
                "input_tokens": int(tok.get("input") or 0),
                "output_tokens": int((tok.get("output") or 0) + (tok.get("thoughts") or 0)),
                "cache_read_input_tokens": int(tok.get("cached") or 0),
                "cache_creation_input_tokens": 0,
            }

            yield {**base, "type": "assistant", "timestamp": ts,
                   "message": {"role": "assistant", "model": m.get("model"),
                                "usage": usage, "content": blocks}}

            # tool_result user event for each toolCall
            if tool_calls:
                result_blocks = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    is_err = str(tc.get("status") or "").lower() == "error"
                    if not is_err:
                        try:
                            resp = (tc.get("result") or [{}])[0]
                            err_val = (resp.get("functionResponse") or {}).get(
                                "response", {}).get("error")
                            if err_val:
                                is_err = True
                        except Exception:
                            pass
                    result_blocks.append({"type": "tool_result", "is_error": bool(is_err)})
                yield {**base, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": result_blocks}}

        # m.type == "info" and anything else -> skip
