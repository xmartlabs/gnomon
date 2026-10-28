"""Standalone CLI entry point for the generic Gnomon client."""

import datetime
import sys

from gnomon.cli import local
from gnomon.cli.period import resolve_period
from gnomon.cli.upload_pipeline import (
    _main_console,
    _main_web,
    _maybe_offer_retention,
    _print_dry_run_plan,
    _upload_retention_window,
)
from gnomon.upload.mirdash import (
    _absolutize_dir_flags,
    _resolve_output_dir,
    decide_mode,
    month_windows,
    parse_window,
    plan_upload,
    resolve_dashboard_url,
)


_HELP_TEXT = """Usage:
    gnomon [source ...] [--local] [--dashboard-url=URL] [--window=N]
           [--no-open] [--quiet] [--verbose] [--console] [--output-dir=PATH]
    gnomon --force | --dry-run | --backfill=N
    gnomon --help

    source        e.g. claude, codex, gemini -- same as paxel.py (default: all)
    --local       run local analysis only (no login, no upload)
    --dashboard-url=URL
                  dashboard URL used for authentication and upload
    --window=N    trailing window size in months for each uploaded point (default 1;
                  upload only, ignored with --local)
    --no-open     skip redirecting to the dashboard report at the end
    --quiet       only print errors and the final report URL
    --verbose     also show paxel's full stdout/stderr
    --console     show progress in the terminal instead of the browser
    --output-dir=PATH
                  copy final artifacts into PATH
"""

# URL options also accept their value as the next token (see _cli_option_value).
_URL_OPTIONS = ("--dashboard-url", "--mirdash-base")
# Wrapper options whose bare form is valid on its own (parse_backfill, parse_window,
# _resolve_output_dir), so only the flag itself is removed, never the next token.
_WRAPPER_VALUE_OPTIONS = ("--window", "--output-dir", "--backfill")


def _without_options(argv, *, remove_flags=(), remove_options=()):
    """Remove wrapper flags and options from argv.

    ``--option=value`` and a bare ``--option`` are dropped for every option in
    ``remove_options``; only URL options also drop a separate value, matching how
    ``resolve_dashboard_url`` reads them.
    """
    result = []
    skip_value = False
    for arg in argv:
        if skip_value:
            skip_value = False
            continue
        if arg in remove_flags:
            continue
        if any(arg.startswith(option + "=") for option in remove_options):
            continue
        if arg in remove_options:
            skip_value = arg in _URL_OPTIONS
            continue
        result.append(arg)
    return result


def _local_argv(argv):
    local_argv = _without_options(
        argv,
        remove_flags={"--local", "--console", "--force", "--dry-run"},
        remove_options=_URL_OPTIONS + _WRAPPER_VALUE_OPTIONS,
    )
    if "--summary" not in local_argv:
        local_argv.append("--summary")
    return local_argv


def _pipeline_argv(argv):
    wrapper_flags = {
        "--local", "--no-open", "--quiet", "--verbose", "--console",
        "--force", "--dry-run", "--summary",
    }
    forwarded = _without_options(
        argv,
        remove_flags=wrapper_flags,
        remove_options=_URL_OPTIONS + _WRAPPER_VALUE_OPTIONS,
    )
    return _absolutize_dir_flags(forwarded)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)

    if "--help" in argv or "-h" in argv:
        print(_HELP_TEXT)
        raise SystemExit(0)

    quiet = "--quiet" in argv
    dry_run = "--dry-run" in argv
    output_dir = _resolve_output_dir(argv)

    if "--local" in argv:
        local_argv = _local_argv(argv)
        period = resolve_period(local_argv)
        _maybe_offer_retention(dry_run, quiet, local_argv,
                               default_window=(period.since, period.until))
        local.main(argv=local_argv, output_dir=output_dir)
        return

    window_months = parse_window(argv)
    mode, token_count = decide_mode(argv)

    if dry_run and mode in ("force", "backfill"):
        today = datetime.date.today()
        windows = month_windows(token_count, today, window_months=window_months)
        if mode == "backfill":
            plan_pairs = [label for _, _, label in windows]
        else:
            plan_pairs = plan_upload(today, [], force=True)
        _print_dry_run_plan(mode, windows, plan_pairs)
        raise SystemExit(0)

    dashboard_url = resolve_dashboard_url(argv)
    if not dashboard_url:
        # Without a URL a normal run still produces the local report; --dry-run
        # promises no side effects, so it only reports the missing URL.
        if not dry_run:
            local.main(argv=_local_argv(argv), output_dir=output_dir)
        print(
            "dashboard URL required to upload; use --local or --dashboard-url=URL",
            file=sys.stderr,
        )
        raise SystemExit(1)

    no_open = "--no-open" in argv
    verbose = "--verbose" in argv
    console = "--console" in argv
    runner = _main_console if console else _main_web

    _maybe_offer_retention(dry_run, quiet, argv,
                           default_window=_upload_retention_window(token_count, window_months))
    return runner(
        argv=argv,
        mode=mode,
        token_count=token_count,
        paxel_forward=_pipeline_argv(argv),
        no_open=no_open,
        quiet=quiet,
        verbose=verbose,
        output_dir=output_dir,
        window_months=window_months,
        dry_run=dry_run,
        brand="gnomon",
        dashboard_url=dashboard_url,
    )


if __name__ == "__main__":
    main()
