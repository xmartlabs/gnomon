import unittest
from datetime import datetime, timedelta

from gnomon.cli.accumulator import (
    Accumulator, derive_session_ordered_facts, aggregate_ordered,
)


def _fact_event(sid, timestamp, name, inp=None, attribution=None):
    event = {"type": "assistant", "sessionId": sid, "timestamp": timestamp,
             "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                         "content": [{"type": "tool_use", "name": name,
                                      "input": inp or {}}]}}
    if attribution:
        event["attributionSkill"] = attribution
    return event


def _workflow_agent_event(parent_sid, timestamp, agent_id):
    """One event inside a dispatched Workflow agent transcript
    (`.../subagents/workflows/wf_*/agent-*.jsonl`). Verified against a real corpus
    sample: `sessionId` carries the PARENT's session id (not a distinct child id),
    while `agentId` carries the per-dispatch child identity."""
    return {"type": "assistant", "sessionId": parent_sid, "agentId": agent_id,
            "isSidechain": True, "timestamp": timestamp,
            "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                        "content": [{"type": "text", "text": "working"}]}}


def _facts_for(acc, src, sid):
    for key, facts in acc.session_ordered_tools.items():
        if key == (src, sid):
            return facts
    return []


def _fact(name, target="", order=0, cwd="/repo", file_class="other", loc=None,
          plan_file=False, plan_skill=False, items=None):
    """Build a rich (already-enriched) ordered fact for testing
    derive_session_ordered_facts directly, bypassing the accumulator."""
    return {
        "name": name, "target": target, "items": items or [], "cwd": cwd,
        "order": order, "ordinal": order, "knowledge": False,
        "file_class": file_class, "loc": loc, "plan_file": plan_file,
        "plan_skill": plan_skill,
    }


class TestEligibilityC2(unittest.TestCase):
    """C2: eligible = code write AND (>=2 distinct code files OR churn>=CHURN_MIN
    OR substantive>=10). Doc/config/lockfile/test-only sessions are excluded;
    mixed code+test sessions stay eligible via the code files."""

    def test_doc_config_lockfile_only_not_eligible(self):
        facts = [
            _fact("Write", "README.md", order=1, file_class="doc", loc=50),
            _fact("Write", "config.yaml", order=2, file_class="config", loc=10),
            _fact("Write", "package-lock.json", order=3, file_class="lockfile", loc=5),
        ]
        self.assertFalse(derive_session_ordered_facts(facts)["eligible"])

    def test_test_only_not_eligible(self):
        facts = [
            _fact("Write", "tests/test_a.py", order=1, file_class="test", loc=20),
            _fact("Edit", "tests/test_b.py", order=2, file_class="test", loc=20),
        ]
        self.assertFalse(derive_session_ordered_facts(facts)["eligible"])

    def test_single_code_file_high_churn_eligible(self):
        facts = [_fact("Write", "src/app.py", order=1, file_class="code", loc=90)]
        self.assertTrue(derive_session_ordered_facts(facts)["eligible"])

    def test_low_churn_and_low_substantive_not_eligible(self):
        facts = [_fact("Edit", "src/app.py", order=1, file_class="code", loc=10)]
        self.assertFalse(derive_session_ordered_facts(facts)["eligible"])

    def test_mixed_code_and_test_eligible_via_code_file(self):
        facts = [
            _fact("Write", "src/app.py", order=1, file_class="code", loc=90),
            _fact("Write", "tests/test_app.py", order=2, file_class="test", loc=40),
        ]
        self.assertTrue(derive_session_ordered_facts(facts)["eligible"])

    def test_two_distinct_code_files_eligible_even_with_low_churn(self):
        facts = [
            _fact("Edit", "src/a.py", order=1, file_class="code", loc=3),
            _fact("Edit", "src/b.py", order=2, file_class="code", loc=3),
        ]
        self.assertTrue(derive_session_ordered_facts(facts)["eligible"])


class TestOrchestratableEligibility(unittest.TestCase):
    def test_delegate_calls_do_not_inflate_orchestration_denominator(self):
        nineteen_work_calls_plus_delegate = (
            [_fact("Bash", order=i) for i in range(1, 19)]
            + [_fact("Edit", "src/app.py", order=19, file_class="code", loc=1)]
            + [_fact("Agent", order=20)]
        )
        result = derive_session_ordered_facts(nineteen_work_calls_plus_delegate)

        self.assertTrue(result["eligible"])
        self.assertFalse(result["orchestratable"])

        # Ordered planning keeps its established substantive-work contract,
        # where delegation is still one of ten substantive calls.
        ordered_planning_boundary = (
            [_fact("Bash", order=i) for i in range(1, 9)]
            + [_fact("Edit", "src/app.py", order=9, file_class="code", loc=1)]
            + [_fact("Agent", order=10)]
        )
        self.assertTrue(
            derive_session_ordered_facts(ordered_planning_boundary)["eligible"]
        )

        twenty_work_calls = (
            [_fact("Bash", order=i) for i in range(1, 20)]
            + [_fact("Edit", "src/app.py", order=20, file_class="code", loc=1)]
        )
        self.assertTrue(
            derive_session_ordered_facts(twenty_work_calls)["orchestratable"]
        )


class TestOrchestrationToolsGate(unittest.TestCase):
    """WU4 (H1a/H1b/H6): the real accumulator.py:1132 gate that feeds
    agents_per_session must be driven by taxonomy.ORCHESTRATION_TOOLS membership,
    not the literal `name == "Agent"` check -- so a Task-only harness (no Agent calls
    at all) still counts toward delegated_orchestratable_sessions the same way an
    Agent-only session would (spec scenario: Task-only harness)."""

    def test_task_only_session_counts_toward_delegated_orchestratable(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        # 3 distinct code-file writes make this session orchestratable on their own
        # (ORCHESTRATABLE_CODE_FILES), independent of any delegate/substantive count.
        for i, path in enumerate(("src/a.py", "src/b.py", "src/c.py")):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:0{i}Z", "Write",
                {"file_path": path, "content": "line1\nline2"},
            ), None, None)
        # The ONLY orchestration signal in this session is a bare Task call --
        # no Agent tool_use anywhere.
        acc.observe(_fact_event("s1", "2026-01-01T00:00:03Z", "Task", {}), None, None)
        acc.end_file()
        stats = acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.agents_per_session.get("s1"), 1)
        self.assertEqual(stats["behavior"]["orchestratable_sessions"], 1)
        self.assertEqual(stats["behavior"]["delegated_orchestratable_sessions"], 1)

    def test_workflow_only_session_also_counts_toward_delegated_orchestratable(self):
        # Triangulation: a Workflow-only session (no Agent/Task calls) must still
        # reach delegated_orchestratable_sessions -- but honestly, via a real
        # dispatched-agent transcript, not the bare Workflow tool_use call itself
        # (contract 15:15:15 fix: the bare call alone no longer credits fan-out).
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i, path in enumerate(("src/a.py", "src/b.py", "src/c.py")):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:0{i}Z", "Write",
                {"file_path": path, "content": "line1\nline2"},
            ), None, None)
        acc.observe(_fact_event("s1", "2026-01-01T00:00:03Z", "Workflow", {}), None, None)
        acc.end_file()
        acc.begin_file("claude", "/base/proj/s1/subagents/workflows/wf_1/agent-a1.jsonl")
        acc.observe(_workflow_agent_event("s1", "2026-01-01T00:00:04Z", "a1"), None, None)
        acc.end_file()
        stats = acc.to_corpus_stats(None, None, False)
        self.assertEqual(stats["behavior"]["delegated_orchestratable_sessions"], 1)

    def test_taskcreate_alone_does_not_count_as_orchestration_dispatch(self):
        # Control: TaskCreate is todo bookkeeping (PLAN_TOOLS), not a dispatch tool,
        # and must NOT count toward agents_per_session / delegated_orchestratable.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i, path in enumerate(("src/a.py", "src/b.py", "src/c.py")):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:0{i}Z", "Write",
                {"file_path": path, "content": "line1\nline2"},
            ), None, None)
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:03Z", "TaskCreate", {"items": ["a", "b", "c"]},
        ), None, None)
        acc.end_file()
        stats = acc.to_corpus_stats(None, None, False)
        self.assertEqual(acc.agents_per_session.get("s1", 0), 0)
        self.assertEqual(stats["behavior"]["delegated_orchestratable_sessions"], 0)


class TestWorkflowFanoutTranscriptAttribution(unittest.TestCase):
    """Fix for Workflow fan-out under-credit (contract 15:15:15): a single `Workflow`
    tool_use call may dispatch many real agents. Fan-out (agents_per_session,
    month_fanouts) is now sourced from the real dispatched-agent transcripts under
    `.../subagents/workflows/wf_*/agent-*.jsonl`, one credit per distinct
    `(parent_sid, agentId)`, instead of one credit per `Workflow` tool_use event."""

    def test_agent_task_calls_keep_prior_fanout_unchanged(self):
        # 2.1: Real Agent/Task calls keep prior fan-out (spec scenario).
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i in range(4):
            acc.observe(_fact_event("s1", f"2026-01-01T00:00:0{i}Z", "Agent", {}), None, None)
        acc.end_file()
        self.assertEqual(acc.agents_per_session.get("s1"), 4)

    def test_bare_workflow_tool_call_alone_credits_nothing(self):
        # 2.3: no per-call increment on Workflow tool_use events.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Workflow", {}), None, None)
        acc.end_file()
        self.assertEqual(acc.agents_per_session.get("s1", 0), 0)

    def test_workflow_fanout_reflects_dispatched_agents_not_tool_calls(self):
        # 2.2: representative corpus shape -- 25 Workflow tool_use events (fewer than
        # the number of runs), 211 distinct dispatched-agent transcripts. Attributed
        # raw count must equal 211, not 25 and not the run count.
        acc = Accumulator()
        acc.begin_file("claude", "parent.jsonl")
        for i in range(25):
            acc.observe(_fact_event(
                "parent1", f"2026-01-01T00:{i:02d}:00Z", "Workflow", {}), None, None)
        acc.end_file()
        for i in range(211):
            fp = f"/base/proj/parent1/subagents/workflows/wf_{i % 22}/agent-{i}.jsonl"
            acc.begin_file("claude", fp)
            acc.observe(_workflow_agent_event(
                "parent1", "2026-01-02T00:00:00Z", str(i)), None, None)
            acc.end_file()
        self.assertEqual(acc.agents_per_session.get("parent1"), 211)

    def test_out_of_window_workflow_agent_transcript_credits_nothing(self):
        # 2.4: dispatched-agent transcript events all before since_dt -> uncredited.
        acc = Accumulator()
        fp = "/base/proj/parent1/subagents/workflows/wf_1/agent-abc.jsonl"
        acc.begin_file("claude", fp)
        since_dt = datetime(2026, 2, 1).astimezone()
        acc.observe(_workflow_agent_event(
            "parent1", "2026-01-01T00:00:00Z", "abc"), since_dt, None)
        acc.end_file()
        self.assertEqual(acc.agents_per_session.get("parent1", 0), 0)
        self.assertEqual(acc.month_fanouts.get("2026-01", {}).get("parent1", 0), 0)

    def test_resumed_workflow_run_credits_same_agent_once(self):
        # 2.5 / Phase 5 (5.2), SYNTHETIC-FIXTURE SUBSTITUTE, lower confidence: the
        # local real corpus sampled during apply (2026-08-06) contains exactly one
        # `wf_*` run directory total (no `resumeFromRunId` occurrence anywhere in
        # that corpus), so a genuine resumed-run duplicate could not be confirmed
        # against real data. This test instead synthesizes the scenario the design
        # describes -- the same child agentId re-referenced from a second `wf_*`
        # dir under the same parent -- and asserts the dedup key (parent_sid,
        # agentId) credits it once. Re-run this confirmation against a real
        # resumed-workflow sample if one becomes available.
        acc = Accumulator()
        fp1 = "/base/proj/parent1/subagents/workflows/wf_original/agent-shared.jsonl"
        acc.begin_file("claude", fp1)
        acc.observe(_workflow_agent_event(
            "parent1", "2026-01-01T00:00:00Z", "shared"), None, None)
        acc.end_file()
        fp2 = "/base/proj/parent1/subagents/workflows/wf_resumed/agent-shared.jsonl"
        acc.begin_file("claude", fp2)
        acc.observe(_workflow_agent_event(
            "parent1", "2026-01-01T01:00:00Z", "shared"), None, None)
        acc.end_file()
        self.assertEqual(acc.agents_per_session.get("parent1"), 1)

    def test_workflow_only_session_counts_as_delegating(self):
        # 2.6: zero Agent/Task events, N>=1 dispatched transcripts -> session
        # appears in delegating_sessions (feeds o_frequency numerator).
        acc = Accumulator()
        fp = "/base/proj/parent1/subagents/workflows/wf_1/agent-a1.jsonl"
        acc.begin_file("claude", fp)
        acc.observe(_workflow_agent_event(
            "parent1", "2026-01-01T00:00:00Z", "a1"), None, None)
        acc.end_file()
        stats = acc.to_corpus_stats(None, None, False)
        self.assertGreaterEqual(acc.agents_per_session.get("parent1", 0), 1)
        self.assertEqual(stats["behavior"]["delegating_sessions"], 1)

    def test_mixed_corpus_agent_only_session_fanout_unaffected(self):
        # 2.7: mixed corpus -- an Agent-only session's fan-out count is identical
        # to before this fix (no median drag introduced by Workflow attribution).
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i in range(3):
            acc.observe(_fact_event("agent_only", f"2026-01-01T00:00:0{i}Z", "Agent", {}), None, None)
        acc.end_file()
        fp = "/base/proj/wf_parent/subagents/workflows/wf_1/agent-a1.jsonl"
        acc.begin_file("claude", fp)
        acc.observe(_workflow_agent_event(
            "wf_parent", "2026-01-01T00:00:00Z", "a1"), None, None)
        acc.end_file()
        self.assertEqual(acc.agents_per_session.get("agent_only"), 3)


class TestPlannedC3C6(unittest.TestCase):
    """C3 (broadened planned) + C6 (substance floor): plan-file/skill signals
    count, but only above the substance floor; bare plan-mode toggles and
    <3-step todos no longer count."""

    def test_plan_file_before_write_with_enough_lines_is_planned(self):
        facts = [
            _fact("Write", ".claude/plans/feature.md", order=1, file_class="other",
                  loc=10, plan_file=True),
            _fact("Edit", "src/a.py", order=2, file_class="code", loc=90),
        ]
        result = derive_session_ordered_facts(facts)
        self.assertTrue(result["eligible"])
        self.assertTrue(result["planned_intra"])

    def test_skill_plus_plan_file_is_planned_even_with_few_lines(self):
        facts = [
            _fact("Skill", "", order=1, plan_skill=True),
            _fact("Write", ".claude/plans/feature.md", order=2, file_class="other",
                  loc=2, plan_file=True),
            _fact("Edit", "src/a.py", order=3, file_class="code", loc=90),
        ]
        result = derive_session_ordered_facts(facts)
        self.assertTrue(result["planned_intra"])

    def test_planning_skill_alone_before_code_is_planned(self):
        facts = [
            _fact("Skill", "", order=1, plan_skill=True),
            _fact("Edit", "src/a.py", order=2, file_class="code", loc=90),
        ]
        result = derive_session_ordered_facts(facts)
        self.assertTrue(result["planned_intra"])
        # skill-only does not create a shared cross-session artifact
        self.assertEqual(result["plan_artifacts"], [])

    def test_planning_skill_after_first_code_write_is_not_planned(self):
        facts = [
            _fact("Edit", "src/a.py", order=1, file_class="code", loc=90),
            _fact("Skill", "", order=2, plan_skill=True),
        ]
        self.assertFalse(derive_session_ordered_facts(facts)["planned_intra"])

    def test_bare_plan_mode_toggle_alone_is_not_planned(self):
        facts = [
            _fact("EnterPlanMode", order=1),
            _fact("ExitPlanMode", order=2),
            _fact("Edit", "src/a.py", order=3, file_class="code", loc=90),
        ]
        self.assertFalse(derive_session_ordered_facts(facts)["planned_intra"])

    def test_two_step_todo_is_not_planned(self):
        facts = [
            _fact("TodoWrite", order=1, items=["inspect", "change"]),
            _fact("Edit", "src/a.py", order=2, file_class="code", loc=90),
        ]
        self.assertFalse(derive_session_ordered_facts(facts)["planned_intra"])

    def test_three_step_todo_is_planned(self):
        facts = [
            _fact("TodoWrite", order=1, items=["inspect", "change", "verify"]),
            _fact("Edit", "src/a.py", order=2, file_class="code", loc=90),
        ]
        self.assertTrue(derive_session_ordered_facts(facts)["planned_intra"])

    def test_plan_file_with_unmeasurable_loc_counts_via_ceremony_fallback(self):
        facts = [
            _fact("Write", ".claude/plans/feature.md", order=1, file_class="other",
                  loc=None, plan_file=True),
            _fact("Edit", "src/a.py", order=2, file_class="code", loc=90),
        ]
        self.assertTrue(derive_session_ordered_facts(facts)["planned_intra"])

    def test_plan_file_too_short_without_skill_is_not_planned(self):
        facts = [
            _fact("Write", ".claude/plans/feature.md", order=1, file_class="other",
                  loc=3, plan_file=True),
            _fact("Edit", "src/a.py", order=2, file_class="code", loc=90),
        ]
        self.assertFalse(derive_session_ordered_facts(facts)["planned_intra"])

    def test_plan_artifacts_exposed_for_cross_session_credit(self):
        facts = [
            _fact("Write", ".claude/plans/feature.md", order=1, cwd="/repo",
                  file_class="other", loc=10, plan_file=True),
        ]
        result = derive_session_ordered_facts(facts)
        self.assertEqual(result["plan_artifacts"], [("/repo", 1)])


class TestWriteFactEnrichment(unittest.TestCase):
    """C1: every write fact is enriched at construction with file_class/loc/
    plan_file/plan_skill. A missing loc must NEVER flip ordered_facts_complete
    (that flag is timestamp-completeness only)."""

    def test_edit_fact_carries_file_class_and_loc(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Edit", {
            "file_path": "src/app.py", "old_string": "a\nb", "new_string": "c\nd\ne",
        }), None, None)
        fact = _facts_for(acc, "claude", "s1")[0]
        self.assertEqual(fact["file_class"], "code")
        self.assertEqual(fact["loc"], 5)  # 3 new + 2 old
        self.assertFalse(fact["plan_file"])
        self.assertTrue(acc.ordered_facts_complete)

    def test_write_fact_classifies_lockfile_and_plan_file(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Write", {
            "file_path": "package-lock.json", "content": "a\nb\nc",
        }), None, None)
        acc.observe(_fact_event("s1", "2026-01-01T00:00:01Z", "Write", {
            "file_path": ".claude/plans/feature.md", "content": "line1\nline2",
        }), None, None)
        facts = _facts_for(acc, "claude", "s1")
        self.assertEqual(facts[0]["file_class"], "lockfile")
        self.assertFalse(facts[0]["plan_file"])
        self.assertTrue(facts[1]["plan_file"])
        self.assertEqual(facts[1]["loc"], 2)

    def test_multiedit_sums_all_edits_and_notebookedit_uses_new_source(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "MultiEdit", {
            "file_path": "src/app.py",
            "edits": [
                {"old_string": "a", "new_string": "b\nc"},
                {"old_string": "x\ny", "new_string": "z"},
            ],
        }), None, None)
        acc.observe(_fact_event("s1", "2026-01-01T00:00:01Z", "NotebookEdit", {
            "notebook_path": "nb.ipynb", "new_source": "line1\nline2\nline3",
        }), None, None)
        facts = _facts_for(acc, "claude", "s1")
        self.assertEqual(facts[0]["loc"], 6)  # (1+2) + (2+1)
        self.assertEqual(facts[1]["loc"], 3)

    def test_non_write_tool_has_none_loc_and_does_not_break_completeness(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Read", {
            "file_path": "src/app.py",
        }), None, None)
        fact = _facts_for(acc, "claude", "s1")[0]
        self.assertIsNone(fact["loc"])
        self.assertTrue(acc.ordered_facts_complete)

    def test_plan_skill_true_via_skill_input(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Skill", {
            "skill": "writing-plans",
        }), None, None)
        fact = _facts_for(acc, "claude", "s1")[0]
        self.assertTrue(fact["plan_skill"])

    def test_plan_skill_true_via_subagent_type(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Agent", {
            "subagent_type": "sdd-design",
        }), None, None)
        fact = _facts_for(acc, "claude", "s1")[0]
        self.assertTrue(fact["plan_skill"])

    def test_plan_skill_true_via_attribution_skill_on_any_tool_use(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Edit", {
            "file_path": "src/app.py", "old_string": "a", "new_string": "b",
        }, attribution="autoplan"), None, None)
        fact = _facts_for(acc, "claude", "s1")[0]
        self.assertTrue(fact["plan_skill"])

    def test_plan_skill_false_when_no_signal(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Edit", {
            "file_path": "src/app.py", "old_string": "a", "new_string": "b",
        }), None, None)
        fact = _facts_for(acc, "claude", "s1")[0]
        self.assertFalse(fact["plan_skill"])


class TestAggregateOrderedC4(unittest.TestCase):
    """C4: cross-session consume-once plan credit. `aggregate_ordered` takes
    the per-session fact lists directly (values of session_ordered_tools)."""

    WINDOW = 72 * 3600

    def _plan_only_session(self, cwd="/repo", order=1000, loc=10):
        # A session that ONLY produces a plan artifact — no code write at all,
        # so it is not itself eligible, but its plan-file is still consumable.
        return [_fact("Write", ".claude/plans/feature.md", order=order, cwd=cwd,
                       file_class="other", loc=loc, plan_file=True)]

    def _execution_session(self, cwd="/repo", order=2000):
        return [_fact("Edit", "src/a.py", order=order, cwd=cwd,
                       file_class="code", loc=90)]

    def test_cross_session_plan_credited_and_consumed(self):
        result = aggregate_ordered([
            self._plan_only_session(order=1000),
            self._execution_session(order=1000 + 3600),  # 1h later, same cwd
        ])
        self.assertEqual(result["eligible"], 1)  # only the execution session is eligible
        self.assertEqual(result["planned"], 1)

    def test_reused_plan_not_credited_twice(self):
        result = aggregate_ordered([
            self._plan_only_session(order=1000),
            self._execution_session(order=1000 + 3600),       # B: first claim
            self._execution_session(order=1000 + 2 * 3600),   # C: same artifact, too late
        ])
        self.assertEqual(result["eligible"], 2)
        self.assertEqual(result["planned"], 1)  # only one of the two executions

    def test_intra_session_plan_is_consumed_before_cross_session_matching(self):
        session_a = self._plan_only_session(order=1000) + self._execution_session(order=1100)
        result = aggregate_ordered([
            session_a,
            self._execution_session(order=1000 + 3600),
        ])
        self.assertEqual((result["eligible"], result["planned"]), (2, 1))

    def test_plan_outside_window_not_credited(self):
        result = aggregate_ordered([
            self._plan_only_session(order=1000),
            self._execution_session(order=1000 + self.WINDOW + 100),
        ])
        self.assertEqual(result["eligible"], 1)
        self.assertEqual(result["planned"], 0)

    def test_plan_in_different_cwd_not_credited(self):
        result = aggregate_ordered([
            self._plan_only_session(cwd="/repo-a", order=1000),
            self._execution_session(cwd="/repo-b", order=1000 + 3600),
        ])
        self.assertEqual(result["eligible"], 1)
        self.assertEqual(result["planned"], 0)

    def test_earliest_eligible_execution_matched_first(self):
        # Two eligible, unplanned executions in the same cwd/window as ONE
        # plan artifact — only the earliest execution should be credited.
        result = aggregate_ordered([
            self._plan_only_session(order=1000),
            self._execution_session(order=1000 + 7200),   # later execution
            self._execution_session(order=1000 + 3600),   # earlier execution
        ])
        self.assertEqual(result["eligible"], 2)
        self.assertEqual(result["planned"], 1)


class TestBackslashPathsOnWindowsTranscripts(unittest.TestCase):
    """Windows transcripts record file_path inconsistently -- the SAME file shows up
    sometimes with `\\` and sometimes with `/`. Paths are only ever inspected as strings
    here (never opened), so both forms must fold to one canonical form: otherwise
    compounding writes go uncounted and a single edit run splits across two dict keys."""

    def test_compounding_write_with_backslash_path_is_counted(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Write", {
            "file_path": r"C:\Users\d\.claude\projects\p\memory\note.md",
            "content": "a\nb",
        }), None, None)
        self.assertEqual(acc.compounding_counter, 1)

    def test_edit_run_not_split_by_separator_style(self):
        # Same file, both spellings -> ONE run of 2, not two runs of 1.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for path in (r"C:\repo\a.py", "C:/repo/a.py"):
            acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Edit", {
                "file_path": path, "old_string": "a", "new_string": "b",
            }), None, None)
        acc.end_file()
        self.assertEqual(acc.edits_per_file_events, [2])

    def test_ordered_target_normalized_for_code_written_dedup(self):
        # _target stored in ordered facts must be forward-slashed so that
        # code_written.add(target) de-duplicates correctly across separators.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for path in (r"C:\repo\src\app.py", "C:/repo/src/app.py"):
            acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Write", {
                "file_path": path, "content": "x",
            }), None, None)
        acc.end_file()
        facts = []
        for v in acc.session_ordered_tools.values():
            facts.extend(v)
        targets = [f["target"] for f in facts if f["name"] == "Write"]
        self.assertTrue(all("/" in t and "\\" not in t for t in targets),
                        f"targets should be forward-slashed: {targets}")
        self.assertEqual(len(set(targets)), 1,
                         "both separator styles should collapse to one target")

    def test_posix_paths_are_untouched(self):
        # Guard for Linux/Mac: a path with no backslash must behave exactly as before.
        # Two DISTINCT posix files stay two separate runs, and the memory write counts.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Write", {
            "file_path": "/home/d/.claude/projects/p/memory/note.md", "content": "a",
        }), None, None)
        acc.observe(_fact_event("s1", "2026-01-01T00:00:01Z", "Edit", {
            "file_path": "/repo/a.py", "old_string": "a", "new_string": "b",
        }), None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 1)
        self.assertEqual(sorted(acc.edits_per_file_events), [1, 1])


class TestMcpKnowledgeWriteCompoundingCredit(unittest.TestCase):
    """Compounding credit for MCP knowledge-writes (contract 16:16:16): mem0/engram
    persistence writes now credit compounding_counter/month_compounding, gated by
    taxonomy.is_mcp_knowledge_write, with a corpus-lifetime per-distinct-target
    dedup set so target-less/repeat-target spam cannot saturate the axis while
    genuinely distinct persisted targets still each earn credit (reconciled spec
    Scenarios A and B)."""

    def test_mem0_add_memory_credits_compounding(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T12:00:00Z", "mcp__mem0__add_memory", {
            "memory_id": "m1", "text": "note",
        }), None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 1)
        self.assertEqual(acc.month_compounding.get("2026-01"), 1)

    def test_engram_mem_save_credits_compounding(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "mcp__engram__mem_save", {
            "topic_key": "sdd/foo/spec",
        }), None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 1)

    def test_reads_and_deletes_and_context7_credit_zero(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i, (name, inp) in enumerate([
            ("mcp__context7__resolve-library-id", {"query": "react"}),
            ("mcp__engram__mem_context", {}),
            ("mcp__engram__mem_current_project", {}),
            ("mcp__engram__mem_review", {}),
            ("mcp__mem0__search_memory", {"query": "x"}),
            ("mcp__mem0__delete_memory", {"memory_id": "m1"}),
        ]):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:0{i}Z", name, inp), None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 0)

    def test_anti_saturation_target_less_repeat_calls_credit_once(self):
        # Scenario A: 10 target-less mem_save calls in one session -> +1, not +10.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i in range(10):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:{i:02d}Z", "mcp__engram__mem_save", {}),
                None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 1)

    def test_anti_saturation_same_target_repeat_calls_credit_once(self):
        # Scenario A variant: same distinct target repeated -> +1, not +N.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i in range(5):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:{i:02d}Z", "mcp__engram__mem_save",
                {"topic_key": "sdd/foo/spec"}), None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 1)

    def test_distinct_targets_each_credit(self):
        # Scenario B: N distinct memory_id/topic_key values -> +N, not collapsed to 1.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        for i in range(4):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:0{i}Z", "mcp__engram__mem_save",
                {"topic_key": f"sdd/foo/target-{i}"}), None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 4)

    def test_out_of_window_mcp_write_credits_nothing(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        since_dt = datetime(2026, 2, 1).astimezone()
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:00Z", "mcp__mem0__add_memory",
            {"memory_id": "m1"}), since_dt, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 0)

    def test_filesystem_compounding_path_unaffected(self):
        # Regression: filesystem compounding sites (memory/ path) still credit
        # exactly as before, independent of any MCP knowledge-write.
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "Write", {
            "file_path": "/repo/memory/note.md", "content": "a\nb",
        }), None, None)
        acc.observe(_fact_event("s1", "2026-01-01T00:00:01Z", "mcp__mem0__add_memory", {
            "memory_id": "m1",
        }), None, None)
        acc.end_file()
        self.assertEqual(acc.compounding_counter, 2)

    def test_tool_calls_total_unchanged_by_mcp_writes(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event("s1", "2026-01-01T00:00:00Z", "mcp__mem0__add_memory", {
            "memory_id": "m1",
        }), None, None)
        acc.end_file()
        self.assertEqual(acc.tool_use_total, 1)


class TestToolSearchDiscoveryCalls(unittest.TestCase):
    """Verify that discovery counts exclude deterministic `select:` tool loading
    while the raw ToolSearch counter continues to include every call."""

    def test_select_prefixed_query_does_not_count_as_discovery(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:00Z", "ToolSearch",
            {"query": "select:Read,Edit"}), None, None)
        acc.end_file()
        self.assertEqual(acc.tool_counter.get("ToolSearch", 0), 1)
        self.assertEqual(acc.toolsearch_discovery_calls, 0)

    def test_keyword_query_counts_as_discovery(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:00Z", "ToolSearch",
            {"query": "notebook jupyter"}), None, None)
        acc.end_file()
        self.assertEqual(acc.tool_counter.get("ToolSearch", 0), 1)
        self.assertEqual(acc.toolsearch_discovery_calls, 1)

    def test_leading_whitespace_before_select_is_still_mandatory_load(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:00Z", "ToolSearch",
            {"query": "   select:Bash"}), None, None)
        acc.end_file()
        self.assertEqual(acc.toolsearch_discovery_calls, 0)

    def test_corpus_stats_tools_dict_contains_discovery_field(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:00Z", "ToolSearch",
            {"query": "select:Read"}), None, None)
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:01Z", "ToolSearch",
            {"query": "how to parse json"}), None, None)
        acc.end_file()
        stats = acc.to_corpus_stats(None, None, False)
        self.assertEqual(stats["tools"]["toolsearch_calls"], 2)
        self.assertEqual(stats["tools"]["toolsearch_discovery_calls"], 1)

    def test_source_stats_tools_dict_contains_discovery_field(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:00Z", "ToolSearch",
            {"query": "select:Read"}), None, None)
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:01Z", "ToolSearch",
            {"query": "how to parse json"}), None, None)
        acc.end_file()
        s_stats = acc.to_source_stats("claude", None, None)
        self.assertEqual(s_stats["tools"]["toolsearch_calls"], 2)
        self.assertEqual(s_stats["tools"]["toolsearch_discovery_calls"], 1)

    def test_monthly_stats_tools_dict_contains_discovery_field(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:00Z", "ToolSearch",
            {"query": "select:Read"}), None, None)
        acc.observe(_fact_event(
            "s1", "2026-01-01T00:00:01Z", "ToolSearch",
            {"query": "how to parse json"}), None, None)
        acc.end_file()
        stats = acc.to_corpus_stats(None, None, False)
        monthly = stats["_scoring_monthly_full"]
        self.assertEqual(len(monthly), 1)
        m_tools = monthly[0]["stats_full"]["tools"]
        self.assertEqual(m_tools["toolsearch_calls"], 2)
        self.assertEqual(m_tools["toolsearch_discovery_calls"], 1)

    def test_discovery_never_exceeds_raw_on_mixed_corpus(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        queries = [
            "select:Read,Edit", "select:Bash", "  select:Grep",
            "how to parse json", "notebook jupyter", "select:Write",
            "refactor patterns", "select:MultiEdit",
        ]
        for i, q in enumerate(queries):
            acc.observe(_fact_event(
                "s1", f"2026-01-01T00:00:{i:02d}Z", "ToolSearch", {"query": q}),
                None, None)
        acc.end_file()
        stats = acc.to_corpus_stats(None, None, False)
        raw = stats["tools"]["toolsearch_calls"]
        discovery = stats["tools"]["toolsearch_discovery_calls"]
        self.assertEqual(raw, 8)
        self.assertEqual(discovery, 3)
        self.assertLessEqual(discovery, raw)


if __name__ == "__main__":
    unittest.main()
