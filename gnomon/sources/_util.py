from datetime import datetime


def _texts(content):
    """Join text from a Claude/Codex/Gemini/Pi/opencode content list (or plain string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict):
                out.append(b.get("text") or b.get("input_text") or b.get("output_text") or "")
            elif isinstance(b, str):
                out.append(b)
        return "\n".join(x for x in out if x)
    return ""


def _iso_ms(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000).astimezone().isoformat()
    except Exception:
        return None
