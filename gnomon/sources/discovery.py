import os
import re
import sys
import glob
from datetime import datetime, timedelta

from gnomon.config import BASE

CODEX_DIR = os.path.join(os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex")), "sessions")
GEMINI_DIR = os.path.expanduser("~/.gemini/tmp")
# CLI: one SQLite file per conversation, protobuf step payloads (fully decodable).
ANTIGRAVITY_CLI_DIR = os.path.expanduser("~/.gemini/antigravity-cli/conversations")
# IDE: full per-step transcripts are encrypted *.pb; this state DB holds the unencrypted
# trajectory index used for a volume/time-only summary (see antigravity_summary).
ANTIGRAVITY_DB = os.path.expanduser(
    "~/Library/Application Support/Antigravity/User/globalStorage/state.vscdb")
PI_DIR = os.path.expanduser("~/.pi/agent/sessions")
OPENCODE_DIR = os.path.expanduser("~/.local/share/opencode")
CURSOR_DIR = os.path.expanduser("~/.cursor/projects")
# Cursor CLI (cursor-agent) per-chat store: <hash>/<chatId>/{meta.json, store.db}. Carries
# the real session timestamp + model that the agent-transcripts JSONL omits.
CURSOR_CHATS_DIR = os.path.expanduser("~/.cursor/chats")


def _cursor_db_path():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/state.vscdb")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return os.path.join(appdata, "Cursor", "User", "globalStorage", "state.vscdb")
    return os.path.expanduser("~/.config/Cursor/User/globalStorage/state.vscdb")


CURSOR_DB = _cursor_db_path()
ALL_SOURCES = ("claude", "codex", "gemini", "antigravity", "antigravity-ide", "pi", "opencode", "cursor")

# antigravity-ide masks the model and exposes no subagent/token signal -> agent-mode unsupported.
_AGENT_UNSUPPORTED_SOURCES = frozenset({"gemini", "antigravity-ide"})

_DIR_FLAGS = {"claude": ("BASE", "projects"), "codex": ("CODEX_DIR", "sessions"),
              "gemini": ("GEMINI_DIR", None), "antigravity": ("ANTIGRAVITY_CLI_DIR", "conversations"),
              "pi": ("PI_DIR", None),
              "opencode": ("OPENCODE_DIR", None), "cursor": ("CURSOR_DIR", "projects")}


def parse_window(argv, now=None):
    """Time-window flags -> (since_dt, until_dt), tz-aware local datetimes, either None.

    --since=YYYY-MM-DD   inclusive start of window
    --until=YYYY-MM-DD   inclusive END DAY (internally exclusive next-midnight, so
                         --until=2026-03-31 keeps the whole 31st)
    --last=N[d|w|m]      rolling window ending now (d=days, w=weeks, m=30-day months);
                         overrides --since/--until

    Bad values warn and are ignored (same spirit as unknown sources/flags)."""
    since = until = None
    for a in argv:
        m = re.match(r"--(since|until)=(\d{4}-\d{2}-\d{2})$", a)
        if m:
            try:
                dt = datetime.fromisoformat(m.group(2)).astimezone()
            except ValueError:
                print(f"  warning: bad date in {a} ignored (use YYYY-MM-DD)")
                continue
            if m.group(1) == "since":
                since = dt
            else:
                until = dt + timedelta(days=1)
            continue
        if a.startswith(("--since=", "--until=")):
            print(f"  warning: bad date in {a} ignored (use YYYY-MM-DD)")
            continue
        m = re.match(r"--last=(\d+)([dwm]?)$", a)
        if m:
            days = int(m.group(1)) * {"": 1, "d": 1, "w": 7, "m": 30}[m.group(2)]
            end = now or datetime.now().astimezone()
            return end - timedelta(days=days), None    # open-ended: up to now
        if a.startswith("--last="):
            print(f"  warning: bad value in {a} ignored (use --last=N[d|w|m])")
    return since, until


def _resolve_source_dir(path, inner):
    """Accept a source dir override as either the tool's config root or the transcripts
    subdir itself (e.g. --claude-dir=~/.claude OR ~/.claude/projects)."""
    p = os.path.expanduser(path)
    if inner and os.path.isdir(os.path.join(p, inner)):
        return os.path.join(p, inner)
    return p


def _walk_ext(root, ext):
    """Yield sorted file paths matching *<ext> under root.

    Uses os.walk (scandir-backed on Python 3.5+) instead of glob.glob with
    recursive=True, avoiding fnmatch overhead on every directory entry.
    Hidden directories (starting with '.') are pruned early.
    """
    if not os.path.isdir(root):
        return []
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for fn in filenames:
            if fn.endswith(ext):
                result.append(os.path.join(dirpath, fn))
    return sorted(result)


def _cursor_jsonl_files():
    """All agent-transcripts JSONL files: main sessions AND subagent sidechains
    (.../<session>/subagents/<id>.jsonl -- one glob level deeper)."""
    if not os.path.isdir(CURSOR_DIR):
        return []
    result = []
    for dirpath, dirnames, filenames in os.walk(CURSOR_DIR):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        base = os.path.basename(dirpath)
        if base in ("agent-transcripts",):
            continue
        parent = os.path.basename(os.path.dirname(dirpath))
        grandparent = os.path.basename(os.path.dirname(os.path.dirname(dirpath)))
        in_transcripts = (parent == "agent-transcripts"
                          or grandparent == "agent-transcripts")
        if in_transcripts:
            for fn in filenames:
                if fn.endswith(".jsonl"):
                    result.append(os.path.join(dirpath, fn))
    return sorted(result)


def discover_sources(selected):
    out = []
    if "claude" in selected and os.path.isdir(BASE):
        for fp in _walk_ext(BASE, ".jsonl"):
            out.append(("claude", fp, "claude"))
    if "codex" in selected and os.path.isdir(CODEX_DIR):
        for fp in _walk_ext(CODEX_DIR, ".jsonl"):
            out.append(("codex", fp, "codex"))
    if "gemini" in selected and os.path.isdir(GEMINI_DIR):
        for fp in _walk_ext(GEMINI_DIR, ".json"):
            out.append(("gemini", fp, "gemini"))
    if "antigravity" in selected and os.path.isdir(ANTIGRAVITY_CLI_DIR):
        for fp in sorted(glob.glob(os.path.join(ANTIGRAVITY_CLI_DIR, "*.db"))):
            out.append(("antigravity", fp, "antigravity-cli"))
    if "pi" in selected and os.path.isdir(PI_DIR):
        for fp in _walk_ext(PI_DIR, ".jsonl"):
            out.append(("pi", fp, "pi"))
    if "opencode" in selected and os.path.isdir(OPENCODE_DIR):
        session_glob = os.path.join(OPENCODE_DIR, "storage", "session", "*", "*.json")
        for fp in sorted(glob.glob(session_glob)):
            out.append(("opencode", fp, "opencode"))
    if "cursor" in selected and os.path.isdir(CURSOR_DIR):
        for fp in sorted(_cursor_jsonl_files()):
            out.append(("cursor", fp, "cursor-jsonl"))
    if "cursor" in selected and os.path.isfile(CURSOR_DB):
        out.append(("cursor", CURSOR_DB, "cursor-sqlite"))
    return out
