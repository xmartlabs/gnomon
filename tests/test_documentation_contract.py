import pathlib
import unittest

from gnomon.cli.insights import _HELP_TEXT
from gnomon.scoring.aq import CONTEXT_INTELLIGENCE_TARGET
from gnomon.scoring.gstack import AQ_AXIS_NOTES


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestPublicDocumentationContract(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.philosophy = (ROOT / "docs" / "scoring-philosophy.md").read_text(
            encoding="utf-8")

    def test_help_and_readme_both_publish_one_month_default(self):
        # v10: a point is scored on the month it labels. Both surfaces are hardcoded, so
        # both are pinned -- the failure this guards is one of them keeping the old
        # default and telling users their score covers six months when it covers one.
        self.assertIn("default 1", _HELP_TEXT)
        self.assertIn("default 1", self.readme)
        self.assertNotIn("default 6", _HELP_TEXT)
        self.assertNotIn("default 6", self.readme)

    def test_readme_separates_the_scoring_window_from_the_evidence_window(self):
        # The two spans differ now, and conflating them is the way a reader concludes the
        # score is a six-month number. mirdash's per-month self-heal is why the evidence
        # block stays wide, so the README has to say both things.
        normalized = " ".join(self.readme.split())
        self.assertIn("noticed_stats_monthly", normalized)
        self.assertIn("Only the scoring window is published as `context.window_months`",
                      normalized)

    def test_readme_documents_partial_term_disclosure(self):
        normalized = " ".join(self.readme.split())
        self.assertIn("partial_terms", normalized)
        self.assertIn("eligible_change_sessions", normalized)

    def test_readme_explains_rolling_30_day_weighting(self):
        self.assertIn(
            "recent (rolling 30-day) + 35% full-window",
            " ".join(self.readme.split()),
        )
        self.assertIn("65%", self.readme)
        self.assertIn("35%", self.readme)

    def test_public_docs_admit_the_blend_is_degenerate_at_a_one_month_window(self):
        """The blend was written to damp one unusual month against a stable six-month
        baseline. At a one-month scoring window `full_window` spans the calendar month
        (28-31 days) and `recent_30d` spans the trailing 30 days ending at the same
        anchor, so the two components cover 93.3% (a 28-day February) to 100% (any 30-day
        month) of the same days -- 96.8% for a 31-day month. It re-reads one month twice.

        The blend is deliberately NOT removed in this change (that is its own contract
        bump, kept separate so a score movement stays attributable to one cause), so the
        docs are what has to stop claiming a two-horizon damper. A reader who takes
        "recent behavior dominates while the full window provides stability" at face value
        concludes the published number is damped against history, and it is not."""
        metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8")
        for name, document in (("README.md", self.readme),
                               ("docs/metrics-by-source.md", metrics)):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("96.8%", normalized,
                              "the overlap between the two blend components is not "
                              "quantified anywhere in this document")
                self.assertIn("no longer damps", normalized)
                self.assertIn("next contract bump", normalized)

    def test_the_blend_code_says_the_two_components_now_overlap(self):
        """Same claim, at the two places a maintainer reads before touching the blend.
        The prose in the source is the only statement of intent the blend has -- there is
        no runtime assertion of a damping property -- so a test is what stops it silently
        reverting to the six-month story it was written for.

        `gnomon/scoring/aggregate.py` owns the weights and `_blend_aq`;
        `gnomon/cli/local.py::_rolling_aq_bucket_windows` is what actually materializes
        the 30-day bucket against the scoring window."""
        for relative in ("gnomon/scoring/aggregate.py", "gnomon/cli/local.py"):
            source = " ".join((ROOT / relative).read_text(encoding="utf-8").split())
            with self.subTest(source=relative):
                self.assertIn("no longer damps", source)
                self.assertIn("96.8%", source)

    def test_readme_discloses_raw_identifiers_without_claiming_project_names_never_upload(self):
        self.assertIn("custom skill and MCP server names", self.readme)
        self.assertIn("user-chosen identifiers", self.readme)
        self.assertIn("Prompts and file contents are not uploaded", self.readme)
        self.assertNotIn("No prompts, no quotes, no project names are ever sent", self.readme)

    def test_public_docs_publish_runtime_scoring_contract_v10(self):
        metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8")
        for document in (self.readme, metrics):
            self.assertIn("scoring inputs version 10", document)
            self.assertIn("AQ version 10", document)
            self.assertIn("GStack version 10", document)
            self.assertIn("10:10:10", document)
            self.assertNotIn("scoring contract version 7", document)
            # A stale contract literal is the failure this test exists for: the docs
            # must not still advertise a superseded triple as current.
            self.assertNotIn("8:8:8", document)
            self.assertNotIn("9:9:9", document)

    def test_readme_model_mix_describes_explicit_provider_tiers(self):
        self.assertIn("explicit provider tier tables", self.readme)
        self.assertNotIn("no hard-coded model names", self.readme)

    def test_philosophy_publishes_executable_targets_as_product_hypotheses(self):
        normalized = " ".join(self.philosophy.split())
        self.assertIn("Planning readiness | Grade ordered planning readiness only on "
                      "eligible non-trivial changes and target 50% coverage",
                      normalized)
        self.assertIn("Context Intelligence | Target evidence gathering before the first "
                      "write in 60% of eligible changes", normalized)
        # Planning practice was never pinned here even though it is an executable target
        # like the other two. Pin it WITH its denominator: the two Planning figures differ
        # only by denominator, and that is precisely what a reader conflates.
        self.assertIn("Target 30% of sessions", normalized)
        self.assertIn("50% Planning readiness, 30% Planning practice and 60% Context "
                      "Intelligence targets are explicit, versioned product hypotheses",
                      normalized)
        self.assertIn("50% of eligible *non-trivial changes* for readiness, 30% of *all "
                      "eligible top-level sessions* for practice", normalized)

    def test_context_intelligence_note_matches_executable_contract(self):
        note = AQ_AXIS_NOTES["Context Intelligence"]

        self.assertIn("eligible change sessions", note)
        self.assertIn(f"coverage / {CONTEXT_INTELLIGENCE_TARGET:.2f}", note)
        self.assertNotIn("write-sessions", note)

    def test_philosophy_describes_ordered_planning_redesign(self):
        # Ordered-planning eligibility redesign (C1-C7): the public doc must
        # describe the CURRENT mechanics, not the pre-redesign baseline.
        normalized = " ".join(self.philosophy.split())
        self.assertIn(
            "doc, config, lockfile, and test-only sessions are excluded",
            normalized,
        )
        self.assertIn("at least three distinct plan/task steps", normalized)
        self.assertIn("consume-once", normalized)
        self.assertNotIn(
            "Only Plan Mode or at least two distinct plan/task steps before "
            "the first write prove ordered readiness",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
