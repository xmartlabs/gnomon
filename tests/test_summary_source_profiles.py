import unittest

import paxel
from gnomon.scoring.aggregate import score_by_source
from gnomon.scoring.inputs import build_scoring_inputs
from tests.test_smoke import _claude_turn, _run_claude_transcript


class TestProfilesBySourceAndUsage(unittest.TestCase):
    """build_summary emits precomputed per-source/aggregate profiles + per-tool usage share."""

    def _summary(self):
        rows = []
        for i in range(6):
            rows += _claude_turn(f"pbs-{i}", f"2026-03-1{i}T10:00:00.000Z", tool="Edit",
                                 file_path=f"/Users/demo/proj/f{i}.py",
                                 new_string="a\nb\nc", prompt=f"do thing {i}",
                                 usage={"input_tokens": 300, "output_tokens": 30,
                                        "cache_read_input_tokens": 5,
                                        "cache_creation_input_tokens": 1})
        stats = _run_claude_transcript(self, rows)
        return paxel.build_summary(stats), stats

    def test_profiles_by_source_shape(self):
        summary, _ = self._summary()
        pbs = summary["profiles_by_source"]
        self.assertIn("by_source", pbs)
        self.assertIn("aggregate", pbs)
        self.assertIn("claude", pbs["by_source"])
        prof = pbs["by_source"]["claude"]
        for key in ("aq", "scores", "archetype", "steering", "growth_edges",
                    "signature_moves", "model_usage"):
            self.assertIn(key, prof)
        self.assertIn("aq_0_100", prof["aq"])

    def test_per_source_model_usage_populated(self):
        """score_by_source leaves model_usage empty; build_summary fills it per source."""
        summary, _ = self._summary()
        mu = summary["profiles_by_source"]["by_source"]["claude"]["model_usage"]
        self.assertTrue(mu, "per-source model_usage should be populated from stack.models")
        self.assertIn("pct", mu[0])
        self.assertIn("model", mu[0])

    def test_source_usage_primary_and_pcts(self):
        summary, _ = self._summary()
        su = summary["source_usage"]
        self.assertEqual(su["primary_metric"], "prompts")
        self.assertIn("claude", su["by_source"])
        self.assertEqual(su["by_source"]["claude"]["prompts_pct"], 1.0)
        self.assertEqual(su["totals"]["prompts"], summary["context"]["total_prompts"])

    def test_source_usage_monthly_per_month(self):
        summary, _ = self._summary()
        sum_ = summary["source_usage_monthly"]
        self.assertIsInstance(sum_, list)
        self.assertTrue(sum_, "expected at least one month")
        for entry in sum_:
            self.assertIn("month", entry)
            self.assertEqual(entry["primary_metric"], "prompts")
            self.assertIn("claude", entry["by_source"])
        months = [e["month"] for e in sum_]
        self.assertEqual(months, sorted(months), "must be chronological")

    def test_per_source_model_usage_keeps_tokens(self):
        summary, _ = self._summary()
        mu = summary["profiles_by_source"]["by_source"]["claude"]["model_usage"]
        self.assertTrue(mu)
        self.assertTrue(any(e["tokens_input"] > 0 for e in mu),
                        "per-source model_usage should keep token counts")

    def test_pooled_profile_still_the_headline(self):
        summary, _ = self._summary()
        self.assertIn("profile", summary)
        self.assertIn("aq", summary["profile"])


class TestAggregatePlanningSessionPooling(unittest.TestCase):
    @staticmethod
    def _block(source, *, planning, eligible, unmeasured, tools, sessions):
        state = ("measured" if eligible and not unmeasured
                 else "partial" if eligible else "unmeasured")
        share = planning / eligible if eligible else None
        coverage = eligible / (eligible + unmeasured) if eligible else None
        stats = {
            "corpus": {"sources": {source: {}}},
            "volume": {"total_sessions": sessions, "total_prompts": sessions,
                       "tool_calls_total": tools, "thinking_blocks": 0},
            "velocity": {"active_hours": 1, "tool_churn_edit_write": 0},
            "behavior": {
                "planning_ratio_explore_to_doing": 0,
                "planning_skill_sessions": planning,
                "planning_skill_eligible_sessions": eligible,
                "planning_skill_unmeasured_sessions": unmeasured,
                "planning_skill_session_scope_state": state,
                "planning_skill_session_share": share,
                "planning_skill_session_coverage": coverage,
                "eligible_change_sessions": 0,
                "planned_eligible_sessions": 0,
                "ordered_facts_state": "unmeasured",
            },
            "stack": {"skills_all": [], "top_skills": [], "models": []},
            "tools": {},
        }
        return build_scoring_inputs(stats)

    def test_zero_tool_source_contributes_unmeasured_sessions_to_planning(self):
        measured = self._block(
            "claude", planning=1, eligible=1, unmeasured=0, tools=100, sessions=1)
        zero_tool = self._block(
            "gemini", planning=0, eligible=0, unmeasured=2, tools=0, sessions=2)
        result = score_by_source({
            "claude": {"window": measured},
            "gemini": {"window": zero_tool},
        })
        sub = next(
            item for item in result["aggregate"]["scores"]["planning"]["subs"]
            if item["label"] == "Planning skill practice")
        self.assertEqual((
            sub["planning_skill_sessions"],
            sub["planning_skill_eligible_sessions"],
            sub["planning_skill_unmeasured_sessions"],
            sub["scope_state"],
        ), (1, 1, 2, "partial"))
        self.assertEqual(sub["your_value"], 1.0)
        self.assertAlmostEqual(sub["coverage"], 1 / 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
