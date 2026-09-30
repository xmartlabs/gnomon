"""Compatibility entry point for the local profile renderer.

The profile page lives in :mod:`gnomon.output.profile`.  This module remains a
small shim because the legacy ``paxel`` entry point and downstream callers
import ``_hero_lead`` and ``write_profile_html`` from here.
"""

import os
from typing import Optional

from gnomon.cli.period import Period
from gnomon.config import OUT_DIR
from gnomon.output.profile.context import build_context
from gnomon.output.profile.page import render_page


def _hero_lead(archetype):
    """Return the grammatical lead used by the historical profile API."""
    return "You're" if (archetype or "")[:4].lower() == "the " else "You're a"


def write_profile_html(stats, archetype, quote, scores, voice=None, output_dir=None, *,
                       period: Optional[Period] = None, trend: Optional[dict] = None) -> None:
    """Render and overwrite the profile in ``output_dir`` (or the configured output dir)."""
    if period is None:
        period = Period("all_history", None, None, None, "All history", None, None)
    output_path = output_dir or OUT_DIR
    context = build_context(stats, archetype, quote, scores, voice, period, trend)
    with open(os.path.join(output_path, "profile.html"), "w", encoding="utf-8") as handle:
        handle.write(render_page(context))
