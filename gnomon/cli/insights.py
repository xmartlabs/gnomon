"""CLI entry point for xl-ai-insights (auth + upload wrapper around local analysis)."""

import datetime
import importlib.metadata
import os
import re
import sys
import urllib.parse
import urllib.request
import webbrowser
from itertools import zip_longest
from concurrent.futures import ThreadPoolExecutor, as_completed

from gnomon.upload.auth import _capture_cli_token, _wait_for_auth_tokens, _SHARE_AUTH_TIMEOUT, _WEB_AUTH_TIMEOUT
from gnomon.upload.mirdash import (
    _resolve_mirdash_base, _resolve_output_dir, _absolutize_dir_flags,
    _DEFAULT_WINDOW_MONTHS, _UPLOAD_CONCURRENCY, parse_window, decide_mode,
    month_windows, months_to_upload, plan_upload, windows_for_anchors,
    _is_report_url, _upload_window, _upload_window_web,
    _PAXEL_ERROR, _UPLOAD_ERROR, _format_summary,
    # Re-exported so tests can patch them as attributes of this module and so the
    # web fallback to console mode keeps a stable surface.
    _run_paxel, _upload_summary,  # noqa: F401
)


_HELP_TEXT = """Usage:
    xl-ai-insights [source ...] [--local] [--allow-stale-cli] [--mirdash-base=URL] [--window=N] [--no-open] [--quiet] [--verbose] [--console] [--output-dir=PATH]
    xl-ai-insights --force
    xl-ai-insights --dry-run
    xl-ai-insights --help
    xl-ai-insights -h

    source        e.g. claude, codex, gemini -- same as paxel.py (default: all)
    --local       run local analysis only (no login, no upload)
    --allow-stale-cli
                  continue network/upload flows after a confirmed stale CLI warning
    --force       re-upload all months (ignores what has already been uploaded)
    --dry-run     show what would be uploaded (and why) without uploading anything
    --mirdash-base=URL  override the mirdash server URL
    --window=N    trailing window size in months for each scored point (default 6)
    --no-open     skip redirecting to the mirdash report at the end
    --quiet       only print errors and the final report URL
    --verbose     also show paxel's full stdout/stderr
    --console     show progress in the terminal instead of the browser
    --tools       print per-session tool usage (self-check + rate calibration)
    --output-dir=PATH
                  copy final artifacts into PATH (use . for current directory)

    Without flags, xl-ai-insights auto-detects which months are missing and
    uploads only what is needed (first run uploads everything automatically).
"""

_LATEST_CLI_RELEASE_URL = "https://raw.githubusercontent.com/xmartlabs/gnomon/latest/pyproject.toml"
_CLI_REFRESH_COMMAND = "uvx --refresh --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights"
_ALLOW_STALE_CLI_FLAG = "--allow-stale-cli"


_REASON_LABELS = {
    "force":   "force re-upload",
    "initial": "no prior uploads",
    "current": "current month",
    "gap":     "missing on server",
    "refresh": "refresh (server snapshot predates month end)",
    "backfill": "backfill",
}


def _release_result(status, current=None, latest=None, reason=None):
    return {"status": status, "current": current, "latest": latest, "reason": reason}


def _plain_numeric_release(version):
    if not isinstance(version, str) or not re.match(r"^\d+(?:\.\d+)*$", version):
        return None
    return tuple(int(part) for part in version.split("."))


def _compare_plain_numeric_release(current, latest):
    current_parts = _plain_numeric_release(current)
    latest_parts = _plain_numeric_release(latest)
    if current_parts is None or latest_parts is None:
        return None
    for current_part, latest_part in zip_longest(current_parts, latest_parts, fillvalue=0):
        if current_part < latest_part:
            return -1
        if current_part > latest_part:
            return 1
    return 0


def _parse_project_version(pyproject_text):
    in_project = False
    for line in pyproject_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = re.match(r'''version\s*=\s*["']([^"']+)["']''', stripped)
            if match:
                return match.group(1)
    return None


def _check_latest_cli_release(timeout=1.5):
    try:
        current = importlib.metadata.version("xl-ai-insights")
    except Exception as exc:
        return _release_result("unknown", reason=f"current-version:{exc.__class__.__name__}")

    if _plain_numeric_release(current) is None:
        return _release_result("unknown", current=current, reason="current-version-not-plain-numeric")

    try:
        with urllib.request.urlopen(_LATEST_CLI_RELEASE_URL, timeout=timeout) as response:
            latest_text = response.read().decode("utf-8")
    except Exception as exc:
        return _release_result("unknown", current=current, reason=f"latest-fetch:{exc.__class__.__name__}")

    latest = _parse_project_version(latest_text)
    if not latest:
        return _release_result("unknown", current=current, reason="latest-version-missing")

    comparison = _compare_plain_numeric_release(current, latest)
    if comparison is None:
        return _release_result("unknown", current=current, latest=latest, reason="ambiguous-version")
    if comparison != 0:
        return _release_result("mismatch", current=current, latest=latest)
    return _release_result("current", current=current, latest=latest)


def _enforce_cli_freshness(allow_stale: bool):
    release = _check_latest_cli_release()
    if release.get("status") != "mismatch":
        return

    print(
        "  warning: this xl-ai-insights CLI is not the published latest release "
        f"(installed {release.get('current')}, published latest {release.get('latest')})."
    )
    print(f"  Refresh with: {_CLI_REFRESH_COMMAND}")
    if allow_stale:
        print("  Continuing because --allow-stale-cli was provided.")
        return
    print("  Aborting before auth/upload. Re-run with --allow-stale-cli to override.")
    raise SystemExit(1)


def _print_dry_run_plan(mode, windows, plan_pairs):
    """Print the dry-run plan to stdout.

    windows:    list of (since, until, label) — used to count total months
    plan_pairs: list of (monthKey, reason) or list of monthKey strings (backfill)
    """
    print("  Dry run -- no uploads, no tokens consumed.")
    print(f"  Mode: {mode}")
    print(f"  Would analyze and upload {len(windows)} month(s):")
    if plan_pairs and isinstance(plan_pairs[0], tuple):
        for label, reason in plan_pairs:
            readable = _REASON_LABELS.get(reason, reason)
            print(f"    {label}  {readable}")
    else:
        # backfill: plain list of labels
        for label in plan_pairs:
            print(f"    {label}  {_REASON_LABELS['backfill']}")
    print("  (empty months are skipped automatically on a real run)")


def _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
              output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS, *, dry_run=False):
    """Web progress mode: auth + progress in browser, minimal console output."""
    from gnomon.upload.progress_server import ProgressServer

    port = 8799
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    try:
        server = ProgressServer(port=port, auth_url=auth_url)
    except OSError as exc:
        print(f"  warning: could not bind localhost:{port} ({exc}) -- falling back to console mode")
        _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                      output_dir=output_dir, window_months=window_months, dry_run=dry_run)
        return

    if not quiet:
        print(f"\n  -> See progress at {server.url}")

    try:
        opened = webbrowser.open(auth_url)
    except Exception as exc:
        print(f"  warning: could not open a browser ({exc}) -- nothing was analysed or shared.")
        server.shutdown(delay=0)
        sys.exit(0)
    if not opened:
        print("  warning: no browser available (headless/CI) -- nothing was analysed or shared.")
        server.shutdown(delay=0)
        sys.exit(0)

    tokens = _wait_for_auth_tokens(server, port)
    uploaded = server.uploaded  # consumed in auto-mode (G4)
    if not tokens:
        print("  Authentication cancelled or timed out -- nothing was analysed or shared.")
        # Tell any open progress page the truth instead of leaving it spinning.
        server.push_event("auth_timeout", {})
        server.shutdown(delay=1.0)
        sys.exit(0)

    paxel_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "paxel.py")
    paxel_src = os.path.normpath(paxel_src)
    if not os.path.isfile(paxel_src):
        print(f"  error: paxel.py not found at {paxel_src}")
        server.shutdown(delay=0)
        sys.exit(1)

    today = datetime.date.today()

    # Decide which month windows to upload. auto/force run through the
    # detection helpers; backfill keeps the explicit trailing-N window list.
    if mode == "backfill":
        windows = month_windows(token_count, today, window_months=window_months)
    else:  # auto or force
        anchors = months_to_upload(today, uploaded, force=(mode == "force"))
        windows = windows_for_anchors(anchors, window_months=window_months)

    month_labels = [label for _, _, label in windows]

    if dry_run:
        if mode == "backfill":
            plan_pairs = [label for _, _, label in windows]
        else:
            plan_pairs = plan_upload(today, uploaded, force=(mode == "force"))
        _print_dry_run_plan(mode, windows, plan_pairs)
        server.push_event("done", {
            "reportUrl": "",
            "mirdashBase": mirdash_base,
            "uploaded": 0,
            "failed": 0,
            "total": len(windows),
            "noOpen": True,
            "dryRun": True,
        })
        server.shutdown()
        sys.exit(0)

    server.push_event("auth_ok", {
        "message": "Authenticated",
        "mirdashBase": mirdash_base,
        "months": month_labels,
    })

    # Pre-assign one token per window by index (zip truncates to the shorter
    # list, which replaces the old `token_idx >= len(tokens)` guard). Each month
    # runs paxel as a subprocess, so a bounded thread pool gives real multi-core
    # parallelism without GIL contention.
    scheduled = list(enumerate(zip(windows, tokens)))
    total = len(windows)

    def _run_one(i, since, until, label, token):
        prefix = f"gnomon-{label}-" if output_dir else ""
        # Patched as an attribute of this module by tests -- call via the module
        # name so the indirection is preserved.
        return _upload_window_web(
            mirdash_base, token, paxel_src,
            paxel_forward, since, until, label, verbose, server, i, total,
            output_dir=output_dir,
            quiet=quiet,
            window_months=window_months,
            file_prefix=prefix,
        )

    results = {}  # index -> report_url / sentinel
    workers = min(_UPLOAD_CONCURRENCY, len(scheduled)) or 1
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_run_one, i, since, until, label, tok): i
            for i, ((since, until, label), tok) in scheduled
        }
        for fut in as_completed(futs):
            results[futs[fut]] = fut.result()

    # Aggregate deterministically from results keyed by window index. Pick the
    # highest successful index as last_report_url to preserve "most recent month".
    uploaded_count = sum(1 for r in results.values() if _is_report_url(r))
    failed = sum(1 for r in results.values() if r in (_UPLOAD_ERROR, _PAXEL_ERROR))
    last_report_url = None
    for i in sorted(results):
        if _is_report_url(results[i]):
            last_report_url = results[i]

    server.push_event("done", {
        "reportUrl": last_report_url or "",
        "mirdashBase": mirdash_base,
        "uploaded": uploaded_count,
        "failed": failed,
        "total": len(windows),
        "noOpen": no_open,
    })

    if last_report_url:
        full_report = urllib.parse.urljoin(mirdash_base + "/", last_report_url)
        if not quiet:
            msg = f"  [ok] {uploaded_count}/{len(windows)} months uploaded"
            if failed:
                msg += f" ({failed} failed)"
            print(msg)
        print(f"  Report ready: {full_report}")
    elif failed:
        print(f"  error: {failed}/{len(windows)} months failed to upload -- nothing was shared")
    else:
        print("  nothing to share (no sessions found)")

    server.shutdown()
    # Hard-fail only when nothing made it through; partial success still
    # exits 0 (the UI and terminal already flag the failed months).
    if failed and uploaded_count == 0:
        sys.exit(1)


def _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                  output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS, *, dry_run=False):
    """Console mode: original behavior with full terminal output."""
    port = 8799
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    if not quiet:
        print(f"\n  Opening mirdash for authentication... (close the browser or wait {_SHARE_AUTH_TIMEOUT}s to skip)")

    try:
        opened = webbrowser.open(auth_url)
    except Exception as exc:
        print(f"  warning: could not open a browser for auth ({exc}) -- nothing was analysed or shared.")
        sys.exit(0)
    if not opened:
        print("  warning: no browser available (headless/CI) -- nothing was analysed or shared.")
        sys.exit(0)

    tokens, uploaded = _capture_cli_token(port=port, timeout=_SHARE_AUTH_TIMEOUT)  # uploaded consumed in auto-mode (G4)
    if not tokens:
        print("  Authentication cancelled or timed out -- nothing was analysed or shared.")
        sys.exit(0)

    paxel_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "paxel.py")
    paxel_src = os.path.normpath(paxel_src)
    if not os.path.isfile(paxel_src):
        print(f"  error: paxel.py not found at {paxel_src}")
        sys.exit(1)

    today = datetime.date.today()

    # Decide which month windows to upload. auto/force run through the
    # detection helpers; backfill keeps the explicit trailing-N window list.
    if mode == "backfill":
        windows = month_windows(token_count, today, window_months=window_months)
    else:  # auto or force
        anchors = months_to_upload(today, uploaded, force=(mode == "force"))
        windows = windows_for_anchors(anchors, window_months=window_months)

    if dry_run:
        if mode == "backfill":
            plan_pairs = [label for _, _, label in windows]
        else:
            plan_pairs = plan_upload(today, uploaded, force=(mode == "force"))
        _print_dry_run_plan(mode, windows, plan_pairs)
        sys.exit(0)

    # Pre-assign one token per window by index; zip truncates to the shorter
    # list. If there are fewer tokens than windows, warn (preserves the old
    # "ran out of tokens" message) before the truncated windows are dropped.
    scheduled = list(enumerate(zip(windows, tokens)))
    if len(windows) > len(tokens):
        print("  warning: ran out of tokens before all months were uploaded -- stopping")

    def _run_one(since, until, label, token):
        prefix = f"gnomon-{label}-" if output_dir else ""
        # Patched as an attribute of this module by tests -- call via the module
        # name so the indirection is preserved.
        return _upload_window(
            mirdash_base, token, paxel_src,
            paxel_forward, since, until, label, verbose, quiet,
            output_dir=output_dir,
            window_months=window_months,
            file_prefix=prefix,
        )

    results = {}  # index -> (result, summary)
    workers = min(_UPLOAD_CONCURRENCY, len(scheduled)) or 1
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_run_one, since, until, label, tok): (i, label)
            for i, ((since, until, label), tok) in scheduled
        }
        for fut in as_completed(futs):
            i, label = futs[fut]
            result, summary = fut.result()
            results[i] = (result, summary)
            if _is_report_url(result) and not quiet:
                print(f"  ^ {label} uploaded")

    # Aggregate deterministically from results keyed by window index.
    uploaded_count = sum(1 for r, _ in results.values() if _is_report_url(r))
    failed = sum(1 for r, _ in results.values() if r in (_UPLOAD_ERROR, _PAXEL_ERROR))
    last_report_url = None
    last_summary = None
    for i in sorted(results):
        result, summary = results[i]
        if _is_report_url(result):
            last_report_url = result
            last_summary = summary

    if not quiet:
        msg = f"  uploaded {uploaded_count}/{len(windows)} months"
        if failed:
            msg += f" ({failed} failed)"
        print(msg)

    if last_report_url:
        # Single successful window (the common default run): print the build
        # profile block. For batch runs (>1 uploaded) keep the consolidated output.
        if uploaded_count == 1 and last_summary is not None:
            block = _format_summary(last_summary, quiet=quiet)
            if block:
                print(block)
        full_report = urllib.parse.urljoin(mirdash_base + "/", last_report_url)
        print(f"  Report ready: {full_report}")
        if not no_open:
            try:
                webbrowser.open(full_report)
            except Exception as exc:
                print(f"  warning: could not open report in browser: {exc}")
        return

    # Mirror the web loop: a real failure must not be reported as "nothing to share".
    if failed:
        print(f"  error: {failed}/{len(windows)} months failed to upload -- nothing was shared")
        sys.exit(1)

    print("  nothing to share (no sessions found)")
    sys.exit(0)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    if argv is None:
        argv = sys.argv[1:]

    if "--help" in argv or "-h" in argv:
        print(_HELP_TEXT)
        raise SystemExit(0)

    allow_stale_cli = _ALLOW_STALE_CLI_FLAG in argv
    argv = [a for a in argv if a != _ALLOW_STALE_CLI_FLAG]

    # --local mode: run analysis directly, no auth/upload
    if "--local" in argv:
        from gnomon.cli.local import main as local_main
        # Strip --local and wrapper-only flags, pass the rest to local_main
        local_argv = [a for a in argv if a != "--local" and not re.match(r"--mirdash-base=", a)
                      and not re.match(r"--window(=.*)?$", a) and a != "--console"
                      and not re.match(r"--backfill(=.*)?$", a) and a != "--force"]
        # Ensure --summary is passed for summary.json generation
        if "--summary" not in local_argv:
            local_argv.append("--summary")
        output_dir = _resolve_output_dir(argv)
        local_main(argv=local_argv, output_dir=output_dir)
        return

    # Flags consumed by this wrapper (not forwarded to paxel)
    wrapper_flags = {"--no-open", "--quiet", "--verbose", "--console", "--output-dir"}
    no_open = "--no-open" in argv
    quiet = "--quiet" in argv
    verbose = "--verbose" in argv
    console = "--console" in argv
    dry_run = "--dry-run" in argv
    output_dir = _resolve_output_dir(argv)

    # Parse --window=N (trailing N-month scoring window; default 6)
    window_months = parse_window(argv)

    # Determine operating mode
    mode, token_count = decide_mode(argv)

    # Flags appended literally below — strip from user passthrough to avoid duplicates
    paxel_literal_flags = {"--summary", "--no-open"}

    # Build paxel args: strip wrapper-only flags, literal flags, backfill/force/dry-run flags,
    # mirdash overrides, and window override; keep source names and dir overrides
    paxel_forward = [
        a for a in argv
        if a not in wrapper_flags
        and a not in paxel_literal_flags
        and not re.match(r"--mirdash-base=", a)
        and not re.match(r"--backfill(=.*)?$", a)
        and not re.match(r"--window(=.*)?$", a)
        and not re.match(r"--output-dir=(.+)$", a)
        and a != "--force"
        and a != "--dry-run"
    ]
    # Resolve relative --<source>-dir overrides against the caller's cwd before paxel
    # runs from its temp directory (see _absolutize_dir_flags).
    paxel_forward = _absolutize_dir_flags(paxel_forward)

    mirdash_base = _resolve_mirdash_base(argv)

    # force/backfill dry-run plans depend only on `today`, not on the server's
    # uploaded state, so compute and print them without auth/browser/tokens.
    # auto dry-run still needs login (the plan depends on `uploaded`) and is
    # handled inside _main_web/_main_console.
    if dry_run and mode in ("force", "backfill"):
        today = datetime.date.today()
        windows = month_windows(token_count, today, window_months=window_months)
        if mode == "backfill":
            plan_pairs = [label for _, _, label in windows]
        else:  # force
            plan_pairs = plan_upload(today, [], force=True)
        _print_dry_run_plan(mode, windows, plan_pairs)
        sys.exit(0)

    _enforce_cli_freshness(allow_stale=allow_stale_cli)

    if console:
        _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                      output_dir, window_months=window_months, dry_run=dry_run)
    else:
        _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                  output_dir, window_months=window_months, dry_run=dry_run)


if __name__ == "__main__":
    main()
