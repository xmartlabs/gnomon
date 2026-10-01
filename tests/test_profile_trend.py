"""Contract tests for the T5 AQ trend section."""

import unittest
from types import SimpleNamespace

from gnomon.output.profile.sections.trend import CSS, render


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

        self.assertIn("AQ by month · 6 months", page)
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

        self.assertIn("AQ by month · 1 month", page)
        self.assertEqual(page.count('class="trend-col"'), 1)
        self.assertIn('data-month="2026-06"', page)

    def test_marks_approximate_points_and_explains_the_mark(self):
        page = render(_context([
            _point("2026-05", "May", 71, approximate=True),
            _point("2026-06", "Jun", 74, in_progress=True),
        ]))

        self.assertIn('data-approximate="true"', page)
        self.assertIn('<span class="trend-value">≈71</span>', page)
        self.assertIn("Approximate values combine multiple sources.", page)
        self.assertIn('border-top: 1px solid var(--rule-default)', CSS)

    def test_empty_trend_uses_the_profile_empty_state(self):
        self.assertEqual(
            render(SimpleNamespace(trend=None)),
            '<p class="gn-empty">No months with activity yet.</p>',
        )


if __name__ == "__main__":
    unittest.main()
