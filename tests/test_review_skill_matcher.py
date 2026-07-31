"""_is_review_skill_name (honest-aq-series step 4): exact-TAIL matching for
"verify", replacing the old bare substring match. A name with "verify"
embedded mid-string but NOT at the tail (e.g. "email-verify-flow") must not
be treated as a review/verification skill."""
import unittest

from gnomon.analysis.metrics import _is_review_skill_name


class TestReviewSkillMatcherPreserved(unittest.TestCase):
    """These MUST stay True after the fix."""

    def test_judgment_day(self):
        self.assertTrue(_is_review_skill_name("judgment-day"))

    def test_jd_judge_a(self):
        self.assertTrue(_is_review_skill_name("jd-judge-a"))

    def test_review_risk(self):
        self.assertTrue(_is_review_skill_name("review-risk"))

    def test_code_review(self):
        self.assertTrue(_is_review_skill_name("code-review"))

    def test_bare_verify(self):
        self.assertTrue(_is_review_skill_name("verify"))

    def test_sdd_verify_tail_anchored(self):
        self.assertTrue(_is_review_skill_name("sdd-verify"))

    def test_cerberus(self):
        self.assertTrue(_is_review_skill_name("cerberus"))

    def test_bare_review_tail(self):
        self.assertTrue(_is_review_skill_name("review"))

    def test_security_review(self):
        self.assertTrue(_is_review_skill_name("security-review"))


class TestReviewSkillMatcherDropped(unittest.TestCase):
    """These MUST stay/become False."""

    def test_plan_eng_review(self):
        self.assertFalse(_is_review_skill_name("plan-eng-review"))

    def test_ceo_review(self):
        self.assertFalse(_is_review_skill_name("ceo-review"))

    def test_embedded_verify_not_tail_anchored(self):
        # "verify" appears as a substring but is not the terminal segment --
        # the old bare-substring match wrongly returned True for this.
        self.assertFalse(_is_review_skill_name("email-verify-flow"))

    def test_verify_prefix_not_tail(self):
        self.assertFalse(_is_review_skill_name("verify-and-notify"))

    def test_unrelated_skill(self):
        self.assertFalse(_is_review_skill_name("brainstorm"))


if __name__ == "__main__":
    unittest.main()
