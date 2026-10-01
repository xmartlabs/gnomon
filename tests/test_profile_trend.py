"""Contract tests for the T5 AQ trend section."""

import unittest
from types import SimpleNamespace

from gnomon.output.profile.sections.trend import render


def _context(points):
    return SimpleNamespace(trend={"end_month": "2026-06", "points": points})


def _point(month, label, aq, in_progress=False, approximate=False):
    return {
        "month": month,
        "label": label,
        "aq": aq,
        "tier": "Proficient",
        "in_progress": in_progress,
        "approximate": approximate,
        "sources": ["claude"],
    }


class TestProfileTrend(unittest.TestCase):
    def test_renders_all_points_oldest_first_with_current_marker(self):
        page = render(_context([
            _point("2026-01", "Jan", 58),
            _point("2026-02", "Feb", 63),
            _point("2026-03", "Mar", 67),
            _point("2026-04", "Apr", 69),
            _point("2026-05", "May", 71),
            _point("2026-06", "Jun", 74, in_progress=True),
        ]))

        self.assertIn("<h2>AQ evolution by month</h2>", page)
        self.assertNotIn("6 months", page)
        self.assertEqual(page.count('class="trend-col"'), 6)
        self.assertIn(
            'data-month="2026-06" data-aq="74" data-in-progress="true" '
            'data-approximate="false"', page)
        self.assertIn("in progress", page)
        self.assertIn('style="height:81px"', page)
        self.assertIn("AQ by month: Jan AQ 58", page)
        self.assertIn("Jun AQ 74 in progress", page)
        self.assertNotIn("≈", page)

    def test_sparse_trend_renders_only_months_with_activity(self):
        page = render(_context([_point("2026-06", "Jun", 74, in_progress=True)]))

        self.assertIn("<h2>AQ evolution by month</h2>", page)
        self.assertEqual(page.count('class="trend-col"'), 1)
        self.assertIn('data-month="2026-06"', page)

    def test_approximate_points_render_like_any_other(self):
        page = render(_context([
            _point("2026-05", "May", 71, approximate=True),
            _point("2026-06", "Jun", 74, in_progress=True),
        ]))

        self.assertIn('<span class="trend-value">71</span>', page)
        self.assertNotIn("≈", page)
        self.assertNotIn("pproximate", page.replace('data-approximate=', ''))
        self.assertNotIn("AQ per month", page)

    def test_empty_trend_uses_the_profile_empty_state(self):
        page = render(SimpleNamespace(trend=None, stats={}))
        self.assertIn('<p class="gn-empty">No months with activity yet.</p>', page)
        self.assertNotIn('class="trend-next"', page)


def _aq_context(score):
    return SimpleNamespace(trend=None, stats={"agentic": {"aq_0_100": score}})


class TestNextLevel(unittest.TestCase):
    def test_points_to_the_next_tier(self):
        page = render(_aq_context(74))
        self.assertIn('data-next-tier="Advanced" data-points="1"', page)
        self.assertIn("1</span><span class=\"trend-next-unit\">point to Advanced", page)
        self.assertIn("Your AQ is 74. Advanced starts at 75.", page)

    def test_tier_floor_counts_as_reaching_it(self):
        page = render(_aq_context(60))
        self.assertIn('data-next-tier="Advanced" data-points="15"', page)
        self.assertIn("Proficient · 60", page)

    def test_top_tier_has_no_next_level(self):
        page = render(_aq_context(91))
        self.assertIn('data-next-tier=""', page)
        self.assertIn("Elite is the top level.", page)


if __name__ == "__main__":
    unittest.main()
