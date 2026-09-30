"""Contract tests for the T15 share poster."""

import json
import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.poster import POSTER_JS, poster_data


class TestProfilePoster(unittest.TestCase):
    def _context(self, period=None, trend=None, voice=None):
        return ProfileContext(
            stats={
                "agentic": {
                    "aq_0_100": 81,
                    "tier": "Advanced",
                    "pillars": [
                        {"name": "Breadth", "score": 75.6},
                        {"name": "Craft", "score": 87.4},
                        {"name": "Efficiency", "score": 88.0},
                        {"name": "Savvy", "score": 69.2},
                    ],
                },
            },
            archetype="", quote="", scores={},
            voice=voice or {"cryptics": ["ok ship it but leave the flag off"]},
            period=period or Period(
                "current_month", None, None, "2026-06",
                "Jun 2026 · in progress · 20 days", 20, 30),
            trend=trend or {
                "points": [
                    {"month": "2026-05", "label": "May", "aq": 77},
                    {"month": "2026-06", "label": "Jun", "aq": 81},
                ],
            },
            moves=[
                {"tag": "Think", "title": "You think before you touch the diff"},
                {"tag": "Build", "title": "You keep the loop tight"},
                {"tag": "Ship", "title": "You leave a clean trail"},
                {"tag": "Extra", "title": "Not included"},
            ],
            edges=[], caption="",
        )

    def test_card_contains_light_aq_pillars_delta_moves_and_one_quote(self):
        card = poster_data(self._context())

        self.assertEqual(card["theme"], "light")
        self.assertEqual(card["period"], "Jun 2026 · in progress")
        self.assertEqual(card["tier"], "Advanced")
        self.assertEqual(card["aq"], 81)
        self.assertEqual(card["delta"], {"value": 4, "label": "vs May"})
        self.assertEqual(card["delta_empty"], None)
        self.assertEqual(card["pillars"], [
            {"name": "Breadth", "score": 76},
            {"name": "Craft", "score": 87},
            {"name": "Efficiency", "score": 88},
            {"name": "Savvy", "score": 69},
        ])
        self.assertEqual(len(card["moves"]), 3)
        self.assertEqual(card["quote"], {
            "live": "cuff", "text": "ok ship it but leave the flag off",
        })
        self.assertEqual(card["fonts"], {"ui": "Archivo", "mono": "IBM Plex Mono"})
        self.assertEqual(card["repo"], "github.com/xmartlabs/gnomon")
        self.assertNotIn("scores", card)
        self.assertEqual(json.loads(json.dumps(card)), card)

    def test_custom_window_has_no_delta_and_keeps_requested_period(self):
        period = Period(
            "custom", None, None, None,
            "2026-03-01 → 2026-05-31", None, None)
        card = poster_data(self._context(period=period, trend=None))

        self.assertEqual(card["period"], "2026-03-01 → 2026-05-31")
        self.assertIsNone(card["delta"])
        self.assertIsNone(card["delta_empty"])

    def test_poster_js_is_light_and_reads_the_visible_cuff_quote(self):
        self.assertIn("document.fonts.load", POSTER_JS)
        self.assertIn('document.getElementById("q-cuff")', POSTER_JS)
        self.assertIn("textContent", POSTER_JS)
        self.assertIn('link.download = "gnomon-profile.png"', POSTER_JS)
        self.assertNotIn("getComputedStyle", POSTER_JS)
        self.assertNotIn("data-theme", POSTER_JS)
        self.assertNotIn("CARD.scores", POSTER_JS)
        self.assertNotIn("#ED7379", POSTER_JS)
        self.assertNotIn("#D14E57", POSTER_JS)


if __name__ == "__main__":
    unittest.main()
