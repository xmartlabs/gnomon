"""Contract tests for the T9 Activity section."""

import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.sections.activity import render


def _context(stats, period=None):
    return ProfileContext(
        stats=stats, archetype="", quote="", scores={}, voice={},
        period=period or Period(
            "current_month", None, None, "2026-06", "Jun 2026 · in progress · 30 days", 30, 30),
        trend=None, moves=[], edges=[], caption="",
    )


def _stats():
    return {
        "volume": {"total_sessions": 3, "total_prompts": 20, "tool_calls_total": 100},
        "velocity": {
            "git_churn_total": 44,
            "tool_churn_edit_write": 31,
            "shell_authored_lines_est": 12,
        },
        "behavior": {
            "delegate_actions": 8,
            "fanout_median": 2,
            "background_tasks": 3,
            "scheduled_actions": 1,
            "error_recovery_ratio": 0.75,
            "error_rate_per_100_tools": 4.2,
            "tool_errors": 5,
            "iteration_depth_max": 18,
            "iteration_depth_mean": 4.5,
            "files_hammered_over_15x": 2,
        },
        "tools": {"top_tools": [["Bash<read>", 40]]},
        "stack": {"models": [["claude-opus-4-7", 60], ["gpt-5.4", 40]]},
    }


class TestProfileActivity(unittest.TestCase):
    def test_renders_period_counts_and_models(self):
        page = render(_context(_stats()))

        self.assertIn("Activity · Jun 2026", page)
        self.assertIn("3 sessions · 20 prompts · 100 tool calls", page)
        self.assertIn("Counts and readings — none of these are graded.", page)
        self.assertIn("How much did you ship?", page)
        for key in (
            "git_lines", "edit_write_lines", "shell_lines", "subagents",
            "errors", "max_edits", "go_to_tool",
        ):
            self.assertIn('class="activity-count" data-key="{}"'.format(key), page)
        self.assertIn('data-key="errors" data-value="5"', page)
        self.assertIn("errors · 75% recovered", page)
        self.assertIn("Roughly 4.2 per 100 tool calls", page)
        self.assertIn("18", page)
        self.assertIn("2 files went past 15 edits", page)

        self.assertIn('data-model="Opus 4.7" data-turns="60" data-pct="60"', page)
        self.assertIn('data-model="GPT 5.4" data-turns="40" data-pct="40"', page)
        self.assertLess(page.index('data-model="Opus 4.7"'), page.index('data-model="GPT 5.4"'))
        self.assertIn("Every model you used in Jun 2026, largest first.", page)
        self.assertIn("Bash&lt;read&gt;", page)

    def test_custom_window_uses_window_model_note(self):
        period = Period("custom", None, None, None, "this window", None, None)
        page = render(_context(_stats(), period))

        self.assertIn("Activity · this window", page)
        self.assertIn("Every model you used in this window, largest first.", page)

    def test_null_metrics_keep_unmeasured_wording(self):
        stats = _stats()
        stats["behavior"]["error_recovery_ratio"] = None
        stats["behavior"]["error_rate_per_100_tools"] = None
        stats["behavior"]["fanout_median"] = None
        stats["behavior"]["iteration_depth_max"] = None
        stats["behavior"]["iteration_depth_mean"] = None
        stats["tools"]["top_tools"] = []
        stats["stack"]["models"] = []
        page = render(_context(stats))

        self.assertGreaterEqual(page.count("not measured for this source"), 5)
        self.assertIn('data-key="errors"', page)
        self.assertIn('data-key="go_to_tool"', page)
        self.assertIn('class="gn-empty model-empty">not measured for this source', page)



class TestModelsUsedTopFive(unittest.TestCase):
    def test_shows_top_five_and_groups_the_rest_in_others(self):
        stats = _stats()
        stats["stack"] = {"models": [
            ["m-a", 500], ["m-b", 300], ["<synthetic>", 250], ["m-c", 100],
            ["m-d", 50], ["m-e", 30], ["m-f", 15], ["m-g", 5]]}
        page = render(_context(stats))
        models = page.split('id="models-used"', 1)[1]
        self.assertEqual(models.count('class="model-row"'), 6)
        self.assertIn('data-model="Others" data-turns="20"', models)
        self.assertIn("20 turns · 2 models", models)
        self.assertNotIn("synthetic", page)
        self.assertIn("1,000 turns", page)   # the total leaves "<synthetic>" out
        self.assertIn("Your 5 most-used models in Jun 2026", page)

    def test_five_or_fewer_models_have_no_others_row(self):
        page = render(_context(_stats()))
        self.assertNotIn('data-model="Others"', page)

if __name__ == "__main__":
    unittest.main()
