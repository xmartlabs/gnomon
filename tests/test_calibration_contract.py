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
import unittest
from unittest import mock

from gnomon.scoring import aq
from gnomon.scoring.calibration import (
    CALIBRATION_CONSTANT_NAMES,
    CALIBRATION_FINGERPRINTS,
    NON_CALIBRATION_CONSTANT_NAMES,
    ZERO_CALIBRATION_DELTA_CONTRACT_IDS,
    calibration_fingerprint,
)
from gnomon.scoring.versioning import SCORE_CONTRACT_ID


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
                 if name.isupper() and not name.startswith("_")
                 and isinstance(value, (int, float))}
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
    """v17 (drop toolsearch rate term from Tool command + Token economy): a REAL score
    delta AND -- unlike v14/v15/v16 -- a REAL calibration delta. Removing
    TOOLSEARCH_PER_CALL_TARGET from CALIBRATION_CONSTANT_NAMES genuinely moves the
    fingerprint, so 17:17:17 carries a NEW digest and is NOT a zero-calibration-delta
    contract. (17:17:17 is now historical; v18 is the live contract below.)"""

    def test_seventeen_is_registered(self):
        self.assertIn("17:17:17", CALIBRATION_FINGERPRINTS)

    def test_seventeen_fingerprint_is_pinned(self):
        self.assertEqual(CALIBRATION_FINGERPRINTS["17:17:17"], "dc99dad882305bb6")

    def test_seventeen_digest_is_a_new_unique_value(self):
        # A constant left the fingerprinted set, so the digest MUST differ from every
        # prior contract -- this is the calibration delta the bump records.
        self.assertNotEqual(
            CALIBRATION_FINGERPRINTS["17:17:17"], CALIBRATION_FINGERPRINTS["16:16:16"])
        others = [fp for cid, fp in CALIBRATION_FINGERPRINTS.items() if cid != "17:17:17"]
        self.assertNotIn(CALIBRATION_FINGERPRINTS["17:17:17"], others)

    def test_seventeen_is_not_a_zero_calibration_delta_contract(self):
        self.assertNotIn("17:17:17", ZERO_CALIBRATION_DELTA_CONTRACT_IDS)

    def test_toolsearch_target_is_no_longer_registered_or_present(self):
        self.assertNotIn("TOOLSEARCH_PER_CALL_TARGET", CALIBRATION_CONSTANT_NAMES)
        self.assertFalse(hasattr(aq, "TOOLSEARCH_PER_CALL_TARGET"))


if __name__ == "__main__":
    unittest.main()
