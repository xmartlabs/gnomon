"""CLI entry point for xl-ai-insights (auth + upload wrapper around local analysis)."""

import datetime
import importlib.metadata
import json
import os
import re
import sys
import urllib.request

from gnomon.cli.upload_pipeline import (
    _DEFAULT_SETTINGS_PATH,
    _SUGGESTED_RETENTION_DAYS,
    _REASON_LABELS,
    _warn_unavailable_comparison,
    _print_dry_run_plan,
    offer_retention_config,
    _maybe_offer_retention,
    _main_web,
    _main_console,
)
from gnomon.upload.mirdash import (
    _resolve_mirdash_base, _resolve_output_dir, _absolutize_dir_flags,
    _DEFAULT_MIRDASH_BASE,
    parse_window, decide_mode, month_windows, plan_upload,
    _run_paxel, _upload_summary, months_to_upload,  # noqa: F401
)


_HELP_TEXT = """Usage:
    xl-ai-insights [source ...] [--local] [--include-low-volume] [--allow-stale-cli] [--mirdash-base=URL] [--window=N] [--no-open] [--quiet] [--verbose] [--console] [--output-dir=PATH]
    xl-ai-insights --force
    xl-ai-insights --dry-run
    xl-ai-insights --help
    xl-ai-insights -h

    source        e.g. claude, codex, gemini -- same as paxel.py (default: all)
    --local       run local analysis only (no login, no upload)
    --include-low-volume
                  include sources with fewer than 10 in-window sessions
    --allow-stale-cli
                  continue network/upload flows after a confirmed stale CLI warning
    --force       re-upload all months (ignores what has already been uploaded)
    --dry-run     show what would be uploaded (and why) without uploading anything
    --mirdash-base=URL  override the mirdash server URL
    --window=N    trailing window size in months for each scored point (default 1)
    --no-open     skip redirecting to the mirdash report at the end
    --quiet       only print errors and the final report URL
    --verbose     also show paxel's full stdout/stderr
    --console     show progress in the terminal instead of the browser
    --tools       print per-tool-call rates (self-check + rate calibration)
    --output-dir=PATH
                  copy final artifacts into PATH (use . for current directory)

    Without flags, xl-ai-insights uploads the current month. When the prior
    month is missing or uses another scoring contract, it rebuilds the previous month first.
"""

_LATEST_CLI_RELEASE_URL = "https://api.github.com/repos/xmartlabs/gnomon/releases/latest"
_CLI_REFRESH_COMMAND = "uvx --refresh --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights"
_ALLOW_STALE_CLI_FLAG = "--allow-stale-cli"

# Retention offer (honest-aq-series step 1, design decision F): the suggested
# value only -- never forced, never written silently.










def _release_result(status, current=None, latest=None, reason=None):
    return {"status": status, "current": current, "latest": latest, "reason": reason}


def _parse_stable_release_tag(release_text):
    """Return normalized X.Y.Z from a stable GitHub Release tag, else None."""
    try:
        tag_name = json.loads(release_text).get("tag_name")
    except (AttributeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(tag_name, str):
        return None
    match = re.fullmatch(r"v?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))", tag_name)
    return match.group(1) if match else None


def _check_latest_cli_release(timeout=1.5):
    try:
        current = importlib.metadata.version("xl-ai-insights")
    except Exception as exc:
        return _release_result("unknown", reason=f"current-version:{exc.__class__.__name__}")

    if not isinstance(current, str) or not current:
        return _release_result("unknown", reason="current-version-missing")

    try:
        with urllib.request.urlopen(_LATEST_CLI_RELEASE_URL, timeout=timeout) as response:
            latest_text = response.read().decode("utf-8")
    except Exception as exc:
        return _release_result("unknown", current=current, reason=f"latest-fetch:{exc.__class__.__name__}")

    latest = _parse_stable_release_tag(latest_text)
    if not latest:
        return _release_result("unknown", current=current, reason="latest-version-missing")

    if current != latest:
        return _release_result("mismatch", current=current, latest=latest)
    return _release_result("current", current=current, latest=latest)


def _enforce_cli_freshness(allow_stale: bool):
    release = _check_latest_cli_release()
    if release.get("status") != "mismatch":
        return

    print("\n  ! xl-ai-insights is not running the published release\n")
    print(f"    Installed:        {release.get('current')}")
    print(f"    Published latest: {release.get('latest')}")
    print("\n  Use the latest stable release before uploading metrics.")
    print("\n  Run latest version:")
    print(f"      {_CLI_REFRESH_COMMAND}")
    if allow_stale:
        print("\n  Continuing because --allow-stale-cli was provided.")
        return
    print("\n  Override:")
    print("      xl-ai-insights --allow-stale-cli ...")
    print("\n  Aborted before auth/upload.\n")
    raise SystemExit(1)








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

    # Read early: both are needed before the --local branch returns, because a
    # --local run analyses transcripts too and so has the same stake in retention.
    quiet = "--quiet" in argv
    dry_run = "--dry-run" in argv

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
        _maybe_offer_retention(dry_run, quiet, local_argv)
        local_main(argv=local_argv, output_dir=output_dir)
        return

    # Flags consumed by this wrapper (not forwarded to paxel)
    wrapper_flags = {"--no-open", "--quiet", "--verbose", "--console", "--output-dir"}
    no_open = "--no-open" in argv
    verbose = "--verbose" in argv
    console = "--console" in argv
    output_dir = _resolve_output_dir(argv)

    # Parse --window=N (trailing N-month scoring window; default 1)
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

    if mirdash_base == _DEFAULT_MIRDASH_BASE:
        _enforce_cli_freshness(allow_stale=allow_stale_cli)

    today = datetime.date.today()
    current_window = month_windows(token_count, today, window_months=window_months)[-1]
    current_window = tuple(
        datetime.datetime.fromisoformat(bound).astimezone()
        for bound in current_window[:2]
    )
    _maybe_offer_retention(
        dry_run, quiet, argv, default_window=current_window)

    if console:
        _main_console(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                      output_dir, window_months=window_months, dry_run=dry_run)
    else:
        _main_web(argv, mirdash_base, mode, token_count, paxel_forward, no_open, quiet, verbose,
                  output_dir, window_months=window_months, dry_run=dry_run)


if __name__ == "__main__":
    main()
