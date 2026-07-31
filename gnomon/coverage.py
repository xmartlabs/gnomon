"""Per-month coverage index over ~/.claude/history.jsonl -- a NEW, isolated
observability lane that never feeds scoring (see design decision A).

Boundary, enforced by geometry, not discipline: BASE = <CLAUDE_CONFIG_DIR>/projects
(gnomon/config.py) and gnomon.sources.discovery.discover_sources only walks BASE.
history.jsonl is a *sibling* of BASE (os.path.dirname(BASE)), so it can never be
reached by _walk_ext(BASE, ".jsonl") -- see tests/test_coverage.py's
TestDiscoverySourcesBoundary for the RED test that pins this invariant.

Leaf module: imports gnomon.config.BASE and stdlib only. Nothing in
gnomon/sources/ or gnomon/cli/accumulator.py imports this module, and this
module never imports gnomon.sources or gnomon.cli -- probe_month() takes
`source_paths` INJECTED by its caller (e.g. gnomon.upload.mirdash, which is
already a top-level consumer that may import gnomon.sources.discovery) so this
module stays free of those imports (decision A's dependency-injection resolution).

history.jsonl carries exactly 5 keys per line (display, pastedContents,
timestamp, project, sessionId) -- no tool calls, no models, no tokens. It can
NEVER become a scoring input; it is an index only, used to compute an
ADVISORY coverage ratio and a categorical flag.
"""
import json
import os
from datetime import datetime

from gnomon.config import BASE

HISTORY_PATH = os.path.join(os.path.dirname(BASE), "history.jsonl")

# "unknown" deliberately has no rank -- it is INCOMPARABLE, not a value on the
# insufficient < partial < complete ladder.
COVERAGE_RANK = {"insufficient": 0, "partial": 1, "complete": 2}

# The reference machine's history.jsonl is dominated by an automated probe
# (CodexBar/ClaudeProbe) that writes real interactive-looking rows but is not
# a human interactive session -- excluded from the indexed-session count.
_EXCLUDED_PROJECT_NEEDLES = ("codexbar", "claudeprobe")


def _is_excluded_project(project):
    p = str(project or "").lower()
    return any(needle in p for needle in _EXCLUDED_PROJECT_NEEDLES)


def _month_key_from_ts(ts):
    """history.jsonl timestamps are epoch milliseconds; tolerate seconds too."""
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return None
    if value > 1e12:  # looks like milliseconds
        value = value / 1000.0
    try:
        return datetime.fromtimestamp(value).astimezone().strftime("%Y-%m")
    except (OverflowError, OSError, ValueError):
        return None


def month_index(path=None):
    """Per-month distinct sessionId sets from history.jsonl, excluding the
    CodexBar/ClaudeProbe automated-probe project.

    Missing file, unreadable file, or a file with zero usable rows all fold to
    an empty dict -- callers look up one month at a time via `.get(mkey)`,
    which returns None for a month with no evidence either way (the ladder in
    `coverage_for`/`flag_for_counts` reads that as "unknown", never conflated
    with the real-zero case "insufficient"). Never returns None itself, so
    callers do not need a None-guard before `.get(...)`.

    `path` defaults to the CURRENT value of the module-level HISTORY_PATH at
    CALL time (not def time), so tests/overrides via
    `--claude-dir=`/CLAUDE_CONFIG_DIR (which patch this module's HISTORY_PATH
    attribute) are honored without callers needing to pass the path explicitly.
    """
    if path is None:
        path = HISTORY_PATH
    result = {}
    if not os.path.isfile(path):
        return result
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(row, dict):
                    continue
                if _is_excluded_project(row.get("project")):
                    continue
                sid = row.get("sessionId")
                if not sid:
                    continue
                mkey = _month_key_from_ts(row.get("timestamp"))
                if not mkey:
                    continue
                result.setdefault(mkey, set()).add(sid)
    except OSError:
        return {}
    return result


def flag_for_counts(indexed, transcripts):
    """The 4-value flag ladder over plain counts (used by the cheap pre-scoring
    check and the CLI<->server coverage comparison, where only counts -- not
    session-id sets -- are available).

    complete   = transcripts >= indexed > 0    ("no evidence of loss", not proof
                                                 of completeness -- the index is
                                                 itself a lower bound)
    partial    = 0 < transcripts < indexed
    insufficient = indexed > 0 and transcripts == 0
    unknown    = indexed is None or indexed <= 0 -- no evidence either way for
                 this month (missing history.jsonl on this machine, OR the file
                 exists but has zero rows for this specific month). Distinct
                 from `insufficient` by construction: `insufficient` requires
                 POSITIVE indexed evidence, `unknown` never has any.
    """
    if indexed is None or indexed <= 0:
        return "unknown"
    if transcripts <= 0:
        return "insufficient"
    if transcripts < indexed:
        return "partial"
    return "complete"


def coverage_for(indexed_sessions, transcript_sessions):
    """Per-month coverage record from two session-id sets.

    `indexed_sessions` is None when this month has no history.jsonl evidence
    at all (unknown); `transcript_sessions` is the real, already-accumulated
    set of session ids observed in this month's transcripts (NOT the mtime
    estimate -- see probe_month for the cheap pre-scoring approximation).

    Returns the exact 5 fields the coverage-index capability emits per month:
    indexed_interactive_sessions, available_transcripts, interactive_coverage
    (advisory ratio only -- never asserted as an exact percentage anywhere in
    the spec), transcript_only_sessions, flag.
    """
    transcripts = len(transcript_sessions or ())
    indexed = len(indexed_sessions) if indexed_sessions is not None else None
    flag = flag_for_counts(indexed, transcripts)
    if flag == "unknown":
        return {
            "flag": flag,
            "indexed_interactive_sessions": indexed,
            "available_transcripts": transcripts,
            "interactive_coverage": None,
            "transcript_only_sessions": transcripts,
        }
    overlap = len(transcript_sessions & indexed_sessions) if transcript_sessions else 0
    return {
        "flag": flag,
        "indexed_interactive_sessions": indexed,
        "available_transcripts": transcripts,
        "interactive_coverage": round(transcripts / indexed, 3),
        "transcript_only_sessions": transcripts - overlap,
    }


def probe_month(mkey, source_paths, history_index=None):
    """Cheap pre-scoring estimate for one month: no accumulator run, no JSON
    parsing of transcript contents.

    `indexed` comes from a real history.jsonl pass (`history_index`, a
    `month_index()`-shaped dict; computed once by the caller and reused across
    months so this stays a single pass, or passed as {} to test the pure
    mtime-estimate path in isolation). `source_paths` is INJECTED by the
    caller (kept import-free of gnomon.sources -- decision A) and bucketed by
    st_mtime (last-write time), NOT event time: this is NOT a lower-bound
    estimate in either direction. A transcript appended in month M+1
    containing month-M events buckets ENTIRELY into M+1 -- over-counting the
    write month and under-counting the event month simultaneously. Safe for a
    gate only (a spurious refresh wastes one upload; a missed refresh is
    recoverable via --force) -- see design decision B.

    Returns (indexed, transcripts_estimate). `indexed` is None when this month
    has no history.jsonl evidence (unknown).
    """
    idx = history_index if history_index is not None else month_index()
    ids = idx.get(mkey)
    indexed = len(ids) if ids is not None else None

    transcripts_estimate = 0
    for fp in source_paths:
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        fp_mkey = _month_key_from_ts(mtime * 1000.0)
        if fp_mkey == mkey:
            transcripts_estimate += 1
    return (indexed, transcripts_estimate)
