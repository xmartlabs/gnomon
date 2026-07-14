import unittest
import json
import math
import os
import tempfile
from copy import deepcopy

from gnomon.cli.accumulator import Accumulator, derive_ordered_behavior
from gnomon.scoring.aq import (
    CONTEXT_INTELLIGENCE_TARGET,
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
from gnomon.scoring.gstack import compute_scores, score_breakdown
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
        old_terms = {"Explore-before-build", "Reasoning depth", "Planning skill practice"}
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
                 "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                             "content": [{"type": "tool_use", "name": name,
                                          "input": inp or {}}]}}
        if attribution:
            event["attributionSkill"] = attribution
        return event

    def test_plan_tools_do_not_count_as_planning_skill_in_window_source_or_month(self):
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

    def test_codex_shell_skill_read_counts_planning_skill_practice(self):
        acc = Accumulator()
        acc.begin_file("codex", "skill.jsonl")
        acc.observe(self._event(
            "shell-plan", "2026-01-01T00:00:00Z", "Bash",
            {"command": "cat /Users/me/.codex/skills/writing-plans/SKILL.md"},
        ), None, None)
        stats = acc.to_source_stats("codex", None, None)
        self.assertEqual(stats["behavior"]["planning_skill_sessions"], 1)


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
        self.assertEqual(SCORE_CONTRACT_ID, "5:3:3")
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
