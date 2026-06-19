"""Legacy import shim. Prefer gnomon.cli.insights."""

import os  # noqa: F401 — tests patch xl_ai_insights.os.path
import sys  # noqa: F401 — tests patch xl_ai_insights.sys
import webbrowser  # noqa: F401 — tests patch xl_ai_insights.webbrowser

from gnomon.cli.insights import *  # noqa: F401,F403
from gnomon.upload.mirdash import (  # noqa: F401
    _MAX_BACKFILL, _DEFAULT_WINDOW_MONTHS, _run_paxel, _upload_summary,
    _resolve_mirdash_base, _resolve_output_dir, _absolutize_dir_flags,
    parse_window, parse_backfill, decide_mode, month_windows,
    _summary_is_empty, _is_report_url,
    _format_summary, _PAXEL_ERROR, _UPLOAD_ERROR, _paxel_until_arg,
    _copy_artifacts, latest_month_with_data,
)
from gnomon.upload.auth import (  # noqa: F401
    _tokens_from_query, _capture_cli_token, _wait_for_auth_tokens,
    _SHARE_AUTH_TIMEOUT, _WEB_AUTH_TIMEOUT,
)

# main, _main_web, _main_console must be defined HERE (not imported) so that
# tests using patch.object(xl_ai_insights, "_run_paxel", ...) affect the
# globals these functions close over.  gnomon.cli.insights has the canonical
# implementations; these thin wrappers delegate but let patching work.
_mod = sys.modules[__name__]


def _upload_window(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                   verbose, quiet, output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS,
                   file_prefix=""):
    """Run paxel for one calendar window and upload the summary."""
    window_args = paxel_args_base + [
        f"--since={since}",
        f"--until={_mod._paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]
    if not quiet:
        print(f"  Analysing {label}...")
    summary = _mod._run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir,
                              file_prefix=file_prefix)
    if summary is None:
        print(f"  skip {label} -- paxel error")
        return None
    if _mod._summary_is_empty(summary):
        if not quiet:
            print(f"  skip {label} -- no activity")
        return None
    summary.setdefault("context", {})["window_months"] = window_months
    try:
        return _mod._upload_summary(mirdash_base, token, summary)
    except Exception as exc:
        print(f"  warning: {label} upload failed: {exc}")
        return None


def _upload_window_web(mirdash_base, token, paxel_src, paxel_args_base, since, until, label,
                       verbose, server, index, total, output_dir=None, quiet=False,
                       window_months=_DEFAULT_WINDOW_MONTHS, file_prefix=""):
    """Run paxel for one calendar window, push SSE events, and upload."""
    window_args = paxel_args_base + [
        f"--since={since}",
        f"--until={_mod._paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]
    server.push_event("analyzing", {"month": label, "label": label, "index": index, "total": total})
    summary = _mod._run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir,
                              file_prefix=file_prefix)
    if summary is None:
        server.push_event("error_msg", {"month": label, "label": label, "message": "paxel error"})
        return _mod._PAXEL_ERROR
    if _mod._summary_is_empty(summary):
        server.push_event("skipped", {"month": label, "label": label, "reason": "no activity"})
        return None
    summary.setdefault("context", {})["window_months"] = window_months
    server.push_event("uploading", {"month": label, "label": label, "index": index, "total": total})
    try:
        report_url = _mod._upload_summary(mirdash_base, token, summary)
        server.push_event("uploaded", {"month": label, "label": label, "index": index, "total": total})
        return report_url
    except Exception as exc:
        server.push_event("error_msg", {"month": label, "label": label, "message": str(exc)})
        return _mod._UPLOAD_ERROR


def _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
              output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS):
    """Web progress mode: auth + progress in browser, minimal console output."""
    from gnomon.upload.progress_server import ProgressServer
    import urllib.parse

    port = 8799
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    try:
        server = ProgressServer(port=port, auth_url=auth_url)
    except OSError as exc:
        print(f"  warning: could not bind localhost:{port} ({exc}) -- falling back to console mode")
        _mod._main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                           output_dir=output_dir, window_months=window_months)
        return

    if not quiet:
        print(f"\n  -> See progress at {server.url}")

    try:
        opened = _mod.webbrowser.open(auth_url)
    except Exception as exc:
        print(f"  warning: could not open a browser ({exc}) -- nothing was analysed or shared.")
        server.shutdown(delay=0)
        sys.exit(0)
    if not opened:
        print("  warning: no browser available (headless/CI) -- nothing was analysed or shared.")
        server.shutdown(delay=0)
        sys.exit(0)

    tokens = _mod._wait_for_auth_tokens(server, port)
    if not tokens:
        print("  Authentication cancelled or timed out -- nothing was analysed or shared.")
        server.push_event("auth_timeout", {})
        server.shutdown(delay=1.0)
        sys.exit(0)

    paxel_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paxel.py")
    if not os.path.isfile(paxel_src):
        print(f"  error: paxel.py not found at {paxel_src}")
        server.shutdown(delay=0)
        sys.exit(1)

    import datetime as _dt
    today = _dt.date.today()

    if mode in ("init", "backfill"):
        windows = _mod.month_windows(token_count, today, window_months=window_months)
        month_labels = [label for _, _, label in windows]
    else:
        month_labels = [_mod.month_windows(1, today, window_months=window_months)[0][2]]

    server.push_event("auth_ok", {
        "message": "Authenticated",
        "mirdashBase": mirdash_base,
        "months": month_labels,
    })

    if mode in ("init", "backfill"):
        token_idx = 0
        uploaded = 0
        failed = 0
        last_report_url = None

        for i, (since, until, label) in enumerate(windows):
            if token_idx >= len(tokens):
                break
            prefix = f"gnomon-{label}-" if output_dir else ""
            report_url = _mod._upload_window_web(
                mirdash_base, tokens[token_idx], paxel_src,
                paxel_forward, since, until, label, verbose, server, i, len(windows),
                output_dir=output_dir, quiet=quiet, window_months=window_months,
                file_prefix=prefix,
            )
            if _mod._is_report_url(report_url):
                last_report_url = report_url
                uploaded += 1
                token_idx += 1
            elif report_url in (_mod._UPLOAD_ERROR, _mod._PAXEL_ERROR):
                failed += 1

        server.push_event("done", {
            "reportUrl": last_report_url or "",
            "mirdashBase": mirdash_base,
            "uploaded": uploaded, "failed": failed, "total": len(windows),
            "noOpen": no_open,
        })

        if last_report_url:
            full_report = urllib.parse.urljoin(mirdash_base + "/", last_report_url)
            if not quiet:
                msg = f"  [ok] {uploaded}/{len(windows)} months uploaded"
                if failed:
                    msg += f" ({failed} failed)"
                print(msg)
            print(f"  Report ready: {full_report}")
        elif failed:
            print(f"  error: {failed}/{len(windows)} months failed to upload -- nothing was shared")

        server.shutdown()
        if failed and uploaded == 0:
            sys.exit(1)
        return

    since, until, label = _mod.month_windows(1, today, window_months=window_months)[0]
    report_url = _mod._upload_window_web(
        mirdash_base, tokens[0], paxel_src,
        paxel_forward, since, until, label, verbose, server, 0, 1,
        output_dir=output_dir, quiet=quiet, window_months=window_months,
    )

    if report_url == _mod._UPLOAD_ERROR:
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "failed": 1, "total": 1,
                                    "noOpen": True, "mirdashBase": mirdash_base})
        print(f"  error: upload failed for {label}")
        server.shutdown()
        sys.exit(1)

    if report_url == _mod._PAXEL_ERROR:
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "failed": 1, "total": 1,
                                    "noOpen": True, "mirdashBase": mirdash_base})
        print(f"  error: could not compute {label} -- nothing was shared")
        server.shutdown()
        sys.exit(1)

    if _mod._is_report_url(report_url):
        server.push_event("done", {
            "reportUrl": report_url, "mirdashBase": mirdash_base,
            "uploaded": 1, "total": 1, "noOpen": no_open,
        })
        full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
        print(f"  [ok] {label} uploaded -> {full_report}")
        server.shutdown()
        return

    all_time_args = paxel_forward + ["--summary", "--no-open"]
    all_time_summary = _mod._run_paxel(paxel_src, all_time_args, verbose, output_dir=output_dir)

    if all_time_summary is None or _mod._summary_is_empty(all_time_summary):
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "total": 1, "noOpen": True})
        print("  nothing to share (no sessions found)")
        server.shutdown()
        sys.exit(0)

    progression = all_time_summary.get("progression_monthly") or []
    fallback_month = _mod.latest_month_with_data(progression)

    if not fallback_month:
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "total": 1, "noOpen": True})
        print("  nothing to share (no sessions found)")
        server.shutdown()
        sys.exit(0)

    fallback_year, fallback_mo = int(fallback_month[:4]), int(fallback_month[5:7])
    fallback_date = _dt.date(fallback_year, fallback_mo, 1)
    fb_since, fb_until, fb_label = _mod.month_windows(1, fallback_date, window_months=window_months)[0]

    report_url = _mod._upload_window_web(
        mirdash_base, tokens[0], paxel_src,
        paxel_forward, fb_since, fb_until, fb_label, verbose, server, 0, 1,
        output_dir=output_dir, quiet=quiet, window_months=window_months,
    )

    if _mod._is_report_url(report_url):
        full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
        server.push_event("done", {
            "reportUrl": report_url, "mirdashBase": mirdash_base,
            "uploaded": 1, "total": 1, "noOpen": no_open,
        })
        print(f"  [ok] {fb_label} uploaded -> {full_report}")
    elif report_url == _mod._UPLOAD_ERROR:
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "failed": 1, "total": 1,
                                    "noOpen": True, "mirdashBase": mirdash_base})
        print(f"  error: upload failed for {fb_label}")
        server.shutdown()
        sys.exit(1)
    else:
        server.push_event("done", {"reportUrl": "", "uploaded": 0, "total": 1, "noOpen": True})
        print("  nothing to share (no sessions found)")

    server.shutdown()


def _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                  output_dir=None, window_months=_DEFAULT_WINDOW_MONTHS):
    """Console mode: original behavior with full terminal output."""
    import urllib.parse

    port = 8799
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    if not quiet:
        print(f"\n  Opening mirdash for authentication... (close the browser or wait {_mod._SHARE_AUTH_TIMEOUT}s to skip)")

    try:
        opened = _mod.webbrowser.open(auth_url)
    except Exception as exc:
        print(f"  warning: could not open a browser for auth ({exc}) -- nothing was analysed or shared.")
        sys.exit(0)
    if not opened:
        print("  warning: no browser available (headless/CI) -- nothing was analysed or shared.")
        sys.exit(0)

    tokens = _mod._capture_cli_token(port=port, timeout=_mod._SHARE_AUTH_TIMEOUT)
    if not tokens:
        print("  Authentication cancelled or timed out -- nothing was analysed or shared.")
        sys.exit(0)

    paxel_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paxel.py")
    if not os.path.isfile(paxel_src):
        print(f"  error: paxel.py not found at {paxel_src}")
        sys.exit(1)

    import datetime as _dt
    today = _dt.date.today()

    if mode in ("init", "backfill"):
        n_months = token_count
        windows = _mod.month_windows(n_months, today, window_months=window_months)

        token_idx = 0
        uploaded = 0
        last_report_url = None

        for since, until, label in windows:
            if token_idx >= len(tokens):
                print("  warning: ran out of tokens before all months were uploaded -- stopping")
                break

            window_args = paxel_forward + [
                f"--since={since}",
                f"--until={_mod._paxel_until_arg(until)}",
                "--summary",
                "--no-open",
            ]
            prefix = f"gnomon-{label}-" if output_dir else ""
            if not quiet:
                print(f"  Analysing {label}...")
            summary = _mod._run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir,
                                      file_prefix=prefix)
            if summary is None:
                print(f"  skip {label} -- paxel error")
                continue
            if _mod._summary_is_empty(summary):
                if not quiet:
                    print(f"  skip {label} -- no activity")
                continue
            summary.setdefault("context", {})["window_months"] = window_months
            try:
                report_url = _mod._upload_summary(mirdash_base, tokens[token_idx], summary)
            except Exception as exc:
                print(f"  warning: {label} upload failed: {exc}")
                continue
            if report_url is not None:
                last_report_url = report_url
                uploaded += 1
                token_idx += 1
                if not quiet:
                    print(f"  ^ {label} uploaded")

        verb = "initialised" if mode == "init" else "backfilled"
        if not quiet:
            print(f"  {verb} {uploaded}/{len(windows)} months")

        if last_report_url:
            full_report = urllib.parse.urljoin(mirdash_base + "/", last_report_url)
            print(f"  Report ready: {full_report}")
            if not no_open:
                try:
                    _mod.webbrowser.open(full_report)
                except Exception as exc:
                    print(f"  warning: could not open report in browser: {exc}")
        return

    since, until, label = _mod.month_windows(1, today, window_months=window_months)[0]

    if not quiet:
        print(f"  Computing your build profile for {label}...")

    window_args = paxel_forward + [
        f"--since={since}",
        f"--until={_mod._paxel_until_arg(until)}",
        "--summary",
        "--no-open",
    ]
    summary = _mod._run_paxel(paxel_src, window_args, verbose, quiet=quiet, output_dir=output_dir)

    if summary is None:
        sys.exit(1)

    if not _mod._summary_is_empty(summary):
        if not quiet:
            print("  Uploading metrics summary to mirdash...")
        summary.setdefault("context", {})["window_months"] = window_months
        try:
            report_url = _mod._upload_summary(mirdash_base, tokens[0], summary)
        except Exception as exc:
            print(f"  warning: {exc}")
            return

        full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
        formatted = _mod._format_summary(summary, quiet=quiet)
        if formatted:
            print(formatted)
        print(f"  Report ready: {full_report}")
        if not no_open:
            try:
                _mod.webbrowser.open(full_report)
            except Exception as exc:
                print(f"  warning: could not open report in browser: {exc}")
        return

    if not quiet:
        print(f"  No activity in {label} yet -- checking for most recent month with data...")

    all_time_args = paxel_forward + ["--summary", "--no-open"]
    all_time_summary = _mod._run_paxel(paxel_src, all_time_args, verbose, quiet=quiet, output_dir=output_dir)

    if all_time_summary is None or _mod._summary_is_empty(all_time_summary):
        print("  nothing to share (no sessions found)")
        sys.exit(0)

    import datetime as _dt2
    progression = all_time_summary.get("progression_monthly") or []
    fallback_month = _mod.latest_month_with_data(progression)

    if not fallback_month:
        print("  nothing to share (no sessions found)")
        sys.exit(0)

    fallback_year, fallback_mo = int(fallback_month[:4]), int(fallback_month[5:7])
    fallback_date = _dt2.date(fallback_year, fallback_mo, 1)
    fb_since, fb_until, fb_label = _mod.month_windows(1, fallback_date, window_months=window_months)[0]

    if not quiet:
        print(f"  Uploading most recent month with data: {fb_label}...")

    fb_args = paxel_forward + [
        f"--since={fb_since}",
        f"--until={_mod._paxel_until_arg(fb_until)}",
        "--summary",
        "--no-open",
    ]
    fb_summary = _mod._run_paxel(paxel_src, fb_args, verbose, quiet=quiet, output_dir=output_dir)

    if fb_summary is None or _mod._summary_is_empty(fb_summary):
        print("  nothing to share (no sessions found)")
        sys.exit(0)

    if not quiet:
        print("  Uploading metrics summary to mirdash...")
    fb_summary.setdefault("context", {})["window_months"] = window_months
    try:
        report_url = _mod._upload_summary(mirdash_base, tokens[0], fb_summary)
    except Exception as exc:
        print(f"  warning: {exc}")
        return

    full_report = urllib.parse.urljoin(mirdash_base + "/", report_url)
    formatted = _mod._format_summary(fb_summary, quiet=quiet)
    if formatted:
        print(formatted)
    print(f"  Report ready: {full_report}")
    if not no_open:
        try:
            _mod.webbrowser.open(full_report)
        except Exception as exc:
            print(f"  warning: could not open report in browser: {exc}")


def main():
    """Authenticate first, then run paxel locally and upload the summary to mirdash."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    import re

    argv = sys.argv[1:]

    if "--help" in argv or "-h" in argv:
        from gnomon.cli.insights import _HELP_TEXT
        print(_HELP_TEXT)
        raise SystemExit(0)

    # Flags consumed by this wrapper (not forwarded to paxel)
    wrapper_flags = {"--no-open", "--quiet", "--verbose", "--console", "--output-dir"}
    no_open = "--no-open" in argv
    quiet = "--quiet" in argv
    verbose = "--verbose" in argv
    console = "--console" in argv
    output_dir = _mod._resolve_output_dir(argv)

    # Parse --window=N (trailing N-month scoring window; default 6)
    window_months = _mod.parse_window(argv)

    # Determine operating mode
    mode, token_count = _mod.decide_mode(argv)

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
        and a != "--init"
    ]
    paxel_forward = _mod._absolutize_dir_flags(paxel_forward)

    mirdash_base = _mod._resolve_mirdash_base(argv)

    if console:
        _mod._main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                           output_dir, window_months=window_months)
    else:
        _mod._main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                       output_dir, window_months=window_months)


if __name__ == "__main__":
    main()
