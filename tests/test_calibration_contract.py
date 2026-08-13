"""The calibration constants and the score contract ID must move TOGETHER.

`tests/test_score_contract_atomicity.py` only proves the contract left "7:7:7"; it stays
green if a target is re-fitted while the contract ID is reused, which silently pools two
different scoring semantics into one cohort (`COMPARISON_POLICY` is
`same_score_contract_id_only`, so mirdash would compare re-fitted rows against pre-fit rows
believing they are comparable).

These tests close that hole mechanically rather than by policy: every score-affecting
calibration constant is hashed into a fingerprint, and the fingerprint is registered against
the contract ID that published it. Editing a constant without adding a NEW contract entry
turns this file red.
"""
import importlib
import unittest
from unittest import mock

from gnomon.scoring import aq, gstack
from gnomon.scoring.calibration import (
    CALIBRATION_CONSTANT_NAMES,
    CALIBRATION_FINGERPRINTS,
    EXTERNAL_CALIBRATION_CONSTANT_NAMES,
    NON_CALIBRATION_CONSTANT_NAMES,
    ZERO_CALIBRATION_DELTA_CONTRACT_IDS,
    calibration_fingerprint,
)
from gnomon.scoring.versioning import SCORE_CONTRACT_ID


GSTACK_CALIBRATION_CONSTANT_NAMES = (
    "EXECUTION_OUTPUT_LINES_PER_HOUR_TARGET",
    "DELEGATION_RUNS_PER_PROMPT_TARGET",
    "PLANNING_EXPLORE_RATIO_TARGET",
    "THINKING_BLOCKS_PER_SESSION_TARGET",
    "ITERATION_DEPTH_MEAN_TARGET",
    "ITERATION_DEPTH_MEAN_DECAY_SPAN",
    "ITERATION_DEPTH_P90_TARGET",
    "ITERATION_DEPTH_P90_DECAY_SPAN",
    "FILES_HAMMERED_PER_SESSION_TARGET",
    "QUALITY_CEREMONY_PER_SESSION_TARGET",
    "ERROR_RATE_PER_100_TOOLS_TARGET",
    "EVIDENCE_SATURATION_TOOL_CALLS",
)
AQ_REEXPORT_NAMES = (
    "CONTEXT_INTELLIGENCE_TARGET",
    "MIN_ELIGIBLE_SESSIONS",
    "PLANNING_PRACTICE_TARGET",
    "PLANNING_TARGET",
)


def _is_public_numeric_constant(name, value):
    return (name.isupper() and not name.startswith("_")
            and isinstance(value, (int, float)))


def _unclassified_gstack_constants():
    aq_classified = set(CALIBRATION_CONSTANT_NAMES) | set(NON_CALIBRATION_CONSTANT_NAMES)
    external = set(EXTERNAL_CALIBRATION_CONSTANT_NAMES)
    return {
        name for name, value in vars(gstack).items()
        if _is_public_numeric_constant(name, value)
        and (name, "gnomon.scoring.gstack") not in external
        and not (name in aq_classified and getattr(gstack, name) is getattr(aq, name))
    }


class TestCalibrationIsBoundToTheContract(unittest.TestCase):
    def test_current_contract_is_registered(self):
        self.assertIn(
            SCORE_CONTRACT_ID, CALIBRATION_FINGERPRINTS,
            "SCORE_CONTRACT_ID was bumped without registering the calibration "
            "fingerprint it publishes. Add an entry to CALIBRATION_FINGERPRINTS.")

    def test_fingerprint_matches_the_one_registered_for_this_contract(self):
        self.assertEqual(
            calibration_fingerprint(), CALIBRATION_FINGERPRINTS[SCORE_CONTRACT_ID],
            "A calibration constant changed but SCORE_CONTRACT_ID did not. Any target "
            "move requires a new contract ID plus a new CALIBRATION_FINGERPRINTS entry "
            "-- never an edit of the existing one, or re-fitted rows pool with pre-fit "
            "rows under one ID.")

    def test_no_two_contracts_share_a_fingerprint(self):
        # Two IDs with one fingerprint means either a contract was bumped without any
        # calibration change (harmless, but must be EXPLICITLY documented via
        # ZERO_CALIBRATION_DELTA_CONTRACT_IDS) OR an entry was edited in place to paper
        # over a mismatch (the failure mode this file exists to catch). Undocumented
        # duplicates keep failing; only the declared exception is allowed through.
        undocumented = {
            contract_id: fp for contract_id, fp in CALIBRATION_FINGERPRINTS.items()
            if contract_id not in ZERO_CALIBRATION_DELTA_CONTRACT_IDS
        }
        fingerprints = list(undocumented.values())
        self.assertEqual(len(fingerprints), len(set(fingerprints)))

    def test_documented_zero_delta_contracts_are_registered_and_genuinely_unchanged(self):
        # A documented zero-delta contract ID must (a) actually exist in the registry
        # and (b) genuinely match ITS OWN live fingerprint (test_fingerprint_matches_the_
        # one_registered_for_this_contract only checks the CURRENT SCORE_CONTRACT_ID, not
        # historical ones) -- otherwise "documented as unchanged" could silently drift.
        for contract_id in ZERO_CALIBRATION_DELTA_CONTRACT_IDS:
            with self.subTest(contract_id=contract_id):
                self.assertIn(contract_id, CALIBRATION_FINGERPRINTS)


class TestFingerprintActuallyCoversTheConstants(unittest.TestCase):
    def test_every_constant_change_moves_the_fingerprint(self):
        # Sensitivity, one constant at a time: a fingerprint that hashes the NAMES but
        # not the VALUES would pass every other test in this file.
        baseline = calibration_fingerprint()
        for name in CALIBRATION_CONSTANT_NAMES:
            current = getattr(aq, name)
            with self.subTest(constant=name):
                with mock.patch.object(aq, name, current + 1):
                    self.assertNotEqual(
                        calibration_fingerprint(), baseline,
                        f"{name} is registered but does not reach the fingerprint")

    def test_no_score_affecting_module_constant_is_left_unfingerprinted(self):
        # Drift catcher: a constant added to aq.py later must be classified, either as
        # calibration (fingerprinted) or explicitly as non-calibration.
        #
        # BOOLS ARE INCLUDED. They were excluded while the only conceivable bool was an
        # import-time feature toggle, but v12 added STEERING_LEVERAGE_BAND_VALIDATED, which is
        # the most score-affecting constant in aq.py -- it decides whether a whole axis is
        # scored at all. Excluding its type from the sweep would have let it, and the next flag
        # like it, be added with nothing demanding it be classified. `bool` is a subclass of
        # `int`, so this is a removed filter rather than a widened one.
        found = {name for name, value in vars(aq).items()
                 if _is_public_numeric_constant(name, value)}
        classified = set(CALIBRATION_CONSTANT_NAMES) | set(NON_CALIBRATION_CONSTANT_NAMES)
        self.assertEqual(
            found - classified, set(),
            "New numeric constant in aq.py is neither fingerprinted nor declared "
            "non-calibration. Add it to CALIBRATION_CONSTANT_NAMES (and bump the "
            "contract) or to NON_CALIBRATION_CONSTANT_NAMES with a reason.")

    def test_registered_names_all_exist(self):
        for name in CALIBRATION_CONSTANT_NAMES:
            with self.subTest(constant=name):
                self.assertTrue(hasattr(aq, name))

    def test_fingerprint_is_deterministic(self):
        self.assertEqual(calibration_fingerprint(), calibration_fingerprint())


class TestGstackCalibrationGovernance(unittest.TestCase):
    def test_every_gstack_target_is_registered_externally(self):
        for name in GSTACK_CALIBRATION_CONSTANT_NAMES:
            with self.subTest(constant=name):
                self.assertIn((name, "gnomon.scoring.gstack"),
                              EXTERNAL_CALIBRATION_CONSTANT_NAMES)

    def test_no_score_affecting_gstack_constant_is_left_unfingerprinted(self):
        self.assertEqual(
            _unclassified_gstack_constants(), set(),
            "New numeric constant in gstack.py is neither fingerprinted externally nor "
            "an identity-preserved aq re-export.")

    def test_external_gstack_names_exist_and_are_unique(self):
        external = [name for name, module_path in EXTERNAL_CALIBRATION_CONSTANT_NAMES
                    if module_path == "gnomon.scoring.gstack"]
        self.assertEqual(len(external), len(set(external)))
        for name in external:
            with self.subTest(constant=name):
                module = importlib.import_module("gnomon.scoring.gstack")
                self.assertTrue(hasattr(module, name))

    def test_every_external_gstack_constant_changes_the_fingerprint(self):
        baseline = calibration_fingerprint()
        for name in GSTACK_CALIBRATION_CONSTANT_NAMES:
            with self.subTest(constant=name):
                current = getattr(gstack, name)
                with mock.patch.object(gstack, name, current + 1):
                    self.assertNotEqual(calibration_fingerprint(), baseline)

    def test_reexported_aq_constants_use_identity_ownership(self):
        external_names = set(EXTERNAL_CALIBRATION_CONSTANT_NAMES)
        for name in AQ_REEXPORT_NAMES:
            with self.subTest(constant=name):
                self.assertNotIn((name, "gnomon.scoring.gstack"), external_names)
                self.assertIs(getattr(gstack, name), getattr(aq, name))

    def test_identity_exemption_rejects_a_fresh_gstack_binding(self):
        name = "MIN_ELIGIBLE_SESSIONS"
        with mock.patch.object(gstack, name, aq.MIN_ELIGIBLE_SESSIONS + 1):
            self.assertIn(name, _unclassified_gstack_constants())


class TestV19CalibrationGovernanceContract(unittest.TestCase):
    CONTRACT_ID = "19:19:19"
    EXPECTED_FINGERPRINT = "8359e20e5f0fce17"

    def test_nineteen_is_registered(self):
        self.assertIn(self.CONTRACT_ID, CALIBRATION_FINGERPRINTS)

    def test_nineteen_fingerprint_is_pinned(self):
        self.assertEqual(
            CALIBRATION_FINGERPRINTS[self.CONTRACT_ID], self.EXPECTED_FINGERPRINT)

    def test_nineteen_digest_is_new_and_unique(self):
        fingerprint = CALIBRATION_FINGERPRINTS[self.CONTRACT_ID]
        prior = [fp for cid, fp in CALIBRATION_FINGERPRINTS.items()
                 if int(cid.split(":")[0]) < 19]
        self.assertNotIn(fingerprint, prior)

    def test_nineteen_is_not_a_zero_calibration_delta_contract(self):
        self.assertNotIn(self.CONTRACT_ID, ZERO_CALIBRATION_DELTA_CONTRACT_IDS)

    def test_nineteen_is_the_current_contract(self):
        self.assertEqual(SCORE_CONTRACT_ID, self.CONTRACT_ID)


class TestV16McpCompoundingContract(unittest.TestCase):
    """v16 (MCP knowledge-write compounding numerator): real score delta, zero
    calibration delta -- same template as v15's Workflow fan-out fix."""

    def test_digest_is_byte_identical_to_thirteen_fourteen_fifteen(self):
        self.assertEqual(CALIBRATION_FINGERPRINTS["16:16:16"], "94f38d0963b1b195")
        self.assertEqual(
            CALIBRATION_FINGERPRINTS["16:16:16"], CALIBRATION_FINGERPRINTS["15:15:15"])
        self.assertEqual(
            CALIBRATION_FINGERPRINTS["16:16:16"], CALIBRATION_FINGERPRINTS["13:13:13"])

    def test_sixteen_is_registered_as_zero_calibration_delta(self):
        self.assertIn("16:16:16", ZERO_CALIBRATION_DELTA_CONTRACT_IDS)


class TestV17DropToolsearchContract(unittest.TestCase):
    """v17 (scratchpad writes excluded from change-session eligibility; toolsearch rate term
    dropped from Tool command + Token economy; Verification per-call density -> pure-fraction
    per-session coverage; Discipline task-tool rate term dropped as trivially saturated): a
    REAL score delta AND -- unlike v14/v15/v16 -- a REAL calibration delta. Removing
    TOOLSEARCH_PER_CALL_TARGET, TEST_RUNS_PER_CALL_TARGET, and TASK_CALLS_PER_CALL_TARGET from
    CALIBRATION_CONSTANT_NAMES genuinely moves the fingerprint, so 17:17:17 carries a NEW
    digest and is NOT a zero-calibration-delta contract."""

    def test_seventeen_is_registered(self):
        self.assertIn("17:17:17", CALIBRATION_FINGERPRINTS)

    def test_seventeen_fingerprint_is_pinned(self):
        self.assertEqual(CALIBRATION_FINGERPRINTS["17:17:17"], "7fd9a230f7fb2264")

    def test_seventeen_digest_is_a_new_unique_value(self):
        # Three constants left the fingerprinted set, so the digest MUST differ from every
        # PRIOR contract -- this is the calibration delta the bump records. Scoped to the
        # contracts 17 followed: a LATER zero-calibration-delta bump legitimately reuses
        # this digest (18:18:18 does), and that is what
        # ZERO_CALIBRATION_DELTA_CONTRACT_IDS documents.
        self.assertNotEqual(
            CALIBRATION_FINGERPRINTS["17:17:17"], CALIBRATION_FINGERPRINTS["16:16:16"])
        priors = [fp for cid, fp in CALIBRATION_FINGERPRINTS.items()
                  if int(cid.split(":")[0]) < 17]
        self.assertNotIn(CALIBRATION_FINGERPRINTS["17:17:17"], priors)

    def test_seventeen_is_not_a_zero_calibration_delta_contract(self):
        self.assertNotIn("17:17:17", ZERO_CALIBRATION_DELTA_CONTRACT_IDS)

    def test_toolsearch_target_is_no_longer_registered_or_present(self):
        self.assertNotIn("TOOLSEARCH_PER_CALL_TARGET", CALIBRATION_CONSTANT_NAMES)
        self.assertFalse(hasattr(aq, "TOOLSEARCH_PER_CALL_TARGET"))

    def test_test_runs_target_is_no_longer_registered_or_present(self):
        self.assertNotIn("TEST_RUNS_PER_CALL_TARGET", CALIBRATION_CONSTANT_NAMES)
        self.assertFalse(hasattr(aq, "TEST_RUNS_PER_CALL_TARGET"))

    def test_task_calls_target_is_no_longer_registered_or_present(self):
        self.assertNotIn("TASK_CALLS_PER_CALL_TARGET", CALIBRATION_CONSTANT_NAMES)
        self.assertFalse(hasattr(aq, "TASK_CALLS_PER_CALL_TARGET"))


class TestV18PowerShellShellTaxonomyContract(unittest.TestCase):
    """v18 (PowerShell admitted to the shell taxonomy, issue #72): real score delta, zero
    calibration delta -- the same template as v14/v15/v16 against 13:13:13."""

    def test_eighteen_is_registered(self):
        self.assertIn("18:18:18", CALIBRATION_FINGERPRINTS)

    def test_eighteen_digest_is_byte_identical_to_seventeen(self):
        # No registered constant moved: only the taxonomy that decides WHICH tool calls
        # reach the axes changed, and the fingerprint hashes constant VALUES, not taxonomy.
        self.assertEqual(
            CALIBRATION_FINGERPRINTS["18:18:18"], CALIBRATION_FINGERPRINTS["17:17:17"])

    def test_eighteen_is_registered_as_zero_calibration_delta(self):
        self.assertIn("18:18:18", ZERO_CALIBRATION_DELTA_CONTRACT_IDS)

    def test_eighteen_is_historical_after_the_v19_governance_bump(self):
        self.assertNotEqual(SCORE_CONTRACT_ID, "18:18:18")


if __name__ == "__main__":
    unittest.main()
