"""Contract tests for the MCP vs CLI and tool diversity readings."""

import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.sections.readings import render


def _context(stats):
    return ProfileContext(
        stats=stats, archetype="", quote="", scores={}, voice={},
        period=Period("all_history", None, None, None, "All history", None, None),
        trend=None, moves=[], edges=[], caption="",
    )


def _stats(agentic=True):
    stats = {
        "volume": {"total_prompts": 20, "total_instructions": 20},
        "behavior": {"actions_per_prompt": 8, "questions_asked": 2},
    }
    if agentic:
        stats["agentic"] = {
            "mcp_vs_cli": {
                "cli_calls": 100, "cli_distinct": 8,
                "mcp_calls": 0, "mcp_distinct": 0, "ratio": None,
            },
            "tool_diversity": {"distinct": 12, "entropy": 0.6},
        }
    return stats


class TestProfileReadings(unittest.TestCase):
    def test_renders_mcp_above_tool_diversity_as_ungraded(self):
        page = render(_context(_stats()))
        self.assertLess(page.index('data-reading="mcp_vs_cli"'),
                        page.index('data-reading="tool_diversity"'))
        self.assertEqual(page.count('data-graded="false"'), 2)
        self.assertIn("MCP vs CLI · described, not graded", page)
        self.assertIn("Tool diversity · described, not graded", page)
        self.assertIn("High range available, concentrated use. Not penalized.", page)
        self.assertNotIn("Steering", page)

    def test_zero_mcp_is_all_cli_with_zero_width_mcp_segment(self):
        page = render(_context(_stats()))
        self.assertIn("all-CLI (no MCP)", page)
        self.assertIn('class="mcp-segment mcp" style="width:0%"', page)

    def test_without_agentic_data_nothing_is_rendered(self):
        self.assertEqual(render(_context(_stats(agentic=False))), "")


if __name__ == "__main__":
    unittest.main()
