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

    def test_public_docs_state_that_the_recency_blend_is_removed(self):
        """v10 pinned the strings that admitted the blend had gone degenerate ("96.8%",
        "no longer damps", "next contract bump"). v11 removes the blend, so those
        descriptions are obsolete and re-pointed rather than deleted: the failure they
        guard is unchanged in kind -- prose that describes a two-horizon damper the code
        does not implement -- only the truth moved. "next contract bump" is now an
        ANTI-pin: the docs must not still promise a removal that already happened.

        The overlap arithmetic ("96.8%") is deliberately still required. It is the
        evidence for WHY the blend went, and a reader who finds "the blend was removed"
        with no measurement has to take it on faith."""
        metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8")
        for name, document in (("README.md", self.readme),
                               ("docs/metrics-by-source.md", metrics)):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("96.8%", normalized,
                              "the overlap that justified removing the blend is not "
                              "quantified anywhere in this document")
                self.assertIn("no longer damp", normalized)
                self.assertNotIn("next contract bump", normalized,
                                 "the docs still promise the removal as future work")
                self.assertNotIn("65% recent (rolling 30-day) + 35% full-window** (the "
                                 "entire scored period)", normalized,
                                 "the docs still describe the blend as current behaviour")

    def test_the_blend_code_says_it_was_removed_and_why(self):
        """Same claim, at the two places a maintainer reads before reaching for the
        blend again. There is no runtime assertion of a damping property, so prose is the
        only statement of intent -- and now the only statement of what was deleted.

        The two files carry different halves of the argument and are pinned separately:

        `gnomon/scoring/aggregate.py` owns `HISTORY_WEIGHT` and `_blend_aq`, which SURVIVE
        for replay of pre-v11 payloads and are therefore the code a reader is most likely
        to mistake for live behaviour. It has to carry the overlap measurement -- the
        evidence for the removal -- and say the survivors are readers, not producers.

        `gnomon/cli/local.py` is where the blend used to overwrite the published corpus AQ
        and where `--tools` reads that AQ back. It has to carry the mixed-basis story, or
        the next person to put a second window into `stats["agentic"]` reintroduces the
        bug with nothing in the file to warn them."""
        pins = {
            "gnomon/scoring/aggregate.py": ("96.8%", "no longer damp", "v11",
                                            "REMOVED as a producer"),
            "gnomon/cli/local.py": ("recency blend", "v11", "ONE WINDOW",
                                    "same corpus"),
        }
        for relative, expected in pins.items():
            source = " ".join((ROOT / relative).read_text(encoding="utf-8").split())
            for phrase in expected:
                with self.subTest(source=relative, phrase=phrase):
                    self.assertIn(phrase, source)

    def test_readme_discloses_raw_identifiers_without_claiming_project_names_never_upload(self):
        self.assertIn("custom skill and MCP server names", self.readme)
        self.assertIn("user-chosen identifiers", self.readme)
        self.assertIn("Prompts and file contents are not uploaded", self.readme)
        self.assertNotIn("No prompts, no quotes, no project names are ever sent", self.readme)

    def test_public_docs_publish_runtime_scoring_contract_v12(self):
        metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8")
        for document in (self.readme, metrics):
            self.assertIn("scoring inputs version 12", document)
            self.assertIn("AQ version 12", document)
            self.assertIn("GStack version 12", document)
            self.assertIn("12:12:12", document)
            self.assertNotIn("scoring contract version 7", document)
            # A stale contract literal is the failure this test exists for: the docs
            # must not still advertise a superseded triple as current.
            self.assertNotIn("8:8:8", document)
            self.assertNotIn("9:9:9", document)
            self.assertNotIn("10:10:10", document)
            self.assertNotIn("11:11:11", document)

    def test_public_docs_state_which_population_actions_per_prompt_measures(self):
        """v12 changed what the field COUNTS without changing its name, which is exactly the
        kind of move a reader cannot infer from a number. Both surfaces have to say the
        numerator is top-level-only and that the delegated volume is published separately,
        or `actions_per_prompt` reads as a drop in activity rather than a definition change.
        """
        metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8")
        for name, document in (("README.md", self.readme),
                               ("docs/metrics-by-source.md", metrics)):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("sidechain_tool_calls", normalized)
                self.assertIn("top-level", normalized)

    def test_public_docs_state_that_the_steering_term_is_withheld_not_scored(self):
        """v12 publishes `actions_per_prompt` and does NOT grade it, because the band it would
        be graded through was never fitted. A reader who is told the numerator was fixed and
        not told the term is ungraded will read a missing axis as a bug, and — worse — will
        read the fix as an improvement to their Steering score. Both surfaces must say three
        things: the term is withheld, the band is unfitted, and what replaces it.

        The pins are on the CLAIM, not on prose style, and they include an ANTI-pin for the
        sentence that was deleted: "the ratio reads 25.3 before and the axis 0.868; after, the
        axis is 1.000" was a true measurement of ONE corpus stated as a population fact, and it
        is false for 41 of the 48 measured users. The correction that replaces it may still
        quote the old figures as a record of what was wrong -- what must not come back is the
        claim itself.
        """
        metrics = (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8")
        for name, document in (("README.md", self.readme),
                               ("docs/metrics-by-source.md", metrics)):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertNotIn(
                    "the ratio reads 25.3 before and the axis 0.868; after, the axis is 1.000",
                    normalized,
                    "the docs still generalise one corpus's 0.868 -> 1.000 move into a "
                    "population claim that is false for 41 of 48 measured users")
                self.assertIn("never fitted", normalized,
                              "the docs do not say the band was never fitted")
                # The withholding itself, and that it is a decision rather than an omission.
                self.assertIn("not scored", normalized)
                # What replaces it: the measured share a 12:12:12 cohort makes available.
                self.assertIn("12:12:12", normalized)
                self.assertIn("sidechain_tool_calls", normalized)
                # ...and that the count is still published even though it is not graded.
                self.assertIn("actions_per_prompt", normalized)

    def test_metrics_doc_names_the_flag_and_the_state_field(self):
        """The mechanism has to be findable from the doc, or the next reader re-derives it.
        Only the by-source doc carries payload-field detail (the README stays prose), so the
        flag name, the two state values and the renormalization are pinned there."""
        normalized = " ".join(
            (ROOT / "docs" / "metrics-by-source.md").read_text(encoding="utf-8").split())
        self.assertIn("STEERING_LEVERAGE_BAND_VALIDATED", normalized)
        self.assertIn("withheld_unvalidated_band", normalized)
        self.assertIn("unmeasured_sidechain_labels", normalized)
        self.assertIn("CALIBRATION_CONSTANT_NAMES", normalized)
        # The measured cost, so "small" is never an unbacked adjective in the doc.
        self.assertIn("not** concentrated on delegators", normalized)

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
