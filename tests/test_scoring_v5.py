import unittest
import json
import math
import os
import tempfile
from copy import deepcopy

from gnomon.cli.accumulator import Accumulator, derive_ordered_behavior
from gnomon.scoring.aq import (
    CONTEXT_INTELLIGENCE_TARGET,
    ORCHESTRATION_FREQUENCY_TARGET,
    PLANNING_PRACTICE_TARGET,
    PLANNING_TARGET,
    MIN_ELIGIBLE_SESSIONS,
    compute_aq,
    score_linked_routing,
)
from gnomon.scoring.versioning import SCORE_CONTRACT_ID
from gnomon.scoring.aggregate import blend_model_mix_components
from gnomon.scoring.aggregate import _blend_aq
from gnomon.scoring.versioning import IncompatibleScoreContract
from gnomon.scoring.inputs import build_scoring_inputs
from gnomon.scoring.gstack import (
    _planning_skill_evidence, compute_scores, score_breakdown,
)
from gnomon.scoring.aggregate import score_by_source
from gnomon.sources.codex import _codex_events, _codex_tool
from gnomon.sources import iter_events


def _v5_scoring_stats(source="claude", planned=6, evidence=6):
    """Rich, non-saturated stats for v5 contribution and capability regressions."""
    return {
        "corpus": {"sources": {source: {}}},
        "volume": {"total_sessions": 10, "total_prompts": 10,
                   "tool_calls_total": 100, "thinking_blocks": 30},
        "velocity": {"active_hours": 2, "tool_churn_edit_write": 500},
        "tools": {
            "agent_calls": 3, "mcp_servers_distinct": 3, "clis_distinct": 5,
            "toolsearch_calls": 1, "task_tool_calls": 0,
            "cli_calls": 20, "mcp_calls": 10, "tool_diversity": 6,
            "tool_entropy_normalized": 0.5,
        },
        "stack": {
            "skills_distinct": 1, "skills_total": 2,
            "top_skills": [("code-review", 2)],
            "skills_all": [("code-review", 2)],
            "subagent_types_distinct": 2, "max_session_subagent_types": 2,
            "compounding_writes": 1,
            "models": [("model-primary", 8), ("model-secondary", 2)],
        },
        "behavior": {
            "fanout_median": 2, "shell_test_runs": 1,
            "planning_ratio_explore_to_doing": 0.3,
            "actions_per_prompt": 8, "error_recovery_ratio": 0.8,
            "api_errors_retries": 1, "planning_skill_sessions": 1,
            "eligible_change_sessions": 10,
            "planned_eligible_sessions": planned,
            "evidence_eligible_sessions": evidence,
            "ordered_facts_state": "measured",
            "linked_model_routing_state": "unsupported",
            "linked_model_pairs": [],
            "delegate_actions": 1, "background_tasks": 0,
            "iteration_depth_mean": 4, "iteration_depth_p90": 6,
            "iteration_depth_max": 8, "files_hammered_over_15x": 1,
            "error_rate_per_100_tools": 5, "no_tool_activity": False,
        },
    }


class TestOrderedBehavior(unittest.TestCase):
    def test_requires_write_and_two_files_or_ten_substantive_calls(self):
        # C6 raised the todo-step floor from >=2 to >=3 (anti-theater); use 3
        # distinct steps here so this stays a "planned" fixture.
        facts = derive_ordered_behavior([
            {"name": "Read", "target": "a.py"},
            {"name": "TodoWrite", "items": ["inspect", "change", "verify"]},
            {"name": "Edit", "target": "a.py"},
            {"name": "Write", "target": "b.py"},
        ])
        self.assertEqual(facts, {"eligible": True, "planned": True, "evidence": True})

        trivial = derive_ordered_behavior([
            *({"name": "Bash"} for _ in range(8)),
            {"name": "Edit", "target": "a.py"},
        ])
        self.assertEqual(trivial, {"eligible": False, "planned": False, "evidence": False})

    def test_deduplicates_reads_and_rejects_late_plan_and_evidence(self):
        events = [
            {"name": "Edit", "target": "a.py"},
            {"name": "Read", "target": "b.py"},
            {"name": "TodoWrite", "items": ["one", "two"]},
            {"name": "Write", "target": "b.py"},
        ]
        self.assertEqual(
            derive_ordered_behavior(events),
            {"eligible": True, "planned": False, "evidence": False},
        )

    def test_one_file_and_nine_substantive_calls_is_not_eligible(self):
        # The write itself is substantive, so 8 Bash + 1 Edit is the exact total-9 edge.
        nine_calls = ([{"name": "Bash"} for _ in range(8)]
                      + [{"name": "Edit", "target": "a.py"}])
        ten_calls = ([{"name": "Bash"} for _ in range(9)]
                     + [{"name": "Edit", "target": "a.py"}])
        self.assertFalse(derive_ordered_behavior(nine_calls)["eligible"])
        self.assertTrue(derive_ordered_behavior(ten_calls)["eligible"])

    def test_orders_facts_by_timestamp_not_file_iteration_order(self):
        facts = derive_ordered_behavior([
            {"name": "Edit", "target": "a.py", "order": 3},
            {"name": "Write", "target": "b.py", "order": 4},
            {"name": "Read", "target": "a.py", "order": 1},
            {"name": "TodoWrite", "items": ["inspect", "change", "verify"], "order": 2},
        ])
        self.assertEqual(facts, {"eligible": True, "planned": True, "evidence": True})

    def test_normalizes_written_path_aliases_against_session_cwd(self):
        facts = derive_ordered_behavior([
            {"name": "Edit", "target": "a.py", "cwd": "/repo"},
            {"name": "Write", "target": "./a.py", "cwd": "/repo"},
        ])
        self.assertEqual(facts, {"eligible": False, "planned": False, "evidence": False})

    def test_taxonomy_excludes_bookkeeping_and_deduplicates_read_targets(self):
        bookkeeping = ([{"name": "TaskList"}] * 4
                       + [{"name": "CronList"}] * 3
                       + [{"name": "mcp__jobs__get_status"}] * 3
                       + [{"name": "Edit", "target": "a.py"}])
        self.assertFalse(derive_ordered_behavior(bookkeeping)["eligible"])

        repeated_reads = [
            {"name": name, "target": "./a.py", "cwd": "/repo"}
            for name in ("Read", "Grep", "Glob", "NotebookRead", "Read", "Grep",
                         "Glob", "NotebookRead", "Read", "Grep")
        ]
        repeated_reads = repeated_reads[:4] + ([{"name": "Bash"}] * 6)
        repeated_reads.append({"name": "Edit", "target": "b.py", "cwd": "/repo"})
        self.assertFalse(derive_ordered_behavior(repeated_reads)["eligible"])

        substantive = [{"name": "Bash"} for _ in range(10)]
        substantive.append({"name": "Edit", "target": "a.py"})
        self.assertTrue(derive_ordered_behavior(substantive)["eligible"])

    def test_codex_update_plan_steps_accumulate_before_first_write(self):
        # 3 distinct update_plan steps clears the C6 floor (raised from 2 to
        # PLAN_MIN_STEPS=3); see test_two_codex_plan_steps_no_longer_planned
        # below for the below-floor case.
        rows = [
            {"type": "session_meta", "payload": {"id": "s1", "cwd": "/repo"}},
            {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"type": "function_call", "name": "update_plan",
                         "arguments": json.dumps({"plan": [{"step": "inspect"}]})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:02Z",
             "payload": {"type": "function_call", "name": "update_plan",
                         "arguments": json.dumps({"plan": [{"step": "change"}]})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:03Z",
             "payload": {"type": "function_call", "name": "update_plan",
                         "arguments": json.dumps({"plan": [{"step": "verify"}]})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:04Z",
             "payload": {"type": "function_call", "name": "write_file",
                         "arguments": json.dumps({"path": "a.py", "content": "a"})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:05Z",
             "payload": {"type": "function_call", "name": "write_file",
                         "arguments": json.dumps({"path": "b.py", "content": "b"})}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
            handle.write("\n".join(json.dumps(row) for row in rows))
            path = handle.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        acc = Accumulator()
        acc.begin_file("codex", path)
        for event in _codex_events(path):
            acc.observe(event, None, None)
        stats = acc.to_source_stats("codex", None, None)
        self.assertEqual(stats["behavior"]["eligible_change_sessions"], 1)
        self.assertEqual(stats["behavior"]["planned_eligible_sessions"], 1)

    def test_two_codex_plan_steps_no_longer_planned(self):
        # C6: the substance floor was raised from >=2 to >=3 distinct steps —
        # a 2-step plan is no longer "planned" (anti-theater).
        rows = [
            {"type": "session_meta", "payload": {"id": "s1", "cwd": "/repo"}},
            {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"type": "function_call", "name": "update_plan",
                         "arguments": json.dumps({"plan": [{"step": "inspect"}]})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:02Z",
             "payload": {"type": "function_call", "name": "update_plan",
                         "arguments": json.dumps({"plan": [{"step": "change"}]})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:03Z",
             "payload": {"type": "function_call", "name": "write_file",
                         "arguments": json.dumps({"path": "a.py", "content": "a"})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:04Z",
             "payload": {"type": "function_call", "name": "write_file",
                         "arguments": json.dumps({"path": "b.py", "content": "b"})}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
            handle.write("\n".join(json.dumps(row) for row in rows))
            path = handle.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        acc = Accumulator()
        acc.begin_file("codex", path)
        for event in _codex_events(path):
            acc.observe(event, None, None)
        stats = acc.to_source_stats("codex", None, None)
        self.assertEqual(stats["behavior"]["eligible_change_sessions"], 1)
        self.assertEqual(stats["behavior"]["planned_eligible_sessions"], 0)

    def test_repeated_plan_step_updates_do_not_become_two_actionable_steps(self):
        facts = derive_ordered_behavior([
            {"name": "TodoWrite", "items": ["inspect"]},
            {"name": "TodoWrite", "items": ["inspect"]},
            {"name": "Edit", "target": "a.py"},
            {"name": "Write", "target": "b.py"},
        ])
        self.assertEqual(facts, {"eligible": True, "planned": False, "evidence": False})

    def test_equal_timestamps_use_adapter_ordinal(self):
        facts = derive_ordered_behavior([
            {"name": "Edit", "target": "a.py", "order": 1, "ordinal": 3},
            {"name": "Write", "target": "b.py", "order": 1, "ordinal": 4},
            {"name": "Read", "target": "a.py", "order": 1, "ordinal": 1},
            {"name": "TodoWrite", "items": ["inspect", "change", "verify"],
             "order": 1, "ordinal": 2},
        ])
        self.assertEqual(facts, {"eligible": True, "planned": True, "evidence": True})

    def test_undated_tool_events_make_ordering_unmeasured(self):
        acc = Accumulator()
        acc.begin_file("codex", "undated.jsonl")
        for name, path in (("Edit", "a.py"), ("Write", "b.py")):
            acc.observe({
                "type": "assistant", "sessionId": "s1",
                "message": {"role": "assistant", "model": "gpt-5.4", "content": [{
                    "type": "tool_use", "name": name, "input": {"file_path": path},
                }]},
            }, None, None)
        self.assertEqual(
            acc.to_source_stats("codex", None, None)["behavior"]["ordered_facts_state"],
            "unmeasured",
        )

    def test_ordered_facts_namespace_same_session_id_by_source(self):
        acc = Accumulator()
        for source, prefix in (("claude", "a"), ("codex", "b")):
            acc.begin_file(source, f"{source}.jsonl")
            for ordinal, path in enumerate((f"{prefix}1.py", f"{prefix}2.py")):
                acc.observe({
                    "type": "assistant", "sessionId": "shared-id",
                    "timestamp": f"2026-01-01T00:00:0{ordinal + 1}Z",
                    "message": {"role": "assistant", "model": "model", "content": [{
                        "type": "tool_use", "name": "Edit",
                        "input": {"file_path": path, "new_string": "x"},
                    }]},
                }, None, None)
        stats = acc.to_corpus_stats(None, None, False)
        self.assertEqual(stats["behavior"]["eligible_change_sessions"], 2)
        self.assertEqual(
            stats["_scoring_monthly_full"][0]["stats_full"]["behavior"]
            ["eligible_change_sessions"],
            2,
        )


class TestConditionalScoring(unittest.TestCase):
    @staticmethod
    def _aq_axis(stats, pillar_name, axis_name):
        aq = compute_aq(stats)
        pillar = next(p for p in aq["pillars"] if p["name"] == pillar_name)
        return next(a for a in pillar["axes"] if a["name"] == axis_name)

    def test_aq_targets_five_of_ten_planning_and_six_of_ten_context(self):
        three = _v5_scoring_stats(planned=3, evidence=6)
        five = _v5_scoring_stats(planned=5, evidence=6)
        ten = _v5_scoring_stats(planned=10, evidence=10)

        ci = self._aq_axis(five, "Craft", "Context Intelligence")
        self.assertEqual(PLANNING_TARGET, 0.50)
        self.assertEqual(CONTEXT_INTELLIGENCE_TARGET, 0.60)
        self.assertEqual(ci["signals"]["target_coverage"], CONTEXT_INTELLIGENCE_TARGET)
        self.assertIn("coverage / 0.60", ci["signals"]["score_formula"])
        self.assertEqual(ci["score"], ci["weight"])
        self.assertEqual(
            self._aq_axis(five, "Breadth", "Discipline")["score"],
            self._aq_axis(ten, "Breadth", "Discipline")["score"],
        )
        self.assertLess(
            self._aq_axis(three, "Breadth", "Discipline")["score"],
            self._aq_axis(five, "Breadth", "Discipline")["score"],
        )

    def test_orchestration_exports_raw_frequency_and_normalized_score(self):
        stats = _v5_scoring_stats()
        stats["behavior"].update({
            "orchestratable_sessions": 5,
            "delegated_orchestratable_sessions": 3,
        })

        axis = self._aq_axis(stats, "Breadth", "Orchestration")
        signals = axis["signals"]

        self.assertEqual(signals["frequency"], 0.6)
        self.assertEqual(
            signals["frequency_score"],
            round(0.6 / ORCHESTRATION_FREQUENCY_TARGET, 3),
        )
        self.assertEqual(signals["frequency_confidence"], 1.0)
        self.assertEqual(signals["frequency_weight"], 0.3)
        self.assertAlmostEqual(
            axis["normalized_score"],
            0.7 * signals["coordination_quality"]
            + 0.3 * signals["frequency_score"],
            places=3,
        )

    def test_orchestration_frequency_confidence_progresses_through_five_sessions(self):
        four = _v5_scoring_stats()
        four["behavior"].update({
            "orchestratable_sessions": 4,
            "delegated_orchestratable_sessions": 4,
        })
        five = _v5_scoring_stats()
        five["behavior"].update({
            "orchestratable_sessions": 5,
            "delegated_orchestratable_sessions": 5,
        })

        four_axis = self._aq_axis(four, "Breadth", "Orchestration")
        five_axis = self._aq_axis(five, "Breadth", "Orchestration")

        self.assertEqual(four_axis["signals"]["frequency_confidence"], 0.8)
        self.assertEqual(four_axis["signals"]["frequency_weight"], 0.24)
        self.assertEqual(five_axis["signals"]["frequency_confidence"], 1.0)
        self.assertEqual(five_axis["signals"]["frequency_weight"], 0.3)
        self.assertAlmostEqual(
            four_axis["normalized_score"],
            0.76 * four_axis["signals"]["coordination_quality"]
            + 0.24 * four_axis["signals"]["frequency_score"],
            places=3,
        )
        self.assertAlmostEqual(
            five_axis["normalized_score"],
            0.7 * five_axis["signals"]["coordination_quality"]
            + 0.3 * five_axis["signals"]["frequency_score"],
            places=3,
        )

    def test_orchestration_zero_sessions_uses_coordination_quality_only(self):
        stats = _v5_scoring_stats()
        stats["behavior"].update({
            "orchestratable_sessions": 0,
            "delegated_orchestratable_sessions": 0,
        })

        axis = self._aq_axis(stats, "Breadth", "Orchestration")
        signals = axis["signals"]

        self.assertIsNone(signals["frequency"])
        self.assertIsNone(signals["frequency_score"])
        self.assertEqual(signals["frequency_confidence"], 0.0)
        self.assertEqual(signals["frequency_weight"], 0.0)
        self.assertEqual(axis["normalized_score"], signals["coordination_quality"])
        self.assertNotIn("quality", signals)

    def test_gstack_five_of_ten_is_full_credit_for_ordered_planning(self):
        three = _v5_scoring_stats(planned=3, evidence=4)
        five = _v5_scoring_stats(planned=5, evidence=4)
        ten = _v5_scoring_stats(planned=10, evidence=10)
        three_plan = score_breakdown(three)["planning"]["subs"]
        five_plan = score_breakdown(five)["planning"]["subs"]
        ten_plan = score_breakdown(ten)["planning"]["subs"]
        ordered = lambda subs: next(
            sub for sub in subs if sub["label"] == "Ordered planning readiness")
        self.assertEqual(ordered(five_plan)["target"], PLANNING_TARGET)
        self.assertLess(ordered(three_plan)["pct"], 1.0)
        self.assertEqual(ordered(five_plan)["pct"], 1.0)
        self.assertEqual(ordered(ten_plan)["pct"], 1.0)
        self.assertEqual(compute_scores(five)["Planning"],
                         compute_scores(ten)["Planning"])

    def test_aq_axes_expose_stable_base_weight_and_normalized_score(self):
        aq = compute_aq(_v5_scoring_stats(planned=2, evidence=3))

        for pillar in aq["pillars"]:
            for axis in pillar["axes"]:
                self.assertIn("base_weight", axis)
                self.assertIn("normalized_score", axis)
                self.assertGreater(axis["base_weight"], 0)
                self.assertGreaterEqual(axis["normalized_score"], 0)
                self.assertLessEqual(axis["normalized_score"], 1)
                self.assertAlmostEqual(
                    axis["score"],
                    round(axis["weight"] * axis["normalized_score"], 1),
                )

    def test_aq_normalized_score_is_canonical_across_summation_algorithms(self):
        terms = [1 / 60, 1 / 3, 11 / 30]
        naive = 0.0
        for term in terms:
            naive += term
        compensated = math.fsum(terms)

        self.assertEqual(naive, 0.7166666666666666)
        self.assertEqual(compensated, 0.7166666666666667)

        naive_stats = _v5_scoring_stats()
        compensated_stats = deepcopy(naive_stats)
        naive_stats["behavior"]["planning_ratio_explore_to_doing"] = naive
        compensated_stats["behavior"]["planning_ratio_explore_to_doing"] = compensated

        naive_axis = self._aq_axis(naive_stats, "Craft", "Grounding")
        compensated_axis = self._aq_axis(compensated_stats, "Craft", "Grounding")

        self.assertEqual(
            naive_axis["normalized_score"],
            compensated_axis["normalized_score"],
        )
        self.assertEqual(naive_axis["normalized_score"], 0.716666666666667)

    def test_ordered_terms_preserve_every_unaffected_aq_and_gstack_contribution(self):
        without_ordered_success = _v5_scoring_stats(planned=0, evidence=0)
        with_ordered_success = deepcopy(without_ordered_success)
        with_ordered_success["behavior"].update({
            "planned_eligible_sessions": 6,
            "evidence_eligible_sessions": 6,
        })

        def aq_axes(stats):
            return {axis["name"]: axis["score"]
                    for pillar in compute_aq(stats)["pillars"]
                    for axis in pillar["axes"]}

        before_aq, after_aq = aq_axes(without_ordered_success), aq_axes(with_ordered_success)
        changed_aq = {name for name in before_aq if before_aq[name] != after_aq[name]}
        self.assertEqual(changed_aq, {"Discipline", "Context Intelligence"})
        self.assertEqual(
            {name: score for name, score in before_aq.items() if name not in changed_aq},
            {name: score for name, score in after_aq.items() if name not in changed_aq},
        )

        before_scores = compute_scores(without_ordered_success)
        after_scores = compute_scores(with_ordered_success)
        self.assertEqual(
            {name for name in before_scores if before_scores[name] != after_scores[name]},
            {"Planning"},
        )
        before_subs = {sub["label"]: sub["pct"] for sub in
                       score_breakdown(without_ordered_success)["planning"]["subs"]}
        after_subs = {sub["label"]: sub["pct"] for sub in
                      score_breakdown(with_ordered_success)["planning"]["subs"]}
        old_terms = {"Explore-before-build", "Reasoning depth", "Planning practice"}
        self.assertEqual({name: before_subs[name] for name in old_terms},
                         {name: after_subs[name] for name in old_terms})

    def test_below_eligible_floor_drops_ordered_term_and_renormalizes(self):
        # C7: eligible_change_sessions < MIN_ELIGIBLE_SESSIONS(5) drops the
        # ordered-planning term (None -> renormalized), not just eligible == 0.
        below_floor = _v5_scoring_stats(planned=4, evidence=4)
        below_floor["behavior"]["eligible_change_sessions"] = MIN_ELIGIBLE_SESSIONS - 1
        at_floor = _v5_scoring_stats(planned=4, evidence=4)
        at_floor["behavior"]["eligible_change_sessions"] = MIN_ELIGIBLE_SESSIONS

        discipline_below = self._aq_axis(below_floor, "Breadth", "Discipline")
        discipline_at = self._aq_axis(at_floor, "Breadth", "Discipline")
        self.assertNotEqual(discipline_below["score"], discipline_at["score"])

        below_plan_subs = score_breakdown(below_floor)["planning"]["subs"]
        at_plan_subs = score_breakdown(at_floor)["planning"]["subs"]
        below_labels = {sub["label"] for sub in below_plan_subs}
        at_labels = {sub["label"] for sub in at_plan_subs}
        self.assertNotIn("Ordered planning readiness", below_labels)
        self.assertIn("Ordered planning readiness", at_labels)

    def test_planning_practice_target_is_single_source_of_truth(self):
        """The planning-practice target lived as a bare 0.4 literal in four places
        (compute_scores, the zero-axis fallback, and twice in the live breakdown), kept in
        sync only by assertions. Pin the named constant so a retune moves one line."""
        self.assertEqual(PLANNING_PRACTICE_TARGET, 0.30)
        subs = score_breakdown(_v5_scoring_stats())["planning"]["subs"]
        sub = next(s for s in subs if s["label"] == "Planning practice")
        self.assertEqual(sub["target"], PLANNING_PRACTICE_TARGET)

    def test_planning_practice_target_is_measured_not_rounded(self):
        """0.30 is not a round number picked for looks. It is the fraction of eligible
        top-level sessions that carry a substantive code change on a real corpus
        (374/1181 = 0.317), i.e. "plan in about every session where you touch real code".
        The prior 0.40 predated any measurement. The band is asserted rather than the exact
        value so a recalibration against a bigger corpus does not have to fight this test,
        but a drift back toward an unanchored round number does."""
        self.assertGreaterEqual(PLANNING_PRACTICE_TARGET, 0.25)
        self.assertLessEqual(PLANNING_PRACTICE_TARGET, 0.35)

    def test_stale_planning_skill_label_is_gone_from_every_axis(self):
        """The term counts plan mode as well as planning Skills, so "skill practice" is a
        false name. Guard the rename: mirdash keys its per-metric explanations off this
        exact string, and a silent drift there leaves the row with no explanation."""
        stale = "Planning skill" + " practice"   # split so a blind rename cannot eat it
        breakdown = score_breakdown(_v5_scoring_stats())
        for axis in breakdown.values():
            self.assertNotIn(stale, {sub["label"] for sub in axis["subs"]})
        self.assertIn("Planning practice",
                      {sub["label"] for sub in breakdown["planning"]["subs"]})

    def test_cursor_profile_drops_model_mix_while_routing_inputs_stay_na(self):
        stats = _v5_scoring_stats(source="cursor")
        scoring_inputs = build_scoring_inputs(stats)
        profile = score_by_source({
            "cursor": {"window": scoring_inputs},
        })["by_source"]["cursor"]
        savvy = next(p for p in profile["aq"]["pillars"] if p["name"] == "Savvy")
        na = set(savvy.get("not_applicable") or [])
        self.assertIn("Model mix", na)


class TestPlanningSkillSessions(unittest.TestCase):
    @staticmethod
    def _event(sid, timestamp, name, inp=None, attribution=None):
        event = {"type": "assistant", "sessionId": sid, "timestamp": timestamp,
                 "isSidechain": False,
                 "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                             "content": [{"type": "tool_use", "name": name,
                                          "input": inp or {}}]}}
        if attribution:
            event["attributionSkill"] = attribution
        return event

    def test_todo_tools_do_not_count_as_planning_practice_in_window_source_or_month(self):
        """The todo family stays legacy-only. It is the agent's own execution bookkeeping,
        and it already earns "Ordered planning readiness" through the PLAN_MIN_STEPS
        distinct-step gate — admitting it here would double-count inside one axis."""
        acc = Accumulator()
        acc.begin_file("claude", "plans.jsonl")
        acc.observe(self._event("tool-plan", "2026-01-01T00:00:00Z", "TodoWrite",
                                {"todos": [{"content": "inspect"}, {"content": "change"}]}),
                    None, None)
        acc.observe(self._event("skill-plan", "2026-01-01T01:00:00Z", "Skill",
                                {"skill": "writing-plans"}), None, None)
        acc.observe(self._event("attributed-plan", "2026-01-01T02:00:00Z", "Read",
                                {"file_path": "a.py"}, attribution="autoplan"), None, None)
        corpus = acc.to_corpus_stats(None, None, False)
        source = acc.to_source_stats("claude", None, None)
        month = source["_scoring_monthly_full"][0]["stats_full"]
        self.assertEqual(corpus["behavior"]["plan_sessions"], 3)
        self.assertEqual(corpus["behavior"]["planning_skill_sessions"], 2)
        self.assertEqual(source["behavior"]["planning_skill_sessions"], 2)
        self.assertEqual(month["behavior"]["planning_skill_sessions"], 2)

    def test_plan_mode_counts_as_planning_practice_in_window_source_or_month(self):
        """Claude Code plan mode (ExitPlanMode) and Cursor's create_plan (EnterPlanMode)
        must reach the qualified numerator in every slice, not just the legacy union."""
        acc = Accumulator()
        acc.begin_file("claude", "plans.jsonl")
        # Mid-month timestamps on purpose: parse_ts localizes, so a 2026-01-01T0X:00Z
        # event can land in the previous month's slice and split the assertion.
        acc.observe(self._event("todo-only", "2026-01-15T12:00:00Z", "TodoWrite",
                                {"todos": [{"content": "inspect"}, {"content": "change"}]}),
                    None, None)
        acc.observe(self._event("skill-plan", "2026-01-15T13:00:00Z", "Skill",
                                {"skill": "writing-plans"}), None, None)
        acc.observe(self._event("exit-plan-mode", "2026-01-15T14:00:00Z", "ExitPlanMode"),
                    None, None)
        acc.observe(self._event("enter-plan-mode", "2026-01-15T15:00:00Z", "EnterPlanMode"),
                    None, None)
        corpus = acc.to_corpus_stats(None, None, False)
        source = acc.to_source_stats("claude", None, None)
        month = source["_scoring_monthly_full"][0]["stats_full"]
        self.assertEqual(corpus["behavior"]["plan_sessions"], 4)
        # skill-plan + exit-plan-mode + enter-plan-mode; todo-only stays out.
        self.assertEqual(corpus["behavior"]["planning_skill_sessions"], 3)
        self.assertEqual(source["behavior"]["planning_skill_sessions"], 3)
        self.assertEqual(month["behavior"]["planning_skill_sessions"], 3)

    def test_plan_mode_in_a_child_session_does_not_credit_the_numerator(self):
        """A subagent entering plan mode is the agent's own ceremony, not the human's.
        The child guard that already covers Skill/Agent markers must cover this one too."""
        acc = Accumulator()
        acc.begin_file("claude", "plans.jsonl")
        child = self._event("child-plan", "2026-01-01T00:00:00Z", "ExitPlanMode")
        child["isSidechain"] = True
        acc.observe(child, None, None)
        corpus = acc.to_corpus_stats(None, None, False)
        self.assertEqual(corpus["behavior"]["planning_skill_sessions"], 0)
        self.assertEqual(corpus["behavior"]["planning_skill_eligible_sessions"], 0)

    def test_codex_shell_skill_read_counts_planning_skill_practice(self):
        acc = Accumulator()
        acc.begin_file("codex", "skill.jsonl")
        acc.observe(self._event(
            "shell-plan", "2026-01-01T00:00:00Z", "Bash",
            {"command": "cat /Users/me/.codex/skills/writing-plans/SKILL.md"},
        ), None, None)
        stats = acc.to_source_stats("codex", None, None)
        self.assertEqual(stats["behavior"]["planning_skill_sessions"], 1)


class TestDisciplinePlanningHabit(unittest.TestCase):
    """AQ Discipline used to score planning as a BINARY skill-presence check: invoke a
    planning skill once in a thousand sessions and the term was maxed forever. It could not
    tell someone who planned once from someone who plans in a third of their sessions. It
    now reads the same qualified share the GStack Planning practice term reads, so both
    scoring systems agree on what planning discipline means."""

    @staticmethod
    def _stats(share=None, eligible=40, skills=(("writing-plans", 60),)):
        stats = _v5_scoring_stats()
        stats["stack"]["skills_all"] = list(skills)
        stats["stack"]["top_skills"] = list(skills)
        if share is None:
            stats["behavior"].update({
                "planning_skill_sessions": 0,
                "planning_skill_eligible_sessions": 0,
                "planning_skill_unmeasured_sessions": 3,
                "planning_skill_session_scope_state": "unmeasured",
                "planning_skill_session_share": None,
                "planning_skill_session_coverage": None,
            })
            return stats
        planning = round(share * eligible)
        stats["behavior"].update({
            "planning_skill_sessions": planning,
            "planning_skill_eligible_sessions": eligible,
            "planning_skill_unmeasured_sessions": 0,
            "planning_skill_session_scope_state": "measured",
            "planning_skill_session_share": planning / eligible,
            "planning_skill_session_coverage": 1.0,
        })
        return stats

    @staticmethod
    def _discipline(stats):
        aq = compute_aq(stats)
        breadth = next(p for p in aq["pillars"] if p["name"] == "Breadth")
        return next(a for a in breadth["axes"] if a["name"] == "Discipline")

    def test_planning_term_tracks_the_share_not_skill_presence(self):
        low = self._stats(share=0.10)
        high = self._stats(share=0.30)
        self.assertLess(self._discipline(low)["score"],
                        self._discipline(high)["score"])

    def test_planning_term_saturates_at_the_shared_target(self):
        at_target = self._stats(share=PLANNING_PRACTICE_TARGET)
        double = self._stats(share=min(2 * PLANNING_PRACTICE_TARGET, 1.0))
        self.assertEqual(self._discipline(at_target)["score"],
                         self._discipline(double)["score"])

    def test_skill_presence_alone_no_longer_credits_discipline(self):
        with_plan_skill = self._stats(share=0.15, skills=(("writing-plans", 60),))
        without = self._stats(share=0.15, skills=(("read-file", 60),))
        self.assertEqual(self._discipline(with_plan_skill)["score"],
                         self._discipline(without)["score"])

    def test_unavailable_share_drops_the_term_and_renormalizes(self):
        """Unmeasured planning scope must not be scored as zero planning discipline."""
        unmeasured = self._stats(share=None)
        unmeasured["behavior"]["ordered_facts_state"] = "unmeasured"
        axis = self._discipline(unmeasured)
        expected = axis["weight"] * min(
            (unmeasured["tools"]["task_tool_calls"]
             + 0) / max(unmeasured["volume"]["total_sessions"], 1) / 1.0, 1.0)
        self.assertAlmostEqual(axis["score"], expected, places=6)
        breadth = next(p for p in compute_aq(unmeasured)["pillars"]
                       if p["name"] == "Breadth")
        self.assertNotIn("Discipline", set(breadth.get("not_applicable") or []))

    def test_below_eligible_floor_drops_the_planning_habit_term(self):
        """A 1-of-2 corpus is 0.5 share and would max the term on noise. The floor that
        already guards ordered planning must guard this one too."""
        thin = self._stats(share=0.5, eligible=MIN_ELIGIBLE_SESSIONS - 1)
        thin["behavior"]["ordered_facts_state"] = "unmeasured"
        unavailable = self._stats(share=None)
        unavailable["behavior"]["ordered_facts_state"] = "unmeasured"
        self.assertAlmostEqual(self._discipline(thin)["score"],
                               self._discipline(unavailable)["score"], places=6)

    def test_source_that_cannot_emit_any_planning_signal_drops_the_term(self):
        """opencode is a MEASURED planning scope, so its eligible denominator accrues, but
        it can emit neither plan mode nor any Skill-shaped marker — its numerator is
        structurally 0. Scoring that as zero planning discipline would punish a source for
        telemetry it cannot produce, which is exactly what capability caps exist to prevent.
        The term must drop and renormalize, as the old binary term did via the skills cap."""
        stats = self._stats(share=0.0, eligible=10)
        stats["corpus"] = {"sources": {"opencode": {}}}
        stats["behavior"]["ordered_facts_state"] = "unmeasured"
        stats["tools"]["task_tool_calls"] = 0
        breadth = next(p for p in compute_aq(stats)["pillars"] if p["name"] == "Breadth")
        self.assertIn("Discipline", set(breadth.get("not_applicable") or []))

    def test_planning_capable_source_keeps_the_term_at_a_zero_share(self):
        """The guard must key off CAPABILITY, not off the share being zero: a claude corpus
        that genuinely never planned has to score 0, not drop the term."""
        stats = self._stats(share=0.0, eligible=10)
        stats["corpus"] = {"sources": {"claude": {}}}
        breadth = next(p for p in compute_aq(stats)["pillars"] if p["name"] == "Breadth")
        self.assertNotIn("Discipline", set(breadth.get("not_applicable") or []))

    def test_legacy_block_still_scores_the_habit_from_plan_sessions(self):
        """A historical payload without the qualified fields must keep a planning term
        rather than silently losing it, using the legacy all-session denominator."""
        legacy = _v5_scoring_stats()
        legacy["behavior"]["plan_sessions"] = 4
        legacy["behavior"].pop("planning_skill_sessions", None)
        cold = _v5_scoring_stats()
        cold["behavior"]["plan_sessions"] = 0
        cold["behavior"].pop("planning_skill_sessions", None)
        self.assertGreater(self._discipline(legacy)["score"],
                           self._discipline(cold)["score"])


class TestPlanningPartialCoverageScoring(unittest.TestCase):
    @staticmethod
    def _fields(planning, eligible, unmeasured):
        if eligible:
            share = planning / eligible
            coverage = eligible / (eligible + unmeasured)
            state = "partial" if unmeasured else "measured"
        else:
            share = coverage = None
            state = "unmeasured"
        return {
            "planning_skill_sessions": planning,
            "planning_skill_eligible_sessions": eligible,
            "planning_skill_unmeasured_sessions": unmeasured,
            "planning_skill_session_scope_state": state,
            "planning_skill_session_share": share,
            "planning_skill_session_coverage": coverage,
        }

    def test_partial_evidence_scales_effective_weight_and_matches_profile(self):
        stats = _v5_scoring_stats()
        stats["behavior"].update(self._fields(187, 1180, 5))
        evidence = _planning_skill_evidence(stats["behavior"], 10)
        self.assertAlmostEqual(evidence["share"], 187 / 1180)
        self.assertAlmostEqual(evidence["coverage"], 1180 / 1185)
        self.assertEqual(evidence["state"], "partial")
        self.assertAlmostEqual(
            evidence["effective_weight"], 0.25 * (1180 / 1185))

        sub = next(s for s in score_breakdown(stats)["planning"]["subs"]
                   if s["label"] == "Planning practice")
        self.assertAlmostEqual(sub["your_value"], evidence["share"])
        self.assertAlmostEqual(sub["coverage"], evidence["coverage"])
        self.assertAlmostEqual(
            sub["effective_weight"], evidence["effective_weight"])
        self.assertEqual(sub["score_pct"],
                         round(100 * (187 / 1180) / PLANNING_PRACTICE_TARGET))
        self.assertEqual(
            compute_scores(stats)["Planning"],
            score_breakdown(stats)["planning"]["value"])

    def test_gstack_drops_the_term_for_a_source_with_no_planning_signal(self):
        """The same capability hole exists in the GStack Planning axis: opencode's eligible
        denominator accrues while its numerator cannot fire, so the term must drop rather
        than drag the axis to a zero it cannot escape."""
        stats = _v5_scoring_stats()
        stats["corpus"] = {"sources": {"opencode": {}}}
        stats["behavior"].update(self._fields(0, 10, 0))
        labels = {s["label"] for s in score_breakdown(stats)["planning"]["subs"]}
        self.assertNotIn("Planning practice", labels)

    def test_gstack_keeps_the_term_at_a_zero_share_for_a_capable_source(self):
        stats = _v5_scoring_stats()
        stats["corpus"] = {"sources": {"claude": {}}}
        stats["behavior"].update(self._fields(0, 10, 0))
        labels = {s["label"] for s in score_breakdown(stats)["planning"]["subs"]}
        self.assertIn("Planning practice", labels)

    def test_axis_and_breakdown_agree_on_the_split_capability_path(self):
        """The cap for this term is `"skills" if legacy else "planning_signal"`, written out
        three times: the compute_scores axis term, the score_breakdown axis term, and the sub
        `_cap`. The pre-existing equality test uses a claude corpus, which holds BOTH caps, so
        a swapped key in one of the three would go unnoticed. Cursor is the discriminating
        case: it has `planning_signal` (create_plan normalizes to EnterPlanMode) but NOT
        `skills` (no first-class Skill tool)."""
        for source in ("cursor", "claude"):
            with self.subTest(source=source):
                stats = _v5_scoring_stats(source=source)
                stats["behavior"].update(self._fields(3, 10, 0))
                self.assertEqual(compute_scores(stats)["Planning"],
                                 score_breakdown(stats)["planning"]["value"])
                labels = {s["label"] for s in score_breakdown(stats)["planning"]["subs"]}
                self.assertIn("Planning practice", labels)

    def test_legacy_evidence_needs_the_skills_cap_so_cursor_drops_it(self):
        """The ternary's other branch: on the LEGACY path the share comes from plan_sessions
        over all sessions, which only a Skill-capable source populates, so cursor must drop
        the term and the axis and breakdown must still agree about that."""
        stats = _v5_scoring_stats(source="cursor")
        stats["behavior"]["plan_sessions"] = 4
        for field in ("planning_skill_eligible_sessions",
                      "planning_skill_unmeasured_sessions",
                      "planning_skill_session_scope_state",
                      "planning_skill_session_share",
                      "planning_skill_session_coverage"):
            stats["behavior"].pop(field, None)
        self.assertEqual(compute_scores(stats)["Planning"],
                         score_breakdown(stats)["planning"]["value"])
        labels = {s["label"] for s in score_breakdown(stats)["planning"]["subs"]}
        self.assertNotIn("Planning practice", labels)

    def test_zero_tool_root_preserves_authoritative_planning_evidence(self):
        acc = Accumulator()
        acc.begin_file("claude", "zero-tool-root.jsonl")
        acc.observe({
            "type": "user",
            "sessionId": "dated-root",
            "timestamp": "2026-07-01T00:00:00Z",
            "isSidechain": False,
            "injectedSkills": ["writing-plans"],
            "message": {"role": "user", "content": "Plan this change"},
        }, None, None)
        stats = acc.to_source_stats("claude", None, None)
        behavior = stats["behavior"]
        self.assertEqual(stats["volume"]["tool_calls_total"], 0)
        self.assertEqual(
            (behavior["planning_skill_sessions"],
             behavior["planning_skill_eligible_sessions"],
             behavior["planning_skill_unmeasured_sessions"]),
            (1, 1, 0),
        )

        scores = compute_scores(stats)
        breakdown = score_breakdown(stats)
        sub = next(s for s in breakdown["planning"]["subs"]
                   if s["label"] == "Planning practice")
        self.assertEqual(sub["your_value"], 1.0)
        self.assertEqual(sub["pct"], 1.0)
        self.assertEqual(sub["scope_state"], "measured")
        self.assertEqual({
            key: sub[key] for key in (
                "planning_skill_sessions",
                "planning_skill_eligible_sessions",
                "planning_skill_unmeasured_sessions",
                "planning_skill_session_share",
                "planning_skill_session_coverage",
                "scope_state",
            )
        }, {
            "planning_skill_sessions": 1,
            "planning_skill_eligible_sessions": 1,
            "planning_skill_unmeasured_sessions": 0,
            "planning_skill_session_share": 1.0,
            "planning_skill_session_coverage": 1.0,
            "scope_state": "measured",
        })
        self.assertEqual(sub["base_weight"], 0.25)
        self.assertEqual(sub["effective_weight"], 0.25)
        self.assertEqual(scores["Planning"], breakdown["planning"]["value"])
        self.assertEqual((scores["Execution"], scores["Engineering"]), (0.0, 0.0))

        legacy = deepcopy(stats)
        for field in self._fields(1, 1, 0):
            if field != "planning_skill_sessions":
                legacy["behavior"].pop(field)
        self.assertEqual(
            compute_scores(legacy),
            {"Execution": 0.0, "Planning": 0.0, "Engineering": 0.0},
        )

    def test_incomplete_or_inconsistent_new_payload_fails_closed(self):
        complete = self._fields(1, 4, 1)
        invalid_payloads = []
        for field in complete:
            payload = dict(complete)
            payload.pop(field)
            invalid_payloads.append(payload)
        invalid_payloads.append({**complete, "planning_skill_session_share": 0.9})
        invalid_payloads.append({**complete, "planning_skill_session_coverage": 0.9})
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                evidence = _planning_skill_evidence(payload, 99)
                self.assertIsNone(evidence["share"])
                self.assertEqual(evidence["state"], "unmeasured")
                self.assertEqual(evidence["effective_weight"], 0.0)

    def test_legacy_fallback_requires_every_new_field_to_be_absent(self):
        legacy = _planning_skill_evidence({"planning_skill_sessions": 2}, 4)
        self.assertEqual(legacy["share"], 0.5)
        self.assertTrue(legacy["legacy"])
        self.assertEqual(legacy["effective_weight"], 0.25)

        for field in (
            "planning_skill_eligible_sessions",
            "planning_skill_unmeasured_sessions",
            "planning_skill_session_scope_state",
            "planning_skill_session_share",
            "planning_skill_session_coverage",
        ):
            with self.subTest(field=field):
                evidence = _planning_skill_evidence(
                    {"planning_skill_sessions": 2, field: None}, 4)
                self.assertFalse(evidence["legacy"])
                self.assertIsNone(evidence["share"])


class TestRouting(unittest.TestCase):
    def _claude_stats(self, *files):
        acc = Accumulator()
        for label, rows in files:
            fd, path = tempfile.mkstemp(prefix=label, suffix=".jsonl")
            os.close(fd)
            self.addCleanup(lambda p=path: os.path.exists(p) and os.unlink(p))
            with open(path, "w") as handle:
                handle.write("\n".join(json.dumps(row) for row in rows))
            acc.begin_file("claude", path)
            for event in iter_events(path, "claude"):
                acc.observe(event, None, None)
            acc.end_file()
        return acc.to_source_stats("claude", None, None)

    @staticmethod
    def _claude_parent(status="completed", include_result=True):
        use_id = "toolu_agent_1"
        rows = [{
            "type": "assistant", "uuid": "assistant-use", "sessionId": "parent",
            "timestamp": "2026-01-01T00:00:00Z", "isSidechain": False,
            "message": {"model": "claude-opus-4-6", "content": [{
                "type": "tool_use", "id": use_id, "name": "Agent",
                "input": {"subagent_type": "Explore"},
            }]},
        }]
        if include_result:
            rows.append({
                "type": "user", "sessionId": "parent",
                "timestamp": "2026-01-01T00:00:03Z", "isSidechain": False,
                "sourceToolAssistantUUID": "assistant-use",
                "toolUseResult": {"status": status, "agentId": "child-1"},
                "message": {"content": [{
                    "type": "tool_result", "tool_use_id": use_id,
                    "is_error": status in {"failed", "killed", "stopped"},
                }]},
            })
        return rows

    @staticmethod
    def _claude_child(agent_id="child-1"):
        return [{
            "type": "assistant", "sessionId": "parent", "agentId": agent_id,
            "timestamp": "2026-01-01T00:00:01Z", "isSidechain": True,
            "message": {"model": "claude-sonnet-4-6", "content": [{
                "type": "tool_use", "id": "toolu_child_edit", "name": "Edit",
                "input": {"file_path": "a.py", "old_string": "", "new_string": "x"},
            }]},
        }]

    def test_claude_links_completed_lower_tier_child_from_real_fields(self):
        stats = self._claude_stats(
            ("child", self._claude_child()),
            ("parent", self._claude_parent()),
        )
        pairs = stats["behavior"]["linked_model_pairs"]
        self.assertEqual(stats["behavior"]["linked_model_routing_state"], "measured")
        self.assertEqual(pairs, [{
            "provider": "anthropic", "parent_session": "parent",
            "child_session": "child-1", "lead_model": "claude-opus-4-6",
            "child_model": "claude-sonnet-4-6", "completed": True,
            "substantive_calls": 1, "writes": 1,
        }])
        self.assertEqual(score_linked_routing(pairs, "measured")["score"], 1.0)

    def test_claude_missing_result_is_unmeasured(self):
        stats = self._claude_stats(
            ("parent", self._claude_parent(include_result=False)),
            ("child", self._claude_child()),
        )
        self.assertEqual(stats["behavior"]["linked_model_routing_state"], "unmeasured")

    def test_claude_ignores_non_agent_tool_results(self):
        parent = [{
            "type": "assistant", "uuid": "read-use", "sessionId": "parent",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"model": "claude-opus-4-6", "content": [{
                "type": "tool_use", "id": "toolu_read", "name": "Read",
                "input": {"file_path": "a.py"},
            }]},
        }, {
            "type": "user", "sessionId": "parent", "timestamp": "2026-01-01T00:00:01Z",
            "toolUseResult": {"type": "text", "file": {"filePath": "a.py"}},
            "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_read"}]},
        }, *self._claude_parent()]
        stats = self._claude_stats(("parent", parent), ("child", self._claude_child()))
        self.assertEqual(stats["behavior"]["linked_model_routing_state"], "measured")
        self.assertEqual(len(stats["behavior"]["linked_model_pairs"]), 1)

    def test_claude_orphan_child_is_unmeasured(self):
        stats = self._claude_stats(("orphan", self._claude_child("orphan")))
        self.assertEqual(stats["behavior"]["linked_model_routing_state"], "unmeasured")

    def test_claude_known_cancelled_completion_is_measured_exclusion(self):
        parent = self._claude_parent(status="async_launched")
        parent.append({
            "type": "user", "sessionId": "parent", "origin": {"kind": "task-notification"},
            "timestamp": "2026-01-01T00:00:04Z",
            "message": {"content": (
                "<task-notification><task-id>child-1</task-id>"
                "<tool-use-id>toolu_agent_1</tool-use-id>"
                "<status>killed</status></task-notification>"
            )},
        })
        stats = self._claude_stats(
            ("parent", parent),
            ("child", self._claude_child()),
        )
        state = stats["behavior"]["linked_model_routing_state"]
        scored = score_linked_routing(stats["behavior"]["linked_model_pairs"], state)
        self.assertEqual(state, "measured")
        self.assertEqual(scored["excluded_reasons"], {"incomplete": 1})

    def test_claude_known_killed_result_without_child_is_measured_exclusion(self):
        stats = self._claude_stats(("parent", self._claude_parent(status="killed")))
        state = stats["behavior"]["linked_model_routing_state"]
        scored = score_linked_routing(stats["behavior"]["linked_model_pairs"], state)
        self.assertEqual(state, "measured")
        self.assertEqual(scored["excluded_reasons"], {"incomplete": 1})

    def test_claude_ambiguous_result_identity_is_unmeasured(self):
        rows = self._claude_parent()
        rows[1]["sourceToolAssistantUUID"] = "different-assistant-use"
        stats = self._claude_stats(("parent", rows), ("child", self._claude_child()))
        self.assertEqual(stats["behavior"]["linked_model_routing_state"], "unmeasured")

    def test_claude_async_notification_proves_completion(self):
        parent = self._claude_parent(status="async_launched")
        parent.append({
            "type": "user", "sessionId": "parent", "origin": {"kind": "task-notification"},
            "timestamp": "2026-01-01T00:00:04Z",
            "message": {"content": (
                "<task-notification><task-id>child-1</task-id>"
                "<tool-use-id>toolu_agent_1</tool-use-id>"
                "<status>completed</status></task-notification>"
            )},
        })
        stats = self._claude_stats(("parent", parent), ("child", self._claude_child()))
        pair = stats["behavior"]["linked_model_pairs"][0]
        self.assertEqual(stats["behavior"]["linked_model_routing_state"], "measured")
        self.assertEqual(pair["completed"], True)

    def test_claude_tool_result_total_does_not_make_bookkeeping_substantive(self):
        parent = self._claude_parent()
        parent[1]["toolUseResult"]["totalToolUseCount"] = 9
        child = [{
            "type": "assistant", "sessionId": "parent", "agentId": "child-1",
            "timestamp": "2026-01-01T00:00:01Z", "isSidechain": True,
            "message": {"model": "claude-sonnet-4-6", "content": [{
                "type": "tool_use", "id": "toolu_child_plan", "name": "TodoWrite",
                "input": {"todos": [{"content": "one"}]},
            }]},
        }]
        stats = self._claude_stats(("parent", parent), ("child", child))
        pair = stats["behavior"]["linked_model_pairs"][0]
        self.assertEqual(pair["substantive_calls"], 0)
        self.assertEqual(score_linked_routing([pair], "measured")["eligible_completed_substantive_pairs"], 0)

    def test_lower_tier_completed_substantive_pair_scores(self):
        result = score_linked_routing([{
            "provider": "anthropic", "lead_model": "claude-opus-4-1",
            "child_model": "claude-sonnet-4", "completed": True,
            "writes": 1, "substantive_calls": 0,
        }], "measured")
        self.assertEqual(result["state"], "measured")
        self.assertEqual(result["successful_lower_tier_pairs"], 1)
        self.assertEqual(result["score"], 1.0)

    def test_unsupported_and_unknown_are_not_zero(self):
        self.assertEqual(score_linked_routing([], "unsupported")["score"], None)
        unknown = score_linked_routing([{
            "provider": "openai", "lead_model": "unknown", "child_model": "gpt-5-mini",
            "completed": True, "writes": 1, "substantive_calls": 0,
        }], "measured")
        self.assertEqual(unknown["state"], "unmeasured")
        self.assertEqual(unknown["excluded_reasons"], {"unknown_model": 1})

    def test_codex_requires_explicit_task_complete(self):
        rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
             "payload": {"id": "child", "source": {"subagent": {"thread_spawn": {
                 "parent_thread_id": "parent"}}}}},
            {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5-mini"}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1"}},
        ]
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        with open(path, "w") as handle:
            handle.write("\n".join(json.dumps(row) for row in rows))
        links = [event for event in _codex_events(path) if event.get("type") == "routing_link"]
        self.assertEqual(links[0]["routing"]["completed"], True)
        rows.pop()
        with open(path, "w") as handle:
            handle.write("\n".join(json.dumps(row) for row in rows))
        links = [event for event in _codex_events(path) if event.get("type") == "routing_link"]
        self.assertEqual(links[0]["routing"]["completed"], False)
        self.assertEqual(links[0]["routing"]["lifecycle_known"], False)

    def test_codex_delegation_aliases_canonicalize_to_agent(self):
        for name in ("spawn_agent", "collaboration.spawn_agent"):
            canonical, _ = _codex_tool({
                "type": "function_call", "name": name,
                "arguments": json.dumps({"task_name": "worker"}),
            })
            self.assertEqual(canonical, "Agent")

    def test_codex_real_spawn_is_not_duplicated_by_child_metadata(self):
        parent_rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
             "payload": {"id": "parent"}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"turn_id": "parent-turn", "model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:02Z",
             "payload": {"type": "function_call", "name": "spawn_agent",
                         "call_id": "spawn-1", "arguments": json.dumps({
                             "task_name": "worker", "message": "work"})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:03Z",
             "payload": {"type": "function_call_output", "call_id": "spawn-1",
                         "output": json.dumps({"task_name": "/root/worker"})}},
        ]
        child_rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:04Z",
             "payload": {"id": "child", "source": {"subagent": {"thread_spawn": {
                 "parent_thread_id": "parent", "agent_path": "/root/worker"}}}}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:05Z",
             "payload": {"turn_id": "child-turn", "model": "gpt-5-mini"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:06Z",
             "payload": {"type": "function_call", "name": "write_file",
                         "arguments": '{"path":"a.py","content":"x"}'}},
            {"type": "event_msg", "timestamp": "2026-01-01T00:00:07Z",
             "payload": {"type": "task_complete", "turn_id": "child-turn"}},
        ]
        events = list(_codex_events(self._write_codex_rows(parent_rows)))
        events += list(_codex_events(self._write_codex_rows(child_rows)))
        agents = [block for event in events for block in
                  ((event.get("message") or {}).get("content") or [])
                  if block.get("type") == "tool_use" and block.get("name") == "Agent"]
        self.assertEqual(len(agents), 1)

        acc = Accumulator()
        acc.begin_file("codex", "combined.jsonl")
        for event in events:
            acc.observe(event, None, None)
        behavior = acc.to_source_stats("codex", None, None)["behavior"]
        self.assertEqual(behavior["linked_model_routing_state"], "measured")
        self.assertEqual(behavior["linked_model_pairs"][0]["lead_model"], "gpt-5.4")

    def test_codex_custom_exec_counts_real_shell_work_not_status_bookkeeping(self):
        rows = [
            {"type": "session_meta", "payload": {"id": "child", "source": {
                "subagent": {"thread_spawn": {"parent_thread_id": "parent",
                                               "agent_path": "/root/worker"}}}}},
            {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5-mini"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call",
                         "name": "exec", "input": (
                             'await tools.exec_command({cmd:"python3 -m unittest"})')}},
            {"type": "response_item", "payload": {"type": "custom_tool_call",
                         "name": "exec", "input": "await tools.get_goal({})"}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1"}},
        ]
        link = next(event["routing"] for event in _codex_events(self._write_codex_rows(rows))
                    if event.get("type") == "routing_link")
        self.assertEqual(link["substantive_calls"], 1)

    def test_codex_shell_command_lists_are_canonical_strings(self):
        name, inp = _codex_tool({
            "type": "function_call", "name": "shell",
            "arguments": json.dumps({"command": ["python3", "-m", "unittest"]}),
        })
        self.assertEqual(name, "Bash")
        self.assertEqual(inp["command"], "python3 && -m && unittest")

    def test_codex_reused_child_turns_link_to_exact_delegations(self):
        parent_rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
             "payload": {"id": "parent"}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"turn_id": "p1", "model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:02Z",
             "payload": {"type": "function_call", "name": "spawn_agent",
                         "call_id": "spawn-1", "arguments": json.dumps({
                             "task_name": "worker", "message": "first"})}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:03Z",
             "payload": {"type": "function_call_output", "call_id": "spawn-1",
                         "output": json.dumps({"task_name": "/root/worker"})}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:10Z",
             "payload": {"turn_id": "p2", "model": "gpt-5.4-mini"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:11Z",
             "payload": {"type": "function_call", "name": "followup_task",
                         "call_id": "follow-1", "arguments": json.dumps({
                             "target": "/root/worker", "message": "second"})}},
        ]
        child_rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:04Z",
             "payload": {"id": "child", "source": {"subagent": {"thread_spawn": {
                 "parent_thread_id": "parent", "agent_path": "/root/worker"}}}}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:05Z",
             "payload": {"turn_id": "c1", "model": "gpt-5-mini"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:06Z",
             "payload": {"type": "function_call", "name": "write_file",
                         "arguments": '{"path":"a.py","content":"x"}'}},
            {"type": "event_msg", "timestamp": "2026-01-01T00:00:07Z",
             "payload": {"type": "task_complete", "turn_id": "c1"}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:12Z",
             "payload": {"turn_id": "c2", "model": "gpt-5-nano"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:13Z",
             "payload": {"type": "function_call", "name": "write_file",
                         "arguments": '{"path":"b.py","content":"y"}'}},
            {"type": "event_msg", "timestamp": "2026-01-01T00:00:14Z",
             "payload": {"type": "task_complete", "turn_id": "c2"}},
        ]
        acc = Accumulator()
        acc.begin_file("codex", "reused-child.jsonl")
        # Child-first proves linkage is independent of file iteration order.
        for event in list(_codex_events(self._write_codex_rows(child_rows))) + list(
                _codex_events(self._write_codex_rows(parent_rows))):
            acc.observe(event, None, None)
        behavior = acc.to_source_stats("codex", None, None)["behavior"]
        self.assertEqual(behavior["linked_model_routing_state"], "measured")
        pairs = {pair["turn_id"]: pair for pair in behavior["linked_model_pairs"]}
        self.assertEqual(pairs["c1"]["lead_model"], "gpt-5.4")
        self.assertEqual(pairs["c2"]["lead_model"], "gpt-5.4-mini")

    def test_codex_exact_submission_precedes_reused_child_identity(self):
        acc = Accumulator()
        acc.begin_file("codex", "submission-priority.jsonl")
        for stamp, model, turn_id in (
                (1, "gpt-5.4", None), (2, "gpt-5.4-mini", "submission-2")):
            inp = {"_routing_identity": "/root/worker"}
            if turn_id:
                inp["_routing_turn_id"] = turn_id
            acc.observe({
                "type": "assistant", "sessionId": "parent",
                "timestamp": f"2026-01-01T00:00:0{stamp}Z",
                "message": {"role": "assistant", "model": model, "content": [{
                    "type": "tool_use", "name": "Agent", "input": inp,
                }]},
            }, None, None)
        for stamp, turn_id in ((3, "submission-2"), (4, "fallback-turn")):
            acc.observe({
                "type": "routing_link", "sessionId": "child",
                "timestamp": f"2026-01-01T00:00:0{stamp}Z", "routing": {
                    "provider": "openai", "parent_session": "parent",
                    "child_session": "child", "delegation_identity": "/root/worker",
                    "turn_id": turn_id, "child_model": "gpt-5-mini", "completed": True,
                    "lifecycle_known": True, "substantive_calls": 1, "writes": 1,
                },
            }, None, None)
        behavior = acc.to_source_stats("codex", None, None)["behavior"]
        self.assertEqual(behavior["linked_model_routing_state"], "measured")
        pairs = {pair["turn_id"]: pair for pair in behavior["linked_model_pairs"]}
        self.assertEqual(pairs["submission-2"]["lead_model"], "gpt-5.4-mini")
        self.assertEqual(pairs["fallback-turn"]["lead_model"], "gpt-5.4")

    def test_codex_exec_compositor_preserves_nested_tool_payloads(self):
        patch = "*** Begin Patch\n*** Add File: src/a.py\n+one\n*** End Patch"
        rows = [
            {"type": "session_meta", "payload": {"id": "s1", "cwd": "/repo"}},
            {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5.4"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"type": "custom_tool_call", "name": "exec", "input": (
                 'const r=await tools.update_plan({plan:[{step:"inspect",status:"pending"},'
                 '{step:"change",status:"pending"}]});text(r);')}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:02Z",
             "payload": {"type": "custom_tool_call", "name": "exec", "input": (
                 f"const patch={json.dumps(patch)};"
                 "const r=await tools.apply_patch(patch);text(r);")}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:03Z",
             "payload": {"type": "custom_tool_call", "name": "exec", "input": (
                 'const r=await tools.exec_command({cmd:"pytest tests/unit"});text(r.output);')}},
        ]
        events = list(_codex_events(self._write_codex_rows(rows)))
        uses = [block for event in events
                for block in (event.get("message", {}).get("content") or [])
                if block.get("type") == "tool_use"]
        self.assertEqual([use["name"] for use in uses], ["TodoWrite", "Edit", "Bash"])
        self.assertEqual(
            [item["step"] for item in uses[0]["input"]["plan"]],
            ["inspect", "change"],
        )
        self.assertEqual(uses[1]["input"]["file_path"], "src/a.py")
        self.assertEqual(uses[1]["input"]["new_string"], "one\n")
        self.assertEqual(uses[2]["input"]["command"], "pytest tests/unit")

    def test_codex_exec_compositor_does_not_fabricate_malformed_payload(self):
        name, inp = _codex_tool({
            "type": "custom_tool_call", "name": "exec",
            "input": "await tools.update_plan({plan:[broken syntax})",
        })
        self.assertEqual((name, inp), ("exec", {}))

    def test_codex_exec_compositor_rejects_ambiguous_scopes(self):
        call = 'tools.exec_command({cmd:"phantom"})'
        for script in (f"if (false) {{ await {call}; }}",
                       f"function unused() {{ return {call}; }}",
                       f"for (; false;) await {call};",
                       f"if (true) {{}} else await {call};",
                       f"false && await {call};"):
            with self.subTest(script=script):
                self.assertEqual(_codex_tool({
                    "type": "custom_tool_call", "name": "exec", "input": script,
                }), ("exec", {}))
        self.assertEqual(_codex_tool({
            "type": "custom_tool_call", "name": "exec", "input": f"await {call};",
        }), ("Bash", {"command": "phantom"}))
        self.assertEqual(_codex_tool({
            "type": "custom_tool_call", "name": "exec",
            "input": f"await {call}; function unused() {{}}",
        }), ("Bash", {"command": "phantom"}))

    def test_codex_exec_compositor_keeps_call_after_semicolon_free_block(self):
        script = (
            'if (true) {\n'
            '  text("completed")\n'
            '}\n'
            'await tools.exec_command({cmd:"real"});'
        )
        self.assertEqual(_codex_tool({
            "type": "custom_tool_call", "name": "exec", "input": script,
        }), ("Bash", {"command": "real"}))

    def test_codex_exec_compositor_keeps_eager_expression_calls(self):
        scripts = (
            'await Promise.all([tools.exec_command({cmd:"real"})]);',
            '[await tools.exec_command({cmd:"real"})];',
            'const result = {value: await tools.exec_command({cmd:"real"})};',
        )
        for script in scripts:
            with self.subTest(script=script):
                self.assertEqual(_codex_tool({
                    "type": "custom_tool_call", "name": "exec", "input": script,
                }), ("Bash", {"command": "real"}))

    def test_codex_exec_compositor_ignores_tool_text_inside_strings(self):
        name, inp = _codex_tool({
            "type": "custom_tool_call", "name": "exec",
            "input": 'const example="tools.update_plan({plan:[{step:\'fake\'}]})";text(example);',
        })
        self.assertEqual((name, inp), ("exec", {}))

    def test_codex_ambiguous_same_target_delegations_are_unmeasured(self):
        acc = Accumulator()
        acc.begin_file("codex", "ambiguous.jsonl")
        for stamp, model in ((1, "gpt-5.4"), (2, "gpt-5.4-mini")):
            acc.observe({
                "type": "assistant", "sessionId": "parent",
                "timestamp": f"2026-01-01T00:00:0{stamp}Z",
                "message": {"role": "assistant", "model": model, "content": [{
                    "type": "tool_use", "name": "Agent", "input": {
                        "_routing_identity": "/root/worker"},
                }]},
            }, None, None)
        acc.observe({
            "type": "routing_link", "sessionId": "child",
            "timestamp": "2026-01-01T00:00:03Z", "routing": {
                "provider": "openai", "parent_session": "parent",
                "child_session": "child", "delegation_identity": "/root/worker",
                "turn_id": "c1", "child_model": "gpt-5-mini", "completed": True,
                "lifecycle_known": True, "substantive_calls": 1, "writes": 1,
            },
        }, None, None)
        behavior = acc.to_source_stats("codex", None, None)["behavior"]
        self.assertEqual(behavior["linked_model_routing_state"], "unmeasured")
        self.assertIsNone(behavior["linked_model_pairs"][0]["lead_model"])

    def test_codex_missing_child_turn_id_is_unmeasured(self):
        rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
             "payload": {"id": "child", "source": {"subagent": {"thread_spawn": {
                 "parent_thread_id": "parent"}}}}},
            {"type": "turn_context", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"model": "gpt-5-mini"}},
            {"type": "event_msg", "timestamp": "2026-01-01T00:00:02Z",
             "payload": {"type": "task_complete"}},
        ]
        acc = Accumulator()
        path = self._write_codex_rows(rows)
        acc.begin_file("codex", path)
        for event in _codex_events(path):
            acc.observe(event, None, None)
        self.assertEqual(
            acc.to_source_stats("codex", None, None)["behavior"]
            ["linked_model_routing_state"],
            "unmeasured",
        )

    def test_codex_routing_uses_parent_model_at_spawn_time(self):
        acc = Accumulator()
        acc.begin_file("codex", "mixed-model.jsonl")
        acc.observe({
            "type": "assistant", "sessionId": "parent",
            "timestamp": "2026-01-01T00:00:01Z",
            "message": {"role": "assistant", "model": "gpt-5.4", "content": [{
                "type": "tool_use", "name": "Agent", "input": {
                    "_routing_identity": "/root/worker"},
            }]},
        }, None, None)
        acc.observe({
            "type": "routing_link", "sessionId": "child",
            "timestamp": "2026-01-01T00:00:02Z", "routing": {
                "provider": "openai", "parent_session": "parent",
                "child_session": "child", "turn_id": "t1",
                "delegation_identity": "/root/worker",
                "child_model": "gpt-5-mini", "completed": True,
                "lifecycle_known": True, "substantive_calls": 5, "writes": 0,
            },
        }, None, None)
        acc.observe({
            "type": "assistant", "sessionId": "parent",
            "timestamp": "2026-01-01T00:00:03Z",
            "message": {"role": "assistant", "model": "gpt-5-mini", "content": []},
        }, None, None)
        pair = acc.to_source_stats("codex", None, None)["behavior"]["linked_model_pairs"][0]
        self.assertEqual(pair["lead_model"], "gpt-5.4")

    def test_codex_routing_does_not_guess_last_model_without_spawn_event(self):
        acc = Accumulator()
        acc.begin_file("codex", "missing-spawn.jsonl")
        acc.observe({
            "type": "routing_link", "sessionId": "child",
            "timestamp": "2026-01-01T00:00:02Z", "routing": {
                "provider": "openai", "parent_session": "parent",
                "child_session": "child", "turn_id": "t1",
                "child_model": "gpt-5-mini", "completed": True,
                "lifecycle_known": True, "substantive_calls": 5, "writes": 0,
            },
        }, None, None)
        acc.observe({
            "type": "assistant", "sessionId": "parent",
            "timestamp": "2026-01-01T00:00:03Z",
            "message": {"role": "assistant", "model": "gpt-5-mini", "content": []},
        }, None, None)
        pair = acc.to_source_stats("codex", None, None)["behavior"]["linked_model_pairs"][0]
        self.assertIsNone(pair["lead_model"])

    def test_codex_routing_uses_canonical_substantive_taxonomy(self):
        rows = [
            {"type": "session_meta", "payload": {"id": "child", "source": {
                "subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}}},
            {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5-mini"}},
            *({"type": "response_item", "payload": {"type": "function_call",
               "name": "update_plan", "arguments": json.dumps({"plan": [{"step": str(i)}]})}}
              for i in range(6)),
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "t1"}},
        ]
        path = self._write_codex_rows(rows)
        link = next(event["routing"] for event in _codex_events(path)
                    if event.get("type") == "routing_link")
        self.assertEqual(link["substantive_calls"], 0)
        self.assertEqual(link["writes"], 0)

        rows.insert(-1, {"type": "response_item", "payload": {"type": "function_call",
                        "name": "write_file", "arguments": json.dumps({
                            "path": "a.py", "content": "x"})}})
        path = self._write_codex_rows(rows)
        link = next(event["routing"] for event in _codex_events(path)
                    if event.get("type") == "routing_link")
        self.assertEqual(link["substantive_calls"], 1)
        self.assertEqual(link["writes"], 1)

    def test_codex_lifecycle_is_joined_by_turn_id(self):
        rows = [
            {"type": "session_meta", "payload": {"id": "child", "source": {
                "subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}}},
            {"type": "turn_context", "payload": {"turn_id": "old", "model": "gpt-5-mini"}},
            {"type": "response_item", "payload": {"type": "function_call",
                         "name": "exec_command", "arguments": '{"cmd":"ls"}'}},
            {"type": "event_msg", "payload": {"type": "turn_aborted", "turn_id": "old"}},
            {"type": "turn_context", "payload": {"turn_id": "current", "model": "gpt-5-mini"}},
            {"type": "response_item", "payload": {"type": "function_call",
                         "name": "write_file", "arguments": '{"path":"a.py","content":"x"}'}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "current"}},
        ]
        links = [event["routing"] for event in _codex_events(self._write_codex_rows(rows))
                 if event.get("type") == "routing_link"]
        by_turn = {link["turn_id"]: link for link in links}
        self.assertEqual(by_turn["old"]["completed"], False)
        self.assertEqual(by_turn["old"]["lifecycle_known"], True)
        self.assertEqual(by_turn["current"]["completed"], True)
        self.assertEqual(by_turn["current"]["writes"], 1)

    def test_known_codex_abort_is_measured_exclusion(self):
        rows = [
            {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z",
             "payload": {"id": "child", "source": {"subagent": {"thread_spawn": {
                 "parent_thread_id": "parent"}}}}},
            {"type": "turn_context", "payload": {"turn_id": "t1", "model": "gpt-5-mini"}},
            {"type": "response_item", "payload": {"type": "function_call",
                         "name": "exec_command", "arguments": '{"cmd":"ls"}'}},
            {"type": "event_msg", "payload": {"type": "turn_aborted", "turn_id": "t1"}},
        ]
        acc = Accumulator()
        path = self._write_codex_rows(rows)
        acc.begin_file("codex", path)
        for event in _codex_events(path):
            acc.observe(event, None, None)
        stats = acc.to_source_stats("codex", None, None)
        self.assertEqual(stats["behavior"]["linked_model_routing_state"], "measured")
        scored = score_linked_routing(stats["behavior"]["linked_model_pairs"], "measured")
        self.assertEqual(scored["excluded_reasons"], {"incomplete": 1})

    def _write_codex_rows(self, rows):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        self.addCleanup(lambda p=path: os.path.exists(p) and os.unlink(p))
        with open(path, "w") as handle:
            handle.write("\n".join(json.dumps(row) for row in rows))
        return path

    def test_routing_blend_uses_only_measured_windows(self):
        components = [
            (0.65, {"distinct_models": 3, "offload_share": 0.30,
                    "routing": {"state": "unsupported", "score": None}}),
            (0.35, {"distinct_models": 1, "offload_share": 0,
                    "routing": {"state": "measured", "score": 1.0}}),
        ]
        self.assertAlmostEqual(blend_model_mix_components(components), 0.7958333333)
        unsupported = [(1.0, {"distinct_models": 3, "offload_share": 0.30,
                              "routing": {"state": "unsupported", "score": None}})]
        self.assertEqual(blend_model_mix_components(unsupported), 1.0)


class TestV5Contract(unittest.TestCase):
    def test_compute_aq_emits_exact_contract(self):
        stats = {"corpus": {"sources": {}}, "volume": {"total_sessions": 0},
                 "tools": {}, "stack": {}, "behavior": {}}
        self.assertEqual(SCORE_CONTRACT_ID, "14:14:14")
        self.assertEqual(compute_aq(stats)["score_contract_id"], SCORE_CONTRACT_ID)

    def test_blend_rejects_missing_or_mismatched_contract(self):
        aq = {"score_contract_id": SCORE_CONTRACT_ID, "pillars": [], "aq_0_100": 0}
        with self.assertRaises(IncompatibleScoreContract):
            _blend_aq(aq, [{"configured_weight": 1, "aq": {"pillars": []}}])
        with self.assertRaises(IncompatibleScoreContract):
            _blend_aq(aq, [{"configured_weight": 1, "aq": {
                "score_contract_id": "4:2:2", "pillars": []}}])

    def test_shareable_scoring_inputs_strip_routing_session_ids(self):
        stats = {"behavior": {"linked_model_pairs": [{
            "provider": "openai", "parent_session": "private-parent",
            "child_session": "private-child", "turn_id": "private-turn",
            "lead_model": "gpt-5.4", "child_model": "gpt-5.4-mini",
            "completed": True, "lifecycle_known": True,
            "substantive_calls": 5, "writes": 1,
        }]}}
        pair = build_scoring_inputs(stats)["behavior"]["linked_model_pairs"][0]
        self.assertEqual(pair, {
            "provider": "openai", "lead_model": "gpt-5.4",
            "child_model": "gpt-5.4-mini", "completed": True,
            "lifecycle_known": True, "substantive_calls": 5, "writes": 1,
        })

    def test_shareable_scoring_inputs_keep_grounding_count_without_session_ids(self):
        block = build_scoring_inputs({"tools": {
            "mcp_grounded_sessions": 2,
            "mcp_grounded_session_names": ["private-session-a", "private-session-b"],
        }})
        self.assertEqual(block["tools"]["mcp_grounded_sessions"], 2)
        self.assertNotIn("mcp_grounded_session_names", block["tools"])
        self.assertNotIn("private-session", json.dumps(block))


if __name__ == "__main__":
    unittest.main()
