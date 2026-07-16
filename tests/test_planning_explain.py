import unittest
from collections import Counter

from gnomon.cli.accumulator import aggregate_ordered
from gnomon.output.planning_explain import build_planning_explain


def _fact(name, target="", order=0, cwd="/repo", file_class="other", loc=None,
          plan_file=False, plan_skill=False, items=None):
    return {
        "name": name, "target": target, "items": items or [], "cwd": cwd,
        "order": order, "ordinal": order, "knowledge": False,
        "file_class": file_class, "loc": loc, "plan_file": plan_file,
        "plan_skill": plan_skill,
    }


def _synthetic_sessions():
    """A multi-session set covering: plan-only (ineligible donor), cross-session
    credited execution, intra-planned, trivial ineligible, and bare eligible."""
    return {
        ("claude", "plan"): [
            _fact("Write", ".claude/plans/f.md", order=1000, cwd="/repo",
                  file_class="other", loc=20, plan_file=True),
        ],
        ("claude", "exec"): [
            _fact("Edit", "src/a.py", order=1000 + 3600, cwd="/repo",
                  file_class="code", loc=90),
        ],
        ("claude", "intra"): [
            _fact("TodoWrite", order=1, cwd="/other", items=["a", "b", "c"]),
            _fact("Edit", "src/b.py", order=2, cwd="/other",
                  file_class="code", loc=90),
        ],
        ("claude", "trivial"): [
            _fact("Edit", "src/c.py", order=5, cwd="/x", file_class="code", loc=10),
        ],
        ("claude", "bare"): [
            _fact("Write", "src/d.py", order=9, cwd="/y", file_class="code", loc=90),
        ],
    }


class TestBuildPlanningExplain(unittest.TestCase):
    def setUp(self):
        self.sessions = _synthetic_sessions()
        self.thinking = Counter({("claude", "exec"): 12, ("claude", "intra"): 4})
        self.prompts = {("claude", "exec"): "please build the thing"}
        self.result = build_planning_explain(self.sessions, self.thinking, self.prompts)

    def test_reconciles_with_aggregate_ordered(self):
        agg = aggregate_ordered(self.sessions.values())
        summary = self.result["summary"]
        self.assertTrue(summary["reconciles"])
        self.assertEqual(summary["eligible"], agg["eligible"])
        self.assertEqual(summary["planned"], agg["planned"])
        # rows sum must equal the aggregate too
        self.assertEqual(sum(1 for r in self.result["rows"] if r["eligible"]),
                         agg["eligible"])
        self.assertEqual(
            sum(1 for r in self.result["rows"] if r["eligible"] and r["planned"]),
            agg["planned"])

    def test_summary_counts(self):
        summary = self.result["summary"]
        # eligible: exec, intra, bare = 3
        self.assertEqual(summary["eligible"], 3)
        # planned: exec (cross), intra (intra) = 2
        self.assertEqual(summary["planned"], 2)
        self.assertEqual(summary["ineligible_reasons"].get("trivial"), 1)

    def test_cross_session_credit_reflected_per_session(self):
        rows = {r["session"]: r for r in self.result["rows"]}
        exec_row = rows["exec"]
        self.assertTrue(exec_row["planned"])
        self.assertTrue(exec_row["cross_session"])
        intra_row = rows["intra"]
        self.assertTrue(intra_row["planned"])
        self.assertFalse(intra_row["cross_session"])
        self.assertIn("todo>=3", intra_row["signals"])

    def test_thinking_and_prompt_joined(self):
        rows = {r["session"]: r for r in self.result["rows"]}
        self.assertEqual(rows["exec"]["thinking_blocks"], 12)
        self.assertEqual(rows["exec"]["prompt"], "please build the thing")


class TestSkillOnlySignal(unittest.TestCase):
    def test_plan_skill_alone_surfaces_skill_signal(self):
        sessions = {
            ("claude", "skl"): [
                _fact("Skill", "", order=1, cwd="/z", plan_skill=True),
                _fact("Edit", "src/e.py", order=2, cwd="/z", file_class="code", loc=90),
            ],
        }
        result = build_planning_explain(sessions, Counter(), {})
        row = result["rows"][0]
        self.assertTrue(row["planned"])
        self.assertIn("skill", row["signals"])
        self.assertTrue(result["summary"]["reconciles"])
        self.assertEqual(result["summary"]["planned_signals"].get("skill"), 1)


if __name__ == "__main__":
    unittest.main()
