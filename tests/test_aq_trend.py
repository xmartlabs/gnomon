import unittest
from datetime import datetime

from gnomon.scoring.trend import aq_delta, build_aq_trend, month_bounds, trend_months


class AqTrendHelpersTest(unittest.TestCase):
    def test_trailing_months_and_bounds_are_calendar_aware(self):
        self.assertEqual(
            trend_months("2026-06"),
            ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
        )
        since, until = month_bounds("2026-02")
        self.assertEqual(since.strftime("%Y-%m-%d"), "2026-02-01")
        self.assertEqual(until.strftime("%Y-%m-%d"), "2026-03-01")
        self.assertIsNotNone(since.tzinfo)
        self.assertEqual((until - since).days, 28)

    def test_build_is_sparse_oldest_first_and_marks_multi_source_approximate(self):
        trend = build_aq_trend(
            "2026-06",
            {
                "2026-04": {"aq": {"aq_0_100": 61, "tier": "Proficient"},
                             "sources": ["claude"], "total_sessions": 2},
                "2026-06": {"aq": {"aq_0_100": 74, "tier": "Proficient"},
                             "sources": ["claude", "codex"], "total_sessions": 2},
            },
            now=datetime.fromisoformat("2026-06-30T12:00:00+00:00"),
        )
        self.assertEqual([point["month"] for point in trend["points"]], ["2026-04", "2026-06"])
        self.assertFalse(trend["points"][0]["approximate"])
        self.assertTrue(trend["points"][1]["approximate"])
        self.assertTrue(trend["points"][1]["in_progress"])

    def test_current_month_reuses_current_score_without_approximation(self):
        trend = build_aq_trend(
            "2026-06",
            {"2026-05": {"aq": {"aq_0_100": 71, "tier": "Proficient"},
                          "sources": ["claude", "codex"], "total_sessions": 2}},
            current_month="2026-06",
            current_stats={
                "agentic": {"aq_0_100": 74, "tier": "Proficient"},
                "corpus": {"sources": {"claude": {}, "codex": {}}},
                "volume": {"total_sessions": 2},
            },
            now=datetime.fromisoformat("2026-06-30T12:00:00+00:00"),
        )
        self.assertEqual(trend["points"][-1]["aq"], 74)
        self.assertFalse(trend["points"][-1]["approximate"])
        self.assertEqual(aq_delta(trend, "2026-06"), {
            "value": 3, "prev_month": "2026-05", "prev_label": "May",
        })

    def test_delta_requires_adjacent_month(self):
        trend = {"points": [{"month": "2026-04", "aq": 60, "label": "Apr"},
                             {"month": "2026-06", "aq": 74, "label": "Jun"}]}
        self.assertIsNone(aq_delta(trend, "2026-06"))


if __name__ == "__main__":
    unittest.main()
