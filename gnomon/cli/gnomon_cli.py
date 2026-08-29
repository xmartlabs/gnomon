"""Standalone CLI entry point for the generic Gnomon client."""

import sys

from gnomon.cli import local
from gnomon.cli.upload_pipeline import (
    _main_console,
    _main_web,
    _maybe_offer_retention,
)
from gnomon.upload.mirdash import (
    _absolutize_dir_flags,
    _resolve_output_dir,
    decide_mode,
    parse_window,
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
    --window=N    trailing window size in months for each scored point (default 1)
    --no-open     skip redirecting to the dashboard report at the end
    --quiet       only print errors and the final report URL
    --verbose     also show paxel's full stdout/stderr
    --console     show progress in the terminal instead of the browser
    --output-dir=PATH
                  copy final artifacts into PATH
"""

_URL_OPTIONS = ("--dashboard-url", "--mirdash-base")


def _without_options(argv, *, remove_flags=(), remove_value_options=()):
    """Remove wrapper options, including their separate values, from argv."""
    result = []
    skip_value = False
    for arg in argv:
        if skip_value:
            skip_value = False
            continue
        if arg in remove_flags:
            continue
        if any(arg.startswith(option + "=") for option in remove_value_options):
            continue
        if arg in remove_value_options:
            skip_value = True
            continue
        result.append(arg)
    return result


def _local_argv(argv):
    local_argv = _without_options(
        argv,
        remove_flags={"--local", "--console", "--force", "--dry-run"},
        remove_value_options=set(_URL_OPTIONS) | {"--window", "--output-dir"},
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
        remove_value_options=set(_URL_OPTIONS) | {"--window", "--output-dir", "--backfill"},
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

    output_dir = _resolve_output_dir(argv)
    if "--local" in argv:
        local.main(argv=_local_argv(argv), output_dir=output_dir)
        return

    dashboard_url = resolve_dashboard_url(argv)
    if not dashboard_url:
        # Preserve the useful local artifact even when there is nowhere to upload.
        local.main(argv=_local_argv(argv), output_dir=output_dir)
        print(
            "dashboard URL required to upload; use --local or --dashboard-url=URL",
            file=sys.stderr,
        )
        raise SystemExit(1)

    quiet = "--quiet" in argv
    dry_run = "--dry-run" in argv
    no_open = "--no-open" in argv
    verbose = "--verbose" in argv
    console = "--console" in argv
    window_months = parse_window(argv)
    mode, token_count = decide_mode(argv)
    runner = _main_console if console else _main_web

    _maybe_offer_retention(dry_run, quiet, argv)
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
