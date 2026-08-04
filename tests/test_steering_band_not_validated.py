"""Bloque — the Steering-leverage term is WITHHELD while its band is unfitted, as 12:12:12.

v12 made `actions_per_prompt`'s numerator top-level-only, which is correct. The band that
number is scored through — `STEERING_LEVERAGE_BAND_MIN/_BAND_MAX/_DECAY_SPAN` — was never
fitted against anything: `git log -S` puts all three literals in b65ad99 with a one-line
message and no data (the PROVENANCE block in `gnomon/scoring/aq.py` records the correction of
an earlier claim that they had been). v12 then changed the population underneath them.

Re-fitting was DERIVED and rejected (`.context/refit_steering_band.py`). At the central
projected k = 32 the best available band [3, 13] still leaves 9 of 48 users worse (mean
-0.66 AQ, worst -8.9) against a benefit ceiling of +0.68 AQ for 4 users, and the defect being
fixed needs `app >= 60` when the population max is 22.9. No band fixes it, because the
contraction is PER USER (projected share 0.00-0.97) and a band is two scalars — and the
projection is least trustworthy exactly where the harm is largest.

So the term is not scored at all until the band can be fitted against MEASURED shares. That is
what this codebase does everywhere else it cannot measure something — `partial_terms`, the
coverage flags, the pillar's `not_applicable`, `_fanout_median`'s deliberate `None` — rather
than inventing a value. A uniform, explained absence beats an unexplainable -8.9 for the
heaviest delegators.

The MECHANISM is deliberately the one blocker 3 already built for the non-labelling-source
case: `lever = None`, the axis drops through `build_pillar._live`, and Efficiency renormalizes
its remaining 50-weight Recovery axis back to 100. No second mechanism.

The COST, measured on the same 48-user population (`.context/refit_steering_band.py`, the
`withhold_report` section; Recovery is backed out exactly from the published pillar because
Efficiency has only these two axes: `recovery = efficiency / 50 - lever_pre`):
  * vs v11 as published: mean -0.88 AQ, median -0.66, 40 of 48 users move <= 1 published
    point and 19 do not move at all after rounding. Pearson r against delegation intensity
    is -0.16 — NOT concentrated on delegators.
  * vs v12 as it would otherwise ship (contracted numerator through the unfitted band):
    mean +0.30 AQ, and the four users that band hits hardest (-9.09, -8.70, -8.18, -7.77 AQ)
    come back to +0.10, -1.22, -1.10 and -0.17. Removing that concentration is the point.
  * the single -8.62 outlier is the user whose Recovery is 0.138 — the lowest Efficiency in
    the population. Withholding stops a half-pillar of unvalidated credit from masking a
    measured signal; the unfitted band cost them -4.66 anyway.
"""
import unittest
from unittest import mock

from gnomon.scoring import aq as aq_module
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.calibration import (
    CALIBRATION_CONSTANT_NAMES, CALIBRATION_FINGERPRINTS, calibration_fingerprint,
)
from gnomon.scoring.versioning import SCORE_CONTRACT_ID


def _stats(app, sidechain_label_state="measured", recovery=0.9, api_retries=0):
    """The smallest corpus that reaches Efficiency with a chosen `actions_per_prompt`."""
    return {
        "corpus": {"sources": {"claude": {}}},
        "volume": {"tool_calls_total": 12000, "total_sessions": 20},
        "tools": {"cli_calls": 9000, "mcp_calls": 2000, "toolsearch_calls": 300},
        "stack": {"models": [("claude-opus-4-8", 100), ("claude-haiku-4-5", 40)]},
        "behavior": {"actions_per_prompt": app,
                     "sidechain_label_state": sidechain_label_state,
                     "error_recovery_ratio": recovery,
                     "api_errors_retries": api_retries},
    }


def _efficiency(stats_or_aq):
    aq = stats_or_aq if "pillars" in stats_or_aq else compute_aq(stats_or_aq)
    return next(p for p in aq["pillars"] if p["name"] == "Efficiency")


def _axis(pillar, name):
    return next((a for a in pillar["axes"] if a["name"] == name), None)


class TestTheBandDeclaresItselfUnfitted(unittest.TestCase):
    def test_the_flag_exists_and_says_the_band_is_not_validated(self):
        self.assertIs(aq_module.STEERING_LEVERAGE_BAND_VALIDATED, False)

    def test_the_flag_is_registered_calibration(self):
        """It decides whether a term is scored at all, so it is the most score-affecting
        constant in the block. Registering it also means flipping it back on cannot happen
        without a contract bump — which is the failure this flag exists to prevent."""
        self.assertIn("STEERING_LEVERAGE_BAND_VALIDATED", CALIBRATION_CONSTANT_NAMES)

    def test_flipping_the_flag_moves_the_fingerprint(self):
        baseline = calibration_fingerprint()
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            self.assertNotEqual(calibration_fingerprint(), baseline)

    def test_the_band_values_are_still_the_unfitted_originals(self):
        """The flag is not a licence to also change the numbers: 5/20/40 stay exactly as
        b65ad99 left them, so the re-fit is a separate, measured move."""
        self.assertEqual(aq_module.STEERING_LEVERAGE_BAND_MIN, 5)
        self.assertEqual(aq_module.STEERING_LEVERAGE_BAND_MAX, 20)
        self.assertEqual(aq_module.STEERING_LEVERAGE_DECAY_SPAN, 40)

    def test_the_contract_fingerprint_covers_this_move(self):
        self.assertEqual(calibration_fingerprint(),
                         CALIBRATION_FINGERPRINTS[SCORE_CONTRACT_ID])

    def test_the_older_contract_entries_are_byte_identical(self):
        self.assertEqual(CALIBRATION_FINGERPRINTS["8:8:8"], "38bf1d623bea1517")
        self.assertEqual(CALIBRATION_FINGERPRINTS["9:9:9"], "2e7638d58c2b26e4")
        self.assertEqual(CALIBRATION_FINGERPRINTS["10:10:10"], "7a2c444ff5c26f06")
        self.assertEqual(CALIBRATION_FINGERPRINTS["11:11:11"], "888bec08099b6fbc")


class TestTheTermIsWithheldAndEfficiencyRenormalizes(unittest.TestCase):
    def test_the_axis_is_dropped_even_for_a_ratio_squarely_inside_the_band(self):
        """10.0 is the population median-ish reading and scored a full 1.000. It is dropped
        anyway: the objection is to the BAND, not to any particular value in it."""
        eff = _efficiency(_stats(10.0))
        self.assertEqual(eff.get("not_applicable"), ["Steering leverage"])
        self.assertIsNone(_axis(eff, "Steering leverage"))

    def test_recovery_renormalizes_from_50_to_100(self):
        eff = _efficiency(_stats(10.0))
        recovery = _axis(eff, "Recovery")
        self.assertEqual(recovery["base_weight"], 50)
        self.assertEqual(recovery["weight"], 100)
        self.assertEqual(eff["score"], round(100 * recovery["normalized_score"], 1))

    def test_the_pillar_is_not_halved_the_way_a_zero_would_have_halved_it(self):
        """The alternative to `None` is `0.0`, which asserts a measurement nobody made and
        costs the user half the pillar. Pinned as the concrete difference."""
        eff = _efficiency(_stats(10.0))
        recovery_only = _axis(eff, "Recovery")["normalized_score"]
        self.assertAlmostEqual(eff["score"], round(100 * recovery_only, 1))
        self.assertGreater(eff["score"], round(50 * recovery_only, 1))

    def test_every_reading_of_the_ratio_is_withheld_alike(self):
        """Below the band, inside it, above it, and the degenerate 0 — one uniform absence,
        not a per-user judgement call."""
        for app in (0, 0.5, 2.0, 5.0, 13.8, 20.0, 30.0, 200.0):
            with self.subTest(actions_per_prompt=app):
                eff = _efficiency(_stats(app))
                self.assertEqual(eff.get("not_applicable"), ["Steering leverage"])

    def test_the_axis_weights_still_sum_to_100(self):
        eff = _efficiency(_stats(10.0))
        self.assertEqual(sum(a["weight"] for a in eff["axes"]), 100)


class TestTheMeasuredCountIsStillPublished(unittest.TestCase):
    """`actions_per_prompt` is MEASURED; only its scoring is not. Same principle as
    `partial_terms`: the value stands, the interpretation is withheld. The axis's `signals`
    dict cannot carry it any more (the axis is gone), so it moves to an `agentic` sibling
    beside `mcp_vs_cli` and `tool_diversity`."""

    def test_the_ratio_is_published_beside_the_score(self):
        aq = compute_aq(_stats(13.8))
        self.assertEqual(aq["steering_leverage"]["actions_per_prompt"], 13.8)

    def test_it_is_the_payload_value_and_not_a_recomputation(self):
        for app in (0, 2.0, 13.8, 253.0):
            with self.subTest(actions_per_prompt=app):
                aq = compute_aq(_stats(app))
                self.assertEqual(aq["steering_leverage"]["actions_per_prompt"], app)

    def test_a_payload_missing_the_field_publishes_the_same_default_scoring_reads(self):
        aq = compute_aq({"tools": {}, "stack": {}, "behavior": {}})
        self.assertEqual(aq["steering_leverage"]["actions_per_prompt"], 0)


class TestTheStateSaysWhichReasonApplies(unittest.TestCase):
    """Two different absences must not look alike to a payload reader: "your source cannot
    label subagent calls" is a fact about the ADAPTER and survives the band being fitted;
    "the band is not fitted" is a fact about this CONTRACT and disappears when it is. Mirrors
    the `*_state` convention (`ordered_facts_state`, `linked_model_routing_state`,
    `sidechain_label_state`)."""

    def test_the_unfitted_band_has_its_own_reason(self):
        aq = compute_aq(_stats(10.0))
        self.assertEqual(aq["steering_leverage"]["state"], "withheld_unvalidated_band")

    def test_a_source_that_cannot_label_subagent_calls_reports_that_instead(self):
        aq = compute_aq(_stats(253.0, sidechain_label_state="unmeasured"))
        self.assertEqual(aq["steering_leverage"]["state"], "unmeasured_sidechain_labels")

    def test_the_two_reasons_are_distinguishable(self):
        band = compute_aq(_stats(10.0))["steering_leverage"]["state"]
        label = compute_aq(
            _stats(10.0, sidechain_label_state="unmeasured"))["steering_leverage"]["state"]
        self.assertNotEqual(band, label)

    def test_the_adapter_reason_wins_because_it_outlives_the_band_one(self):
        """Both hold for an unlabelling delegator today. The label verdict is reported because
        it is the one still true after the band is fitted, so the field does not flip meaning
        for that source when the flag flips."""
        stats = _stats(253.0, sidechain_label_state="unmeasured")
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            after_fit = compute_aq(stats)
        self.assertEqual(after_fit["steering_leverage"]["state"],
                         "unmeasured_sidechain_labels")
        self.assertEqual(compute_aq(stats)["steering_leverage"]["state"],
                         "unmeasured_sidechain_labels")

    def test_the_state_does_not_touch_the_input_flag_it_reads(self):
        """`behavior.sidechain_label_state` is an INPUT about the adapter; the new field is an
        OUTPUT about the scoring. A labelling source keeps its "measured" input while its
        term is withheld."""
        stats = _stats(10.0)
        self.assertEqual(stats["behavior"]["sidechain_label_state"], "measured")
        self.assertEqual(compute_aq(stats)["steering_leverage"]["state"],
                         "withheld_unvalidated_band")


class TestFlippingTheFlagRestoresScoring(unittest.TestCase):
    """The scoring path must not become dead code — a withheld term that can never come back
    is a deletion wearing a flag. Every band branch is exercised through the flag."""

    def _scored(self, app):
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            aq = compute_aq(_stats(app))
        return aq, _efficiency(aq)

    def test_the_axis_comes_back_with_the_band_intact(self):
        aq, eff = self._scored(10.0)
        self.assertNotIn("not_applicable", eff)
        axis = _axis(eff, "Steering leverage")
        self.assertEqual(axis["weight"], 50)
        self.assertEqual(axis["normalized_score"], 1.0)
        self.assertEqual(axis["signals"]["actions_per_prompt"], 10.0)
        self.assertEqual(aq["steering_leverage"]["state"], "scored")

    def test_the_whole_curve_is_reachable_again(self):
        for app, expected in ((0, 0.0), (2.0, 0.4), (5.0, 1.0), (20.0, 1.0),
                              (30.0, 0.75), (60.0, 0.0), (200.0, 0.0)):
            with self.subTest(actions_per_prompt=app):
                _aq, eff = self._scored(app)
                self.assertAlmostEqual(
                    _axis(eff, "Steering leverage")["normalized_score"], expected)

    def test_scoring_it_again_costs_the_delegator_what_the_measurement_said_it_would(self):
        """The reason the flag exists, stated as arithmetic. A corpus whose contracted ratio
        lands at 2.0 scores only 0.4 through the unfitted band, and the closed form
        `d_AQ = 10 * (recovery - lever)` says what re-enabling it would take off this user."""
        _aq, scored = self._scored(2.0)
        axis = _axis(scored, "Steering leverage")
        withheld = _efficiency(_stats(2.0))
        recovery = _axis(withheld, "Recovery")["normalized_score"]
        self.assertAlmostEqual(axis["normalized_score"], 0.4)
        lost_aq = (withheld["score"] - scored["score"]) * 20 / 100
        # places=1: the pillar score is rounded to one decimal before the 20/100 pillar weight.
        self.assertAlmostEqual(lost_aq, 10 * (recovery - 0.4), places=1)
        # ...and it is a real cost, not a rounding artefact: > 5 AQ on this corpus.
        self.assertGreater(lost_aq, 5.0)

    def test_the_published_ratio_is_the_same_number_either_way(self):
        """Whether the term is scored or withheld, the measured count does not move — that is
        what makes the absence an interpretation gap rather than a data gap."""
        aq_scored, eff = self._scored(13.8)
        self.assertEqual(aq_scored["steering_leverage"]["actions_per_prompt"],
                         compute_aq(_stats(13.8))["steering_leverage"]["actions_per_prompt"])
        self.assertEqual(_axis(eff, "Steering leverage")["signals"]["actions_per_prompt"],
                         aq_scored["steering_leverage"]["actions_per_prompt"])


class TestTheWithholdingIsNotConcentratedOnDelegators(unittest.TestCase):
    """The population arithmetic that justified the decision, pinned so a later reader can
    re-run it rather than trust the prose. Efficiency has exactly two axes, so the whole
    effect is closed-form: `d_AQ = 10 * (recovery - lever)`."""

    def test_the_cost_is_ten_times_the_recovery_shortfall(self):
        # The worked example from the decision: lever 1.0, recovery 0.95 -> Efficiency goes
        # from 50*1.0 + 50*0.95 = 97.5 to 100*0.95 = 95.0, i.e. -0.5 AQ.
        stats = _stats(10.0, recovery=0.95, api_retries=0)
        withheld = _efficiency(stats)
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            scored = _efficiency(compute_aq(stats))
        recovery = _axis(withheld, "Recovery")["normalized_score"]
        self.assertAlmostEqual(withheld["score"], round(100 * recovery, 1))
        self.assertAlmostEqual(scored["score"], round(50 + 50 * recovery, 1))
        self.assertAlmostEqual((withheld["score"] - scored["score"]) * 20 / 100,
                               10 * (recovery - 1.0), places=2)

    def test_a_user_with_full_recovery_loses_nothing(self):
        """The cost is bounded by the Recovery shortfall, so it cannot exceed 10 AQ and is
        zero for anyone Recovery already scores full. That bound is why the move is small
        for the bulk of the population (measured mean recovery 0.90)."""
        stats = _stats(10.0, recovery=1.0, api_retries=0)
        withheld = _efficiency(stats)
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            scored = _efficiency(compute_aq(stats))
        self.assertEqual(withheld["score"], scored["score"])

    def test_a_delegation_heavy_corpus_is_better_off_withheld(self):
        """The direction that decides it. A heavy delegator's contracted ratio falls to the
        low ramp; withholding pays them back what the unfitted band took."""
        stats = _stats(2.0, recovery=0.9)
        withheld = _efficiency(stats)
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            scored = _efficiency(compute_aq(stats))
        self.assertGreater(withheld["score"], scored["score"])


if __name__ == "__main__":
    unittest.main()
