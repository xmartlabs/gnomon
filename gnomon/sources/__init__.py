import json

from gnomon.sources._util import _texts, _iso_ms
from gnomon.sources.codex import _codex_events
from gnomon.sources.gemini import _gemini_events
from gnomon.sources.pi import _pi_events
from gnomon.sources.opencode import _opencode_events
from gnomon.sources.cursor import _cursor_jsonl_events, _cursor_sqlite_events


def iter_events(fp, fmt, cursor_twins=None):
    """Yield Claude-shaped event dicts for any supported source format."""
    if fmt == "claude":
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
                yield obj if isinstance(obj, dict) else {"__bad__": True}
    elif fmt == "codex":
        yield from _codex_events(fp)
    elif fmt == "gemini":
        yield from _gemini_events(fp)
    elif fmt == "pi":
        yield from _pi_events(fp)
    elif fmt == "opencode":
        yield from _opencode_events(fp)
    elif fmt == "cursor-jsonl":
        yield from _cursor_jsonl_events(fp)
    elif fmt == "cursor-sqlite":
        yield from _cursor_sqlite_events(fp, cursor_twins)
