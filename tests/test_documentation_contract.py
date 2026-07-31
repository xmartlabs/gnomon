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

    def test_help_and_readme_both_publish_six_month_default(self):
        self.assertIn("default 6", _HELP_TEXT)
        self.assertIn("default 6", self.readme)

    def test_readme_explains_rolling_30_day_weighting(self):
        self.assertIn(
            "recent (rolling 30-day) + 35% full-window",
            " ".join(self.readme.split()),
        )
        self.assertIn("65%", self.readme)
        self.assertIn("35%", self.readme)

    def test_readme_discloses_raw_identifiers_without_claiming_project_names_never_upload(self):
        self.assertIn("custom skill and MCP server names", self.readme)
        self.assertIn("user-chosen identifiers", self.readme)
        self.assertIn("Prompts and file contents are not uploaded", self.readme)
        self.assertNotIn("No prompts, no quotes, no project names are ever sent", self.readme)

    def test_public_docs_publish_runtime_scoring_contract_v9(self):
        metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8")
        for document in (self.readme, metrics):
            self.assertIn("scoring inputs version 9", document)
            self.assertIn("AQ version 9", document)
            self.assertIn("GStack version 9", document)
            self.assertIn("9:9:9", document)
            self.assertNotIn("scoring contract version 7", document)
            # A stale contract literal is the failure this test exists for: the docs
            # must not still advertise the superseded triple as current.
            self.assertNotIn("8:8:8", document)

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
