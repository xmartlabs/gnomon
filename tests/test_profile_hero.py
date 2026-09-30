"""Contract tests for the T6 local-profile hero section."""

import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.brand import CAPTION
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.sections.hero import render


def _stats(aq=74, tier="Proficient", tool_calls=1200):
    return {
        "volume": {"total_sessions": 4, "total_prompts": 22,
                   "tool_calls_total": tool_calls},
        "agentic": {"aq_0_100": aq, "tier": tier},
    }


def _context(stats=None, period=None, trend=None, quote="Your thinnest pillar is Craft.",
             scores=None):
    return ProfileContext(
        stats or _stats(), archetype="Proficient", quote=quote,
        scores=scores or {"Execution": 7.8, "Planning": 9, "Engineering": 8.2},
        voice={}, period=period or Period(
            "current_month", None, None, "2026-06",
            "Jun 2026 · in progress · 30 days", 30, 30),
        trend=trend, moves=[], edges=[], caption=CAPTION)


class TestProfileHero(unittest.TestCase):
    def test_current_month_hero_shows_period_scores_and_share_controls(self):
        page = render(_context())

        self.assertIn(
            'id="hero-period" class="hero-period" data-period-kind="current_month" '
            'data-days-elapsed="30">Jun 2026 · in progress · 30 days</p>', page)
        self.assertIn('id="hero-tier" class="hero-tier">You\'re Proficient.</h1>', page)
        self.assertIn('id="hero-aq" class="gn-fig-xl">74</span>', page)
        self.assertIn('data-dimension="Execution" aria-label="Execution score">7.8', page)
        self.assertIn('data-dimension="Planning" aria-label="Planning score">9', page)
        self.assertIn('data-dimension="Engineering" aria-label="Engineering score">8.2', page)
        self.assertIn('id="hero-sentence"', page)
        self.assertIn("Your thinnest pillar is Craft.", page)
        self.assertIn('id="share-x"', page)
        self.assertIn('id="share-copy"', page)
        self.assertIn('id="share-img"', page)
        self.assertIn(CAPTION, page)

    def test_delta_uses_direction_glyph_and_previous_month(self):
        page = render(_context(trend={"points": [
            {"month": "2026-05", "label": "May", "aq": 70},
            {"month": "2026-06", "label": "Jun", "aq": 74},
        ]}))

        self.assertIn(
            'id="hero-delta" class="hero-delta" data-delta="+4" '
            'data-direction="up">▲ +4 vs May</span>', page)

    def test_missing_previous_month_is_first_month(self):
        page = render(_context(trend={"points": [
            {"month": "2026-04", "label": "Apr", "aq": 70},
            {"month": "2026-06", "label": "Jun", "aq": 74},
        ]}))

        self.assertIn(
            '<span id="hero-delta" class="gn-empty" data-delta="none">first month</span>', page)

    def test_custom_period_has_no_delta(self):
        period = Period("custom", None, None, None, "2026-03-01 → 2026-05-31", None, None)
        page = render(_context(period=period, trend={"points": [
            {"month": "2026-04", "label": "Apr", "aq": 70},
            {"month": "2026-05", "label": "May", "aq": 74},
        ]}))

        self.assertIn('data-period-kind="custom"', page)
        self.assertIn("2026-03-01 → 2026-05-31", page)
        self.assertNotIn('id="hero-delta"', page)

    def test_limited_data_is_explained_without_negative_empty_state(self):
        page = render(_context(stats=_stats(tool_calls=0)))

        self.assertIn('id="hero-limited"', page)
        self.assertIn("Limited data.", page)
        self.assertNotIn("var(--negative)", page.split("<p id=\"hero-limited\"", 1)[1].split(
            "</p>", 1)[0])


if __name__ == "__main__":
    unittest.main()
