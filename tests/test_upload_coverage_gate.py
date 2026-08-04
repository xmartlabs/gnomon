"""Coverage-gated refresh (honest-aq-series step 2, design decision B):
contract-bridge is DELETED from plan_upload's contract-aware branch. Refresh
of the previous month is now gated purely on comparable coverage: refresh
only when producible coverage strictly exceeds stored coverage
(lexicographic (rank, transcripts)); scoreContractId is no longer consulted
at all for this decision."""
import datetime
import unittest

from gnomon.upload.mirdash import plan_upload, _history_from_query
from gnomon.coverage import COVERAGE_RANK


TODAY = datetime.date(2026, 1, 15)


def _history(months):
    return {"state": "valid", "months": months}


class TestNoContractBridgeEmitted(unittest.TestCase):
    def test_contract_bridge_never_emitted_regardless_of_contract_mismatch(self):
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 1, "scoreContractId": "6:6:6"},
        ])
        result = plan_upload(TODAY, history, active_contract="8:8:8")
        reasons = [r for _, r in result]
        self.assertNotIn("contract-bridge", reasons)

    def test_missing_previous_entry_is_a_gap_not_a_bridge(self):
        history = _history([
            {"monthKey": "2025-10", "uploadedAt": 1},
        ])
        result = plan_upload(TODAY, history, active_contract="8:8:8")
        self.assertEqual(result, [("2025-12", "gap"), ("2026-01", "current")])


class TestCoverageComparisonGate(unittest.TestCase):
    def _producible(self, rank_name, transcripts):
        return lambda month_key: (COVERAGE_RANK.get(rank_name), transcripts)

    def test_refresh_when_producible_strictly_exceeds_stored(self):
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 1,
             "coverage": {"flag": "insufficient", "indexed": 50, "transcripts": 0}},
        ])
        result = plan_upload(
            TODAY, history, active_contract="8:8:8",
            producible_coverage_for=self._producible("complete", 50),
        )
        self.assertEqual(result, [("2025-12", "refresh"), ("2026-01", "current")])

    def test_no_refresh_when_producible_equal_to_stored(self):
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 1,
             "coverage": {"flag": "complete", "indexed": 50, "transcripts": 50}},
        ])
        result = plan_upload(
            TODAY, history, active_contract="8:8:8",
            producible_coverage_for=self._producible("complete", 50),
        )
        self.assertEqual(result, [("2026-01", "current")])

    def test_canonical_complete_tuple_from_mixed_duplicates_does_not_refresh(self):
        """Mirdash preserves the newest timestamp/contract but aggregates the
        guard-protected complete coverage from an older surviving duplicate."""
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 2, "scoreContractId": "new-contract",
             "coverage": {"flag": "complete", "indexed": 50, "transcripts": 50}},
        ])

        result = plan_upload(
            TODAY, history, active_contract="8:8:8",
            producible_coverage_for=self._producible("complete", 50),
        )

        self.assertEqual(result, [("2026-01", "current")])

    def test_no_refresh_when_producible_worse_than_stored(self):
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 1,
             "coverage": {"flag": "complete", "indexed": 50, "transcripts": 50}},
        ])
        result = plan_upload(
            TODAY, history, active_contract="8:8:8",
            producible_coverage_for=self._producible("partial", 20),
        )
        self.assertEqual(result, [("2026-01", "current")])

    def test_unknown_producible_coverage_skips_scoring_no_refresh(self):
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 1,
             "coverage": {"flag": "insufficient", "indexed": 50, "transcripts": 0}},
        ])
        result = plan_upload(
            TODAY, history, active_contract="8:8:8",
            producible_coverage_for=lambda mk: (None, 0),
        )
        self.assertEqual(result, [("2026-01", "current")])

    def test_missing_stored_coverage_never_refreshes_old_server_row(self):
        """Back-compat: a row uploaded before this capability has no `coverage`
        field at all -- rank is None (incomparable), never treated as a
        justification to refresh."""
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 1, "scoreContractId": "8:8:8"},
        ])
        result = plan_upload(
            TODAY, history, active_contract="8:8:8",
            producible_coverage_for=self._producible("complete", 999),
        )
        self.assertEqual(result, [("2026-01", "current")])

    def test_no_producible_coverage_fn_supplied_is_the_safe_no_refresh_default(self):
        history = _history([
            {"monthKey": "2025-12", "uploadedAt": 1,
             "coverage": {"flag": "insufficient", "indexed": 50, "transcripts": 0}},
        ])
        result = plan_upload(TODAY, history, active_contract="8:8:8")
        self.assertEqual(result, [("2026-01", "current")])


class TestHistoryFromQueryParsesCoverage(unittest.TestCase):
    @staticmethod
    def _query(payload):
        import json
        import urllib.parse
        raw = urllib.parse.urlencode({"uploaded_history": json.dumps(payload)})
        return urllib.parse.parse_qs(raw)

    def test_valid_coverage_round_trips(self):
        payload = {"outcome": "valid", "months": [
            {"monthKey": "2025-12", "uploadedAt": 1,
             "coverage": {"flag": "partial", "indexed": 10, "transcripts": 4}},
        ]}
        result = _history_from_query(self._query(payload))
        self.assertEqual(result["months"][0]["coverage"],
                         {"flag": "partial", "indexed": 10, "transcripts": 4})

    def test_absent_coverage_is_fine(self):
        payload = {"outcome": "valid", "months": [
            {"monthKey": "2025-12", "uploadedAt": 1},
        ]}
        result = _history_from_query(self._query(payload))
        self.assertNotIn("coverage", result["months"][0])

    def test_structurally_invalid_coverage_is_malformed(self):
        payload = {"outcome": "valid", "months": [
            {"monthKey": "2025-12", "uploadedAt": 1, "coverage": "not-a-dict"},
        ]}
        result = _history_from_query(self._query(payload))
        self.assertEqual(result, {"state": "malformed", "months": []})


if __name__ == "__main__":
    unittest.main()
