"""Contract tests for the T8 AQ breakdown."""

import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.brand import CAPTION
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.sections.breakdown import _axis_value, render


def _context(agentic, edges=None, stats=None):
    payload = dict(stats or {})
    payload["agentic"] = agentic
    return ProfileContext(
        stats=payload, archetype="", quote="", scores={}, voice={},
        period=Period("all_history", None, None, None, "All history", None, None),
        trend=None, moves=[], edges=edges or [], caption=CAPTION,
    )


def _aq(not_applicable=None):
    axes = {
        "Breadth": [
            ("Orchestration", .81), ("Skill fluency", .52),
            ("Tool command (MCP + CLI)", .67), ("Discipline", .44),
        ],
        "Craft": [
            ("Verification", .73), ("Grounding", .62),
            ("Context Intelligence", .58), ("Compounding", .49),
        ],
        "Efficiency": [("Steering leverage", .40), ("Recovery", .91)],
        "Savvy": [("Model mix", .76), ("Token economy", .68)],
    }
    pillars = []
    for index, name in enumerate(("Breadth", "Craft", "Efficiency", "Savvy")):
        dropped = (not_applicable or {}).get(name, [])
        pillars.append({
            "name": name,
            "weight": (30, 35, 20, 15)[index],
            "score": (61, 59, 66, 72)[index],
            "axes": [{"name": axis, "normalized_score": value}
                     for axis, value in axes[name] if axis not in dropped],
            "not_applicable": dropped,
        })
    return {"aq_0_100": 63, "tier": "Proficient", "pillars": pillars}


class TestProfileBreakdown(unittest.TestCase):
    def test_axis_value_uses_normalized_score_on_0_to_100_scale(self):
        self.assertEqual(_axis_value({"normalized_score": .812}), "81")
        self.assertEqual(_axis_value({"normalized_score": 0}), "0")

    def test_renders_four_pillars_and_all_twelve_axes_without_weights(self):
        page = render(_context(_aq()))
        self.assertEqual(page.count('class="aq-pillar"'), 4)
        self.assertEqual(page.count('class="aq-axis"'), 12)
        self.assertEqual(page.count('class="gn-bar"'), 12)
        self.assertIn("Agentic Quotient · 4 pillars</h2>", page)
        self.assertNotIn("0–100 scale", page)
        self.assertIn("81", page)
        self.assertNotIn("30 weight", page)
        self.assertNotIn("35 weight", page)
        self.assertNotIn("20 weight", page)
        self.assertNotIn("15 weight", page)
        self.assertNotIn("<details", page)
        self.assertNotIn("<summary", page)

    def test_marks_edge_axis(self):
        page = render(_context(
            _aq(), edges=[{"n": "02", "axis": "Verification"}]))
        self.assertIn('data-axis="Verification" data-measured="true" data-edge="02"', page)
        self.assertIn("EDGE 02", page)

    def test_merges_dropped_axis_back_in_canonical_order(self):
        page = render(_context(_aq({"Savvy": ["Model mix"]})))
        self.assertIn(
            'data-axis="Model mix" data-measured="false" data-edge=""', page)
        self.assertIn(
            '<span class="gn-empty aq-axis-unmeasured">not measured for this source</span>', page)
        self.assertLess(page.index('data-axis="Model mix"'), page.index('data-axis="Token economy"'))

    def test_cursor_savvy_note_is_a_pillar_note(self):
        page = render(_context(
            _aq({"Savvy": ["Model mix"]}),
            stats={"corpus": {"sources": {"cursor": {}}}},
        ))
        self.assertIn("Model mix — not graded for Cursor", page)
        self.assertIn("billing plan", page)


if __name__ == "__main__":
    unittest.main()
