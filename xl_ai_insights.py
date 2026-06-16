#!/usr/bin/env python3
"""
xl-ai-insights: analyze your local paxel builder profile with mirdash.

Runs paxel.py locally (bundled alongside this module) to compute your builder
metrics, then authenticates with mirdash via a one-time browser login and
sends summary.json so mirdash can analyze your profile and surface
AI-powered tips.

Nothing from your transcripts, prompts, or project names is ever sent — only
the measured metrics paxel already computes (see docs/metrics-evaluation.md).

Usage:
    xl-ai-insights [source ...] [--mirdash-base=URL] [--no-open] [--quiet] [--verbose] [--console] [--keep-artifacts]

    source        e.g. claude, codex, gemini — same as paxel.py (default: all)
    --mirdash-base=URL  override the mirdash server URL
    --no-open     skip redirecting to the mirdash report at the end
    --quiet       only print errors and the final report URL
    --verbose     also show paxel's full stdout/stderr
    --console     show progress in the terminal instead of the browser
    --keep-artifacts
                  keep paxel's temporary output directory for debugging

No dependencies beyond the Python 3 standard library.
"""

import calendar
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import webbrowser

# How long _capture_cli_token waits for the browser auth callback before giving up.
_SHARE_AUTH_TIMEOUT = 120

# ---------------------------------------------------------------------------
# Config / URL resolution helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Backfill helpers (pure — no I/O)
# ---------------------------------------------------------------------------

# Maximum batch size supported by the mirdash auth endpoint.
_MAX_BACKFILL = 12


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


def month_windows(n, today):
    """Return a list of (since_iso, until_iso, label) for the last *n* calendar months.

    Oldest month first; the last entry is the current (possibly partial) month.
    *today* is a datetime.date; the function never calls datetime.now() itself.

    since = YYYY-MM-01 (inclusive)
    until = first day of the NEXT month (exclusive)
    label = 'YYYY-MM'
    """
    windows = []
    # Work backwards: month index 0 = current month, 1 = previous, …
    for i in range(n - 1, -1, -1):
        # Subtract i months from today's year/month
        total_months = today.year * 12 + (today.month - 1) - i
        year = total_months // 12
        month = total_months % 12 + 1  # 1-based
        since = datetime.date(year, month, 1)
        # until = first day of the next month
        _, last_day = calendar.monthrange(year, month)
        until = since + datetime.timedelta(days=last_day)
        windows.append((since.isoformat(), until.isoformat(), f"{year:04d}-{month:02d}"))
    return windows


def _paxel_until_arg(exclusive_until_iso):
    """Translate an exclusive month-window bound to paxel's inclusive --until date."""
    return (datetime.date.fromisoformat(exclusive_until_iso) - datetime.timedelta(days=1)).isoformat()


def _tokens_from_query(parsed_qs):
    """Extract a list of tokens from a parse_qs result dict.

    Looks for 'tokens' first (JSON array); falls back to single 'token'.
    Returns [] if neither is present.  Never raises.
    """
    # Try the batch key first
    raw_tokens = (parsed_qs.get("tokens") or [""])[0]
    if raw_tokens:
        try:
            tokens = json.loads(raw_tokens)
            if isinstance(tokens, list) and tokens:
                return [str(t) for t in tokens]
        except Exception:
            pass  # malformed JSON — fall through to single-token path

    # Fall back to single token
    token = (parsed_qs.get("token") or [""])[0]
    if token:
        return [token]
    return []


# ---------------------------------------------------------------------------
# One-shot localhost auth callback server
# ---------------------------------------------------------------------------

_SUCCESS_PAGE = b"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>xl-ai-insights \xe2\x80\x94 authenticated</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Outfit:wght@400;500;600&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  :root{
    --bg-base:#1a1f27; --bg-surface:#222831; --bg-elev:#2a3038;
    --text-primary:#f0f0f0; --text-secondary:#c7cacf; --text-muted:#85888f;
    --border:rgba(255,255,255,.078); --accent:#ee1a64; --purple:#5d5fee;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{
    background:var(--bg-base);color:var(--text-primary);
    font-family:'Outfit',system-ui,sans-serif;min-height:100vh;
    display:flex;align-items:center;justify-content:center;
    position:relative;overflow:hidden;
  }
  body::before{content:"";position:absolute;top:-30%;right:-10%;width:60vw;height:60vw;
    border-radius:50%;background:radial-gradient(circle,rgba(238,26,100,.16),transparent 60%);
    filter:blur(40px);pointer-events:none}
  body::after{content:"";position:absolute;bottom:-30%;left:-10%;width:55vw;height:55vw;
    border-radius:50%;background:radial-gradient(circle,rgba(93,95,238,.14),transparent 60%);
    filter:blur(40px);pointer-events:none}
  .card{position:relative;z-index:1;width:100%;max-width:460px;margin:24px;
    background:var(--bg-surface);border:1px solid var(--border);border-radius:20px;
    padding:44px 40px;box-shadow:0 2px 8px rgba(0,0,0,.24),0 18px 42px rgba(0,0,0,.28);
    text-align:center}
  .brand{display:flex;align-items:center;justify-content:center;gap:9px;
    font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:15px;
    letter-spacing:-.01em;color:var(--text-secondary);margin-bottom:30px}
  .brand .dot{width:9px;height:9px;border-radius:50%;
    background:linear-gradient(135deg,var(--accent),var(--purple))}
  .check{width:64px;height:64px;border-radius:50%;margin:0 auto 22px;
    display:flex;align-items:center;justify-content:center;
    background:rgba(238,26,100,.12);border:1px solid rgba(238,26,100,.25);
    box-shadow:0 0 0 6px rgba(238,26,100,.05)}
  .check svg{width:30px;height:30px;stroke:var(--accent);stroke-width:2.5;fill:none;
    stroke-linecap:round;stroke-linejoin:round}
  h1{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:26px;
    letter-spacing:-.02em;margin-bottom:12px}
  p.sub{font-size:14.5px;line-height:1.55;color:var(--text-secondary);margin-bottom:26px}
  .term{display:flex;align-items:center;justify-content:center;gap:10px;
    background:var(--bg-elev);border:1px solid var(--border);border-radius:12px;
    padding:13px 16px;font-size:13px;color:var(--text-secondary);
    font-family:'JetBrains Mono',monospace}
  .term svg{width:15px;height:15px;stroke:var(--purple);stroke-width:2;fill:none;
    stroke-linecap:round;stroke-linejoin:round;flex:none}
  .foot{margin-top:22px;font-size:12px;color:var(--text-muted)}
  .foot b{color:var(--text-secondary);font-weight:600}
</style>
</head>
<body>
  <div class="card">
    <div class="brand"><span class="dot"></span> xl-ai-insights \xc2\xb7 mirdash</div>
    <div class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></div>
    <h1>You\xe2\x80\x99re authenticated</h1>
    <p class="sub">Signed in with your XL account. Close this tab and head back to your terminal \xe2\x80\x94 it\xe2\x80\x99s computing your build profile and sharing it now.</p>
    <div class="term"><svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg> Return to your terminal</div>
    <div class="foot">Only summary.json is uploaded \xc2\xb7 <b>your transcripts never leave your machine</b></div>
  </div>
</body>
</html>
"""


def _capture_cli_token(port=8799, timeout=_SHARE_AUTH_TIMEOUT):
    """Start a one-shot HTTP server on 127.0.0.1:<port>.

    Waits up to *timeout* seconds for a single GET /callback?token=<JWT>
    (and optionally tokens=<url-encoded JSON array>).

    Returns a list of token strings on success (at least one element), or None
    on timeout or error.  The server binds only to loopback and suppresses all
    access-log output.
    """
    import http.server

    captured = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            tokens = _tokens_from_query(params)
            if parsed.path == "/callback" and tokens:
                captured["tokens"] = tokens
                body = _SUCCESS_PAGE
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args):  # noqa: suppress access log
            pass

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
        server.timeout = 1  # poll interval for the outer loop
    except OSError as exc:
        print(f"  warning: could not bind localhost:{port} for auth callback: {exc}")
        return None

    deadline = time.time() + timeout
    try:
        while "tokens" not in captured:
            if time.time() > deadline:
                print(f"  warning: timed out waiting for auth callback after {timeout}s")
                return None
            server.handle_request()
    finally:
        server.server_close()

    return captured.get("tokens")


_ORIGINAL_CAPTURE_CLI_TOKEN = _capture_cli_token


def _wait_for_auth_tokens(server, port):
    """Prefer progress-server auth, but keep legacy token mocks usable in tests."""
    if _capture_cli_token is not _ORIGINAL_CAPTURE_CLI_TOKEN:
        return _capture_cli_token(port=port, timeout=_SHARE_AUTH_TIMEOUT)
    return server.wait_for_auth(timeout=_SHARE_AUTH_TIMEOUT)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Summary formatter
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _run_paxel(paxel_src, paxel_args, verbose, keep_artifacts=False):
    """Run paxel.py in a temp directory and return the parsed summary dict.

    Returns the summary dict on success, or None on failure (errors already printed).
    """
    temp_context = None
    if keep_artifacts:
        tmp = tempfile.mkdtemp(prefix="xl-ai-insights-")
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="xl-ai-insights-")
        tmp = temp_context.name

    try:
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
                return json.load(fh)
        except Exception as exc:
            print(f"  error: could not read summary.json: {exc}")
            return None
    finally:
        if keep_artifacts:
            print(f"  Artifacts kept at: {os.path.abspath(tmp)}")
        elif temp_context is not None:
            temp_context.cleanup()


def _summary_is_empty(summary):
    """Return True if the summary has no sessions or no date_range."""
    ctx = summary.get("context", {})
    dr = ctx.get("date_range") or [None, None]
    return ctx.get("total_sessions", 0) == 0 or not dr[0] or not dr[1]


def _upload_window(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                   verbose, quiet, keep_artifacts=False):
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

    summary = _run_paxel(paxel_src, window_args, verbose, keep_artifacts=keep_artifacts)
    if summary is None:
        print(f"  skip {label} — paxel error")
        return None

    if _summary_is_empty(summary):
        if not quiet:
            print(f"  skip {label} — no activity")
        return None

    try:
        return _upload_summary(mirdash_base, token, summary)
    except Exception as exc:
        print(f"  warning: {label} upload failed: {exc}")
        return None


def _upload_window_web(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                       verbose, server, index, total, keep_artifacts=False):
    """Run paxel for one calendar window, push SSE events, and upload.

    Returns the reportUrl string on success, or None if skipped/error.
    """
    window_args = paxel_args_base + [
        f"--since={since}",
        f"--until={_paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]

    server.push_event("analyzing", {"month": label, "label": label, "index": index, "total": total})

    summary = _run_paxel(paxel_src, window_args, verbose, keep_artifacts=keep_artifacts)
    if summary is None:
        server.push_event("skipped", {"month": label, "label": label, "reason": "paxel error"})
        return None

    if _summary_is_empty(summary):
        server.push_event("skipped", {"month": label, "label": label, "reason": "no activity"})
        return None

    server.push_event("uploading", {"month": label, "label": label, "index": index, "total": total})

    try:
        report_url = _upload_summary(mirdash_base, token, summary)
        server.push_event("uploaded", {"month": label, "label": label, "index": index, "total": total})
        return report_url
    except Exception as exc:
        server.push_event("error_msg", {"month": label, "label": label, "message": str(exc)})
        return "UPLOAD_ERROR"


def _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
              keep_artifacts=False):
    """Web progress mode: auth + progress in browser, minimal console output."""
    from progress_server import ProgressServer

    port = 8799
    try:
        server = ProgressServer(port=port)
    except OSError as exc:
        print(f"  warning: could not bind localhost:{port} ({exc}) — falling back to console mode")
        _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                      keep_artifacts=keep_artifacts)
        return

    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    if not quiet:
        print(f"\n  → See progress at {server.url}")

    try:
        opened = webbrowser.open(auth_url)
    except Exception as exc:
        print(f"  warning: could not open a browser ({exc}) — nothing was analysed or shared.")
        server.shutdown(delay=0)
        sys.exit(0)
    if not opened:
        print("  warning: no browser available (headless/CI) — nothing was analysed or shared.")
        server.shutdown(delay=0)
        sys.exit(0)

    tokens = _wait_for_auth_tokens(server, port)
    if not tokens:
        print("  Authentication cancelled or timed out — nothing was analysed or shared.")
        server.shutdown(delay=0)
        sys.exit(0)

    paxel_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paxel.py")
    if not os.path.isfile(paxel_src):
        print(f"  error: paxel.py not found at {paxel_src}")
        server.shutdown(delay=0)
        sys.exit(1)

    today = datetime.date.today()

    if mode in ("init", "backfill"):
        windows = month_windows(token_count, today)
        month_labels = [label for _, _, label in windows]
    else:
        month_labels = [month_windows(1, today)[0][2]]

    server.push_event("auth_ok", {
        "message": "Authenticated",
        "mirdashBase": mirdash_base,
        "months": month_labels,
    })

    if mode in ("init", "backfill"):
        token_idx = 0
        uploaded = 0
        last_report_url = None

        for i, (since, until, label) in enumerate(windows):
            if token_idx >= len(tokens):
                break
            report_url = _upload_window_web(
                mirdash_base, tokens[token_idx], paxel_src,
                paxel_forward, since, until, label, verbose, server, i, len(windows),
                keep_artifacts=keep_artifacts,
            )
            if report_url is not None and report_url != "UPLOAD_ERROR":
                last_report_url = report_url
                uploaded += 1
                token_idx += 1

        server.push_event("done", {
            "reportUrl": last_report_url or "",
            "mirdashBase": mirdash_base,
            "uploaded": uploaded,
            "total": len(windows),
            "noOpen": no_open,
        })

        if last_report_url:
            full_report = urllib.parse.urljoin(mirdash_base + "/", last_report_url)
            if not quiet:
                print(f"  ✓ {uploaded}/{len(windows)} months uploaded")
            print(f"  Report ready: {full_report}")

        server.shutdown()
        return

    # --- Default: current month ---
    since, until, label = month_windows(1, today)[0]

    report_url = _upload_window_web(
        mirdash_base, tokens[0], paxel_src,
        paxel_forward, since, until, label, verbose, server, 0, 1,
        keep_artifacts=keep_artifacts,
    )

    if report_url == "UPLOAD_ERROR":
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "total": 1, "noOpen": True,
                                    "mirdashBase": mirdash_base})
        print(f"  error: upload failed for {label}")
        server.shutdown()
        return

    if report_url is not None:
        server.push_event("done", {
            "reportUrl": report_url,
            "mirdashBase": mirdash_base,
            "uploaded": 1,
            "total": 1,
            "noOpen": no_open,
        })
        full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
        print(f"  ✓ {label} uploaded → {full_report}")
        server.shutdown()
        return

    # Fallback: current month empty — find most recent month with data
    all_time_args = paxel_forward + ["--summary", "--no-open"]
    all_time_summary = _run_paxel(paxel_src, all_time_args, verbose, keep_artifacts=keep_artifacts)

    if all_time_summary is None or _summary_is_empty(all_time_summary):
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "total": 1, "noOpen": True})
        print("  nothing to share (no sessions found)")
        server.shutdown()
        sys.exit(0)

    progression = all_time_summary.get("progression_monthly") or []
    fallback_month = latest_month_with_data(progression)

    if not fallback_month:
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "total": 1, "noOpen": True})
        print("  nothing to share (no sessions found)")
        server.shutdown()
        sys.exit(0)

    fallback_year, fallback_mo = int(fallback_month[:4]), int(fallback_month[5:7])
    fallback_date = datetime.date(fallback_year, fallback_mo, 1)
    fb_since, fb_until, fb_label = month_windows(1, fallback_date)[0]

    report_url = _upload_window_web(
        mirdash_base, tokens[0], paxel_src,
        paxel_forward, fb_since, fb_until, fb_label, verbose, server, 0, 1,
        keep_artifacts=keep_artifacts,
    )

    if report_url is not None:
        full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
        server.push_event("done", {
            "reportUrl": report_url,
            "mirdashBase": mirdash_base,
            "uploaded": 1,
            "total": 1,
            "noOpen": no_open,
        })
        print(f"  ✓ {fb_label} uploaded → {full_report}")
    else:
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "total": 1, "noOpen": True})
        print("  nothing to share (no sessions found)")

    server.shutdown()


def _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                  keep_artifacts=False):
    """Console mode: original behavior with full terminal output."""
    port = 8799
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    if not quiet:
        print(f"\n  Opening mirdash for authentication… (close the browser or wait {_SHARE_AUTH_TIMEOUT}s to skip)")

    try:
        opened = webbrowser.open(auth_url)
    except Exception as exc:
        print(f"  warning: could not open a browser for auth ({exc}) — nothing was analysed or shared.")
        sys.exit(0)
    if not opened:
        print("  warning: no browser available (headless/CI) — nothing was analysed or shared.")
        sys.exit(0)

    tokens = _capture_cli_token(port=port, timeout=_SHARE_AUTH_TIMEOUT)
    if not tokens:
        print("  Authentication cancelled or timed out — nothing was analysed or shared.")
        sys.exit(0)

    paxel_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paxel.py")
    if not os.path.isfile(paxel_src):
        print(f"  error: paxel.py not found at {paxel_src}")
        sys.exit(1)

    today = datetime.date.today()

    if mode in ("init", "backfill"):
        n_months = token_count
        windows = month_windows(n_months, today)

        token_idx = 0
        uploaded = 0
        last_report_url = None

        for since, until, label in windows:
            if token_idx >= len(tokens):
                print("  warning: ran out of tokens before all months were uploaded — stopping")
                break

            report_url = _upload_window(
                mirdash_base, tokens[token_idx], paxel_src,
                paxel_forward, since, until, label, verbose, quiet,
                keep_artifacts=keep_artifacts,
            )
            if report_url is not None:
                last_report_url = report_url
                uploaded += 1
                token_idx += 1
                if not quiet:
                    print(f"  ↑ {label} uploaded")

        verb = "initialised" if mode == "init" else "backfilled"
        if not quiet:
            print(f"  {verb} {uploaded}/{len(windows)} months")

        if last_report_url:
            full_report = urllib.parse.urljoin(mirdash_base + "/", last_report_url)
            print(f"  Report ready: {full_report}")
            if not no_open:
                try:
                    webbrowser.open(full_report)
                except Exception as exc:
                    print(f"  warning: could not open report in browser: {exc}")
        return

    since, until, label = month_windows(1, today)[0]

    if not quiet:
        print(f"  Computing your build profile for {label}…")

    window_args = paxel_forward + [
        f"--since={since}",
        f"--until={_paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]
    summary = _run_paxel(paxel_src, window_args, verbose, keep_artifacts=keep_artifacts)

    if summary is not None and not _summary_is_empty(summary):
        if not quiet:
            print("  Uploading metrics summary to mirdash…")
        try:
            report_url = _upload_summary(mirdash_base, tokens[0], summary)
        except Exception as exc:
            print(f"  warning: {exc}")
            return

        full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
        formatted = _format_summary(summary, quiet=quiet)
        if formatted:
            print(formatted)
        print(f"  Report ready: {full_report}")
        if not no_open:
            try:
                webbrowser.open(full_report)
            except Exception as exc:
                print(f"  warning: could not open report in browser: {exc}")
        return

    if not quiet:
        print(f"  No activity in {label} yet — checking for most recent month with data…")

    all_time_args = paxel_forward + ["--summary", "--no-open"]
    all_time_summary = _run_paxel(paxel_src, all_time_args, verbose, keep_artifacts=keep_artifacts)

    if all_time_summary is None or _summary_is_empty(all_time_summary):
        print("  nothing to share (no sessions found)")
        sys.exit(0)

    progression = all_time_summary.get("progression_monthly") or []
    fallback_month = latest_month_with_data(progression)

    if not fallback_month:
        print("  nothing to share (no sessions found)")
        sys.exit(0)

    fallback_year, fallback_mo = int(fallback_month[:4]), int(fallback_month[5:7])
    fallback_date = datetime.date(fallback_year, fallback_mo, 1)
    fb_since, fb_until, fb_label = month_windows(1, fallback_date)[0]

    if not quiet:
        print(f"  Uploading most recent month with data: {fb_label}…")

    fb_args = paxel_forward + [
        f"--since={fb_since}",
        f"--until={_paxel_until_arg(fb_until)}",
        "--summary",
        "--no-open",
    ]
    fb_summary = _run_paxel(paxel_src, fb_args, verbose, keep_artifacts=keep_artifacts)

    if fb_summary is None or _summary_is_empty(fb_summary):
        print("  nothing to share (no sessions found)")
        sys.exit(0)

    if not quiet:
        print("  Uploading metrics summary to mirdash…")
    try:
        report_url = _upload_summary(mirdash_base, tokens[0], fb_summary)
    except Exception as exc:
        print(f"  warning: {exc}")
        return

    full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
    formatted = _format_summary(fb_summary, quiet=quiet)
    if formatted:
        print(formatted)
    print(f"  Report ready: {full_report}")
    if not no_open:
        try:
            webbrowser.open(full_report)
        except Exception as exc:
            print(f"  warning: could not open report in browser: {exc}")


def main():
    """Authenticate first, then run paxel locally and upload the summary to mirdash."""
    argv = sys.argv[1:]

    # Flags consumed by this wrapper (not forwarded to paxel)
    wrapper_flags = {"--no-open", "--quiet", "--verbose", "--console", "--keep-artifacts"}
    no_open = "--no-open" in argv
    quiet = "--quiet" in argv
    verbose = "--verbose" in argv
    console = "--console" in argv
    keep_artifacts = "--keep-artifacts" in argv

    # Determine operating mode
    mode, token_count = decide_mode(argv)

    # Flags appended literally below — strip from user passthrough to avoid duplicates
    paxel_literal_flags = {"--summary", "--no-open"}

    # Build paxel args: strip wrapper-only flags, literal flags, backfill/init flags,
    # and mirdash overrides; keep source names and dir overrides
    paxel_forward = [
        a for a in argv
        if a not in wrapper_flags
        and a not in paxel_literal_flags
        and not re.match(r"--mirdash-base=", a)
        and not re.match(r"--backfill(=.*)?$", a)
        and a != "--init"
    ]

    mirdash_base = _resolve_mirdash_base(argv)

    if console:
        _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                      keep_artifacts)
    else:
        _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                  keep_artifacts)


if __name__ == "__main__":
    main()
