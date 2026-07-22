import unittest

from gnomon.analysis.metrics import _is_review_skill_name, _is_task_skill_name
from gnomon.sources.antigravity import _skill_from_path


class TestReviewSkillRecognition(unittest.TestCase):
    def test_review_and_judgment_families(self):
        cases = {
            "review-readability": True,
            "gentle-ai:review-risk": True,
            "/skills/review-resilience": True,
            "judgment-day": True,
            "gentle-ai:jd-judge-reliability": True,
            "caveman-review": True,
            "requesting-code-review": True,
            "plan-eng-review": False,
            "ceo-review": False,
            "sdd-design": False,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(_is_review_skill_name(name), expected)


class TestTaskSkillRecognition(unittest.TestCase):
    def test_sdd_task_planning_families(self):
        cases = {
            "sdd-tasks": True,
            "gentle-ai:sdd-tasks": True,
            "/skills/sdd-ff": True,
            "gentle-ai:sdd-ff": True,
            "sdd-spec": False,
            "sdd-apply": False,
            "writing-plans": False,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(_is_task_skill_name(name), expected)


class TestAntigravitySkillPathRecognition(unittest.TestCase):
    """Antigravity paths arrive either from a `file://` URI (forward slashes by spec) or
    raw from the Windsurf SQLite keys, which on Windows are backslashed. Both spellings
    must resolve the same skill AND hit the same vendored-tree guards."""

    def test_backslash_and_forward_slash_resolve_same_skill(self):
        for path in (r"C:\repo\skills\brainstorming\SKILL.md",
                     "C:/repo/skills/brainstorming/SKILL.md",
                     "/home/d/repo/skills/brainstorming/SKILL.md"):
            with self.subTest(path=path):
                self.assertEqual(_skill_from_path(path), "brainstorming")

    def test_vendored_trees_skipped_in_both_spellings(self):
        for path in (r"C:\repo\node_modules\pkg\skills\x\SKILL.md",
                     "/repo/node_modules/pkg/skills/x/SKILL.md",
                     r"C:\repo\vendor\pkg\skills\x\SKILL.md"):
            with self.subTest(path=path):
                self.assertIsNone(_skill_from_path(path))

    def test_non_skill_paths_and_empties(self):
        for path in (r"C:\repo\src\app.py", "/repo/src/app.py", "", None):
            with self.subTest(path=path):
                self.assertIsNone(_skill_from_path(path))


if __name__ == "__main__":
    unittest.main()
