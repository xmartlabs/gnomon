"""Tests for the local profile diagnosis section and edge origin metadata."""

import unittest

from gnomon.cli.period import Period
from gnomon.output.profile.context import ProfileContext
from gnomon.output.profile.sections.diagnosis import render
from gnomon.scoring.insights import _EDGE_DIMENSION, _growth_edges_pool


def _stats(skills=None, behavior=None):
    return {
        "volume": {"total_sessions": 10, "total_prompts": 100},
        "behavior": dict({
            "error_rate_per_100_tools": 0,
            "iteration_depth_max": 0,
            "files_hammered_over_15x": 0,
            "shell_test_runs": 0,
        }, **(behavior or {})),
        "velocity": {},
        "stack": {
            "top_skills": skills or [],
            "skills_all": skills or [],
        },
        "agentic": {
            "pillars": [{
                "name": "Breadth",
                "axes": [{"name": "Orchestration"}],
            }],
        },
    }


def _context(stats=None, moves=None, edges=None):
    return ProfileContext(
        stats or _stats(), archetype="", quote="", scores={}, voice={},
        period=Period("current_month", None, None, "2026-06", "Jun 2026", 20, 30),
        trend=None, moves=moves or [], edges=edges or [], caption="",
    )


class TestDiagnosisRender(unittest.TestCase):
    def test_renders_at_most_three_moves_and_edges_with_origins(self):
        moves = [{"tag": str(i), "title": "Move", "evidence_html": "Evidence"}
                 for i in range(4)]
        edges = [
            {"n": "01", "axis": "Orchestration", "dimension": None,
             "title": "AQ edge", "advice_html": "<b>Breadth · Orchestration</b> is your thinnest AQ signal. Do this."},
            {"n": "02", "axis": None, "dimension": "Engineering",
             "title": "gstack edge", "advice_html": "Run a quality pass."},
            {"n": "03", "axis": None, "dimension": None,
             "title": "Balanced edge", "advice_html": "Go deeper."},
            {"n": "04", "axis": None, "dimension": "Planning",
             "title": "Ignored edge", "advice_html": "Ignored."},
        ]

        page = render(_context(moves=moves, edges=edges))

        self.assertEqual(page.count('class="move"'), 3)
        self.assertEqual(page.count('class="edge"'), 3)
        self.assertIn('data-n="01" data-axis="Orchestration"', page)
        self.assertIn("Breadth · Orchestration", page)
        self.assertIn("gstack · Engineering", page)
        self.assertIn("gstack · Balanced", page)
        self.assertNotIn("is your thinnest AQ signal", page)
        self.assertIn("How you work", page)
        self.assertIn("What to work on", page)

    def test_empty_columns_explain_the_missing_signal(self):
        page = render(_context(moves=[], edges=[]))

        self.assertIn("No signature moves fired this month", page)
        self.assertIn("10 sessions and 100 prompts", page)
        self.assertIn("Nothing flagged to work on this month", page)
        self.assertIn('class="gn-empty"', page)


class TestGrowthEdgeDimensions(unittest.TestCase):
    def test_confirmed_pending_dimension_mapping_is_isolated(self):
        self.assertEqual(_EDGE_DIMENSION["Add a reflex"], "Engineering")
        self.assertEqual(_EDGE_DIMENSION["Stop the grind"], "Engineering")

    def test_gstack_edges_have_dimensions_and_aq_edges_do_not(self):
        stats = _stats(
            skills=[("code-review", 60)],
            behavior={
                "error_rate_per_100_tools": 7,
                "iteration_depth_max": 50,
                "files_hammered_over_15x": 15,
            },
        )
        stats["agentic"]["pillars"][0]["axes"][0].update({
            "weight": 33, "score": 3, "signals": {},
        })
        pool = _growth_edges_pool(stats, {"Execution": 8, "Planning": 8, "Engineering": 8})

        by_eyebrow = {item["eyebrow"]: item for item in pool}
        self.assertEqual(by_eyebrow["Stop the grind"]["dimension"], "Engineering")
        self.assertIsNone(by_eyebrow["Multiply yourself"]["dimension"])

    def test_balanced_fallback_is_labeled_balanced(self):
        pool = _growth_edges_pool(_stats(), {"Execution": 8, "Planning": 8, "Engineering": 8})
        self.assertEqual(pool[0]["eyebrow"], "Go deeper")
        self.assertIsNone(pool[0]["dimension"])

    def test_closest_edge_uses_the_worst_gstack_dimension(self):
        pool = _growth_edges_pool(_stats(), {"Execution": 5, "Planning": 8, "Engineering": 8})
        self.assertEqual(pool[0]["eyebrow"], "Closest to an edge")
        self.assertEqual(pool[0]["dimension"], "Execution")


if __name__ == "__main__":
    unittest.main()
