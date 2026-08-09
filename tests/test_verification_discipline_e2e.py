"""F6 — real-pipeline (Accumulator-driven) tests for the v18 Verification coverage
term and the v18 Discipline reweight, pinning the arithmetic no existing test exercises
end-to-end.

Every fixture here is driven through `Accumulator.begin_file/observe/end_file` and the
real `to_source_stats`/`to_corpus_stats` shaping — never a hand-built synthetic scoring
block — so these tests fail if the ACCUMULATOR stops deriving the fields correctly, not
just if the scoring formula regresses.
"""
import unittest
from unittest import mock

from gnomon.cli import accumulator as accumulator_module
from gnomon.cli.accumulator import Accumulator
from gnomon.scoring.aq import (
    MIN_ELIGIBLE_SESSIONS, PLANNING_PRACTICE_TARGET, PLANNING_TARGET, compute_aq,
)

_CWD = "/repo"
_NO_CHURN = {"repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
             "deletions": 0, "churn": 0, "commits": 0, "per_repo": []}


def _ts(minute, second=0):
    return f"2026-07-06T10:{minute:02d}:{second:02d}.000Z"


def _write_event(sid, minute, second, path, lines):
    content = "x\n" * lines
    return {"type": "assistant", "sessionId": sid, "cwd": _CWD,
            "timestamp": _ts(minute, second), "isSidechain": False,
            "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                        "content": [{"type": "tool_use", "name": "Write",
                                     "input": {"file_path": path, "content": content}}]}}


def _bash_event(sid, minute, second, command):
    return {"type": "assistant", "sessionId": sid, "cwd": _CWD,
            "timestamp": _ts(minute, second), "isSidechain": False,
            "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                        "content": [{"type": "tool_use", "name": "Bash",
                                     "input": {"command": command}}]}}


def _todo_event(sid, minute, second, steps):
    return {"type": "assistant", "sessionId": sid, "cwd": _CWD,
            "timestamp": _ts(minute, second), "isSidechain": False,
            "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                        "content": [{"type": "tool_use", "name": "TodoWrite",
                                     "input": {"todos": steps}}]}}


def _exit_plan_mode_event(sid, minute, second):
    return {"type": "assistant", "sessionId": sid, "cwd": _CWD,
            "timestamp": _ts(minute, second), "isSidechain": False,
            "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                        "content": [{"type": "tool_use", "name": "ExitPlanMode",
                                     "input": {}}]}}


def _task_update_event(sid, minute, second):
    return {"type": "assistant", "sessionId": sid, "cwd": _CWD,
            "timestamp": _ts(minute, second), "isSidechain": False,
            "message": {"role": "assistant", "model": "claude-sonnet-4-6",
                        "content": [{"type": "tool_use", "name": "TaskUpdate",
                                     "input": {}}]}}


def _drive(rows, source="claude"):
    """Fold `rows` through the REAL accumulator and return (corpus_stats, source_stats)."""
    acc = Accumulator()
    acc.begin_file(source, f"/c/{source}.jsonl")
    for row in rows:
        acc.observe(row, None, None)
    acc.end_file()
    with mock.patch.object(accumulator_module, "git_churn", lambda *a, **k: dict(_NO_CHURN)):
        corpus = acc.to_corpus_stats(None, None, None)
        per_source = acc.to_source_stats(source, None, None)
    return corpus, per_source


def _discipline_axis(agentic):
    breadth = next(p for p in agentic["pillars"] if p["name"] == "Breadth")
    return next(a for a in breadth["axes"] if a["name"] == "Discipline")


def _verification_axis(agentic):
    craft = next(p for p in agentic["pillars"] if p["name"] == "Craft")
    return next(a for a in craft["axes"] if a["name"] == "Verification")


class VerificationCoverageRealPipelineTests(unittest.TestCase):
    """Two ordered-facts change-sessions, ONE also running a recognized shell-test
    command -- the accumulator itself must derive eligible/test-covered/coverage
    correctly, through BOTH the corpus and the per-source stat paths."""

    def _rows(self):
        return [
            _write_event("sA", 0, 0, "src/a.py", 90),
            _bash_event("sA", 0, 1, "pytest"),
            _write_event("sB", 5, 0, "src/b.py", 90),
        ]

    def test_eligible_and_test_covered_counts(self):
        corpus, per_source = _drive(self._rows())
        for stats, label in ((corpus, "corpus"), (per_source, "per_source")):
            behavior = stats["behavior"]
            self.assertEqual(behavior["eligible_change_sessions"], 2, label)
            self.assertEqual(behavior["test_covered_change_sessions"], 1, label)
            self.assertEqual(behavior["ordered_facts_state"], "measured", label)

    def test_coverage_scores_half_through_both_stat_paths(self):
        corpus, per_source = _drive(self._rows())
        for stats, label in ((corpus, "corpus"), (per_source, "per_source")):
            agentic = compute_aq(stats)
            verification = _verification_axis(agentic)
            self.assertEqual(verification["signals"]["test_coverage"], 0.5, label)


class DisciplineWeightedFormulaTests(unittest.TestCase):
    """5 measured change-eligible sessions: 2 carry a qualifying plan (ordered_planning
    numerator) and 1 of the 5 also emits ExitPlanMode (planning_habit numerator), so
    BOTH Discipline survivors are live simultaneously -- pinning the .667/.333
    renormalized weights (v18 dropped the .40 task-tool term) no existing test checks
    with both terms measured at once."""

    def _rows(self):
        rows = []
        # s1: TodoWrite (3 steps, before the write) -> planned; ExitPlanMode -> planning
        # practice numerator.
        rows.append(_todo_event("s1", 0, 0, ["a", "b", "c"]))
        rows.append(_exit_plan_mode_event("s1", 0, 1))
        rows.append(_write_event("s1", 0, 2, "src/s1.py", 90))
        # s2: TodoWrite (3 steps, before the write) -> planned only.
        rows.append(_todo_event("s2", 1, 0, ["a", "b", "c"]))
        rows.append(_write_event("s2", 1, 1, "src/s2.py", 90))
        # s3-s5: plain eligible change sessions, no plan signal at all.
        for i, sid in enumerate(("s3", "s4", "s5"), start=2):
            rows.append(_write_event(sid, i, 0, f"src/{sid}.py", 90))
        return rows

    def test_discipline_pins_667_333_renormalized_weights(self):
        corpus, _ = _drive(self._rows())
        behavior = corpus["behavior"]

        # Sanity: both survivors' denominators clear the significance floor, and their
        # numerators are exactly what the fixture built.
        self.assertGreaterEqual(behavior["eligible_change_sessions"], MIN_ELIGIBLE_SESSIONS)
        self.assertEqual(behavior["eligible_change_sessions"], 5)
        self.assertEqual(behavior["planned_eligible_sessions"], 2)
        self.assertEqual(behavior["planning_skill_sessions"], 1)
        self.assertEqual(behavior["planning_skill_eligible_sessions"], 5)

        planning_habit = min(1.0, (1 / 5) / PLANNING_PRACTICE_TARGET)
        ordered_planning = min(1.0, (2 / 5) / PLANNING_TARGET)
        expected = (.40 * planning_habit + .20 * ordered_planning) / .60
        # The literal .667/.333 renormalized form the fix must reproduce.
        self.assertAlmostEqual(expected, .667 * planning_habit + .333 * ordered_planning,
                               places=3)

        agentic = compute_aq(corpus)
        discipline = _discipline_axis(agentic)
        self.assertNotIn("partial_terms", discipline)  # both terms live -> no disclosure
        self.assertAlmostEqual(discipline["normalized_score"], expected, places=6)


class DisciplineTaskToolInvarianceTests(unittest.TestCase):
    """v18 dropped the task-tool rate term from Discipline entirely -- the raw
    `task_tool_calls` count must stay a published diagnostic while having ZERO effect
    on the scored Discipline axis, whether it is 0 or large."""

    def _base_rows(self):
        rows = []
        rows.append(_todo_event("s1", 0, 0, ["a", "b", "c"]))
        rows.append(_exit_plan_mode_event("s1", 0, 1))
        rows.append(_write_event("s1", 0, 2, "src/s1.py", 90))
        rows.append(_todo_event("s2", 1, 0, ["a", "b", "c"]))
        rows.append(_write_event("s2", 1, 1, "src/s2.py", 90))
        for i, sid in enumerate(("s3", "s4", "s5"), start=2):
            rows.append(_write_event(sid, i, 0, f"src/{sid}.py", 90))
        return rows

    def test_task_tool_calls_does_not_move_discipline(self):
        zero_rows = self._base_rows()
        many_rows = self._base_rows() + [
            _task_update_event("s3", 2, i + 1) for i in range(40)
        ]

        zero_corpus, _ = _drive(zero_rows)
        many_corpus, _ = _drive(many_rows)

        self.assertEqual(zero_corpus["tools"]["task_tool_calls"], 0)
        self.assertEqual(many_corpus["tools"]["task_tool_calls"], 40)

        zero_discipline = _discipline_axis(compute_aq(zero_corpus))
        many_discipline = _discipline_axis(compute_aq(many_corpus))

        self.assertEqual(zero_discipline["normalized_score"],
                          many_discipline["normalized_score"])
        # The count is still disclosed as a diagnostic on the axis's signals.
        self.assertEqual(zero_discipline["signals"]["task_tool_calls"], 0)
        self.assertEqual(many_discipline["signals"]["task_tool_calls"], 40)


if __name__ == "__main__":
    unittest.main()
