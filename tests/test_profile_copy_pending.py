"""Regression tests for the confirmed T16 profile-only copy changes."""

import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.sections.diagnosis import render as render_diagnosis
from gnomon.output.profile.sections.readings import render as render_readings
from gnomon.scoring.archetype import pick_archetype
from gnomon.scoring.insights import growth_edges_structured


def _context(edges):
    stats = {
        "volume": {"total_sessions": 2, "total_prompts": 4},
        "agentic": {"pillars": [{"name": "Craft", "axes": []}]},
    }
    return ProfileContext(
        stats=stats, archetype="", quote="", scores={}, voice={},
        period=Period("current_month", None, None, "2026-06", "Jun 2026", 20, 30),
        trend=None, moves=[], edges=edges, caption="",
    )


def _reading_context(cli_calls, mcp_calls):
    stats = {
        "volume": {"total_prompts": 1, "total_instructions": 1},
        "behavior": {"actions_per_prompt": 1, "questions_asked": 0},
        "agentic": {
            "mcp_vs_cli": {
                "cli_calls": cli_calls,
                "cli_distinct": 1,
                "mcp_calls": mcp_calls,
                "mcp_distinct": 1,
                "ratio": round(cli_calls / mcp_calls, 1) if mcp_calls else None,
            },
            "tool_diversity": {"distinct": 1, "entropy": 0.0},
        },
    }
    return ProfileContext(
        stats=stats, archetype="", quote="", scores={}, voice={},
        period=Period("all_history", None, None, None, "All history", None, None),
        trend=None, moves=[], edges=[], caption="",
    )


class TestProfileCopyPending(unittest.TestCase):
    def test_archetype_names_the_thinnest_pillar(self):
        stats = {
            "agentic": {
                "tier": "Advanced",
                "aq_0_100": 80,
                "pillars": [
                    {"name": "Breadth", "score": 70},
                    {"name": "Craft", "score": 55},
                ],
            },
        }
        _, quote = pick_archetype(stats, {})
        self.assertIn("Your thinnest pillar is craft", quote)
        self.assertNotIn("thinnest axis", quote)

    def test_profile_strips_aq_edge_opener_without_mutating_summary_advice(self):
        edge = {
            "n": "01",
            "axis": "Orchestration",
            "dimension": None,
            "title": "Run agents in parallel, not in series",
            "advice_html": "<b>Breadth · Orchestration</b> is your thinnest AQ signal. Do this.",
        }
        page = render_diagnosis(_context([edge]))
        self.assertNotIn("is your thinnest AQ signal", page)
        self.assertEqual(
            edge["advice_html"],
            "<b>Breadth · Orchestration</b> is your thinnest AQ signal. Do this.",
        )

    def test_mcp_leading_reading_uses_neutral_copy(self):
        page = render_readings(_reading_context(8, 10))
        self.assertIn("Ratio <b>0.8:1</b> — MCP carries more of your tool traffic this month.", page)
        self.assertNotIn("CLI-first", page)

    def test_cli_leading_reading_keeps_cli_first_copy(self):
        page = render_readings(_reading_context(10, 8))
        self.assertIn("CLI-first", page)

    def test_structured_advice_contract_is_unchanged_by_profile_rendering(self):
        stats = {
            "volume": {"total_sessions": 2, "total_prompts": 4},
            "behavior": {"error_rate_per_100_tools": 0, "shell_test_runs": 0},
            "velocity": {},
            "stack": {"top_skills": [], "skills_all": []},
            "agentic": {"pillars": []},
        }
        scores = {"Planning": 8, "Execution": 8, "Engineering": 8}
        before = growth_edges_structured(stats, scores)
        edge = {
            "n": "01",
            "axis": None,
            "dimension": None,
            "title": "Balanced edge",
            "advice_html": "Go deeper.",
        }
        render_diagnosis(_context([edge]))
        after = growth_edges_structured(stats, scores)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
