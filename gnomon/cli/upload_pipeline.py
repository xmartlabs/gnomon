"""Shared authentication, retention, and upload orchestration for Gnomon clients."""

import datetime
import json
import os
import sys
import time
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

from gnomon.config import BASE
from gnomon.scoring.versioning import SCORE_CONTRACT_ID
from gnomon.upload.auth import (
    _capture_cli_token,
    _wait_for_auth_tokens,
    _SHARE_AUTH_TIMEOUT,
    _WEB_AUTH_TIMEOUT,
)
from gnomon.upload.mirdash import (
    _resolve_output_dir,
    _absolutize_dir_flags,
    _DEFAULT_MIRDASH_BASE,
    _DEFAULT_WINDOW_MONTHS,
    _UPLOAD_CONCURRENCY,
    parse_window,
    decide_mode,
    month_windows,
    plan_upload,
    windows_for_anchors,
    default_producible_coverage_for,
    _is_report_url,
    _is_archived_only,
    _result_report_url,
    _upload_window,
    _upload_window_web,
    _PAXEL_ERROR,
    _UPLOAD_ERROR,
    _format_summary,
    PayloadTooLarge,
    _run_paxel,
    _upload_summary,
    months_to_upload,
)
from gnomon.upload.progress_server import ProgressServer


_BRAND_STRINGS = {
    "xl-ai-insights": {
        "title": "xl-ai-insights",
        "brand_line": "xl-ai-insights · mirdash",
        "sign_in": "Sign in with mirdash",
        "upload_step": "Upload to mirdash",
        "uploading": "Uploading to mirdash…",
        "opening": "Opening mirdash for authentication",
    },
    "gnomon": {
        "title": "gnomon",
        "brand_line": "gnomon",
        "sign_in": "Sign in",
        "upload_step": "Upload",
        "uploading": "Uploading…",
        "opening": "Opening dashboard for authentication",
    },
}


def _brand_cfg(brand):
    return _BRAND_STRINGS.get(brand, _BRAND_STRINGS["gnomon"])


class _ReasonLabels(dict):
    """Legacy mapping with an owner marker for extraction introspection."""

    __module__ = __name__


_SUGGESTED_RETENTION_DAYS = 180

_DEFAULT_SETTINGS_PATH = os.path.join(os.path.dirname(BASE), "settings.json")

def offer_retention_config(settings_path=None):
    """Interactive-only offer to set `cleanupPeriodDays` in
    ~/.claude/settings.json (design decision F). Returns a dict describing
    what happened -- never raises, never writes silently.

    Safety contract (threat matrix):
      - non-tty (CI, piped stdin) -> skip silently, zero prompt, zero write.
      - `cleanupPeriodDays` already present -> skip without prompting (never
        overwrite a user's existing choice).
      - malformed/unreadable existing settings.json -> decline with manual
        instructions, never write a partial file.
      - accept -> back up the CURRENT file (if any) to
        `<settings_path>.gnomon-backup-<epoch>` BEFORE writing, then write
        `cleanupPeriodDays: 180`, merged into the existing keys, and print the
        exact undo command plus the backup path.
    """
    path = settings_path or _DEFAULT_SETTINGS_PATH

    if not sys.stdin.isatty():
        return {"action": "skipped", "reason": "non-tty"}

    existing = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
            existing = json.loads(raw) if raw.strip() else {}
            if not isinstance(existing, dict):
                raise ValueError("settings.json root is not an object")
        except (OSError, ValueError, json.JSONDecodeError):
            print(
                f"  warning: could not parse {path} -- leaving it untouched. "
                f"To set retention manually, add \"cleanupPeriodDays\": "
                f"{_SUGGESTED_RETENTION_DAYS} to that file."
            )
            return {"action": "declined", "reason": "malformed"}

    if "cleanupPeriodDays" in existing:
        return {"action": "skipped", "reason": "already_set"}

    print(
        "\n  We detected that you use Claude Code as an AI tool.\n"
        "  Gnomon uses Claude Code transcripts to calculate your AI usage. "
        "By default, it can only use Claude Code's last 30 days of transcript history.\n"
        '  Gnomon can optionally add "cleanupPeriodDays": 180 to\n'
        "  ~/.claude/settings.json so Claude Code keeps your transcripts for 180 days.\n"
        "  This controls transcript retention only; it does not change Gnomon's scoring window.\n"
        "\n  Press y to add this setting automatically.\n"
        "  Press n or Enter to leave your settings unchanged. [y/N] "
    )
    try:
        answer = input().strip().lower()
    except EOFError:
        answer = ""
    if answer not in ("y", "yes"):
        return {"action": "declined", "reason": "user"}

    backup_path = None
    if os.path.isfile(path):
        backup_path = f"{path}.gnomon-backup-{int(time.time())}"
        with open(path, "r", encoding="utf-8") as src, \
                open(backup_path, "w", encoding="utf-8") as dst:
            dst.write(src.read())

    written = dict(existing)
    written["cleanupPeriodDays"] = _SUGGESTED_RETENTION_DAYS
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(written, fh, indent=2)
        fh.write("\n")

    print(f"  Set cleanupPeriodDays={_SUGGESTED_RETENTION_DAYS} in {path}.")
    if backup_path:
        print(f"  Backup of the previous file: {backup_path}")
        print(f"  Undo: cp {backup_path} {path}")
    else:
        print(f"  Undo: remove \"cleanupPeriodDays\" from {path} (it did not exist before).")

    return {"action": "accepted", "written": {"cleanupPeriodDays": _SUGGESTED_RETENTION_DAYS},
            "backup_path": backup_path}

def _maybe_offer_retention(dry_run, quiet, argv=None, default_window=None):
    """Offer the retention config on a real, talkative run (design decision F).

    A 30-day `cleanupPeriodDays` silently truncates the transcript history every
    score is derived from, so ask before analysis -- but only when asking is
    appropriate. `--dry-run` promises zero side effects, and `--quiet` promises only
    errors and the report URL, while the offer prints a prompt and an undo hint.
    `offer_retention_config()` owns the tty and already-set guards, so this decides
    the flag policy and history eligibility only, and both call sites (upload and
    `--local`) share it.
    """
    if dry_run or quiet:
        return
    from gnomon.cli.local import _claude_history_preflight

    if not _claude_history_preflight(argv or [], default_window=default_window):
        return
    offer_retention_config()

_REASON_LABELS = _ReasonLabels({
    "force":   "force re-upload",
    "initial": "no prior uploads",
    "current": "current month",
    "gap":     "missing on server",
    "refresh": "refresh (server snapshot predates month end)",
    "contract-upgrade": "contract-upgrade",
    "backfill": "backfill",
})

def _warn_unavailable_comparison(history):
    if isinstance(history, dict) and history.get("state") in (
        "unavailable",
        "legacy",
        "malformed",
    ):
        print(
            "  warning: uploaded history is unavailable or incompatible; "
            "uploading current month only and comparison remains unavailable"
        )

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

def _main_web(argv, mirdash_base=None, mode=None, token_count=None, paxel_forward=None,
              no_open=False, quiet=False, verbose=False, output_dir=None,
              window_months=_DEFAULT_WINDOW_MONTHS, *, dry_run=False,
              brand="xl-ai-insights", dashboard_url=None):
    """Web progress mode: auth + progress in browser, minimal console output."""

    if dashboard_url is not None:
        mirdash_base = dashboard_url

    port = 8799
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    try:
        server = ProgressServer(port=port, auth_url=auth_url, brand=brand)
    except OSError as exc:
        print(f"  warning: could not bind localhost:{port} ({exc}) -- falling back to console mode")
        _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                      output_dir=output_dir, window_months=window_months, dry_run=dry_run,
                      brand=brand)
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
    history = server.history
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
        forced_labels = frozenset()
    else:  # auto or force
        # plan_upload (not months_to_upload) so the per-month REASON survives:
        # the `force` upload directive stamped on each payload is bound to that
        # month's own reason, never to the global mode string.
        plan_reasons = plan_upload(
            today,
            history,
            force=(mode == "force"),
            active_contract=SCORE_CONTRACT_ID,
            producible_coverage_for=default_producible_coverage_for,
        )
        anchors = [anchor for anchor, _ in plan_reasons]
        forced_labels = frozenset(a for a, reason in plan_reasons if reason == "force")
        windows = windows_for_anchors(anchors, window_months=window_months, today=today)
        if mode == "auto":
            _warn_unavailable_comparison(history)

    month_labels = [label for _, _, label in windows]

    if dry_run:
        # Reuse the plan computed above instead of recomputing it: a second
        # plan_upload call would probe the filesystem for the previous month's
        # producible coverage all over again for a provably identical answer.
        plan_pairs = ([label for _, _, label in windows] if mode == "backfill"
                      else plan_reasons)
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

    if mode == "auto" and len(tokens) < len(windows):
        print("  error: authentication returned fewer tokens than the automatic upload plan")
        server.push_event("done", {"reportUrl": "", "mirdashBase": mirdash_base,
                                   "uploaded": 0, "failed": len(windows),
                                   "total": len(windows), "noOpen": no_open})
        server.shutdown()
        sys.exit(1)

    # Pre-assign one token per window by index. Each month runs paxel as a
    # subprocess, so a bounded thread pool gives real multi-core parallelism.
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
            force=(label in forced_labels),
        )

    results = {}  # index -> report_url / sentinel
    # Tracked distinctly from _PAXEL_ERROR/_UPLOAD_ERROR: current_failed below only
    # inspects the LAST (current) window, so a budget violation on an earlier
    # (non-latest) month would otherwise exit 0 whenever the current month
    # succeeds -- exactly the silent reupload-loop data-floor this guards against.
    budget_violation = False
    workers = min(_UPLOAD_CONCURRENCY, len(scheduled)) or 1
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_run_one, i, since, until, label, tok): (i, label)
            for i, ((since, until, label), tok) in scheduled
        }
        for fut in as_completed(futs):
            i, label = futs[fut]
            try:
                results[i] = fut.result()
            except PayloadTooLarge as exc:
                print(f"  error: {label} upload failed: {exc}")
                results[i] = _UPLOAD_ERROR
                budget_violation = True
            except Exception:
                print(f"  warning: {label} failed unexpectedly")
                results[i] = _PAXEL_ERROR

    # Aggregate deterministically from results keyed by window index. Automatic
    # success is anchored to the current (last planned) window.
    uploaded_count = sum(1 for r in results.values() if _is_report_url(r))
    guarded_count = sum(1 for r in results.values() if _is_archived_only(r))
    failed = sum(1 for r in results.values() if r in (_UPLOAD_ERROR, _PAXEL_ERROR))
    last_report_url = None
    last_guarded_url = None
    for i in sorted(results):
        if _is_report_url(results[i]) and (mode != "auto" or i == len(windows) - 1):
            last_report_url = _result_report_url(results[i])
        if _is_archived_only(results[i]) and (mode != "auto" or i == len(windows) - 1):
            last_guarded_url = _result_report_url(results[i])

    server.push_event("done", {
        "reportUrl": last_report_url or last_guarded_url or "",
        "mirdashBase": mirdash_base,
        "uploaded": uploaded_count,
        "guarded": guarded_count,
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
    elif guarded_count:
        if not quiet:
            print(f"  [guarded] {guarded_count}/{len(windows)} months archived only; live profile unchanged")
        if last_guarded_url:
            full_report = urllib.parse.urljoin(mirdash_base + "/", last_guarded_url)
            print(f"  Existing report: {full_report}")
    elif failed:
        print(f"  error: {failed}/{len(windows)} months failed to upload -- nothing was shared")
    else:
        print("  nothing to share (no sessions found)")

    server.shutdown()
    # Hard-fail only when nothing made it through; partial success still
    # exits 0 (the UI and terminal already flag the failed months) -- EXCEPT a
    # payload-budget violation, which must always surface as a nonzero exit
    # regardless of which window it hit or whether other windows succeeded.
    current_failed = results.get(len(windows) - 1) in (_UPLOAD_ERROR, _PAXEL_ERROR)
    if budget_violation or (mode == "auto" and current_failed) or (failed and uploaded_count == 0):
        sys.exit(1)

def _main_console(argv, mirdash_base=None, mode=None, token_count=None, paxel_forward=None,
                  no_open=False, quiet=False, verbose=False, output_dir=None,
                  window_months=_DEFAULT_WINDOW_MONTHS, *, dry_run=False,
                  brand="xl-ai-insights", dashboard_url=None):
    """Console mode: original behavior with full terminal output."""

    if dashboard_url is not None:
        mirdash_base = dashboard_url
    brand_cfg = _brand_cfg(brand)
    port = 8799
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    auth_url = f"{mirdash_base}/cli-auth?redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    if token_count > 1:
        auth_url += f"&count={token_count}"

    if not quiet:
        print(f"\n  {brand_cfg['opening']}... (close the browser or wait {_SHARE_AUTH_TIMEOUT}s to skip)")

    try:
        opened = webbrowser.open(auth_url)
    except Exception as exc:
        print(f"  warning: could not open a browser for auth ({exc}) -- nothing was analysed or shared.")
        sys.exit(0)
    if not opened:
        print("  warning: no browser available (headless/CI) -- nothing was analysed or shared.")
        sys.exit(0)

    tokens, history = _capture_cli_token(port=port, timeout=_SHARE_AUTH_TIMEOUT, brand=brand)
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
        forced_labels = frozenset()
    else:  # auto or force
        # plan_upload (not months_to_upload) so the per-month REASON survives:
        # the `force` upload directive stamped on each payload is bound to that
        # month's own reason, never to the global mode string.
        plan_reasons = plan_upload(
            today,
            history,
            force=(mode == "force"),
            active_contract=SCORE_CONTRACT_ID,
            producible_coverage_for=default_producible_coverage_for,
        )
        anchors = [anchor for anchor, _ in plan_reasons]
        forced_labels = frozenset(a for a, reason in plan_reasons if reason == "force")
        windows = windows_for_anchors(anchors, window_months=window_months, today=today)
        if mode == "auto":
            _warn_unavailable_comparison(history)

    if dry_run:
        # Reuse the plan computed above instead of recomputing it: a second
        # plan_upload call would probe the filesystem for the previous month's
        # producible coverage all over again for a provably identical answer.
        plan_pairs = ([label for _, _, label in windows] if mode == "backfill"
                      else plan_reasons)
        _print_dry_run_plan(mode, windows, plan_pairs)
        sys.exit(0)

    if len(windows) > len(tokens):
        if mode == "auto":
            print("  error: authentication returned fewer tokens than the automatic upload plan")
            sys.exit(1)
        print("  warning: ran out of tokens before all months were uploaded -- stopping")
    scheduled = list(enumerate(zip(windows, tokens)))

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
            force=(label in forced_labels),
        )

    results = {}  # index -> (result, summary)
    # Tracked distinctly from _PAXEL_ERROR/_UPLOAD_ERROR: a later window's success
    # sets last_report_url and returns early below, which would otherwise mask a
    # budget violation on an earlier (non-latest) month -- exactly the silent
    # reupload-loop data-floor this guards against.
    budget_violation = False

    def _record_result(i, label, result, summary):
        results[i] = (result, summary)
        if _is_report_url(result) and not quiet:
            print(f"  ^ {label} uploaded")
        elif _is_archived_only(result) and not quiet:
            print(f"  ^ {label} guarded (archive only)")

    workers = min(_UPLOAD_CONCURRENCY, len(scheduled)) or 1
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(_run_one, since, until, label, tok): (i, label)
            for i, ((since, until, label), tok) in scheduled
        }
        for fut in as_completed(futs):
            i, label = futs[fut]
            try:
                result, summary = fut.result()
            except PayloadTooLarge as exc:
                print(f"  error: {label} upload failed: {exc}")
                result, summary = _UPLOAD_ERROR, None
                budget_violation = True
            except Exception:
                print(f"  warning: {label} failed unexpectedly")
                result, summary = _PAXEL_ERROR, None
            _record_result(i, label, result, summary)

    # Aggregate deterministically from results keyed by window index.
    uploaded_count = sum(1 for r, _ in results.values() if _is_report_url(r))
    guarded_count = sum(1 for r, _ in results.values() if _is_archived_only(r))
    failed = sum(1 for r, _ in results.values() if r in (_UPLOAD_ERROR, _PAXEL_ERROR))
    last_report_url = None
    last_summary = None
    for i in sorted(results):
        result, summary = results[i]
        if _is_report_url(result) and (mode != "auto" or i == len(windows) - 1):
            last_report_url = _result_report_url(result)
            last_summary = summary

    if not quiet:
        msg = f"  uploaded {uploaded_count}/{len(windows)} months"
        if guarded_count:
            msg += f" ({guarded_count} guarded)"
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
        # A budget violation on any window must exit nonzero even when a later
        # window succeeded and would otherwise return here with exit 0.
        if budget_violation:
            sys.exit(1)
        return

    if guarded_count:
        print(f"  guarded {guarded_count}/{len(windows)} months -- live profile unchanged")
        return

    # Mirror the web loop: a real failure must not be reported as "nothing to share".
    if failed:
        print(f"  error: {failed}/{len(windows)} months failed to upload -- nothing was shared")
        sys.exit(1)

    print("  nothing to share (no sessions found)")
    sys.exit(0)
