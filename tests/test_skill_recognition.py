import unittest

from gnomon.analysis.metrics import _is_review_skill_name, _is_task_skill_name


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


if __name__ == "__main__":
    unittest.main()
