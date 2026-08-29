"""Programmatic API for running Gnomon analysis and uploads."""

import json
import os
import tempfile

from gnomon.cli import local
from gnomon.cli.upload_pipeline import _main_console, _main_web
from gnomon.upload.mirdash import _upload_summary


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
        flag = "--" + ("window" if name == "window_months" else name.replace("_", "-"))
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

    def run(self, mode="auto", console=False, **kwargs):
        """Run the shared authentication, analysis, and upload pipeline."""
        if not self.dashboard_url:
            raise ValueError("dashboard_url required for run")

        argv = list(kwargs.pop("argv", self.sources))
        window_months = kwargs.pop("window_months", self.window_months)
        token_count = kwargs.pop("token_count", 1)
        paxel_forward = kwargs.pop("paxel_forward", list(argv))
        pipeline = _main_console if console else _main_web
        return pipeline(
            argv=argv,
            mode=mode,
            token_count=token_count,
            paxel_forward=paxel_forward,
            no_open=kwargs.pop("no_open", False),
            quiet=kwargs.pop("quiet", False),
            verbose=kwargs.pop("verbose", False),
            output_dir=kwargs.pop("output_dir", None),
            window_months=window_months,
            dry_run=kwargs.pop("dry_run", False),
            brand="gnomon",
            dashboard_url=self.dashboard_url,
        )
