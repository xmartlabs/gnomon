"""Programmatic API for running Gnomon analysis and uploads."""

import json
import os
import tempfile

from gnomon.cli import local
from gnomon.cli.upload_pipeline import _main_console, _main_web, _print_static_dry_run_plan
from gnomon.upload.mirdash import (
    _MAX_BACKFILL,
    _absolutize_dir_flags,
    _upload_summary,
    decide_mode,
)

_RUN_MODES = ("auto", "force", "backfill")


class GnomonRunError(RuntimeError):
    """The upload pipeline ended with a non-zero exit status."""

    def __init__(self, exit_code):
        super().__init__(f"gnomon run failed with exit code {exit_code}")
        self.exit_code = exit_code


def _mode_token_count(mode, months):
    """Return the token count for ``mode`` exactly as the CLI flags would."""
    if mode not in _RUN_MODES:
        raise ValueError(f"mode must be one of {', '.join(_RUN_MODES)}; got {mode!r}")
    if months is not None and mode != "backfill":
        raise ValueError("months only applies to mode='backfill'")
    if months is not None and not (isinstance(months, int) and 1 <= months <= _MAX_BACKFILL):
        raise ValueError(f"months must be an integer from 1 to {_MAX_BACKFILL}; got {months!r}")
    if mode == "force":
        flags = ["--force"]
    elif mode == "backfill":
        flags = ["--backfill" if months is None else f"--backfill={months}"]
    else:
        flags = []
    return decide_mode(flags)[1]


def _source_list(sources):
    if sources is None:
        return []
    if isinstance(sources, str):
        return [sources]
    return list(sources)


def _append_options(argv, options):
    """Translate simple keyword options into the CLI flags local accepts."""
    for name, value in options.items():
        if value is None or value is False:
            continue
        flag = "--" + name.replace("_", "-")
        if value is True:
            argv.append(flag)
        elif isinstance(value, (list, tuple)):
            argv.extend(f"{flag}={item}" for item in value)
        else:
            argv.append(f"{flag}={value}")
    return argv


class Gnomon:
    """Run local Gnomon analysis and optionally upload it to a dashboard."""

    def __init__(self, dashboard_url=None, sources=None, window_months=1):
        self.dashboard_url = dashboard_url
        self.sources = _source_list(sources)
        self.window_months = window_months

    def analyze(self, output_dir=None, **kwargs):
        """Run local analysis and return the generated ``summary.json`` dict."""
        argv = list(kwargs.pop("argv", self.sources))
        if "--summary" not in argv:
            argv.append("--summary")
        if "--no-open" not in argv:
            argv.append("--no-open")
        if "window_months" in kwargs:
            raise ValueError(
                "window_months only applies to uploads (run()); bound local analysis "
                "with since/until/last instead"
            )
        _append_options(argv, kwargs)

        temporary = None
        if output_dir is None:
            temporary = tempfile.TemporaryDirectory(prefix="gnomon-")
            output_dir = temporary.name
        else:
            output_dir = os.fspath(output_dir)
            os.makedirs(output_dir, exist_ok=True)

        try:
            local.main(argv=argv, output_dir=output_dir)
            with open(os.path.join(output_dir, "summary.json"), encoding="utf-8") as fh:
                return json.load(fh)
        finally:
            if temporary is not None:
                temporary.cleanup()

    def upload(self, summary, token):
        """Upload a pre-computed summary using this instance's dashboard URL."""
        if not self.dashboard_url:
            raise ValueError("dashboard_url required for upload")
        return _upload_summary(self.dashboard_url, token, summary)

    def run(self, mode="auto", console=False, *, months=None, argv=None,
            window_months=None, paxel_forward=None, no_open=False, quiet=False,
            verbose=False, output_dir=None, dry_run=False):
        """Run the shared authentication, analysis, and upload pipeline.

        ``mode`` is ``"auto"``, ``"force"`` or ``"backfill"``; ``months`` sets the
        backfill size (default 6, like a bare ``--backfill``). A force or backfill
        ``dry_run`` only prints the plan, with no login. Returns ``None``
        when the pipeline finishes with exit status 0 and raises
        ``GnomonRunError`` otherwise, so the CLI's ``sys.exit`` never reaches the
        host process. Exit status 0 also covers runs that shared nothing, such
        as a cancelled login or a machine without a browser.
        """
        if not self.dashboard_url:
            raise ValueError("dashboard_url required for run")

        token_count = _mode_token_count(mode, months)
        argv = list(self.sources if argv is None else argv)
        window_months = self.window_months if window_months is None else window_months
        if dry_run and mode in ("force", "backfill"):
            _print_static_dry_run_plan(mode, token_count, window_months)
            return None
        # Resolve relative --<source>-dir flags against the caller's cwd, as the CLI does.
        forward = _absolutize_dir_flags(list(argv if paxel_forward is None else paxel_forward))
        pipeline = _main_console if console else _main_web
        try:
            pipeline(
                argv=argv,
                mode=mode,
                token_count=token_count,
                paxel_forward=forward,
                no_open=no_open,
                quiet=quiet,
                verbose=verbose,
                output_dir=output_dir,
                window_months=window_months,
                dry_run=dry_run,
                brand="gnomon",
                dashboard_url=self.dashboard_url,
            )
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise GnomonRunError(exc.code) from None
