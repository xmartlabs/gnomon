"""CLI entry point for xl-ai-insights (auth + upload wrapper around local analysis)."""

import datetime
import os
import re
import sys
import urllib.parse
import webbrowser

from gnomon.upload.auth import _capture_cli_token, _wait_for_auth_tokens, _SHARE_AUTH_TIMEOUT, _WEB_AUTH_TIMEOUT
from gnomon.upload.mirdash import (
    _resolve_mirdash_base, _resolve_output_dir, _absolutize_dir_flags,
    _DEFAULT_WINDOW_MONTHS, parse_window, decide_mode,
    month_windows, months_to_upload, windows_for_anchors,
    _is_report_url, _upload_window, _upload_window_web,
    _PAXEL_ERROR, _UPLOAD_ERROR,
    # Re-exported so tests can patch them as attributes of this module and so the
    # web fallback to console mode keeps a stable surface.
    _run_paxel, _upload_summary,  # noqa: F401
)


_HELP_TEXT = """Usage:
    xl-ai-insights [source ...] [--local] [--mirdash-base=URL] [--window=N] [--no-open] [--quiet] [--verbose] [--console] [--output-dir=PATH]
    xl-ai-insights --force
    xl-ai-insights --help
    xl-ai-insights -h

    source        e.g. claude, codex, gemini -- same as paxel.py (default: all)
    --local       run local analysis only (no login, no upload)
    --force       re-upload all months (ignores what has already been uploaded)
    --mirdash-base=URL  override the mirdash server URL
    --window=N    trailing window size in months for each scored point (default 6)
    --no-open     skip redirecting to the mirdash report at the end
    --quiet       only print errors and the final report URL
    --verbose     also show paxel's full stdout/stderr
    --console     show progress in the terminal instead of the browser
    --output-dir=PATH
                  copy final artifacts into PATH (use . for current directory)

    Without flags, xl-ai-insights auto-detects which months are missing and
    uploads only what is needed (first run uploads everything automatically).
"""


def _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
              output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS):
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
                      output_dir=output_dir, window_months=window_months)
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

    server.push_event("auth_ok", {
        "message": "Authenticated",
        "mirdashBase": mirdash_base,
        "months": month_labels,
    })

    token_idx = 0
    uploaded_count = 0
    failed = 0
    last_report_url = None

    for i, (since, until, label) in enumerate(windows):
        if token_idx >= len(tokens):
            break
        prefix = f"gnomon-{label}-" if output_dir else ""
        report_url = _upload_window_web(
            mirdash_base, tokens[token_idx], paxel_src,
            paxel_forward, since, until, label, verbose, server, i, len(windows),
            output_dir=output_dir,
            quiet=quiet,
            window_months=window_months,
            file_prefix=prefix,
        )
        if _is_report_url(report_url):
            last_report_url = report_url
            uploaded_count += 1
            token_idx += 1
        elif report_url in (_UPLOAD_ERROR, _PAXEL_ERROR):
            failed += 1

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
                  output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS):
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

    token_idx = 0
    uploaded_count = 0
    last_report_url = None

    for since, until, label in windows:
        if token_idx >= len(tokens):
            print("  warning: ran out of tokens before all months were uploaded -- stopping")
            break

        prefix = f"gnomon-{label}-" if output_dir else ""
        report_url = _upload_window(
            mirdash_base, tokens[token_idx], paxel_src,
            paxel_forward, since, until, label, verbose, quiet,
            output_dir=output_dir,
            window_months=window_months,
            file_prefix=prefix,
        )
        if report_url is not None:
            last_report_url = report_url
            uploaded_count += 1
            token_idx += 1
            if not quiet:
                print(f"  ^ {label} uploaded")

    if not quiet:
        print(f"  uploaded {uploaded_count}/{len(windows)} months")

    if last_report_url:
        full_report = urllib.parse.urljoin(mirdash_base + "/", last_report_url)
        print(f"  Report ready: {full_report}")
        if not no_open:
            try:
                webbrowser.open(full_report)
            except Exception as exc:
                print(f"  warning: could not open report in browser: {exc}")
        return

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
    output_dir = _resolve_output_dir(argv)

    # Parse --window=N (trailing N-month scoring window; default 6)
    window_months = parse_window(argv)

    # Determine operating mode
    mode, token_count = decide_mode(argv)

    # Flags appended literally below — strip from user passthrough to avoid duplicates
    paxel_literal_flags = {"--summary", "--no-open"}

    # Build paxel args: strip wrapper-only flags, literal flags, backfill/init flags,
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
    ]
    # Resolve relative --<source>-dir overrides against the caller's cwd before paxel
    # runs from its temp directory (see _absolutize_dir_flags).
    paxel_forward = _absolutize_dir_flags(paxel_forward)

    mirdash_base = _resolve_mirdash_base(argv)

    if console:
        _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                      output_dir, window_months=window_months)
    else:
        _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                  output_dir, window_months=window_months)


if __name__ == "__main__":
    main()
