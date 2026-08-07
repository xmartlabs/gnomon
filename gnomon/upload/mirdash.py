import calendar
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

from gnomon.scoring.aq import DEFAULT_SCORING_WINDOW_MONTHS
from gnomon.scoring.versioning import SCORE_CONTRACT_ID
from gnomon.coverage import COVERAGE_RANK, flag_for_counts, month_index, probe_month


_COPIED_OUTPUTS = (
    "summary.json",
    "stats.json",
    "report.md",
    "profile.html",
    "narrative_input.md",
)

_DEFAULT_MIRDASH_BASE = "https://mirdash.xmartlabs.com"

# mirdash's /api/gnomon/ingest route stores the raw summary verbatim in a single
# Convex document (route.ts's MAX_BODY_BYTES = 900 * 1024, binary KB) against a 1 MiB
# per-document limit. This is gnomon's mirror of that same arithmetic, checked BEFORE
# the POST so an over-budget payload fails loudly here instead of a 413 from the
# server.
#
# persist-recompute-grade-inputs SCOPE RELAXATION: an earlier revision of this
# capability shipped a `scoring_inputs_corpus` merged-corpus block so a future
# recompute job could reproduce profile.aq EXACTLY for multi-source corpora.
# Measured on real 8-source data (python3 -m gnomon.cli.insights --local --console),
# that block alone cost ~487 KB and pushed a real payload from 824,398 bytes
# (ratio 0.8945, fits) to 1,369,511 bytes (ratio 1.4860, OVER this cap) --
# exactness was its only value; the same approximate combined AQ it enabled was
# already reconstructible from the per-source blocks that ship regardless (see
# gnomon/scoring/replay.py's module docstring). The requirement was relaxed:
# approximate multi-source recompute is acceptable, so `scoring_inputs_corpus`
# is no longer built or shipped at all, for any source count. Real measurement
# after dropping it (keeping bucket_scoring_inputs + payload_features):
# 839,496 bytes, ratio 0.9109 -- FITS. v11 then removed the recency blend and with it
# `bucket_scoring_inputs`, so a current payload is strictly smaller than that figure;
# the number is left as measured rather than re-estimated.
#
# KNOWN RISK (documented, not a blocker): the real baseline (everything except
# this capability's two additive blocks) already sits at ~89% of this budget
# for a heavy 8-source, multi-month user -- a PRE-EXISTING condition this
# change did not create (it predates this capability entirely) and does not
# meaningfully worsen (adds only ~1.6 percentage points on real data). A fully
# synthetic worst-case fixture (every documented per-source/per-month list cap
# hit simultaneously across all 8 sources, see tests/test_payload_budget.py)
# shows the PRE-EXISTING scoring_inputs_by_source + profiles_by_source fields
# can alone exceed this cap in an extreme, never-observed scenario -- unrelated
# to bucket_scoring_inputs/payload_features. Closing that gap is the deferred
# mirdash structural split (denormalized scoring-inputs table), tracked as a
# follow-up, not a blocker for this change. See
# tests/test_payload_budget.py::WorstCasePayloadBudget for the assertions this
# capability's own footprint is held to, and
# docs/metrics-by-source.md's "Upload payload budget" section for the full
# writeup.
_INGEST_MAX_BYTES = 900 * 1024


class PayloadTooLarge(RuntimeError):
    """Raised by _upload_summary when the serialized payload exceeds
    _INGEST_MAX_BYTES. A RuntimeError subclass so nothing that already catches
    RuntimeError changes shape, but a distinct type so callers can separate a
    budget violation from a network/HTTP failure and refuse to swallow it."""


def _gnomon_config():
    """Read ~/.config/gnomon/config.json; return {} on missing/invalid."""
    path = os.path.expanduser("~/.config/gnomon/config.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _resolve_mirdash_base(argv):
    """Return the mirdash base URL (no trailing slash).

    Precedence (first match wins):
      1. --mirdash-base=URL CLI flag
      2. env GNOMON_MIRDASH_BASE
      3. ~/.config/gnomon/config.json key 'mirdash_base'
      4. baked default https://mirdash.xmartlabs.com
    """
    for a in argv:
        m = re.match(r"--mirdash-base=(.+)$", a)
        if m:
            return m.group(1).rstrip("/")
    env = os.environ.get("GNOMON_MIRDASH_BASE", "").strip()
    if env:
        return env.rstrip("/")
    cfg = _gnomon_config().get("mirdash_base", "").strip()
    if cfg:
        return cfg.rstrip("/")
    return _DEFAULT_MIRDASH_BASE


# Maximum batch size supported by the mirdash auth endpoint.
_MAX_BACKFILL = 12

# Default window size when --window is absent. Re-exported, not defined: the window is a
# calibration input (it decides the corpus every absolute ceiling and session-count floor
# in aq.py is judged against), so it is owned by the scoring module and covered by
# gnomon/scoring/calibration.py's fingerprint. This alias keeps every existing importer --
# gnomon/cli/insights.py, xl_ai_insights.py, tests -- reading the same value.
_DEFAULT_WINDOW_MONTHS = DEFAULT_SCORING_WINDOW_MONTHS

# Parallel month uploads. Each month runs paxel.py as a subprocess (CPU-bound),
# so threads only block on subprocess.run -- no GIL contention, real multi-core.
_UPLOAD_CONCURRENCY = 4

# Sentinels returned by the web upload helper so callers can tell a real reportUrl
# apart from the two distinct failure modes (paxel run failed vs. upload POST failed).
_PAXEL_ERROR = "PAXEL_ERROR"
_UPLOAD_ERROR = "UPLOAD_ERROR"


def _is_report_url(value):
    """True only when a live upload was stored and has a report URL."""
    return not _is_archived_only(value) and _result_report_url(value) is not None


def _is_archived_only(value):
    return isinstance(value, dict) and value.get("outcome") == "archived_only"


def _result_report_url(value):
    if isinstance(value, dict):
        report_url = value.get("reportUrl")
        return report_url if isinstance(report_url, str) and report_url else None
    if isinstance(value, str) and value not in (_PAXEL_ERROR, _UPLOAD_ERROR):
        return value
    return None


def _upload_summary(mirdash_base, token, summary):
    """POST summary dict to mirdash /api/gnomon/ingest.

    Returns a tagged stored/archive-only response when the server supplies an
    outcome. Legacy responses without an outcome remain reportUrl strings.
    Raises on error. Token is never logged.
    """
    import urllib.error
    import urllib.request
    body = json.dumps(summary, default=str).encode("utf-8")
    if len(body) >= _INGEST_MAX_BYTES:
        raise PayloadTooLarge(
            f"summary payload is {len(body)} bytes, at or over the mirdash "
            f"ingest budget of {_INGEST_MAX_BYTES} bytes -- refusing to upload "
            f"a payload the server would reject or truncate")
    req = urllib.request.Request(
        f"{mirdash_base}/api/gnomon/ingest",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        report_url = data["reportUrl"]
        outcome = data.get("outcome")
        if outcome is None:
            return report_url
        if outcome not in ("stored", "archived_only"):
            raise RuntimeError(f"upload returned unsupported outcome: {outcome}")
        return {"outcome": outcome, "reportUrl": report_url}
    except urllib.error.HTTPError as exc:
        try:
            server_msg = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            server_msg = ""
        detail = f": {server_msg}" if server_msg else ""
        raise RuntimeError(f"upload failed (HTTP {exc.code}){detail}") from exc


def _format_summary(summary: dict, quiet: bool = False) -> str:
    """Return a concise, terminal-friendly multi-line string from a paxel summary.json dict.

    Ratios (planning_ratio_explore_to_doing and errors.error_recovery_ratio) are shown as
    integer percentages.  Everything else uses labeled counts/values with explicit units.
    Returns "" immediately when quiet is True.
    """
    if quiet:
        return ""

    ctx = summary.get("context", {}) or {}
    dr = ctx.get("date_range") or ["?", "?"]
    start = dr[0] if len(dr) > 0 else "?"
    end   = dr[1] if len(dr) > 1 else "?"
    sessions = ctx.get("total_sessions", 0) or 0

    lines = []
    lines.append(f"\n  Your build profile  -  {sessions} sessions  -  {start}->{end}")

    # Label column width — keep values aligned (longest label "Compounding writes" = 18)
    W = 19

    planning_ratio = summary.get("planning_ratio_explore_to_doing")
    if planning_ratio is not None:
        pct = round(float(planning_ratio) * 100)
        lines.append(f"  {'Planning ratio':<{W}}{pct}%")

    errors = summary.get("errors", {}) or {}
    recovery = errors.get("error_recovery_ratio")
    if recovery is not None:
        pct = round(float(recovery) * 100)
        lines.append(f"  {'Error recovery':<{W}}{pct}%")
    err_rate = errors.get("error_rate_per_100_tools")
    if err_rate is not None:
        lines.append(f"  {'Error rate':<{W}}{err_rate:.1f} errors / 100 tools")

    iteration = summary.get("iteration_depth", {}) or {}
    mean = iteration.get("mean")
    p90  = iteration.get("p90")
    if mean is not None:
        p90_str = f" (p90 {p90})" if p90 is not None else ""
        lines.append(f"  {'Iteration depth':<{W}}~{float(mean):.1f} edits/file{p90_str}")

    churn = summary.get("churn", {}) or {}
    git_churn = churn.get("git_churn_total")
    if git_churn is not None:
        lines.append(f"  {'Code churn':<{W}}{git_churn} lines (git)")

    orch = summary.get("orchestration", {}) or {}
    fanout = orch.get("fanout_median")
    delegate = orch.get("delegate_actions")
    if fanout is not None or delegate is not None:
        fanout_str   = f"fanout ~{float(fanout):.1f}" if fanout is not None else ""
        delegate_str = f"{delegate} delegated" if delegate is not None else ""
        parts = [p for p in [fanout_str, delegate_str] if p]
        lines.append(f"  {'Orchestration':<{W}}{', '.join(parts)}")

    compounding = summary.get("compounding_writes")
    if compounding is not None:
        lines.append(f"  {'Compounding writes':<{W}}{compounding}")

    ecosystem = summary.get("ecosystem", {}) or {}
    skills     = ecosystem.get("skills_distinct")
    mcp_servers = ecosystem.get("mcp_servers_distinct")
    if skills is not None or mcp_servers is not None:
        skills_str = f"{skills} skills" if skills is not None else ""
        mcp_str    = f"{mcp_servers} MCP servers" if mcp_servers is not None else ""
        parts = [p for p in [skills_str, mcp_str] if p]
        lines.append(f"  {'Ecosystem':<{W}}{', '.join(parts)}")

    return "\n".join(lines)


def _absolutize_dir_flags(args):
    """Rewrite relative --<source>-dir=PATH values to absolute paths.

    paxel runs from a temporary working directory, so a relative override like
    --claude-dir=./backup would resolve against that temp dir and silently find
    nothing. Resolve such paths against the caller's current working directory
    here, before forwarding. Absolute paths and non-dir flags pass through unchanged.
    """
    out = []
    for a in args:
        m = re.match(r"(--[a-z]+-dir=)(.+)$", a)
        if m:
            out.append(m.group(1) + os.path.abspath(os.path.expanduser(m.group(2))))
        else:
            out.append(a)
    return out


def _resolve_output_dir(argv):
    """Return the CLI-provided output dir, or None if unset/invalid."""
    for a in argv:
        if a == "--output-dir":
            print("  warning: --output-dir needs a value (use --output-dir=PATH)", file=sys.stderr)
            return None
        m = re.match(r"--output-dir=(.+)$", a)
        if m:
            return m.group(1)
    return None


def _copy_artifacts(src_dir, output_dir, file_prefix=""):
    """Copy final paxel outputs into output_dir, overwriting existing files."""
    dst_dir = os.path.abspath(os.path.expanduser(output_dir))
    os.makedirs(dst_dir, exist_ok=True)
    for name in _COPIED_OUTPUTS:
        src = os.path.join(src_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst_dir, file_prefix + name))
    return dst_dir


def parse_window(argv):
    """Return the window_months value from argv.

    --window=N  → int(N) if N >= 1, else warning + default
    absent      → default (_DEFAULT_WINDOW_MONTHS)
    invalid N   → warning + default
    """
    for a in argv:
        if a == "--window":
            print(
                f"  warning: --window needs a value (use --window=N)"
                f" -- using default {_DEFAULT_WINDOW_MONTHS}",
                file=sys.stderr,
            )
            return _DEFAULT_WINDOW_MONTHS
        m = re.match(r"--window=(.+)$", a)
        if m:
            raw = m.group(1)
            try:
                n = int(raw)
            except ValueError:
                print(
                    f"  warning: --window={raw!r} is not a valid integer"
                    f" -- using default {_DEFAULT_WINDOW_MONTHS}",
                    file=sys.stderr,
                )
                return _DEFAULT_WINDOW_MONTHS
            if n < 1:
                print(
                    f"  warning: --window={n} must be >= 1"
                    f" -- using default {_DEFAULT_WINDOW_MONTHS}",
                    file=sys.stderr,
                )
                return _DEFAULT_WINDOW_MONTHS
            return n
    return _DEFAULT_WINDOW_MONTHS


def parse_backfill(argv):
    """Return the backfill count from argv, or None if --backfill is absent.

    --backfill        → 6
    --backfill=N      → int(N) clamped to [1, _MAX_BACKFILL]
    non-int value     → 6 (treat as bare flag)
    absent            → None
    """
    for a in argv:
        if a == "--backfill":
            return 6
        m = re.match(r"--backfill=(.+)$", a)
        if m:
            try:
                n = int(m.group(1))
            except ValueError:
                return 6  # non-int → treat as bare flag
            return max(1, min(n, _MAX_BACKFILL))
    return None


def decide_mode(argv):
    """Return (mode, n) from argv.

    Precedence (first match wins):
      --force             → ('force', _MAX_BACKFILL)
      --backfill[=N]      → ('backfill', N)
      neither             → ('auto', _MAX_BACKFILL)
    """
    if "--force" in argv:
        return ("force", _MAX_BACKFILL)
    n = parse_backfill(argv)
    if n is not None:
        return ("backfill", n)
    return ("auto", _MAX_BACKFILL)


def latest_month_with_data(progression_monthly):
    """Return the most recent 'YYYY-MM' string from a progression_monthly list.

    Each entry is expected to have a 'month' key with value 'YYYY-MM'.
    Entries missing the 'month' key are silently skipped.
    Returns None if the list is empty or all entries lack 'month'.
    """
    months = [entry["month"] for entry in progression_monthly if "month" in entry]
    if not months:
        return None
    return max(months)


def _anchor_window(anchor_year, anchor_month, window_months=1, today=None):
    """Return (since_iso, until_iso, label) for a single anchor month.

    When *today* is provided, the anchor is today's current month, and
    ``window_months == 1``, the window becomes a **trailing 30-day window**
    ending at *today* (inclusive) instead of the full calendar month::

        since = today - 30 days
        until = today + 1 day  (exclusive upper bound)

    Closed months (anchor != today's month) and multi-month windows
    (``window_months > 1``) always use full calendar-month bounds regardless
    of *today*.

    Calendar-month semantics (closed months / multi-month windows):
      since = first day of the month that is (window_months-1) months before the anchor (inclusive).
      until = first day of the month AFTER the anchor (exclusive).
      label = 'YYYY-MM' of the anchor.

    window_months=1 gives a single-calendar-month window (since == anchor's first day).
    """
    label = f"{anchor_year:04d}-{anchor_month:02d}"

    # Current month with single-month window: trailing 30-day window
    if (today is not None
            and window_months == 1
            and anchor_year == today.year
            and anchor_month == today.month):
        since = today - datetime.timedelta(days=30)
        until = today + datetime.timedelta(days=1)
        return (since.isoformat(), until.isoformat(), label)

    # Closed month or multi-month window: full calendar-month bounds
    anchor_total_months = anchor_year * 12 + (anchor_month - 1)

    # Compute start month
    start_total_months = anchor_total_months - (window_months - 1)
    start_year = start_total_months // 12
    start_month = start_total_months % 12 + 1  # 1-based

    since = datetime.date(start_year, start_month, 1)
    # until = first day of the month after the anchor
    _, last_day = calendar.monthrange(anchor_year, anchor_month)
    until = datetime.date(anchor_year, anchor_month, 1) + datetime.timedelta(days=last_day)
    return (since.isoformat(), until.isoformat(), label)


def month_windows(n, today, window_months=1):
    """Return a list of (since_iso, until_iso, label) for the last *n* calendar months.

    Each entry spans `window_months` calendar months ending at (and including) an anchor month.
    Oldest month first; the last entry is the current (possibly partial) month.
    *today* is a datetime.date; the function never calls datetime.now() itself.

    For each anchor month:
      since = YYYY-MM-01 (inclusive) = first day of the month that is (window_months - 1) months before anchor
      until = first day of the month AFTER the anchor (exclusive)
      label = 'YYYY-MM' (the anchor month — the END month of the window)

    window_months=1 reproduces the legacy single-calendar-month windows.
    """
    windows = []
    # Work backwards: month index 0 = current month, 1 = previous, …
    for i in range(n - 1, -1, -1):
        # Compute the anchor month (end of the window)
        anchor_total_months = today.year * 12 + (today.month - 1) - i
        anchor_year = anchor_total_months // 12
        anchor_month = anchor_total_months % 12 + 1  # 1-based
        windows.append(_anchor_window(anchor_year, anchor_month, window_months, today=today))
    return windows


def windows_for_anchors(anchor_labels, window_months=1, today=None):
    """Map a list of anchor labels ['YYYY-MM', ...] to [(since_iso, until_iso, label), ...].

    Preserves the input order.  Uses _anchor_window for each label.
    anchor_labels: list of 'YYYY-MM' strings, oldest first.

    When *today* is provided it is forwarded to ``_anchor_window`` so the
    current month can use a trailing 30-day window instead of full calendar
    bounds.
    """
    result = []
    for label in anchor_labels:
        year = int(label[:4])
        month = int(label[5:7])
        result.append(_anchor_window(year, month, window_months, today=today))
    return result


def default_producible_coverage_for(month_key):
    """Real `producible_coverage_for` implementation: the cheap pre-scoring
    check (no accumulator run, no JSON parsing of transcripts) that decides
    whether re-scoring the previous month is even worth attempting.

    Wired by gnomon/cli/insights.py's real console/web call sites; deliberately
    NOT plan_upload's default (see its docstring) so a caller that has not
    explicitly opted in never touches the filesystem for this decision."""
    from gnomon.sources.discovery import ALL_SOURCES, discover_sources
    source_paths = [fp for _, fp, _ in discover_sources(ALL_SOURCES)]
    idx = month_index()
    indexed, transcripts = probe_month(month_key, source_paths, history_index=idx)
    flag = flag_for_counts(indexed, transcripts)
    return (COVERAGE_RANK.get(flag), transcripts)


def _stored_coverage_rank_and_transcripts(previous_entry):
    """(rank, transcripts) from a server-stored month entry's `coverage` field,
    or (None, 0) when absent/invalid -- `None` is INCOMPARABLE (never a
    justification to refresh), covering both a pre-coverage-capability upload
    (old client/server) and a genuinely unknown month."""
    coverage = previous_entry.get("coverage") if isinstance(previous_entry, dict) else None
    if not isinstance(coverage, dict):
        return (None, 0)
    rank = COVERAGE_RANK.get(coverage.get("flag"))
    transcripts = coverage.get("transcripts") or 0
    if not isinstance(transcripts, int) or isinstance(transcripts, bool):
        transcripts = 0
    return (rank, transcripts)


def plan_upload(
    today,
    server_months,
    force=False,
    max_months=_MAX_BACKFILL,
    *,
    active_contract=SCORE_CONTRACT_ID,
    producible_coverage_for=None,
):
    """Return sorted list (oldest first) of (anchor 'YYYY-MM', reason) pairs to upload.

    today:         datetime.date — caller must supply; this function never calls date.today().
    server_months: explicit history-state dict for contract-aware auto mode.
                   Legacy list inputs retain the pre-protocol planner for
                   internal backward compatibility only.
    force:         bool — when True, behave as if server were empty (full backfill).
    max_months:    hard cap; never return more than this many anchors.
    producible_coverage_for: optional `month_key -> (rank, transcripts)` callable
                   (see gnomon.coverage.COVERAGE_RANK) used ONLY to decide whether
                   the previous month is worth a coverage-gated refresh. The
                   transcript value is a local estimate and is used to derive the
                   rank, but is not compared numerically with the server value:
                   the local pre-check counts files by mtime while the server
                   stores unique transcript sessions. Omitting it (the default)
                   is the SAFE choice: no refresh is ever triggered, so a caller
                   that has not wired a real cheap pre-check
                   (gnomon.coverage.probe_month over discover_sources) never
                   spends an upload on a refresh it cannot justify.

    reason ∈ {'force', 'initial', 'current', 'gap', 'refresh'}
      explicit valid history:
        previous entry missing                        → gap, then current
        previous or producible coverage rank is None   → current only (incomparable; no refresh)
        producible rank > stored rank                   → refresh, then current
        equal ranks                                     → current only
        otherwise                                       → current only
      unavailable/legacy/malformed/valid-empty → current only
      force=True → full explicit backfill

    `contract-bridge` (scoreContractId-based comparison) is REMOVED: coverage
    is the only comparison basis for whether the previous month is worth
    re-scoring (see design.md decision B; a coverage-gated refresh is safe
    across a contract change too, since the anti-degradation guard on the
    server never lets a worse payload replace a better stored row).
    Legacy list compatibility:
      force=True                      → each anchor gets reason 'force'
      server empty (no valid entries) → each anchor gets reason 'initial'
      incremental:
        current month                 → 'current'
        gap months (missing on server, strictly between latest_server and current) → 'gap'
        prev if stale                 → 'refresh'
        Precedence if overlap: current > gap > refresh (disjoint in practice)
    """
    current = f"{today.year:04d}-{today.month:02d}"

    if isinstance(server_months, dict) and "state" in server_months:
        if force:
            return [(w[2], "force") for w in month_windows(max_months, today, 1)]

        state = server_months.get("state")
        months = server_months.get("months")
        if state != "valid" or not isinstance(months, list):
            return [(current, "current")]
        if not months:
            return [(w[2], "initial") for w in month_windows(max_months, today, 1)]

        current_total = today.year * 12 + (today.month - 1)
        previous_total = current_total - 1
        previous = f"{previous_total // 12:04d}-{previous_total % 12 + 1:02d}"
        by_month = {
            entry.get("monthKey"): entry
            for entry in months
            if isinstance(entry, dict) and isinstance(entry.get("monthKey"), str)
        }
        previous_entry = by_month.get(previous)
        if previous_entry is None:
            return [(previous, "gap"), (current, "current")]

        stored_rank, _ = _stored_coverage_rank_and_transcripts(previous_entry)
        producible = producible_coverage_for(previous) if producible_coverage_for else (None, 0)
        producible_rank, _ = producible if producible else (None, 0)

        if stored_rank is not None and producible_rank is not None:
            if producible_rank > stored_rank:
                return [(previous, "refresh"), (current, "current")]
            return [(current, "current")]

        return [(current, "current")]

    # Parse server_months defensively; skip malformed entries
    valid_server = {}
    for entry in server_months:
        if not isinstance(entry, dict):
            continue
        mk = entry.get("monthKey")
        if not isinstance(mk, str) or not re.fullmatch(r"\d{4}-\d{2}", mk):
            continue
        try:
            ua = int(entry["uploadedAt"])
        except (KeyError, TypeError, ValueError):
            continue
        valid_server[mk] = ua

    # force → full backfill with reason 'force'
    if force:
        return [(w[2], "force") for w in month_windows(max_months, today, 1)]

    # no valid server data → full backfill with reason 'initial'
    if not valid_server:
        return [(w[2], "initial") for w in month_windows(max_months, today, 1)]

    # Incremental path: build {label: reason} dict
    reasons = {}
    reasons[current] = "current"

    # Gap fill: months strictly between latest_server (exclusive) and current (exclusive)
    latest_server = max(valid_server)
    ls_y = int(latest_server[:4])
    ls_m = int(latest_server[5:7])
    cur_y = today.year
    cur_m = today.month
    ls_total = ls_y * 12 + (ls_m - 1)
    cur_total = cur_y * 12 + (cur_m - 1)
    for t in range(ls_total + 1, cur_total):  # strictly between, current added separately
        gy = t // 12
        gm = t % 12 + 1
        label = f"{gy:04d}-{gm:02d}"
        if label not in reasons:
            reasons[label] = "gap"

    # Stale refresh for prev month
    prev_total = cur_total - 1
    prev_y = prev_total // 12
    prev_m = prev_total % 12 + 1
    prev_label = f"{prev_y:04d}-{prev_m:02d}"
    if prev_label in valid_server:
        # end_of_month bound = 00:00:00 UTC of first day of next month after prev
        if prev_m == 12:
            bound_y, bound_m = prev_y + 1, 1
        else:
            bound_y, bound_m = prev_y, prev_m + 1
        bound_ms = int(
            datetime.datetime(bound_y, bound_m, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000
        )
        if valid_server[prev_label] < bound_ms:
            if prev_label not in reasons:
                reasons[prev_label] = "refresh"

    # Dedup + sort lexicographically (= chronologically for zero-padded YYYY-MM)
    sorted_pairs = sorted(reasons.items())

    # Truncate to max_months most recent
    if len(sorted_pairs) > max_months:
        sorted_pairs = sorted_pairs[-max_months:]

    return sorted_pairs


def months_to_upload(
    today,
    server_months,
    force=False,
    max_months=_MAX_BACKFILL,
    *,
    active_contract=SCORE_CONTRACT_ID,
    producible_coverage_for=None,
):
    """Return sorted list (oldest first) of anchor 'YYYY-MM' labels to upload.

    today:         datetime.date — caller must supply; this function never calls date.today().
    server_months: explicit history-state dict, or a legacy list accepted only
                   for internal backward compatibility.
    force:         bool — when True, behave as if server were empty (full backfill).
    max_months:    hard cap; never return more than this many anchors.

    Algorithm:
      force OR server empty → last max_months months (oldest first) — behaves like the old --init.
      incremental:
        1. Always include current month.
        2. Gap fill: every month strictly between latest_server and current.
        3. Stale refresh: include prev (current - 1 month) if it's in server_months
           AND its uploadedAt < 00:00:00 UTC on the first day of the NEXT month after prev
           (i.e. the snapshot did not yet capture the full month).
        4. Dedup → sort → keep max_months most recent.
    """
    return [
        m
        for m, _ in plan_upload(
            today,
            server_months,
            force,
            max_months,
            active_contract=active_contract,
            producible_coverage_for=producible_coverage_for,
        )
    ]


def _history_from_query(parsed_qs):
    """Parse the explicit uploaded-history callback parameter without partial trust.

    Returns {'state': valid|unavailable|legacy|malformed, 'months': [...]}. A
    missing explicit object is legacy even when the old `uploaded` alias exists.
    """
    raw = (parsed_qs.get("uploaded_history") or [""])[0]
    if not raw:
        return {"state": "legacy", "months": []}
    try:
        data = json.loads(raw)
    except Exception:
        return {"state": "malformed", "months": []}
    if not isinstance(data, dict):
        return {"state": "malformed", "months": []}

    outcome = data.get("outcome")
    if outcome == "unavailable":
        return {"state": "unavailable", "months": []}
    if outcome != "valid" or not isinstance(data.get("months"), list):
        return {"state": "malformed", "months": []}

    best = {}
    for entry in data["months"]:
        if not isinstance(entry, dict):
            return {"state": "malformed", "months": []}
        month_key = entry.get("monthKey")
        if (
            not isinstance(month_key, str)
            or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month_key)
        ):
            return {"state": "malformed", "months": []}
        uploaded_at = entry.get("uploadedAt")
        if isinstance(uploaded_at, bool) or not isinstance(uploaded_at, (int, float)):
            return {"state": "malformed", "months": []}
        if isinstance(uploaded_at, float):
            if not math.isfinite(uploaded_at) or not uploaded_at.is_integer():
                return {"state": "malformed", "months": []}
            uploaded_at = int(uploaded_at)
        if uploaded_at < 0 or uploaded_at > 9_007_199_254_740_991:
            return {"state": "malformed", "months": []}
        contract = entry.get("scoreContractId")
        if contract is not None and (not isinstance(contract, str) or not contract):
            return {"state": "malformed", "months": []}
        coverage = entry.get("coverage")
        if coverage is not None:
            _flag = coverage.get("flag") if isinstance(coverage, dict) else None
            _indexed = coverage.get("indexed") if isinstance(coverage, dict) else None
            _transcripts = coverage.get("transcripts") if isinstance(coverage, dict) else None
            if (
                not isinstance(coverage, dict)
                or _flag not in ("complete", "partial", "insufficient", "unknown")
                or not isinstance(_indexed, int) or isinstance(_indexed, bool)
                or not isinstance(_transcripts, int) or isinstance(_transcripts, bool)
            ):
                # All-or-nothing strictness (consistent with the rest of this
                # parser): a structurally invalid coverage object invalidates
                # the WHOLE history, not just this one entry.
                return {"state": "malformed", "months": []}
        total_sessions = entry.get("totalSessions")
        normalized = {"monthKey": month_key, "uploadedAt": uploaded_at}
        if contract is not None:
            normalized["scoreContractId"] = contract
        if coverage is not None:
            normalized["coverage"] = coverage
        if isinstance(total_sessions, (int, float)) and not isinstance(total_sessions, bool):
            normalized["totalSessions"] = int(total_sessions)
        existing = best.get(month_key)
        if existing is None or normalized["uploadedAt"] > existing["uploadedAt"]:
            best[month_key] = normalized

    return {"state": "valid", "months": [best[key] for key in sorted(best)]}


def _uploaded_from_query(parsed_qs):
    """Extract the uploaded-month list from a parse_qs result dict.

    Expects: &uploaded=<JSON url-encoded>
    where the JSON is a list of {'monthKey': 'YYYY-MM', 'uploadedAt': <int>} dicts.

    Returns a list of validated dicts with 'monthKey' (str) and 'uploadedAt' (int).
    Returns [] if the key is absent, the JSON is malformed, or any validation fails.
    Never raises.
    """
    raw = (parsed_qs.get("uploaded") or [""])[0]
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    result = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        mk = entry.get("monthKey")
        if not isinstance(mk, str) or not re.fullmatch(r"\d{4}-\d{2}", mk):
            continue
        try:
            ua = int(entry["uploadedAt"])
        except (KeyError, TypeError, ValueError):
            continue
        result.append({"monthKey": mk, "uploadedAt": ua})
    return result


def _paxel_until_arg(exclusive_until_iso):
    """Translate an exclusive month-window bound to paxel's inclusive --until date."""
    return (datetime.date.fromisoformat(exclusive_until_iso) - datetime.timedelta(days=1)).isoformat()


def _run_paxel(paxel_src, paxel_args, verbose, quiet=False, output_dir=None, file_prefix=""):
    """Run paxel.py in a temp directory and return the parsed summary dict.

    Returns the summary dict on success, or None on failure (errors already printed).
    """
    tmp = tempfile.mkdtemp(prefix="xl-ai-insights-")
    resolved_output_dir = None
    if output_dir:
        resolved_output_dir = os.path.abspath(os.path.expanduser(output_dir))

    tmp_paxel = os.path.join(tmp, "paxel.py")
    shutil.copy2(paxel_src, tmp_paxel)

    result = subprocess.run(
        [sys.executable, tmp_paxel] + paxel_args,
        cwd=tmp,
        capture_output=True,
        text=True,
    )
    if verbose:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        if not verbose and result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        print(f"  error: paxel.py exited with code {result.returncode} -- nothing to share")
        return None

    summary_path = os.path.join(tmp, "summary.json")
    if not os.path.isfile(summary_path):
        print("  error: paxel.py did not write summary.json -- nothing to share")
        return None

    try:
        with open(summary_path, encoding="utf-8") as fh:
            summary = json.load(fh)
    except Exception as exc:
        print(f"  error: could not read summary.json: {exc}")
        return None

    if resolved_output_dir:
        resolved_output_dir = _copy_artifacts(tmp, resolved_output_dir, file_prefix=file_prefix)

    if not quiet:
        if resolved_output_dir:
            print(f"  Artifacts copied to: {resolved_output_dir}")
            if verbose:
                print(f"  Artifacts kept at: {os.path.abspath(tmp)}")
        elif verbose:
            print(f"  Artifacts kept at: {os.path.abspath(tmp)}")
    return summary


def _summary_is_empty(summary):
    """Return True if the summary has no sessions or no date_range."""
    ctx = summary.get("context", {})
    dr = ctx.get("date_range") or [None, None]
    return ctx.get("total_sessions", 0) == 0 or not dr[0] or not dr[1]


def _stamp_window_months(summary, window_months):
    """Fill in `context.window_months` ONLY when the payload does not already declare it.

    `gnomon/output/summary.py::build_summary` owns this field. It derives the span from
    the bounds the run actually covered, which is a fact about the corpus; `--window=N`
    is only what this wrapper ASKED for, and a payload that echoed the request rather
    than the corpus is exactly how a six-month corpus used to end up pooled with the
    one-month cohort (see gnomon/scoring/replay.py's corpus-scale gate).

    The two writers cannot disagree: `_anchor_window` only ever requests bounds that are
    a whole number of calendar months, and those bounds derive back to exactly the
    `window_months` that produced them (pinned in tests/test_window_flag.py). This stamp
    therefore only ever fires for a summary built by something that does not derive it --
    an older paxel, or a hand-built dict -- and when a payload DOES declare a span, that
    declaration wins. Overwriting it with the request would let the wrapper certify a
    corpus scale it never observed.
    """
    ctx = summary.setdefault("context", {})
    if ctx.get("window_months") is None:
        ctx["window_months"] = window_months
    return summary


def _stamp_force_directive(summary, force):
    """Attach the top-level `force` upload directive to a summary, in place.

    Shape contract with mirdash: /api/gnomon/ingest's `summarySchema` is a
    field-by-field zod whitelist carrying `force: z.boolean().optional()` as a
    TOP-LEVEL key -- a sibling of `context` and `coverage` (which
    gnomon/output/summary.py attaches the same way), NOT nested under
    `context`. A nested copy would be silently dropped by the whitelist. The
    route forwards it to the ingestBuildMetrics mutation, whose
    anti-degradation guard reads `!args.force`; without it the mutation
    rejects any payload a stored row beats on completeness and the route still
    answers HTTP 200, so `--force` fails silently exactly when Claude Code's
    shrinking 30-day retention makes a fresh force upload carry FEWER sessions
    than the stored row.

    Written ONLY when force is true. The field is optional server-side and the
    guard tests falsiness, so an explicit `false` is indistinguishable from an
    absent key -- omitting it keeps every auto/backfill payload byte-identical
    to what shipped before this change (no new key for replay/recompute
    consumers to reason about, no added bytes against _INGEST_MAX_BYTES).
    """
    if force:
        summary["force"] = True
    return summary


def _upload_window(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                   verbose, quiet, output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS,
                   file_prefix="", force=False):
    """Run paxel for one calendar window and upload the summary.

    Returns a ``(result, summary)`` tuple mirroring the sentinel semantics of
    ``_upload_window_web`` so the console loop can distinguish a real success
    from the two failure modes:
      - ``result``: a tagged stored/archive-only response (or a legacy
        reportUrl string) | ``None`` when the window is genuinely empty (a
        normal skip) | ``_PAXEL_ERROR`` if the paxel run failed |
        ``_UPLOAD_ERROR`` if the upload POST failed.
      - ``summary``: the paxel summary dict on a successful upload; ``None``
        otherwise (enables the caller to print ``_format_summary``).

    ``force``: True only when THIS month's plan reason is 'force'; stamps the
    top-level ``force`` upload directive on the payload (see
    ``_stamp_force_directive``).
    """
    window_args = paxel_args_base + [
        f"--since={since}",
        f"--until={_paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]

    if not quiet:
        print(f"  Analysing {label}...")

    summary = _run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir,
                         file_prefix=file_prefix)
    if summary is None:
        print(f"  skip {label} -- paxel error")
        return (_PAXEL_ERROR, None)

    if _summary_is_empty(summary):
        if not quiet:
            print(f"  skip {label} -- no activity")
        return (None, None)

    _stamp_window_months(summary, window_months)
    _stamp_force_directive(summary, force)
    try:
        return (_upload_summary(mirdash_base, token, summary), summary)
    except PayloadTooLarge:
        # A budget violation is a distinct, unswallowable failure -- unlike
        # every other upload error (network/HTTP), it must propagate so the
        # caller can never collapse it into the generic _UPLOAD_ERROR sentinel
        # (which some exit-code paths treat as a normal, ignorable skip).
        raise
    except Exception as exc:
        print(f"  warning: {label} upload failed: {exc}")
        return (_UPLOAD_ERROR, None)


def _upload_window_web(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                       verbose, server, index, total, output_dir=None, quiet=False,
                       window_months=_DEFAULT_WINDOW_MONTHS, file_prefix="", force=False):
    """Run paxel for one calendar window, push SSE events, and upload.

    Returns a tagged stored/archive-only response (or a legacy reportUrl
    string), one of the failure sentinels (`_PAXEL_ERROR` or `_UPLOAD_ERROR`),
    or None when the window is genuinely empty (no activity — a normal skip).

    ``force``: True only when THIS month's plan reason is 'force'; stamps the
    top-level ``force`` upload directive on the payload (see
    ``_stamp_force_directive``).
    """
    window_args = paxel_args_base + [
        f"--since={since}",
        f"--until={_paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]

    server.push_event("analyzing", {"month": label, "label": label, "index": index, "total": total})

    summary = _run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir,
                         file_prefix=file_prefix)
    if summary is None:
        # paxel failed to compute this window — surface it as a failure (red),
        # not a "skip" (which the UI reserves for genuinely empty windows).
        server.push_event("error_msg", {"month": label, "label": label, "message": "paxel error"})
        return _PAXEL_ERROR

    if _summary_is_empty(summary):
        server.push_event("skipped", {"month": label, "label": label, "reason": "no activity"})
        return None

    _stamp_window_months(summary, window_months)
    _stamp_force_directive(summary, force)
    server.push_event("uploading", {"month": label, "label": label, "index": index, "total": total})

    try:
        result = _upload_summary(mirdash_base, token, summary)
        event = "guarded" if _is_archived_only(result) else "uploaded"
        server.push_event(event, {"month": label, "label": label, "index": index, "total": total})
        return result
    except PayloadTooLarge as exc:
        # The browser sees the reason (naming the byte size) via the SSE event,
        # AND the exception still propagates -- unlike every other upload
        # failure, a budget violation must not collapse into _UPLOAD_ERROR.
        server.push_event("error_msg", {"month": label, "label": label, "message": str(exc)})
        raise
    except Exception as exc:
        server.push_event("error_msg", {"month": label, "label": label, "message": str(exc)})
        return _UPLOAD_ERROR
