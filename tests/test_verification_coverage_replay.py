"""F1 regression — a replayed pre-v18 (v17) payload must not fabricate Verification
coverage 0.0 when `test_covered_change_sessions` is genuinely ABSENT.

v17's `ordered_facts_state`/`eligible_change_sessions` already existed before v18 added
the coverage numerator (`test_covered_change_sessions`), so a legacy payload can have
`ordered_facts_state == "measured"` and `eligible_change_sessions > 0` while carrying no
`test_covered_change_sessions` key at all. Coercing that ABSENCE to 0 (either in
`build_scoring_inputs` or in `compute_aq` itself) is indistinguishable from a real
MEASURED zero and stamps a corrupted 0.0 coverage on a payload that never measured
coverage — see `gnomon/scoring/inputs.py` and `gnomon/scoring/aq.py`.

Both code paths must preserve the None/absent vs 0/measured distinction:
  - `build_scoring_inputs` (gnomon/scoring/inputs.py) — the live/monthly scoring-input
    builder.
  - `stats_from_scoring_block` -> `compute_aq` (the replay path, gnomon/scoring/profiles.py
    + gnomon/scoring/replay.py) — reads a persisted block's `behavior` dict verbatim, so
    whatever `build_scoring_inputs` wrote (or a hand-built legacy block) travels straight
    into `compute_aq`.
"""
import copy
import unittest

from gnomon.scoring.aq import MIN_ELIGIBLE_SESSIONS, compute_aq
from gnomon.scoring.inputs import build_scoring_inputs
from gnomon.scoring.profiles import stats_from_scoring_block

_MODELS = [["model-a", 30], ["model-b", 10]]
_MISSING = object()


def _v17_window_block(*, eligible, review_uses, test_covered=_MISSING):
    """A pre-v18 scoring-input `window` block, in `build_scoring_inputs`' persisted shape.

    `ordered_facts_state` and `eligible_change_sessions` are already "v17" fields (they
    predate the v18 coverage numerator), so this block is exactly what a v17 CLI run would
    have persisted: measured ordered facts, a real eligible-session count, review-skill
    evidence — and, unless `test_covered` is given, NO `test_covered_change_sessions` key
    at all (the field did not exist yet)."""
    behavior = {
        "planning_ratio_explore_to_doing": 0.5, "actions_per_prompt": 8.0,
        "questions_asked": 1, "error_recovery_ratio": 0.5,
        "error_rate_per_100_tools": 2.0, "api_errors_retries": 0,
        "fanout_median": 1, "max_session_fanout": 1, "parallel_dispatch_turns": 0,
        "delegating_sessions": 1, "parallel_session_share": 0.0,
        "shell_test_runs": 0, "plan_sessions": 0,
        "planning_skill_sessions": 0, "planning_skill_eligible_sessions": 0,
        "planning_skill_unmeasured_sessions": 0,
        "planning_skill_session_scope_state": "unmeasured",
        "planning_skill_session_share": None,
        "planning_skill_session_coverage": None,
        "eligible_change_sessions": eligible,
        "planned_eligible_sessions": 0,
        "evidence_eligible_sessions": 0,
        "ordered_facts_state": "measured",
        "sidechain_label_state": "measured",
        "linked_model_pairs": [], "linked_model_routing_state": "unsupported",
        "delegate_actions": 1, "background_tasks": 0, "iteration_depth_mean": 2.0,
        "iteration_depth_p90": 3, "iteration_depth_max": 4,
        "files_hammered_over_15x": 0, "no_tool_activity": False,
        "orchestratable_sessions": 0, "delegated_orchestratable_sessions": 0,
    }
    if test_covered is not _MISSING:
        behavior["test_covered_change_sessions"] = test_covered
    skills = [["code-review", review_uses]] if review_uses else []
    return {
        "source": "claude",
        "scoring_inputs_version": 5,
        "corpus": {"sources": {"claude": {}}},
        "volume": {"total_sessions": 20, "total_prompts": 60,
                   "tool_calls_total": 500, "thinking_blocks": 0},
        "velocity": {"active_hours": 10.0, "tool_churn_edit_write": 1000,
                     "shell_authored_lines_est": 100},
        "behavior": behavior,
        "stack": {
            "skills_distinct": 1 if review_uses else 0, "skills_total": review_uses,
            "compounding_writes": 0,
            "subagent_types_distinct": 1, "max_session_subagent_types": 1,
            "subagent_types": [],
            "top_skills": [list(p) for p in skills],
            "skills_all": [list(p) for p in skills],
            "models": copy.deepcopy(_MODELS),
        },
        "tools": {
            "agent_calls": 1, "mcp_servers_distinct": 1, "clis_distinct": 1,
            "toolsearch_calls": 0, "task_tool_calls": 0, "cli_calls": 1,
            "mcp_calls": 1, "tool_diversity": 5, "tool_entropy_normalized": 0.5,
            "mcp_knowledge_calls": 0, "mcp_knowledge_servers": 0,
            "mcp_knowledge_server_names": [], "mcp_grounded_sessions": 0,
            "mcp_write_sessions": 0, "mcp_subcategory_breakdown": {}, "top_tools": [],
        },
        "token_usage": {"by_model": []},
    }


def _verification_axis(agentic):
    craft = next(p for p in agentic["pillars"] if p["name"] == "Craft")
    return next(a for a in craft["axes"] if a["name"] == "Verification")


class LegacyReplayCoverageAbsenceTests(unittest.TestCase):
    """The replay path: a hand-built/persisted v17 block -> stats_from_scoring_block ->
    compute_aq must never fabricate a 0.0 coverage half from an absent field."""

    def test_absent_field_survives_replay_as_na_not_zero(self):
        block = _v17_window_block(eligible=5, review_uses=6)  # NO test_covered key
        stats = stats_from_scoring_block(block)
        # Absence must travel through stats_from_scoring_block as None, not 0.
        self.assertIsNone(stats["behavior"].get("test_covered_change_sessions"))

        agentic = compute_aq(stats)
        verification = _verification_axis(agentic)

        # Coverage was NOT scored (dropped -> renormalized onto review_skills alone), so
        # Verification's only live term is the review-skill rate, which saturates at 1.0
        # for 6 review-skill uses over 500 tool calls (well above REVIEW_SKILLS_PER_CALL_
        # TARGET). A fabricated 0.0 coverage would instead average in at 0.5 weight and
        # halve this normalized score.
        self.assertEqual(verification["normalized_score"], 1.0)
        self.assertIn("partial_terms", verification)
        self.assertEqual(verification["partial_terms"]["scored"], 1)
        self.assertEqual(verification["partial_terms"]["total"], 2)
        self.assertIsNone(verification["signals"]["test_coverage"])
        # The raw diagnostic must publish the true absence, not a fabricated 0.
        self.assertIsNone(verification["signals"]["test_covered_change_sessions"])

    def test_present_measured_zero_still_scores_zero_coverage(self):
        """A REAL measured zero (the field present, value 0) must still score 0.0
        coverage — absence and a genuine zero are different facts and must not collapse
        to the same treatment in the opposite direction either."""
        block = _v17_window_block(eligible=5, review_uses=6, test_covered=0)
        stats = stats_from_scoring_block(block)
        self.assertEqual(stats["behavior"].get("test_covered_change_sessions"), 0)

        agentic = compute_aq(stats)
        verification = _verification_axis(agentic)

        # Both terms are now live (coverage measured at 0.0, review at 1.0), so the
        # 50/50 weighted mean is 0.5 — proving a present 0 IS scored, unlike an absence.
        self.assertEqual(verification["normalized_score"], 0.5)
        self.assertNotIn("partial_terms", verification)
        self.assertEqual(verification["signals"]["test_coverage"], 0.0)
        self.assertEqual(verification["signals"]["test_covered_change_sessions"], 0)


class EvidenceFloorF8Tests(unittest.TestCase):
    """F8 — Verification coverage and Context Intelligence both need
    MIN_ELIGIBLE_SESSIONS eligible sessions before a per-session coverage
    ratio is a defensible measurement. `eligible=4` here is a genuinely
    MEASURED 100%/0% ratio (not an absent field, unlike the class above) but
    still below the floor, so both terms must drop (None -> renormalized)
    rather than publish a ratio computed from 4 or fewer sessions."""

    def test_verification_coverage_dropped_below_floor_scores_review_only(self):
        below = _v17_window_block(eligible=MIN_ELIGIBLE_SESSIONS - 1,
                                  review_uses=6, test_covered=MIN_ELIGIBLE_SESSIONS - 1)
        stats = stats_from_scoring_block(below)

        agentic = compute_aq(stats)
        verification = _verification_axis(agentic)

        # Coverage dropped by the floor -> only the review-skill rate term is live,
        # same shape as the absent-field case above (saturates at 1.0 for 6 uses/500
        # tool calls, well above REVIEW_SKILLS_PER_CALL_TARGET).
        self.assertEqual(verification["normalized_score"], 1.0)
        self.assertIn("partial_terms", verification)
        self.assertEqual(verification["partial_terms"]["scored"], 1)
        self.assertIsNone(verification["signals"]["test_coverage"])
        # The raw diagnostic still discloses the real (measured, not absent) counts.
        self.assertEqual(
            verification["signals"]["test_covered_change_sessions"],
            MIN_ELIGIBLE_SESSIONS - 1)
        self.assertEqual(verification["signals"]["eligible_change_sessions"],
                         MIN_ELIGIBLE_SESSIONS - 1)

    def test_verification_coverage_scored_at_floor(self):
        at = _v17_window_block(eligible=MIN_ELIGIBLE_SESSIONS,
                               review_uses=6, test_covered=MIN_ELIGIBLE_SESSIONS)
        stats = stats_from_scoring_block(at)

        agentic = compute_aq(stats)
        verification = _verification_axis(agentic)

        # AT the floor (not below it), a real 100% coverage is scored: both terms
        # live at 1.0, so the 50/50 mean is 1.0 too (same number, different reason —
        # confirmed by partial_terms being absent, i.e. fully measured).
        self.assertEqual(verification["normalized_score"], 1.0)
        self.assertNotIn("partial_terms", verification)
        self.assertEqual(verification["signals"]["test_coverage"], 1.0)

    def test_context_intelligence_na_below_floor(self):
        below = _v17_window_block(eligible=MIN_ELIGIBLE_SESSIONS - 1, review_uses=6)
        stats = stats_from_scoring_block(below)

        agentic = compute_aq(stats)
        craft = next(p for p in agentic["pillars"] if p["name"] == "Craft")
        axis_names = [a["name"] for a in craft["axes"]]
        self.assertNotIn("Context Intelligence", axis_names)
        self.assertIn("Context Intelligence", craft.get("not_applicable", []))


class ClampDiagnosticF9Tests(unittest.TestCase):
    """F9 — the SCORED verification_coverage term was already clamped via
    sat(_, 1.0), but the published `signals.test_coverage` diagnostic used
    the raw ratio directly and could exceed 1.0 for a malformed/replayed
    block where `test_covered_change_sessions` > `eligible_change_sessions`
    (a shape the accumulator's own aggregate_ordered never produces, but a
    replayed/foreign payload is not guaranteed to respect)."""

    def test_covered_greater_than_eligible_clamps_diagnostic_and_score(self):
        # eligible=5 (>= MIN_ELIGIBLE_SESSIONS, so F8's floor does not also
        # drop the term and mask this), test_covered=8 -- malformed: covered
        # > eligible, raw ratio would be 8/5 = 1.6.
        block = _v17_window_block(
            eligible=MIN_ELIGIBLE_SESSIONS, review_uses=6,
            test_covered=MIN_ELIGIBLE_SESSIONS + 3)
        stats = stats_from_scoring_block(block)

        agentic = compute_aq(stats)
        verification = _verification_axis(agentic)

        self.assertLessEqual(verification["signals"]["test_coverage"], 1.0)
        self.assertEqual(verification["signals"]["test_coverage"], 1.0)
        # The scored term was already implicitly clamped by sat(_, 1.0); this
        # pins that it stays clamped once the diagnostic is fixed too.
        self.assertEqual(verification["normalized_score"], 1.0)


class BuildScoringInputsAbsencePreservationTests(unittest.TestCase):
    """`build_scoring_inputs` itself must not coerce an absent numerator to 0."""

    def test_build_scoring_inputs_preserves_absence_as_none(self):
        legacy_stats = {
            "corpus": {"sources": {"claude": {}}},
            "volume": {"total_sessions": 1, "tool_calls_total": 10},
            "velocity": {},
            "behavior": {
                "ordered_facts_state": "measured",
                "eligible_change_sessions": 5,
                # no test_covered_change_sessions key at all
            },
            "stack": {}, "tools": {},
        }
        block = build_scoring_inputs(legacy_stats)
        self.assertIsNone(block["behavior"]["test_covered_change_sessions"])

    def test_build_scoring_inputs_preserves_a_real_measured_zero(self):
        stats_with_zero = {
            "corpus": {"sources": {"claude": {}}},
            "volume": {"total_sessions": 1, "tool_calls_total": 10},
            "velocity": {},
            "behavior": {
                "ordered_facts_state": "measured",
                "eligible_change_sessions": 5,
                "test_covered_change_sessions": 0,
            },
            "stack": {}, "tools": {},
        }
        block = build_scoring_inputs(stats_with_zero)
        self.assertEqual(block["behavior"]["test_covered_change_sessions"], 0)


if __name__ == "__main__":
    unittest.main()
