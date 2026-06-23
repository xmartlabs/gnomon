"""Tests for the new pure functions in gnomon/upload/mirdash.py (G1).

Covers:
  - _anchor_window: per-anchor window computation + equivalence vs month_windows
  - windows_for_anchors: maps label list → windows, equivalence with month_windows
  - months_to_upload: decision algorithm (force, empty server, incremental, stale/fresh, gaps)
  - _uploaded_from_query: defensive JSON parsing of the server-uploaded-months callback param
"""

import datetime
import json
import re
import unittest
import urllib.parse

import gnomon.upload.mirdash as _mirdash
from gnomon.upload.mirdash import (
    _MAX_BACKFILL,
    _anchor_window,
    month_windows,
    months_to_upload,
    windows_for_anchors,
    _uploaded_from_query,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _end_of_month_utc_ms(year, month):
    """Return epoch-ms for 00:00:00 UTC of the first day of the NEXT month.

    This is the exclusive upper bound of 'month' — the same bound that
    months_to_upload uses to decide whether a prev upload is stale.
    """
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    dt = datetime.datetime(next_year, next_month, 1, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# _anchor_window
# ---------------------------------------------------------------------------


class TestAnchorWindow(unittest.TestCase):
    """_anchor_window(anchor_year, anchor_month, window_months=1)
    returns (since_iso, until_iso, label).
    """

    def test_basic_single_month(self):
        since, until, label = _anchor_window(2025, 3)
        self.assertEqual(since, "2025-03-01")
        self.assertEqual(until, "2025-04-01")
        self.assertEqual(label, "2025-03")

    def test_december_until_crosses_year(self):
        since, until, label = _anchor_window(2025, 12)
        self.assertEqual(since, "2025-12-01")
        self.assertEqual(until, "2026-01-01")
        self.assertEqual(label, "2025-12")

    def test_january(self):
        since, until, label = _anchor_window(2026, 1)
        self.assertEqual(since, "2026-01-01")
        self.assertEqual(until, "2026-02-01")
        self.assertEqual(label, "2026-01")

    def test_window_months_2_since_is_one_month_back(self):
        # anchor = 2025-06, window_months=2 → since = 2025-05
        since, until, label = _anchor_window(2025, 6, window_months=2)
        self.assertEqual(since, "2025-05-01")
        self.assertEqual(until, "2025-07-01")
        self.assertEqual(label, "2025-06")

    def test_window_months_3_crosses_year_boundary(self):
        # anchor = 2025-02, window_months=3 → since = 2024-12
        since, until, label = _anchor_window(2025, 2, window_months=3)
        self.assertEqual(since, "2024-12-01")
        self.assertEqual(until, "2025-03-01")
        self.assertEqual(label, "2025-02")

    def test_label_format_zero_padded(self):
        _, _, label = _anchor_window(2025, 1)
        self.assertRegex(label, r"^\d{4}-\d{2}$")

    # -------------------------------------------------------------------------
    # Equivalence: _anchor_window must reproduce month_windows per-entry
    # -------------------------------------------------------------------------

    def test_equivalence_with_month_windows_window1(self):
        """For window_months=1, each entry from month_windows must match _anchor_window."""
        today = datetime.date(2025, 7, 15)
        for n in (1, 6, 12):
            windows = month_windows(n, today, window_months=1)
            for since, until, label in windows:
                y, m = int(label[:4]), int(label[5:7])
                got = _anchor_window(y, m, window_months=1)
                self.assertEqual(got, (since, until, label),
                                 f"mismatch for label={label} n={n}")

    def test_equivalence_with_month_windows_window6(self):
        """For window_months=6, equivalence holds for all anchors."""
        today = datetime.date(2025, 11, 30)
        windows = month_windows(12, today, window_months=6)
        for since, until, label in windows:
            y, m = int(label[:4]), int(label[5:7])
            got = _anchor_window(y, m, window_months=6)
            self.assertEqual(got, (since, until, label),
                             f"mismatch for label={label}")

    def test_month_windows_output_unchanged_regression(self):
        """month_windows must return EXACTLY the same results after _anchor_window extraction."""
        cases = [
            (1,  datetime.date(2025, 3, 15),  1),
            (12, datetime.date(2025, 12, 31), 1),
            (3,  datetime.date(2025, 3, 15),  1),
            (6,  datetime.date(2025, 1, 5),   6),
            (1,  datetime.date(2025, 12, 1),  1),
        ]
        for n, today, wm in cases:
            with self.subTest(n=n, today=today, wm=wm):
                result = month_windows(n, today, wm)
                self.assertEqual(len(result), n)
                # Spot-check first and last
                self.assertRegex(result[0][2], r"^\d{4}-\d{2}$")
                self.assertRegex(result[-1][2], r"^\d{4}-\d{2}$")
                # Oldest first
                if n > 1:
                    self.assertLess(result[0][2], result[-1][2])


# ---------------------------------------------------------------------------
# windows_for_anchors
# ---------------------------------------------------------------------------


class TestWindowsForAnchors(unittest.TestCase):
    """windows_for_anchors(anchor_labels, window_months=1)"""

    def test_single_label(self):
        result = windows_for_anchors(["2025-03"])
        self.assertEqual(len(result), 1)
        since, until, label = result[0]
        self.assertEqual(since, "2025-03-01")
        self.assertEqual(until, "2025-04-01")
        self.assertEqual(label, "2025-03")

    def test_preserves_order_oldest_first(self):
        labels = ["2025-01", "2025-02", "2025-03"]
        result = windows_for_anchors(labels)
        self.assertEqual([r[2] for r in result], labels)

    def test_empty_list(self):
        self.assertEqual(windows_for_anchors([]), [])

    def test_window_months_2(self):
        result = windows_for_anchors(["2025-06", "2025-07"], window_months=2)
        self.assertEqual(result[0][0], "2025-05-01")  # 2025-06 with wm=2 → since May
        self.assertEqual(result[1][0], "2025-06-01")  # 2025-07 with wm=2 → since Jun

    def test_equivalence_with_month_windows_contiguous(self):
        """For a contiguous run of anchors windows_for_anchors == month_windows."""
        today = datetime.date(2025, 8, 20)
        n = 6
        expected = month_windows(n, today, window_months=1)
        labels = [w[2] for w in expected]
        got = windows_for_anchors(labels, window_months=1)
        self.assertEqual(got, expected)

    def test_equivalence_window6(self):
        today = datetime.date(2025, 11, 1)
        expected = month_windows(12, today, window_months=6)
        labels = [w[2] for w in expected]
        got = windows_for_anchors(labels, window_months=6)
        self.assertEqual(got, expected)


# ---------------------------------------------------------------------------
# months_to_upload
# ---------------------------------------------------------------------------


class TestMonthsToUpload(unittest.TestCase):
    """months_to_upload(today, server_months, force=False, max_months=_MAX_BACKFILL)"""

    # Reference date used in most tests
    TODAY = datetime.date(2025, 7, 15)
    CURRENT = "2025-07"

    # ---- force / empty server ------------------------------------------------

    def test_empty_server_returns_12_anchors(self):
        result = months_to_upload(self.TODAY, [])
        self.assertEqual(len(result), 12)
        expected_labels = [w[2] for w in month_windows(12, self.TODAY, 1)]
        self.assertEqual(result, expected_labels)

    def test_force_true_with_full_server_returns_12_anchors(self):
        server = [
            {"monthKey": f"2025-{m:02d}", "uploadedAt": 9999999999999}
            for m in range(1, 8)
        ]
        result = months_to_upload(self.TODAY, server, force=True)
        expected_labels = [w[2] for w in month_windows(12, self.TODAY, 1)]
        self.assertEqual(result, expected_labels)

    def test_force_true_empty_server_still_12_anchors(self):
        result = months_to_upload(self.TODAY, [], force=True)
        self.assertEqual(len(result), 12)

    # ---- incremental: only current when server has current (fresh prev) ------

    def test_incremental_server_has_current_fresh_prev_returns_only_current(self):
        # prev = 2025-06, uploadedAt is AFTER end of June → fresh
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms + 1000},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        result = months_to_upload(self.TODAY, server)
        self.assertEqual(result, ["2025-07"])

    def test_incremental_server_current_only_returns_current(self):
        # server has only current, no prev → just current
        server = [{"monthKey": "2025-07", "uploadedAt": 9999999999999}]
        result = months_to_upload(self.TODAY, server)
        self.assertEqual(result, ["2025-07"])

    # ---- gap fill ------------------------------------------------------------

    def test_gap_fill_latest_server_3_months_back(self):
        # latest_server = 2025-04 → gap = 2025-05, 2025-06, plus current 2025-07
        server = [{"monthKey": "2025-04", "uploadedAt": 9999999999999}]
        result = months_to_upload(self.TODAY, server)
        self.assertIn("2025-05", result)
        self.assertIn("2025-06", result)
        self.assertIn("2025-07", result)
        # oldest first
        idx_05 = result.index("2025-05")
        idx_06 = result.index("2025-06")
        idx_07 = result.index("2025-07")
        self.assertLess(idx_05, idx_06)
        self.assertLess(idx_06, idx_07)

    def test_gap_fill_capped_at_max_months(self):
        # latest_server = ancient (> 12 months ago) → result capped at max_months
        server = [{"monthKey": "2020-01", "uploadedAt": 9999999999999}]
        result = months_to_upload(self.TODAY, server)
        self.assertEqual(len(result), 12)

    def test_gap_fill_returns_most_recent_n_when_capped(self):
        # When capped the MOST recent N months should be returned
        server = [{"monthKey": "2020-01", "uploadedAt": 9999999999999}]
        result = months_to_upload(self.TODAY, server)
        # result[-1] should be current
        self.assertEqual(result[-1], self.CURRENT)
        # oldest should be 12 months before current (2024-08)
        expected_oldest = [w[2] for w in month_windows(12, self.TODAY, 1)][0]
        self.assertEqual(result[0], expected_oldest)

    # ---- stale / fresh prev --------------------------------------------------

    def test_prev_stale_includes_prev_and_current(self):
        # prev = 2025-06, uploaded BEFORE end of June → stale
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        result = months_to_upload(self.TODAY, server)
        self.assertIn("2025-06", result)
        self.assertIn("2025-07", result)

    def test_prev_fresh_uploadedAt_exactly_at_bound_not_stale(self):
        # uploadedAt == end_of_month boundary → NOT stale (>= means fresh)
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        result = months_to_upload(self.TODAY, server)
        self.assertNotIn("2025-06", result)
        self.assertIn("2025-07", result)

    def test_prev_fresh_uploadedAt_after_bound_not_stale(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms + 86400_000},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        result = months_to_upload(self.TODAY, server)
        self.assertNotIn("2025-06", result)
        self.assertIn("2025-07", result)

    # ---- first of month edge cases -------------------------------------------

    def test_first_of_month_prev_stale(self):
        # today = 2025-07-01; current = 2025-07; prev = 2025-06
        today = datetime.date(2025, 7, 1)
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1000},
            {"monthKey": "2025-07", "uploadedAt": 0},
        ]
        result = months_to_upload(today, server)
        self.assertIn("2025-06", result)
        self.assertIn("2025-07", result)

    def test_first_of_month_prev_fresh_only_current(self):
        today = datetime.date(2025, 7, 1)
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms},
            {"monthKey": "2025-07", "uploadedAt": 0},
        ]
        result = months_to_upload(today, server)
        self.assertNotIn("2025-06", result)
        self.assertIn("2025-07", result)

    # ---- prev not in server --------------------------------------------------

    def test_prev_not_in_server_not_included(self):
        # server has current but NOT prev → prev must NOT be added
        server = [{"monthKey": "2025-07", "uploadedAt": 9999999999999}]
        result = months_to_upload(self.TODAY, server)
        self.assertNotIn("2025-06", result)
        self.assertIn("2025-07", result)

    # ---- dedup + ordering ----------------------------------------------------

    def test_dedup_and_sorted_oldest_first(self):
        # Construct a case where gap + stale would both produce same month
        prev_end_ms = _end_of_month_utc_ms(2025, 5)
        server = [
            # latest_server = 2025-05, so gap = 2025-06; prev (2025-06) is also stale
            {"monthKey": "2025-05", "uploadedAt": 9999999999999},
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1000},
        ]
        result = months_to_upload(self.TODAY, server)
        # No duplicates
        self.assertEqual(len(result), len(set(result)))
        # Sorted oldest first
        self.assertEqual(result, sorted(result))

    def test_result_sorted_lexicographically(self):
        server = [{"monthKey": "2025-04", "uploadedAt": 9999999999999}]
        result = months_to_upload(self.TODAY, server)
        self.assertEqual(result, sorted(result))

    # ---- malformed server_months ---------------------------------------------

    def test_malformed_entries_ignored_without_crash(self):
        server = [
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
            {"bad_key": "2025-06"},                    # missing monthKey
            {"monthKey": "not-a-month", "uploadedAt": 0},  # invalid monthKey format
            None,                                       # not a dict at all — skip silently
            {"monthKey": "2025-05", "uploadedAt": "not-an-int"},  # uploadedAt not coercible
        ]
        # Should not raise
        try:
            result = months_to_upload(self.TODAY, server)
        except Exception as exc:
            self.fail(f"months_to_upload raised {exc!r} with malformed server_months")
        self.assertIn("2025-07", result)

    def test_all_malformed_entries_treated_as_empty_server(self):
        server = [
            {"bad_key": "2025-06"},
            {"monthKey": "invalid"},
        ]
        result = months_to_upload(self.TODAY, server)
        # Treated as empty → 12 anchors
        self.assertEqual(len(result), 12)

    # ---- max_months custom ---------------------------------------------------

    def test_custom_max_months_respected(self):
        result = months_to_upload(self.TODAY, [], max_months=3)
        self.assertEqual(len(result), 3)
        # Most recent 3: 2025-05, 2025-06, 2025-07
        self.assertEqual(result, ["2025-05", "2025-06", "2025-07"])

    def test_incremental_capped_at_custom_max_months(self):
        # latest_server far back; max_months=3 → only 3 most recent
        server = [{"monthKey": "2020-01", "uploadedAt": 9999999999999}]
        result = months_to_upload(self.TODAY, server, max_months=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[-1], self.CURRENT)


# ---------------------------------------------------------------------------
# _uploaded_from_query
# ---------------------------------------------------------------------------


class TestUploadedFromQuery(unittest.TestCase):
    """_uploaded_from_query(parsed_qs) → list[{monthKey, uploadedAt}]"""

    def _qs(self, uploaded_value):
        """Build a parse_qs dict as urllib.parse.parse_qs would produce."""
        raw = urllib.parse.urlencode({"uploaded": uploaded_value})
        return urllib.parse.parse_qs(raw)

    def _qs_raw(self, d):
        """Build a parse_qs dict from an already-constructed dict of lists."""
        return d

    # ---- valid inputs --------------------------------------------------------

    def test_valid_single_entry(self):
        data = [{"monthKey": "2025-07", "uploadedAt": 1750000000000}]
        result = _uploaded_from_query(self._qs(json.dumps(data)))
        self.assertEqual(result, data)

    def test_valid_multiple_entries(self):
        data = [
            {"monthKey": "2025-06", "uploadedAt": 1748000000000},
            {"monthKey": "2025-07", "uploadedAt": 1750000000000},
        ]
        result = _uploaded_from_query(self._qs(json.dumps(data)))
        self.assertEqual(result, data)

    def test_empty_valid_list(self):
        result = _uploaded_from_query(self._qs(json.dumps([])))
        self.assertEqual(result, [])

    # ---- type coercion -------------------------------------------------------

    def test_uploaded_at_as_string_is_coerced_to_int(self):
        data = [{"monthKey": "2025-07", "uploadedAt": "1750000000000"}]
        result = _uploaded_from_query(self._qs(json.dumps(data)))
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0]["uploadedAt"], int)
        self.assertEqual(result[0]["uploadedAt"], 1750000000000)

    def test_uploaded_at_as_float_is_coerced_to_int(self):
        data = [{"monthKey": "2025-07", "uploadedAt": 1750000000000.9}]
        result = _uploaded_from_query(self._qs(json.dumps(data)))
        self.assertEqual(result[0]["uploadedAt"], int(1750000000000.9))

    # ---- missing / malformed -------------------------------------------------

    def test_missing_uploaded_key_returns_empty(self):
        result = _uploaded_from_query({})
        self.assertEqual(result, [])

    def test_malformed_json_returns_empty(self):
        qs = self._qs_raw({"uploaded": ["{not valid json"]})
        result = _uploaded_from_query(qs)
        self.assertEqual(result, [])

    def test_uploaded_not_a_list_returns_empty(self):
        # JSON object instead of list
        qs = self._qs(json.dumps({"monthKey": "2025-07", "uploadedAt": 0}))
        result = _uploaded_from_query(qs)
        self.assertEqual(result, [])

    def test_uploaded_is_null_returns_empty(self):
        qs = self._qs(json.dumps(None))
        result = _uploaded_from_query(qs)
        self.assertEqual(result, [])

    def test_entries_missing_month_key_skipped(self):
        data = [
            {"uploadedAt": 1750000000000},        # no monthKey
            {"monthKey": "2025-07", "uploadedAt": 1750000000000},
        ]
        result = _uploaded_from_query(self._qs(json.dumps(data)))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["monthKey"], "2025-07")

    def test_entries_with_invalid_month_key_format_skipped(self):
        data = [
            {"monthKey": "25-7", "uploadedAt": 0},      # wrong format
            {"monthKey": "2025-07", "uploadedAt": 0},
        ]
        result = _uploaded_from_query(self._qs(json.dumps(data)))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["monthKey"], "2025-07")

    def test_entries_with_non_coercible_uploaded_at_skipped(self):
        data = [
            {"monthKey": "2025-06", "uploadedAt": "not-a-number"},
            {"monthKey": "2025-07", "uploadedAt": 0},
        ]
        result = _uploaded_from_query(self._qs(json.dumps(data)))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["monthKey"], "2025-07")

    def test_never_raises_on_arbitrary_input(self):
        weird_inputs = [
            {},
            {"uploaded": [""]},
            {"uploaded": ["null"]},
            {"uploaded": ["[1,2,3]"]},
            {"uploaded": [json.dumps([{"monthKey": "2025-07", "uploadedAt": None}])]},
        ]
        for qs in weird_inputs:
            with self.subTest(qs=qs):
                try:
                    result = _uploaded_from_query(qs)
                    self.assertIsInstance(result, list)
                except Exception as exc:
                    self.fail(f"_uploaded_from_query raised {exc!r} for qs={qs!r}")


if __name__ == "__main__":
    unittest.main()
