"""Atomicity of steps 5 (skill-dedup counting fix) + 6 (contract bump 7:7:7 ->
8:8:8): ONE test asserts BOTH the contract moved AND the dedup outcome, so
reverting the bump alone (while keeping the dedup fix) turns this test red
mechanically -- not by policy. Reverting the dedup while keeping the bump is
a harmless cohort split and is NOT asserted here (see design.md decision E)."""
import unittest

from gnomon.scoring.versioning import SCORE_CONTRACT_ID
from tests.test_skill_dedup import _feed, _three_file_fixture
from gnomon.cli.accumulator import Accumulator


class TestContractBumpAndDedupLandTogether(unittest.TestCase):
    def test_contract_moved_and_dedup_outcome_in_one_assertion(self):
        # 6: the three-version contract must have moved off the pre-change value.
        self.assertNotEqual(SCORE_CONTRACT_ID, "7:7:7")

        # 5: the 3-file real-corpus dedup fixture must collapse 196 -> 1.
        acc = Accumulator()
        for fp, events in _three_file_fixture():
            _feed(acc, fp, events)
        acc.to_corpus_stats(None, None, False)

        self.assertEqual(SCORE_CONTRACT_ID != "7:7:7"
                          and acc.skill_counter["judgment-day"] == 1, True)


if __name__ == "__main__":
    unittest.main()
