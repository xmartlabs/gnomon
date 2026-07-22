import unittest

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


if __name__ == "__main__":
    unittest.main()
