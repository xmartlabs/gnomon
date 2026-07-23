import json

from gnomon.sources._util import _texts, _iso_ms
from gnomon.sources.codex import _codex_events
from gnomon.sources.gemini import _gemini_events
from gnomon.sources.pi import _pi_events
from gnomon.sources.opencode import _opencode_events, _opencode_sqlite_events
from gnomon.sources.cursor import _cursor_jsonl_events, _cursor_sqlite_events
from gnomon.sources.antigravity import _antigravity_cli_events, _antigravity_ide_export_events


def _iter_events_raw(fp, fmt, cursor_twins=None):
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
                if isinstance(obj, dict):
                    # Claude root transcripts historically omit the field while
                    # sidechain files may rely on their authoritative /subagents/
                    # path. A present malformed value is never coerced to root.
                    path_parts = fp.replace("\\", "/").split("/")
                    path_sidechain = "subagents" in path_parts
                    raw_sidechain = obj.get("isSidechain", path_sidechain)
                    identity = raw_sidechain if isinstance(raw_sidechain, bool) else None
                    obj = dict(obj, isSidechain=identity)
                    yield obj
                else:
                    yield {"__bad__": True}
    elif fmt == "codex":
        yield from _codex_events(fp)
    elif fmt == "gemini":
        yield from _gemini_events(fp)
    elif fmt == "pi":
        yield from _pi_events(fp)
    elif fmt == "opencode":
        yield from _opencode_events(fp)
    elif fmt == "opencode-sqlite":
        yield from _opencode_sqlite_events(fp)
    elif fmt == "cursor-jsonl":
        yield from _cursor_jsonl_events(fp)
    elif fmt == "cursor-sqlite":
        yield from _cursor_sqlite_events(fp, cursor_twins)
    elif fmt == "antigravity-cli":
        yield from _antigravity_cli_events(fp)
    elif fmt == "antigravity-ide-export":
        yield from _antigravity_ide_export_events(fp)


def iter_events(fp, fmt, cursor_twins=None):
    """Yield canonical events with a stable adapter ordinal for timestamp ties."""
    for ordinal, event in enumerate(_iter_events_raw(fp, fmt, cursor_twins)):
        if isinstance(event, dict) and "__ordinal__" not in event:
            event = dict(event, __ordinal__=ordinal)
        yield event
