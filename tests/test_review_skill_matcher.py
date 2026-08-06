"""_is_review_skill_name: `verif*` must LEAD the tail segment, or terminate it as
`-verify`. A name where the word merely appears MID-tail (e.g. "email-verify-flow") is
not a review/verification skill and must stay out.

History, because the rule moved twice. Pre-v8 it was a bare substring match, which
admitted "email-verify-flow". v8 narrowed it to `tail == "verify" or tail.endswith(
"-verify")`, which removed that false positive but also dropped the PREFIX forms real
skills use ("verify-frontend", "verify_changes") -- measured at 2.2% of the pooled review
numerator over 16 real corpora, and 59.5% for one user. v9 restores those via a
`verif`-leading tail, which additionally admits the noun form
"verification-before-completion" that BOTH earlier rules missed ("verification" does not
contain the substring "verify")."""
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

    def test_verify_prefixed_tail(self):
        # Real production skills, dropped by v8's tail-only rule.
        self.assertTrue(_is_review_skill_name("verify-frontend"))
        self.assertTrue(_is_review_skill_name("verify-backend"))
        self.assertTrue(_is_review_skill_name("verify_changes"))

    def test_verification_noun_form(self):
        # Missed by BOTH the pre-v8 substring rule and v8's tail rule.
        self.assertTrue(
            _is_review_skill_name("superpowers:verification-before-completion"))
        self.assertTrue(_is_review_skill_name("verification-before-completion"))


class TestReviewSkillMatcherDropped(unittest.TestCase):
    """These MUST stay/become False."""

    def test_plan_eng_review(self):
        self.assertFalse(_is_review_skill_name("plan-eng-review"))

    def test_ceo_review(self):
        self.assertFalse(_is_review_skill_name("ceo-review"))

    def test_embedded_verify_is_not_a_review_skill(self):
        # "verify" appears mid-tail: this is an email flow, not a review skill. The
        # pre-v8 bare-substring match wrongly returned True; both v8 and v9 reject it,
        # and it is the ONLY false positive v8's narrowing should ever have removed.
        self.assertFalse(_is_review_skill_name("email-verify-flow"))
        self.assertFalse(_is_review_skill_name("send-verify-email"))

    def test_unrelated_skill(self):
        self.assertFalse(_is_review_skill_name("brainstorm"))


if __name__ == "__main__":
    unittest.main()
