import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xl_ai_insights


def _full_summary():
    return {
        "context": {
            "date_range": ["2026-01-01", "2026-06-01"],
            "sources": ["claude", "codex"],
            "total_sessions": 42,
        },
        "planning_ratio_explore_to_doing": 0.62,
        "errors": {
            "error_recovery_ratio": 0.87,
            "error_rate_per_100_tools": 3.5,
        },
        "iteration_depth": {
            "mean": 4.2,
            "median": 3.0,
            "p90": 11,
            "max": 28,
            "files_over_15x": 2,
        },
        "churn": {
            "git_churn_total": 1840,
            "tool_churn_edit_write": 950,
        },
        "orchestration": {
            "fanout_median": 3.5,
            "delegate_actions": 120,
        },
        "compounding_writes": 17,
        "ecosystem": {
            "skills_distinct": 39,
            "skills_total": 8000,
            "mcp_servers_distinct": 12,
        },
    }


class TestFormatSummaryQuiet(unittest.TestCase):
    def test_quiet_returns_empty_string(self):
        result = xl_ai_insights._format_summary(_full_summary(), quiet=True)
        self.assertEqual(result, "")

    def test_quiet_false_is_default(self):
        # Calling without quiet should return a non-empty string
        result = xl_ai_insights._format_summary(_full_summary())
        self.assertNotEqual(result, "")


class TestFormatSummaryContent(unittest.TestCase):
    def setUp(self):
        self.out = xl_ai_insights._format_summary(_full_summary())

    def test_session_count_present(self):
        self.assertIn("42", self.out)

    def test_date_range_present(self):
        self.assertIn("2026-01-01", self.out)
        self.assertIn("2026-06-01", self.out)

    def test_planning_ratio_as_percent(self):
        # 0.62 → 62%
        self.assertIn("62%", self.out)

    def test_error_recovery_as_percent(self):
        # 0.87 → 87%
        self.assertIn("87%", self.out)

    def test_error_rate_labeled(self):
        self.assertIn("3.5 errors / 100 tools", self.out)

    def test_iteration_depth_mean_and_p90(self):
        self.assertIn("4.2", self.out)
        self.assertIn("p90 11", self.out)

    def test_churn_git(self):
        self.assertIn("1840", self.out)
        self.assertIn("(git)", self.out)

    def test_orchestration_fanout_and_delegate(self):
        self.assertIn("3.5", self.out)
        self.assertIn("120", self.out)

    def test_compounding_writes(self):
        self.assertIn("17", self.out)

    def test_ecosystem_skills_and_mcp(self):
        self.assertIn("39", self.out)
        self.assertIn("12", self.out)

    def test_only_two_percent_signs(self):
        # Exactly the two real ratios render as %; everything else stays labeled
        pct_count = self.out.count("%")
        self.assertEqual(pct_count, 2, f"Expected 2 '%%' occurrences, got {pct_count}:\n{self.out}")


class TestFormatSummaryDefensive(unittest.TestCase):
    def test_empty_dict_does_not_crash(self):
        result = xl_ai_insights._format_summary({})
        self.assertIsInstance(result, str)

    def test_missing_context_keys(self):
        result = xl_ai_insights._format_summary({"context": {}})
        self.assertIsInstance(result, str)

    def test_missing_errors_block(self):
        s = _full_summary()
        del s["errors"]
        result = xl_ai_insights._format_summary(s)
        self.assertNotIn("recovery", result.lower())

    def test_missing_iteration_depth(self):
        s = _full_summary()
        del s["iteration_depth"]
        result = xl_ai_insights._format_summary(s)
        self.assertNotIn("edits/file", result)

    def test_missing_orchestration(self):
        s = _full_summary()
        del s["orchestration"]
        result = xl_ai_insights._format_summary(s)
        self.assertNotIn("fanout", result)

    def test_none_values_in_errors(self):
        # Both ratio fields set to None: only error block lines should be suppressed
        s = _full_summary()
        s["errors"] = {"error_recovery_ratio": None, "error_rate_per_100_tools": None}
        result = xl_ai_insights._format_summary(s)
        self.assertIsInstance(result, str)
        self.assertNotIn("Error recovery", result)
        self.assertNotIn("errors / 100 tools", result)

    def test_partial_ecosystem(self):
        s = _full_summary()
        s["ecosystem"] = {"skills_distinct": 5}
        result = xl_ai_insights._format_summary(s)
        self.assertIn("5 skills", result)
        self.assertNotIn("MCP", result)


if __name__ == "__main__":
    unittest.main()
