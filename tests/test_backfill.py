"""Tests for backfill helpers: parse_backfill, month_windows, _tokens_from_query,
and light orchestration tests for the backfill loop.
"""

import contextlib
import datetime
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xl_ai_insights
from xl_ai_insights import (
    _MAX_BACKFILL,
    _tokens_from_query,
    month_windows,
    parse_backfill,
)


# ---------------------------------------------------------------------------
# parse_backfill
# ---------------------------------------------------------------------------


class TestParseBackfill(unittest.TestCase):
    def test_absent_returns_none(self):
        self.assertIsNone(parse_backfill([]))

    def test_bare_flag_returns_6(self):
        self.assertEqual(parse_backfill(["--backfill"]), 6)

    def test_explicit_value(self):
        self.assertEqual(parse_backfill(["--backfill=3"]), 3)

    def test_explicit_value_1(self):
        self.assertEqual(parse_backfill(["--backfill=1"]), 1)

    def test_explicit_value_12(self):
        self.assertEqual(parse_backfill(["--backfill=12"]), 12)

    def test_clamp_above_max(self):
        # Any value > _MAX_BACKFILL is clamped to _MAX_BACKFILL
        self.assertEqual(parse_backfill(["--backfill=99"]), _MAX_BACKFILL)

    def test_clamp_zero_to_1(self):
        self.assertEqual(parse_backfill(["--backfill=0"]), 1)

    def test_clamp_negative_to_1(self):
        self.assertEqual(parse_backfill(["--backfill=-5"]), 1)

    def test_non_int_treated_as_bare_flag(self):
        # Non-integer value → same as bare --backfill → 6
        self.assertEqual(parse_backfill(["--backfill=abc"]), 6)

    def test_other_flags_present(self):
        self.assertEqual(parse_backfill(["--quiet", "--backfill=4", "--no-open"]), 4)

    def test_bare_flag_among_others(self):
        self.assertEqual(parse_backfill(["--quiet", "--backfill"]), 6)

    def test_absent_with_other_flags(self):
        self.assertIsNone(parse_backfill(["--quiet", "--verbose"]))


# ---------------------------------------------------------------------------
# month_windows
# ---------------------------------------------------------------------------


class TestMonthWindows(unittest.TestCase):
    def _check_entry(self, since, until, label):
        """Assert the internal consistency of one window entry."""
        since_d = datetime.date.fromisoformat(since)
        until_d = datetime.date.fromisoformat(until)
        # since must be first of the month
        self.assertEqual(since_d.day, 1, f"since not first of month: {since}")
        # until must also be first of a month
        self.assertEqual(until_d.day, 1, f"until not first of month: {until}")
        # until must be strictly after since
        self.assertGreater(until_d, since_d)
        # until must be exactly the next month after since
        if since_d.month == 12:
            self.assertEqual(until_d.year, since_d.year + 1)
            self.assertEqual(until_d.month, 1)
        else:
            self.assertEqual(until_d.year, since_d.year)
            self.assertEqual(until_d.month, since_d.month + 1)
        # label must match since's year-month
        self.assertEqual(label, f"{since_d.year:04d}-{since_d.month:02d}")

    def test_count_matches_n(self):
        windows = month_windows(6, datetime.date(2025, 3, 15))
        self.assertEqual(len(windows), 6)

    def test_oldest_first(self):
        windows = month_windows(6, datetime.date(2025, 3, 15))
        # Oldest = 2024-10, newest = 2025-03
        since_dates = [datetime.date.fromisoformat(w[0]) for w in windows]
        self.assertEqual(since_dates, sorted(since_dates))

    def test_last_window_is_current_month(self):
        today = datetime.date(2025, 3, 15)
        windows = month_windows(6, today)
        since, until, label = windows[-1]
        self.assertEqual(since, "2025-03-01")
        self.assertEqual(until, "2025-04-01")
        self.assertEqual(label, "2025-03")

    def test_first_window_correct_for_6(self):
        # 6 months back from 2025-03: 2024-10
        windows = month_windows(6, datetime.date(2025, 3, 15))
        since, until, label = windows[0]
        self.assertEqual(since, "2024-10-01")
        self.assertEqual(until, "2024-11-01")
        self.assertEqual(label, "2024-10")

    def test_all_entries_internally_consistent(self):
        windows = month_windows(6, datetime.date(2025, 3, 15))
        for since, until, label in windows:
            self._check_entry(since, until, label)

    def test_year_rollover_december_to_january(self):
        # 3 months ending at 2025-01: windows = 2024-11, 2024-12, 2025-01
        windows = month_windows(3, datetime.date(2025, 1, 10))
        labels = [w[2] for w in windows]
        self.assertEqual(labels, ["2024-11", "2024-12", "2025-01"])
        # Check the Dec→Jan boundary
        since_dec, until_dec, _ = windows[1]
        self.assertEqual(since_dec, "2024-12-01")
        self.assertEqual(until_dec, "2025-01-01")

    def test_n_1_returns_current_month(self):
        today = datetime.date(2025, 7, 4)
        windows = month_windows(1, today)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0][0], "2025-07-01")
        self.assertEqual(windows[0][1], "2025-08-01")

    def test_february_until_is_march_1(self):
        windows = month_windows(1, datetime.date(2024, 2, 15))
        since, until, label = windows[0]
        self.assertEqual(since, "2024-02-01")
        self.assertEqual(until, "2024-03-01")

    def test_no_gaps_between_consecutive_windows(self):
        windows = month_windows(6, datetime.date(2025, 6, 1))
        for i in range(len(windows) - 1):
            _, until_curr, _ = windows[i]
            since_next, _, _ = windows[i + 1]
            self.assertEqual(until_curr, since_next, f"Gap between window {i} and {i+1}")

    def test_n_12_span(self):
        windows = month_windows(12, datetime.date(2025, 12, 31))
        self.assertEqual(len(windows), 12)
        self.assertEqual(windows[0][2], "2025-01")
        self.assertEqual(windows[-1][2], "2025-12")
        # All internally consistent
        for since, until, label in windows:
            self._check_entry(since, until, label)


# ---------------------------------------------------------------------------
# _tokens_from_query
# ---------------------------------------------------------------------------


class TestTokensFromQuery(unittest.TestCase):
    def test_tokens_json_array(self):
        qs = {"tokens": [json.dumps(["tok1", "tok2", "tok3"])]}
        result = _tokens_from_query(qs)
        self.assertEqual(result, ["tok1", "tok2", "tok3"])

    def test_single_token_key_only(self):
        qs = {"token": ["abc123"]}
        result = _tokens_from_query(qs)
        self.assertEqual(result, ["abc123"])

    def test_both_present_prefers_tokens(self):
        qs = {
            "tokens": [json.dumps(["batch1", "batch2"])],
            "token": ["single"],
        }
        result = _tokens_from_query(qs)
        self.assertEqual(result, ["batch1", "batch2"])

    def test_malformed_tokens_falls_back_to_token(self):
        qs = {"tokens": ["not-valid-json{{{"], "token": ["fallback"]}
        result = _tokens_from_query(qs)
        self.assertEqual(result, ["fallback"])

    def test_empty_tokens_array_falls_back_to_token(self):
        qs = {"tokens": [json.dumps([])], "token": ["fallback"]}
        result = _tokens_from_query(qs)
        self.assertEqual(result, ["fallback"])

    def test_neither_present_returns_empty_list(self):
        result = _tokens_from_query({})
        self.assertEqual(result, [])

    def test_empty_dict_does_not_crash(self):
        result = _tokens_from_query({})
        self.assertIsInstance(result, list)

    def test_tokens_is_not_list_falls_back(self):
        # tokens= JSON but not an array
        qs = {"tokens": [json.dumps({"key": "val"})], "token": ["tok"]}
        result = _tokens_from_query(qs)
        self.assertEqual(result, ["tok"])

    def test_token_values_coerced_to_str(self):
        # Ensure numeric values in the JSON array are cast to str
        qs = {"tokens": [json.dumps([1, 2])]}
        result = _tokens_from_query(qs)
        self.assertEqual(result, ["1", "2"])


# ---------------------------------------------------------------------------
# Backfill loop orchestration (light — mocks paxel + upload)
# ---------------------------------------------------------------------------


def _make_summary(sessions=5, since="2025-01-01", until="2025-02-01"):
    return {
        "context": {
            "total_sessions": sessions,
            "date_range": [since, until],
        },
    }


class TestBackfillLoop(unittest.TestCase):
    """Light integration tests for the backfill orchestration in main().

    Strategy: patch _run_paxel and _upload_summary so no real I/O happens.
    """

    def _run_backfill(self, run_paxel_side_effect, upload_return_values, extra_argv=None):
        """Helper: invoke main() with --backfill=N, intercepting I/O."""
        argv = ["--backfill=3", "--no-open", "--console"] + (extra_argv or [])

        tokens = ["t1", "t2", "t3"]

        with (
            patch.object(xl_ai_insights, "_capture_cli_token", return_value=tokens),
            patch.object(xl_ai_insights, "webbrowser") as mock_wb,
            patch.object(
                xl_ai_insights,
                "_run_paxel",
                side_effect=run_paxel_side_effect,
            ) as mock_paxel,
            patch.object(
                xl_ai_insights,
                "_upload_summary",
                side_effect=upload_return_values,
            ) as mock_upload,
            patch.object(xl_ai_insights.os.path, "isfile", return_value=True),
            patch.object(xl_ai_insights.sys, "argv", ["xl-ai-insights"] + argv),
        ):
            mock_wb.open.return_value = True
            xl_ai_insights.main()
            return mock_paxel, mock_upload

    def test_skips_empty_months_no_token_consumed(self):
        """Empty months must NOT consume a token."""
        # Window 0: empty, window 1: non-empty, window 2: non-empty
        summaries = [
            _make_summary(sessions=0),         # skip
            _make_summary(sessions=3),          # upload → t1
            _make_summary(sessions=7),          # upload → t2
        ]
        upload_returns = ["/report/1", "/report/2"]

        mock_paxel, mock_upload = self._run_backfill(summaries, upload_returns)

        self.assertEqual(mock_paxel.call_count, 3)
        # Only 2 uploads (2 non-empty months)
        self.assertEqual(mock_upload.call_count, 2)
        # First upload gets token t1
        self.assertEqual(mock_upload.call_args_list[0][0][1], "t1")
        # Second upload gets token t2
        self.assertEqual(mock_upload.call_args_list[1][0][1], "t2")

    def test_all_months_uploaded(self):
        summaries = [
            _make_summary(sessions=1),
            _make_summary(sessions=2),
            _make_summary(sessions=3),
        ]
        upload_returns = ["/r/1", "/r/2", "/r/3"]
        _, mock_upload = self._run_backfill(summaries, upload_returns)
        self.assertEqual(mock_upload.call_count, 3)

    def test_all_months_empty_no_upload(self):
        summaries = [
            _make_summary(sessions=0),
            _make_summary(sessions=0),
            _make_summary(sessions=0),
        ]
        _, mock_upload = self._run_backfill(summaries, [])
        self.assertEqual(mock_upload.call_count, 0)

    def test_tokens_consumed_in_order(self):
        summaries = [_make_summary(sessions=i + 1) for i in range(3)]
        upload_returns = [f"/r/{i}" for i in range(3)]
        _, mock_upload = self._run_backfill(summaries, upload_returns)
        # Tokens should be t1, t2, t3 in that order
        used_tokens = [c[0][1] for c in mock_upload.call_args_list]
        self.assertEqual(used_tokens, ["t1", "t2", "t3"])

    def test_paxel_error_skips_month(self):
        """If _run_paxel returns None (error), that month is skipped."""
        summaries = [
            None,                       # paxel error → skip
            _make_summary(sessions=4),  # uploaded
            _make_summary(sessions=5),  # uploaded
        ]
        upload_returns = ["/r/1", "/r/2"]
        _, mock_upload = self._run_backfill(summaries, upload_returns)
        self.assertEqual(mock_upload.call_count, 2)
        self.assertEqual(mock_upload.call_args_list[0][0][1], "t1")


class TestBatchOutputContract(unittest.TestCase):
    """Output contract for the batch paths (--init / --backfill):

    - The final report URL must print even with --no-open (only the browser open
      is suppressed) — otherwise a batch run succeeds with no way to reach the report.
    - --quiet must print only errors and the final URL, never per-window status
      lines ('^ uploaded', 'initialised/backfilled X/Y', 'Analysing', 'skip -- no
      activity').
    """

    def _run_main(self, argv, summaries, upload_returns, tokens):
        """Invoke main() with batch I/O mocked; return captured stdout."""
        if "--console" not in argv:
            argv = argv + ["--console"]
        buf = io.StringIO()
        with (
            patch.object(xl_ai_insights, "_capture_cli_token", return_value=tokens),
            patch.object(xl_ai_insights, "webbrowser") as mock_wb,
            patch.object(xl_ai_insights, "_run_paxel", side_effect=summaries),
            patch.object(
                xl_ai_insights, "_upload_summary", side_effect=upload_returns
            ),
            patch.object(xl_ai_insights.os.path, "isfile", return_value=True),
            patch.object(xl_ai_insights.sys, "argv", ["xl-ai-insights"] + argv),
            contextlib.redirect_stdout(buf),
        ):
            mock_wb.open.return_value = True
            xl_ai_insights.main()
        return buf.getvalue()

    def test_backfill_no_open_still_prints_report_url(self):
        out = self._run_main(
            ["--backfill=3", "--no-open"],
            summaries=[_make_summary(sessions=i + 1) for i in range(3)],
            upload_returns=["/r/1", "/r/2", "/r/3"],
            tokens=["t1", "t2", "t3"],
        )
        self.assertIn("Report ready:", out)
        self.assertIn("/r/3", out)

    def test_backfill_quiet_suppresses_status_but_keeps_url(self):
        out = self._run_main(
            ["--backfill=3", "--quiet"],
            summaries=[_make_summary(sessions=i + 1) for i in range(3)],
            upload_returns=["/r/1", "/r/2", "/r/3"],
            tokens=["t1", "t2", "t3"],
        )
        self.assertIn("Report ready:", out)
        self.assertIn("/r/3", out)
        self.assertNotIn("^", out)
        self.assertNotIn("uploaded", out)
        self.assertNotIn("backfilled", out)
        self.assertNotIn("Analysing", out)

    def test_backfill_quiet_suppresses_no_activity_skip(self):
        out = self._run_main(
            ["--backfill=3", "--quiet"],
            summaries=[
                _make_summary(sessions=0),  # empty → skip, must stay silent
                _make_summary(sessions=2),
                _make_summary(sessions=3),
            ],
            upload_returns=["/r/1", "/r/2"],
            tokens=["t1", "t2", "t3"],
        )
        self.assertNotIn("no activity", out)
        self.assertIn("Report ready:", out)

    def test_init_no_open_still_prints_report_url(self):
        out = self._run_main(
            ["--init", "--no-open"],
            summaries=[_make_summary(sessions=i + 1) for i in range(12)],
            upload_returns=[f"/r/{i}" for i in range(12)],
            tokens=[f"t{i}" for i in range(12)],
        )
        self.assertIn("Report ready:", out)

    def test_init_quiet_suppresses_status_but_keeps_url(self):
        out = self._run_main(
            ["--init", "--quiet"],
            summaries=[_make_summary(sessions=i + 1) for i in range(12)],
            upload_returns=[f"/r/{i}" for i in range(12)],
            tokens=[f"t{i}" for i in range(12)],
        )
        self.assertIn("Report ready:", out)
        self.assertNotIn("^", out)
        self.assertNotIn("uploaded", out)
        self.assertNotIn("initialised", out)


if __name__ == "__main__":
    unittest.main()
