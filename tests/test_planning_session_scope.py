import json
import os
import tempfile
import unittest

from gnomon.cli.accumulator import Accumulator
from gnomon.scoring.aggregate import score_by_source
from gnomon.scoring.gstack import (
    _planning_skill_evidence, _planning_skill_share, compute_scores, score_breakdown,
)
from gnomon.scoring.inputs import build_scoring_inputs
from gnomon.scoring.versioning import SCORE_CONTRACT_ID
from gnomon.sources import iter_events
from gnomon.sources.codex import _codex_events
from gnomon.sources.cursor import _cursor_jsonl_events


def _event(sid, *, sidechain=False, source_skill=None, tool=None, synthetic=False,
           timestamp="2026-01-15T10:00:00Z"):
    event = {
        "type": "assistant" if tool else "user",
        "sessionId": sid,
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "message": {"role": "assistant", "content": [tool]} if tool else {
            "role": "user", "content": "work"
        },
    }
    if source_skill:
        event["injectedSkills"] = [source_skill]
    if synthetic:
        event["__synth_ts__"] = True
    return event


def _rich_stats(behavior, source="claude"):
    return {
        "corpus": {"sources": {source: {}}},
        "volume": {"total_sessions": 4, "total_prompts": 4,
                   "tool_calls_total": 100, "thinking_blocks": 12},
        "velocity": {"active_hours": 1, "tool_churn_edit_write": 100},
        "behavior": {
            "planning_ratio_explore_to_doing": 0.2,
            "delegate_actions": 0, "background_tasks": 0,
            "eligible_change_sessions": 0, "planned_eligible_sessions": 0,
            "ordered_facts_state": "unmeasured", "shell_test_runs": 0,
            "iteration_depth_mean": 2, "iteration_depth_p90": 3,
            "files_hammered_over_15x": 0, "error_rate_per_100_tools": 0,
            **behavior,
        },
        "stack": {"skills_all": [], "top_skills": [], "models": []},
        "tools": {},
    }


def _planning_fields(planning, eligible, unmeasured=0):
    state = ("measured" if eligible > 0 and unmeasured == 0
             else "partial" if eligible > 0 else "unmeasured")
    return {
        "planning_skill_sessions": planning,
        "planning_skill_eligible_sessions": eligible,
        "planning_skill_unmeasured_sessions": unmeasured,
        "planning_skill_session_scope_state": state,
        "planning_skill_session_share": planning / eligible if eligible else None,
        "planning_skill_session_coverage": (
            eligible / (eligible + unmeasured) if eligible else None),
    }


class TestAdapterPlanningIdentity(unittest.TestCase):
    def test_claude_root_defaults_to_literal_false(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps({"type": "user", "sessionId": "root",
                                 "timestamp": "2026-01-01T00:00:00Z",
                                 "message": {"content": "hello"}}) + "\n")
            path = fh.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        event = next(iter_events(path, "claude"))
        self.assertIs(event["isSidechain"], False)

    def test_claude_malformed_child_identity_is_not_coerced_to_root(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps({"type": "user", "sessionId": "unknown",
                                 "timestamp": "2026-01-01T00:00:00Z",
                                 "isSidechain": "false",
                                 "message": {"content": "hello"}}) + "\n")
            path = fh.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        event = next(iter_events(path, "claude"))
        self.assertIsNone(event["isSidechain"])

    def test_claude_subagent_path_without_identity_is_authoritatively_child(self):
        root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        child_dir = os.path.join(root, "session", "subagents")
        os.makedirs(child_dir)
        path = os.path.join(child_dir, "agent-worker.jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "user", "sessionId": "child",
                                 "timestamp": "2026-01-01T00:00:00Z",
                                 "message": {"content": "hello"}}) + "\n")
        event = next(iter_events(path, "claude"))
        self.assertIs(event["isSidechain"], True)

    def test_codex_root_and_child_emit_literal_identity(self):
        root_rows = [
            {"type": "session_meta", "payload": {"id": "root", "cwd": "/repo"}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:00Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "hello"}]}},
        ]
        child_rows = [
            {"type": "session_meta", "payload": {"id": "child", "cwd": "/repo",
                "source": {"subagent": {"thread_spawn": {
                    "parent_thread_id": "root", "agent_path": "worker"}}}}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "child work"}]}},
        ]
        paths = []
        for rows in (root_rows, child_rows):
            fh = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
            fh.write("\n".join(json.dumps(row) for row in rows)); fh.close()
            paths.append(fh.name)
        self.addCleanup(lambda: [os.unlink(p) for p in paths if os.path.exists(p)])
        root = next(e for e in _codex_events(paths[0]) if e.get("type") == "user")
        child = next(e for e in _codex_events(paths[1]) if e.get("type") == "user")
        self.assertIs(root["isSidechain"], False)
        self.assertIs(child["isSidechain"], True)

    def test_codex_incomplete_subagent_identity_is_not_coerced_to_root(self):
        rows = [
            {"type": "session_meta", "payload": {"id": "child", "cwd": "/repo",
                "source": {"subagent": {"thread_spawn": {"agent_path": "worker"}}}}},
            {"type": "response_item", "timestamp": "2026-01-01T00:00:01Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "child work"}]}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            fh.write("\n".join(json.dumps(row) for row in rows))
            path = fh.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        event = next(e for e in _codex_events(path) if e.get("type") == "user")
        self.assertIsNone(event["isSidechain"])

    def test_cursor_root_and_shared_sid_child_emit_literal_identity(self):
        root_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(root_dir, ignore_errors=True))
        transcript = os.path.join(root_dir, "agent-transcripts", "parent")
        child_dir = os.path.join(transcript, "subagents")
        os.makedirs(child_dir)
        root_path = transcript + ".jsonl"
        child_path = os.path.join(child_dir, "worker.jsonl")
        row = {"role": "user", "timestamp": "2026-01-01T00:00:00Z",
               "message": {"content": "hello"}}
        for path in (root_path, child_path):
            with open(path, "w") as fh:
                fh.write(json.dumps(row) + "\n")
        root = next(_cursor_jsonl_events(root_path))
        child = next(_cursor_jsonl_events(child_path))
        self.assertIs(root["isSidechain"], False)
        self.assertIs(child["isSidechain"], True)
        self.assertEqual(child["sessionId"], "parent")


class TestQualifiedPlanningAggregation(unittest.TestCase):
    def _acc(self, source="claude"):
        acc = Accumulator()
        acc.begin_file(source, f"{source}.jsonl")
        return acc

    def test_child_marker_does_not_credit_shared_root_sid(self):
        acc = self._acc("cursor")
        acc.observe(_event("same", sidechain=False), None, None)
        acc.observe(_event("same", sidechain=True, tool={
            "type": "tool_use", "name": "Bash",
            "input": {"command": "cat /x/skills/writing-plans/SKILL.md"},
        }), None, None)
        stats = acc.to_source_stats("cursor", None, None)["behavior"]
        self.assertEqual(stats["planning_skill_sessions"], 0)
        self.assertEqual(stats["planning_skill_eligible_sessions"], 1)
        self.assertEqual(stats["planning_skill_session_share"], 0.0)
        self.assertEqual(acc.skill_counter["writing-plans"], 1)

    def test_root_marker_is_idempotent_across_children(self):
        acc = self._acc()
        acc.observe(_event("root", source_skill="writing-plans"), None, None)
        acc.observe(_event("root", source_skill="writing-plans"), None, None)
        acc.observe(_event("child", sidechain=True, source_skill="writing-plans"), None, None)
        behavior = acc.to_source_stats("claude", None, None)["behavior"]
        self.assertEqual((behavior["planning_skill_sessions"],
                          behavior["planning_skill_eligible_sessions"]), (1, 1))

    def test_child_only_and_synthetic_only_are_unavailable(self):
        for event in (_event("child", sidechain=True, source_skill="writing-plans"),
                      _event("synthetic", source_skill="writing-plans", synthetic=True)):
            with self.subTest(event=event["sessionId"]):
                acc = self._acc()
                acc.observe(event, None, None)
                behavior = acc.to_source_stats("claude", None, None)["behavior"]
                self.assertEqual(behavior["planning_skill_eligible_sessions"], 0)
                self.assertIsNone(behavior["planning_skill_session_share"])

    def test_marker_paths_share_one_child_guard(self):
        markers = [
            _event("s", sidechain=True, source_skill="writing-plans"),
            {**_event("s", sidechain=True, tool={"type": "tool_use", "name": "Read",
                                                  "input": {"file_path": "a.py"}}),
             "attributionSkill": "writing-plans"},
            _event("s", sidechain=True, tool={"type": "tool_use", "name": "Skill",
                                               "input": {"skill": "writing-plans"}}),
            _event("s", sidechain=True, tool={"type": "tool_use", "name": "Bash",
                                               "input": {"command": "cat /x/skills/writing-plans/SKILL.md"}}),
        ]
        for marker in markers:
            with self.subTest(marker=marker):
                acc = self._acc()
                acc.observe(marker, None, None)
                self.assertEqual(acc.to_source_stats("claude", None, None)["behavior"]
                                 ["planning_skill_sessions"], 0)

    def test_direct_read_skill_path_credits_root_but_not_child(self):
        read = {"type": "tool_use", "name": "Read",
                "input": {"file_path": "/x/skills/writing-plans/SKILL.md"}}
        root = self._acc()
        root.observe(_event("root", tool=read), None, None)
        root_behavior = root.to_source_stats("claude", None, None)["behavior"]
        self.assertEqual((
            root_behavior["planning_skill_sessions"],
            root_behavior["planning_skill_eligible_sessions"],
        ), (1, 1))

        child = self._acc()
        child.observe(_event("child", sidechain=True, tool=read), None, None)
        child_behavior = child.to_source_stats("claude", None, None)["behavior"]
        self.assertEqual((
            child_behavior["planning_skill_sessions"],
            child_behavior["planning_skill_eligible_sessions"],
        ), (0, 0))
        self.assertEqual(child.skill_counter["writing-plans"], 1)

    def test_agent_subagent_type_planning_credits_root(self):
        agent_tool = {"type": "tool_use", "name": "Agent",
                      "input": {"subagent_type": "writing-plans",
                                "prompt": "plan the feature"}}
        acc = self._acc()
        acc.observe(_event("root", tool=agent_tool), None, None)
        behavior = acc.to_source_stats("claude", None, None)["behavior"]
        self.assertEqual((
            behavior["planning_skill_sessions"],
            behavior["planning_skill_eligible_sessions"],
        ), (1, 1))

    def test_agent_subagent_type_planning_rejected_for_child(self):
        agent_tool = {"type": "tool_use", "name": "Agent",
                      "input": {"subagent_type": "writing-plans",
                                "prompt": "plan the feature"}}
        acc = self._acc()
        acc.observe(_event("root"), None, None)
        acc.observe(_event("child", sidechain=True, tool=agent_tool), None, None)
        behavior = acc.to_source_stats("claude", None, None)["behavior"]
        self.assertEqual(behavior["planning_skill_sessions"], 0)
        self.assertEqual(behavior["planning_skill_eligible_sessions"], 1)

    def test_routing_link_never_enters_planning_session_evidence(self):
        acc = self._acc("codex")
        event = _event("routing", source_skill="writing-plans")
        event["type"] = "routing_link"
        event["routing"] = {"parent_session": "parent", "child_session": "routing"}
        acc.observe(event, None, None)
        behavior = acc.to_source_stats("codex", None, None)["behavior"]
        self.assertEqual((
            behavior["planning_skill_sessions"],
            behavior["planning_skill_eligible_sessions"],
            behavior["planning_skill_unmeasured_sessions"],
        ), (0, 0, 0))

    def test_duplicated_child_fanout_has_zero_planning_delta(self):
        def snapshot(child_count):
            acc = self._acc("cursor")
            acc.observe(_event("root", source_skill="writing-plans"), None, None)
            for index in range(child_count):
                acc.observe(_event(
                    f"child-{index}", sidechain=True,
                    source_skill="writing-plans"), None, None)
            behavior = acc.to_source_stats("cursor", None, None)["behavior"]
            evidence = _planning_skill_evidence(behavior, 1)
            stats = _rich_stats(behavior, "cursor")
            return (
                behavior["planning_skill_sessions"],
                behavior["planning_skill_eligible_sessions"],
                behavior["planning_skill_unmeasured_sessions"],
                behavior["planning_skill_session_share"],
                behavior["planning_skill_session_coverage"],
                evidence["effective_weight"],
                compute_scores(stats)["Planning"],
            )

        self.assertEqual(snapshot(1), snapshot(20))

    def test_source_qualified_ids_and_unmeasured_propagation(self):
        acc = Accumulator()
        for source in ("claude", "codex"):
            acc.begin_file(source, source)
            acc.observe(_event("same", source_skill="writing-plans"), None, None)
        behavior = acc.to_corpus_stats(None, None, False)["behavior"]
        self.assertEqual(behavior["planning_skill_sessions"], 2)
        self.assertEqual(behavior["planning_skill_eligible_sessions"], 2)

        acc.begin_file("gemini", "gemini")
        unknown = _event("g", source_skill="writing-plans")
        unknown.pop("isSidechain")
        acc.observe(unknown, None, None)
        behavior = acc.to_corpus_stats(None, None, False)["behavior"]
        self.assertEqual(behavior["planning_skill_sessions"], 2)
        self.assertEqual(behavior["planning_skill_eligible_sessions"], 2)
        self.assertEqual(behavior["planning_skill_unmeasured_sessions"], 1)
        self.assertEqual(behavior["planning_skill_session_scope_state"], "partial")
        self.assertEqual(behavior["planning_skill_session_share"], 1.0)
        self.assertAlmostEqual(
            behavior["planning_skill_session_coverage"], 2 / 3, places=6)

    def test_unknown_identity_is_unmeasured_until_same_session_has_authoritative_root(self):
        acc = self._acc("codex")
        unknown = _event("same")
        unknown["isSidechain"] = None
        acc.observe(unknown, None, None)
        first = acc.to_source_stats("codex", None, None)["behavior"]
        self.assertEqual(first["planning_skill_unmeasured_sessions"], 1)
        self.assertEqual(first["planning_skill_session_scope_state"], "unmeasured")
        self.assertIsNone(first["planning_skill_session_coverage"])

        acc.observe(_event("same", source_skill="writing-plans"), None, None)
        resolved = acc.to_source_stats("codex", None, None)["behavior"]
        self.assertEqual((
            resolved["planning_skill_sessions"],
            resolved["planning_skill_eligible_sessions"],
            resolved["planning_skill_unmeasured_sessions"],
            resolved["planning_skill_session_scope_state"],
        ), (1, 1, 0, "measured"))
        self.assertEqual(resolved["planning_skill_session_coverage"], 1.0)

    def test_month_and_corpus_partial_evidence_include_zero_tool_sessions(self):
        acc = Accumulator()
        acc.begin_file("claude", "claude")
        acc.observe(_event("measured-zero-tool", source_skill="writing-plans",
                           timestamp="2026-01-15T00:00:00Z"), None, None)
        acc.begin_file("gemini", "gemini")
        unsupported = _event("unsupported-zero-tool",
                             timestamp="2026-02-15T00:00:00Z")
        unsupported.pop("isSidechain")
        acc.observe(unsupported, None, None)

        corpus = acc.to_corpus_stats(None, None, False)["behavior"]
        self.assertEqual((
            corpus["planning_skill_sessions"],
            corpus["planning_skill_eligible_sessions"],
            corpus["planning_skill_unmeasured_sessions"],
            corpus["planning_skill_session_scope_state"],
        ), (1, 1, 1, "partial"))
        self.assertEqual(corpus["planning_skill_session_share"], 1.0)
        self.assertEqual(corpus["planning_skill_session_coverage"], 0.5)

        monthly = acc.to_corpus_stats(None, None, False)["_scoring_monthly_full"]
        by_month = {row["month"]: row["stats_full"]["behavior"] for row in monthly}
        self.assertEqual((
            by_month["2026-01"]["planning_skill_eligible_sessions"],
            by_month["2026-01"]["planning_skill_unmeasured_sessions"],
            by_month["2026-01"]["planning_skill_session_scope_state"],
        ), (1, 0, "measured"))
        self.assertEqual((
            by_month["2026-02"]["planning_skill_eligible_sessions"],
            by_month["2026-02"]["planning_skill_unmeasured_sessions"],
            by_month["2026-02"]["planning_skill_session_scope_state"],
        ), (0, 1, "unmeasured"))

    def test_month_fields_use_matching_qualified_sets(self):
        acc = self._acc()
        acc.observe(_event("jan", source_skill="writing-plans",
                           timestamp="2026-01-15T00:00:00Z"), None, None)
        acc.observe(_event("feb", timestamp="2026-02-15T00:00:00Z"), None, None)
        monthly = acc.to_source_stats("claude", None, None)["_scoring_monthly_full"]
        by_month = {row["month"]: row["stats_full"]["behavior"] for row in monthly}
        self.assertEqual(by_month["2026-01"]["planning_skill_session_share"], 1.0)
        self.assertEqual(by_month["2026-02"]["planning_skill_session_share"], 0.0)

    def test_synthesized_cursor_marker_credits_an_existing_root_only(self):
        acc = self._acc("cursor")
        acc.observe(_event("root"), None, None)
        acc.observe(_event("root", source_skill="writing-plans", synthetic=True), None, None)
        behavior = acc.to_source_stats("cursor", None, None)["behavior"]
        self.assertEqual((behavior["planning_skill_sessions"],
                          behavior["planning_skill_eligible_sessions"]), (1, 1))

        synthetic_only = self._acc("cursor")
        synthetic_only.observe(
            _event("orphan", source_skill="writing-plans", synthetic=True), None, None)
        behavior = synthetic_only.to_source_stats("cursor", None, None)["behavior"]
        self.assertEqual(behavior["planning_skill_sessions"], 0)
        self.assertEqual(behavior["planning_skill_eligible_sessions"], 0)

    def test_synthetic_timestamp_marker_can_credit_root_across_months(self):
        acc = self._acc("cursor")
        acc.observe(_event("root", timestamp="2026-01-15T23:59:00Z"), None, None)
        acc.observe(_event("root", source_skill="writing-plans", synthetic=True,
                           timestamp="2026-02-15T00:01:00Z"), None, None)
        behavior = acc.to_source_stats("cursor", None, None)["behavior"]
        self.assertEqual((behavior["planning_skill_sessions"],
                          behavior["planning_skill_eligible_sessions"]), (1, 1))
        monthly = acc.to_source_stats("cursor", None, None)["_scoring_monthly_full"]
        by_month = {row["month"]: row["stats_full"]["behavior"] for row in monthly}
        self.assertEqual(by_month["2026-01"]["planning_skill_sessions"], 0)
        self.assertEqual(by_month["2026-02"]["planning_skill_sessions"], 0)


class TestPlanningScoringContract(unittest.TestCase):
    def test_share_helper_distinguishes_new_legacy_and_unmeasured(self):
        self.assertEqual(
            _planning_skill_share(_planning_fields(2, 4), 99),
            (0.5, "measured", False))
        self.assertEqual(_planning_skill_share({"planning_skill_sessions": 2}, 4),
                         (0.5, "legacy", True))
        self.assertEqual(
            _planning_skill_share(_planning_fields(0, 0, 2), 4),
            (None, "unmeasured", False))
        self.assertEqual(_planning_skill_share({
            "planning_skill_sessions": 2,
            "planning_skill_session_scope_state": "measured",
        }, 4), (None, "unmeasured", False))

    def test_unavailable_term_is_displayed_and_renormalized(self):
        measured = _rich_stats(_planning_fields(0, 4))
        unavailable = _rich_stats(_planning_fields(0, 0, 4))
        self.assertNotEqual(compute_scores(measured)["Planning"],
                            compute_scores(unavailable)["Planning"])
        sub = next(s for s in score_breakdown(unavailable)["planning"]["subs"]
                   if s["label"] == "Planning skill practice")
        self.assertIsNone(sub["your_value"])
        self.assertIsNone(sub["score_pct"])
        self.assertEqual(sub["display_value"], "unavailable")

    def test_scoring_inputs_preserve_audit_fields_and_contract(self):
        stats = _rich_stats(_planning_fields(1, 4))
        behavior = build_scoring_inputs(stats)["behavior"]
        self.assertEqual(behavior["planning_skill_eligible_sessions"], 4)
        self.assertEqual(behavior["planning_skill_unmeasured_sessions"], 0)
        self.assertEqual(behavior["planning_skill_session_share"], 0.25)
        self.assertEqual(SCORE_CONTRACT_ID, "5:5:5")

    def test_scoring_inputs_do_not_disable_legacy_fallback_with_null_keys(self):
        stats = _rich_stats({"planning_skill_sessions": 2})
        behavior = build_scoring_inputs(stats)["behavior"]
        self.assertNotIn("planning_skill_eligible_sessions", behavior)
        self.assertNotIn("planning_skill_session_scope_state", behavior)
        self.assertEqual(_planning_skill_share(behavior, 4),
                         (0.5, "legacy", True))

    def test_aggregate_planning_uses_synthesized_scope(self):
        measured = build_scoring_inputs(
            _rich_stats(_planning_fields(4, 4), "claude"))
        unavailable = build_scoring_inputs(
            _rich_stats(_planning_fields(0, 0, 4), "gemini"))
        result = score_by_source({"claude": {"window": measured},
                                  "gemini": {"window": unavailable}})
        aggregate = result["aggregate"]
        sub = next(s for s in aggregate["scores"]["planning"]["subs"]
                   if s["label"] == "Planning skill practice")
        self.assertEqual(sub["your_value"], 1.0)
        self.assertEqual(sub["scope_state"], "partial")
        self.assertEqual(sub["coverage"], 0.5)
        self.assertEqual(aggregate["combination"]["axes"]["planning"],
                         "recomputed_from_synthesized_corpus")

    def test_malformed_aggregate_planning_counters_degrade_without_crashing(self):
        malformed_fields = _planning_fields(1, 4)
        malformed_fields["planning_skill_sessions"] = "not-a-count"
        malformed = build_scoring_inputs(_rich_stats(malformed_fields))
        aggregate = score_by_source({"claude": {"window": malformed}})["aggregate"]
        sub = next(s for s in aggregate["scores"]["planning"]["subs"]
                   if s["label"] == "Planning skill practice")
        self.assertIsNone(sub["your_value"])

    def test_all_non_integral_planning_counters_are_unmeasured(self):
        malformed_values = (None, True, float("nan"), float("inf"), -1, 0.5)
        for value in malformed_values:
            for field in ("planning_skill_sessions", "planning_skill_eligible_sessions"):
                with self.subTest(value=value, field=field):
                    behavior = _planning_fields(1, 2)
                    behavior[field] = value
                    self.assertEqual(_planning_skill_share(behavior, 99),
                                     (None, "unmeasured", False))
                    malformed = build_scoring_inputs(_rich_stats(behavior))
                    aggregate = score_by_source({"claude": {"window": malformed}})[
                        "aggregate"]
                    sub = next(s for s in aggregate["scores"]["planning"]["subs"]
                               if s["label"] == "Planning skill practice")
                    self.assertIsNone(sub["your_value"])

    def test_single_source_aggregate_preserves_ordered_planning_inputs(self):
        stats = _rich_stats({
            "eligible_change_sessions": 5,
            "planned_eligible_sessions": 5,
            "ordered_facts_state": "measured",
            **_planning_fields(0, 4),
        })
        result = score_by_source({"claude": {"window": build_scoring_inputs(stats)}})
        source = result["by_source"]["claude"]["scores"]["planning"]
        aggregate = result["aggregate"]["scores"]["planning"]
        self.assertEqual(aggregate["value"], source["value"])
        source_ordered = next(s for s in source["subs"]
                              if s["label"] == "Ordered planning readiness")
        aggregate_ordered = next(s for s in aggregate["subs"]
                                 if s["label"] == "Ordered planning readiness")
        self.assertEqual(aggregate_ordered["your_value"], source_ordered["your_value"])

    def test_zero_tool_unmeasured_source_reduces_aggregate_planning_confidence(self):
        measured = build_scoring_inputs(_rich_stats({
            "eligible_change_sessions": 5, "planned_eligible_sessions": 5,
            "ordered_facts_state": "measured", **_planning_fields(4, 4),
        }, "claude"))
        zero_weight = build_scoring_inputs(_rich_stats({
            **_planning_fields(0, 0, 4),
        }, "gemini"))
        zero_weight["volume"]["tool_calls_total"] = 0
        result = score_by_source({"claude": {"window": measured},
                                  "gemini": {"window": zero_weight}})
        aggregate = result["aggregate"]["scores"]["planning"]
        sub = next(s for s in aggregate["subs"]
                   if s["label"] == "Planning skill practice")
        self.assertEqual(sub["scope_state"], "partial")
        self.assertEqual(sub["planning_skill_unmeasured_sessions"], 4)
        self.assertLess(
            aggregate["value"],
            result["by_source"]["claude"]["scores"]["planning"]["value"])

    def test_single_source_legacy_aggregate_preserves_source_planning_score(self):
        legacy = build_scoring_inputs(_rich_stats({"planning_skill_sessions": 2}))
        result = score_by_source({"claude": {"window": legacy}})
        self.assertEqual(result["aggregate"]["scores"]["planning"]["value"],
                         result["by_source"]["claude"]["scores"]["planning"]["value"])

    def test_mixed_legacy_and_new_aggregate_is_unavailable(self):
        legacy = build_scoring_inputs(_rich_stats({"planning_skill_sessions": 2}, "claude"))
        measured = build_scoring_inputs(
            _rich_stats(_planning_fields(1, 4), "codex"))
        aggregate = score_by_source({"claude": {"window": legacy},
                                     "codex": {"window": measured}})["aggregate"]
        sub = next(s for s in aggregate["scores"]["planning"]["subs"]
                   if s["label"] == "Planning skill practice")
        self.assertIsNone(sub["your_value"])


if __name__ == "__main__":
    unittest.main()
