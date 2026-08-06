import pathlib
import unittest

from gnomon.cli.insights import _HELP_TEXT
from gnomon.scoring.aq import (
    CONTEXT_INTELLIGENCE_TARGET,
    HARNESS_BELOW_TEAM_CREDIT,
    HARNESS_TEAM_SESSION_TYPES,
    STEERING_LEVERAGE_BAND_VALIDATED,
)
from gnomon.scoring.gstack import AQ_AXIS_NOTES, SCORE_NOTES
from gnomon.scoring.versioning import SCORE_CONTRACT_ID


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestPublicDocumentationContract(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(
            encoding="utf-8")
        self.philosophy = (ROOT / "docs" / "scoring-philosophy.md").read_text(
            encoding="utf-8")

    def test_help_and_readme_publish_the_one_month_default(self):
        self.assertIn("default 1", _HELP_TEXT)
        self.assertIn("default 1", self.readme)
        self.assertNotIn("default 6", _HELP_TEXT)
        self.assertNotIn("default 6", self.readme)

    def test_docs_separate_scoring_window_from_evidence_window(self):
        for document in (self.readme, self.metrics):
            normalized = " ".join(document.split())
            self.assertIn("noticed_stats_monthly", normalized)
            self.assertIn("context.window_months", normalized)
            self.assertIn("six-month evidence", normalized)

    def test_public_docs_publish_current_contract_only(self):
        expected = (
            "scoring inputs version 14",
            "AQ version 14",
            "GStack version 14",
            SCORE_CONTRACT_ID,
        )
        for document in (self.readme, self.metrics):
            for phrase in expected:
                with self.subTest(phrase=phrase):
                    self.assertIn(phrase, document)
            self.assertNotIn("scoring inputs version 13", document)
            self.assertNotIn("13:13:13", document)
            self.assertNotIn("96.8%", document)

    def test_public_docs_explain_actions_per_prompt_inputs(self):
        for document in (self.readme, self.metrics):
            normalized = " ".join(document.split())
            for phrase in (
                "actions_per_prompt",
                "top-level tool calls",
                "total_instructions",
                "sidechain_tool_calls",
                "tool_calls_total",
            ):
                with self.subTest(phrase=phrase):
                    self.assertIn(phrase, normalized)

    def test_public_docs_explain_withheld_steering_states(self):
        for document in (self.readme, self.metrics):
            normalized = " ".join(document.split())
            for state in (
                "withheld_unvalidated_band",
                "unmeasured_sidechain_labels",
                "scored",
            ):
                with self.subTest(state=state):
                    self.assertIn(state, normalized)
            self.assertIn("renormalized", normalized)
        self.assertFalse(STEERING_LEVERAGE_BAND_VALIDATED)

    def test_metrics_documents_partial_terms_and_evidence_floor(self):
        normalized = " ".join(self.metrics.split())
        self.assertIn("partial_terms", normalized)
        self.assertIn("{scored, total, weight_scored}", normalized)
        self.assertIn("insufficient denominator drops the term", normalized)

    def test_metrics_documents_source_coverage_and_replay_limits(self):
        normalized = " ".join(self.metrics.split())
        for phrase in (
            "Metric × source",
            "sidechain_label_state",
            "TOP_LEVEL_ACTIONS_INPUTS_VERSION",
            "aq_exactness",
            "profiles_by_source_status",
            "900 KiB",
            "PayloadTooLarge",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized)

    def test_v13_taxonomy_is_named_and_fingerprinted(self):
        source = (ROOT / "gnomon" / "scoring" / "versioning.py").read_text(
            encoding="utf-8")
        calibration = (ROOT / "gnomon" / "scoring" / "calibration.py").read_text(
            encoding="utf-8")
        self.assertEqual(SCORE_CONTRACT_ID, "14:14:14")
        self.assertEqual(HARNESS_TEAM_SESSION_TYPES, 3)
        self.assertEqual(HARNESS_BELOW_TEAM_CREDIT, 0.6)
        self.assertIn("unmeasured delegation", source)
        self.assertIn("HARNESS_TEAM_SESSION_TYPES", calibration)
        self.assertIn("HARNESS_BELOW_TEAM_CREDIT", calibration)
        self.assertIn('"13:13:13"', calibration)
        self.assertIn('"14:14:14"', calibration)
        self.assertNotIn("REUBICATIONS", source)

    def test_readme_discloses_raw_identifiers_without_overclaiming_privacy(self):
        self.assertIn("custom skill and MCP server names", self.readme)
        self.assertIn("user-chosen identifiers", self.readme)
        self.assertIn("Prompts and file contents are not uploaded", self.readme)
        self.assertNotIn("No prompts, no quotes, no project names are ever sent", self.readme)

    def test_readme_model_mix_describes_explicit_provider_tiers(self):
        self.assertIn("explicit provider tier tables", self.readme)
        self.assertNotIn("no hard-coded model names", self.readme)

    def test_philosophy_publishes_executable_targets_as_product_hypotheses(self):
        normalized = " ".join(self.philosophy.split())
        self.assertIn("Planning readiness | Grade ordered planning readiness only on "
                      "eligible non-trivial changes and target 50% coverage", normalized)
        self.assertIn("Context Intelligence | Target evidence gathering before the first "
                      "write in 60% of eligible changes", normalized)
        self.assertIn("Target 30% of sessions", normalized)
        self.assertIn("50% Planning readiness, 30% Planning practice and 60% Context "
                      "Intelligence targets are explicit, versioned product hypotheses",
                      normalized)
        self.assertIn("50% of eligible *non-trivial changes* for readiness, 30% of *all "
                      "eligible top-level sessions* for practice", normalized)

    def test_planning_glossary_matches_the_real_four_term_formula(self):
        """H4: SCORE_NOTES['Planning'] must describe the actual weights at
        gstack.py:345-351 — 0.30 explore, 0.30 reasoning, 0.25*coverage planning
        ceremony (NOT a flat 0.25), 0.15 ordered planning."""
        note = SCORE_NOTES["Planning"]
        self.assertIn("0.30", note)
        self.assertIn("0.25", note)
        self.assertIn("coverage", note)
        self.assertIn("0.15", note)
        self.assertIn("ordered planning", note)

    def test_context_intelligence_note_matches_executable_contract(self):
        note = AQ_AXIS_NOTES["Context Intelligence"]
        self.assertIn("eligible change sessions", note)
        self.assertIn(f"coverage / {CONTEXT_INTELLIGENCE_TARGET:.2f}", note)
        self.assertNotIn("write-sessions", note)

    def test_philosophy_describes_ordered_planning_redesign(self):
        normalized = " ".join(self.philosophy.split())
        self.assertIn("doc, config, lockfile, and test-only sessions are excluded", normalized)
        self.assertIn("at least three distinct plan/task steps", normalized)
        self.assertIn("consume-once", normalized)
        self.assertNotIn(
            "Only Plan Mode or at least two distinct plan/task steps before "
            "the first write prove ordered readiness",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
