import calendar
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse


_COPIED_OUTPUTS = (
    "summary.json",
    "stats.json",
    "report.md",
    "profile.html",
    "narrative_input.md",
)


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
    return "https://mirdash.xmartlabs.com"


# Maximum batch size supported by the mirdash auth endpoint.
_MAX_BACKFILL = 12

# Default window size when --window is absent.
_DEFAULT_WINDOW_MONTHS = 6

# Sentinels returned by the web upload helper so callers can tell a real reportUrl
# apart from the two distinct failure modes (paxel run failed vs. upload POST failed).
_PAXEL_ERROR = "PAXEL_ERROR"
_UPLOAD_ERROR = "UPLOAD_ERROR"


def _is_report_url(value):
    """True only for a real reportUrl — not None and not a failure sentinel."""
    return value is not None and value not in (_PAXEL_ERROR, _UPLOAD_ERROR)


def _upload_summary(mirdash_base, token, summary):
    """POST summary dict to mirdash /api/gnomon/ingest.

    Returns the reportUrl string from the JSON response, or raises on error.
    Token is never logged.
    """
    import urllib.error
    import urllib.request
    body = json.dumps(summary, default=str).encode("utf-8")
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
        return data["reportUrl"]
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
    lines.append(f"\n  Your build profile  ·  {sessions} sessions  ·  {start}→{end}")

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


def _copy_artifacts(src_dir, output_dir):
    """Copy final paxel outputs into output_dir, overwriting existing files."""
    dst_dir = os.path.abspath(os.path.expanduser(output_dir))
    os.makedirs(dst_dir, exist_ok=True)
    for name in _COPIED_OUTPUTS:
        src = os.path.join(src_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst_dir, name))
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
                f" — using default {_DEFAULT_WINDOW_MONTHS}",
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
                    f" — using default {_DEFAULT_WINDOW_MONTHS}",
                    file=sys.stderr,
                )
                return _DEFAULT_WINDOW_MONTHS
            if n < 1:
                print(
                    f"  warning: --window={n} must be >= 1"
                    f" — using default {_DEFAULT_WINDOW_MONTHS}",
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
      --init              → ('init', 12)
      --backfill[=N]      → ('backfill', N)
      neither             → ('current', 1)
    """
    if "--init" in argv:
        return ("init", 12)
    n = parse_backfill(argv)
    if n is not None:
        return ("backfill", n)
    return ("current", 1)


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

        # Compute the start month (window_months - 1) months before the anchor
        start_total_months = anchor_total_months - (window_months - 1)
        start_year = start_total_months // 12
        start_month = start_total_months % 12 + 1  # 1-based

        since = datetime.date(start_year, start_month, 1)
        # until = first day of the month after the anchor
        _, last_day = calendar.monthrange(anchor_year, anchor_month)
        until = datetime.date(anchor_year, anchor_month, 1) + datetime.timedelta(days=last_day)
        windows.append((since.isoformat(), until.isoformat(), f"{anchor_year:04d}-{anchor_month:02d}"))
    return windows


def _paxel_until_arg(exclusive_until_iso):
    """Translate an exclusive month-window bound to paxel's inclusive --until date."""
    return (datetime.date.fromisoformat(exclusive_until_iso) - datetime.timedelta(days=1)).isoformat()


def _run_paxel(paxel_src, paxel_args, verbose, quiet=False, output_dir=None):
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
        print(f"  error: paxel.py exited with code {result.returncode} — nothing to share")
        return None

    summary_path = os.path.join(tmp, "summary.json")
    if not os.path.isfile(summary_path):
        print("  error: paxel.py did not write summary.json — nothing to share")
        return None

    try:
        with open(summary_path, encoding="utf-8") as fh:
            summary = json.load(fh)
    except Exception as exc:
        print(f"  error: could not read summary.json: {exc}")
        return None

    if resolved_output_dir:
        resolved_output_dir = _copy_artifacts(tmp, resolved_output_dir)

    if not quiet:
        if resolved_output_dir:
            print(f"  Artifacts copied to: {resolved_output_dir}")
            if verbose:
                print(f"  Artifacts kept at: {os.path.abspath(tmp)}")
        else:
            print(f"  Artifacts kept at: {os.path.abspath(tmp)}")
    return summary


def _summary_is_empty(summary):
    """Return True if the summary has no sessions or no date_range."""
    ctx = summary.get("context", {})
    dr = ctx.get("date_range") or [None, None]
    return ctx.get("total_sessions", 0) == 0 or not dr[0] or not dr[1]


def _upload_window(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                   verbose, quiet, output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS):
    """Run paxel for one calendar window and upload the summary.

    Returns the reportUrl string on success, or None if the window should be
    skipped (empty summary or paxel error).  Upload errors are printed as
    warnings but do not raise.
    """
    window_args = paxel_args_base + [
        f"--since={since}",
        f"--until={_paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]

    if not quiet:
        print(f"  Analysing {label}…")

    summary = _run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir)
    if summary is None:
        print(f"  skip {label} — paxel error")
        return None

    if _summary_is_empty(summary):
        if not quiet:
            print(f"  skip {label} — no activity")
        return None

    summary.setdefault("context", {})["window_months"] = window_months
    try:
        return _upload_summary(mirdash_base, token, summary)
    except Exception as exc:
        print(f"  warning: {label} upload failed: {exc}")
        return None


def _upload_window_web(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                       verbose, server, index, total, output_dir=None, quiet=False,
                       window_months=_DEFAULT_WINDOW_MONTHS):
    """Run paxel for one calendar window, push SSE events, and upload.

    Returns the reportUrl string on success, or one of the failure sentinels:
    `_PAXEL_ERROR` (paxel run failed), `_UPLOAD_ERROR` (upload POST failed), or
    None when the window is genuinely empty (no activity — a normal skip).
    """
    window_args = paxel_args_base + [
        f"--since={since}",
        f"--until={_paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]

    server.push_event("analyzing", {"month": label, "label": label, "index": index, "total": total})

    summary = _run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir)
    if summary is None:
        # paxel failed to compute this window — surface it as a failure (red),
        # not a "skip" (which the UI reserves for genuinely empty windows).
        server.push_event("error_msg", {"month": label, "label": label, "message": "paxel error"})
        return _PAXEL_ERROR

    if _summary_is_empty(summary):
        server.push_event("skipped", {"month": label, "label": label, "reason": "no activity"})
        return None

    summary.setdefault("context", {})["window_months"] = window_months
    server.push_event("uploading", {"month": label, "label": label, "index": index, "total": total})

    try:
        report_url = _upload_summary(mirdash_base, token, summary)
        server.push_event("uploaded", {"month": label, "label": label, "index": index, "total": total})
        return report_url
    except Exception as exc:
        server.push_event("error_msg", {"month": label, "label": label, "message": str(exc)})
        return _UPLOAD_ERROR
