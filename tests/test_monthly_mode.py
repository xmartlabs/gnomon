"""Tests for the monthly-dashboard mode introduced in v0.5.0.

Covers:
  - decide_mode: arg-parsing precedence (--init, --backfill=N, neither)
  - month_windows(1, ...) for current-month window + year rollover
  - latest_month_with_data: picks most recent month with data, handles edge cases
  - backfill/init loop: N windows produced (reuses month_windows)
  - current-month orchestration: non-empty upload, empty-fallback, total-empty exit
"""

import datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xl_ai_insights
from xl_ai_insights import (
    decide_mode,
    latest_month_with_data,
    month_windows,
)


# ---------------------------------------------------------------------------
# decide_mode
# ---------------------------------------------------------------------------


class TestDecideMode(unittest.TestCase):
    """decide_mode(argv) -> ('init', 12) | ('backfill', N) | ('current', 1)"""

    def test_no_flags_returns_current(self):
        mode, n = decide_mode([])
        self.assertEqual(mode, "current")
        self.assertEqual(n, 1)

    def test_init_flag_returns_init_12(self):
        mode, n = decide_mode(["--init"])
        self.assertEqual(mode, "init")
        self.assertEqual(n, 12)

    def test_backfill_3_returns_backfill_3(self):
        mode, n = decide_mode(["--backfill=3"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 3)

    def test_backfill_bare_flag_returns_backfill_6(self):
        mode, n = decide_mode(["--backfill"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 6)

    def test_init_takes_precedence_over_backfill(self):
        # --init wins if both are present
        mode, n = decide_mode(["--init", "--backfill=5"])
        self.assertEqual(mode, "init")
        self.assertEqual(n, 12)

    def test_current_with_other_flags(self):
        mode, n = decide_mode(["--quiet", "--no-open", "claude"])
        self.assertEqual(mode, "current")
        self.assertEqual(n, 1)

    def test_backfill_with_other_flags(self):
        mode, n = decide_mode(["--quiet", "--backfill=7", "--no-open"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 7)

    def test_init_with_other_flags(self):
        mode, n = decide_mode(["--no-open", "--quiet", "--init"])
        self.assertEqual(mode, "init")
        self.assertEqual(n, 12)

    def test_backfill_12_returns_12(self):
        mode, n = decide_mode(["--backfill=12"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 12)

    def test_backfill_1_returns_1(self):
        mode, n = decide_mode(["--backfill=1"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 1)


# ---------------------------------------------------------------------------
# month_windows(1, ...) — current-month window
# ---------------------------------------------------------------------------


class TestMonthWindowsCurrentMonth(unittest.TestCase):
    def test_march_returns_march_window(self):
        windows = month_windows(1, datetime.date(2025, 3, 15))
        self.assertEqual(len(windows), 1)
        since, until, label = windows[0]
        self.assertEqual(since, "2025-03-01")
        self.assertEqual(until, "2025-04-01")
        self.assertEqual(label, "2025-03")

    def test_january_year_rollover(self):
        # January: since = YYYY-01-01, until = YYYY-02-01 (same year)
        windows = month_windows(1, datetime.date(2026, 1, 5))
        since, until, label = windows[0]
        self.assertEqual(since, "2026-01-01")
        self.assertEqual(until, "2026-02-01")
        self.assertEqual(label, "2026-01")

    def test_december_until_is_next_jan(self):
        windows = month_windows(1, datetime.date(2025, 12, 1))
        since, until, label = windows[0]
        self.assertEqual(since, "2025-12-01")
        self.assertEqual(until, "2026-01-01")
        self.assertEqual(label, "2025-12")

    def test_first_day_of_month(self):
        windows = month_windows(1, datetime.date(2025, 6, 1))
        since, until, label = windows[0]
        self.assertEqual(since, "2025-06-01")
        self.assertEqual(until, "2025-07-01")
        self.assertEqual(label, "2025-06")

    def test_last_day_of_month(self):
        windows = month_windows(1, datetime.date(2025, 1, 31))
        since, until, label = windows[0]
        self.assertEqual(since, "2025-01-01")
        self.assertEqual(until, "2025-02-01")
        self.assertEqual(label, "2025-01")


# ---------------------------------------------------------------------------
# latest_month_with_data
# ---------------------------------------------------------------------------


class TestLatestMonthWithData(unittest.TestCase):
    def test_returns_most_recent_month(self):
        prog = [
            {"month": "2025-01"},
            {"month": "2025-03"},
            {"month": "2025-02"},
        ]
        self.assertEqual(latest_month_with_data(prog), "2025-03")

    def test_single_entry(self):
        self.assertEqual(latest_month_with_data([{"month": "2024-11"}]), "2024-11")

    def test_empty_list_returns_none(self):
        self.assertIsNone(latest_month_with_data([]))

    def test_already_sorted_newest_last(self):
        prog = [{"month": "2024-10"}, {"month": "2024-11"}, {"month": "2024-12"}]
        self.assertEqual(latest_month_with_data(prog), "2024-12")

    def test_already_sorted_newest_first(self):
        prog = [{"month": "2025-06"}, {"month": "2025-04"}, {"month": "2025-01"}]
        self.assertEqual(latest_month_with_data(prog), "2025-06")

    def test_year_boundary(self):
        prog = [{"month": "2024-12"}, {"month": "2025-01"}, {"month": "2025-02"}]
        self.assertEqual(latest_month_with_data(prog), "2025-02")

    def test_extra_fields_ignored(self):
        prog = [{"month": "2025-05", "sessions": 3, "other": "x"}]
        self.assertEqual(latest_month_with_data(prog), "2025-05")

    def test_missing_month_key_entries_skipped(self):
        # Entries without 'month' key should not crash and should be ignored
        prog = [{"month": "2025-03"}, {"sessions": 5}, {"month": "2025-01"}]
        self.assertEqual(latest_month_with_data(prog), "2025-03")


# ---------------------------------------------------------------------------
# month_windows for --init (n=12) and --backfill=N
# ---------------------------------------------------------------------------


class TestMonthWindowsForInitAndBackfill(unittest.TestCase):
    def test_init_12_windows(self):
        windows = month_windows(12, datetime.date(2025, 12, 31))
        self.assertEqual(len(windows), 12)
        self.assertEqual(windows[0][2], "2025-01")
        self.assertEqual(windows[-1][2], "2025-12")

    def test_backfill_n_windows_count(self):
        for n in (1, 3, 6, 12):
            with self.subTest(n=n):
                windows = month_windows(n, datetime.date(2025, 6, 15))
                self.assertEqual(len(windows), n)

    def test_backfill_3_from_march(self):
        windows = month_windows(3, datetime.date(2025, 3, 15))
        labels = [w[2] for w in windows]
        self.assertEqual(labels, ["2025-01", "2025-02", "2025-03"])


# ---------------------------------------------------------------------------
# Orchestration tests: current-month mode (mocked)
# ---------------------------------------------------------------------------


def _make_summary(sessions=5, since="2025-03-01", until="2025-04-01",
                  progression_monthly=None):
    s = {
        "context": {
            "total_sessions": sessions,
            "date_range": [since, until],
        },
    }
    if progression_monthly is not None:
        s["progression_monthly"] = progression_monthly
    return s


class TestCurrentMonthOrchestration(unittest.TestCase):
    """Light integration tests for the default (no-flag) monthly mode."""

    def _run_main(self, argv, run_paxel_side_effect, upload_return_values,
                  tokens=None):
        if tokens is None:
            tokens = ["tok1"]
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
            try:
                xl_ai_insights.main()
            except SystemExit:
                pass
            return mock_paxel, mock_upload

    def test_current_month_nonempty_uploads_once(self):
        """Non-empty current month → exactly 1 paxel run + 1 upload."""
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[_make_summary(sessions=5)],
            upload_return_values=["/report/m"],
        )
        self.assertEqual(mock_paxel.call_count, 1)
        self.assertEqual(mock_upload.call_count, 1)
        self.assertEqual(mock_upload.call_args[0][1], "tok1")

    def test_current_month_nonempty_paxel_args_contain_since_until(self):
        """Paxel is called with --since=YYYY-MM-01 and --until=1st-of-next-month."""
        mock_paxel, _ = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[_make_summary(sessions=3)],
            upload_return_values=["/r"],
        )
        call_args = mock_paxel.call_args[0][1]  # paxel_args list
        since_args = [a for a in call_args if a.startswith("--since=")]
        until_args = [a for a in call_args if a.startswith("--until=")]
        self.assertEqual(len(since_args), 1)
        self.assertEqual(len(until_args), 1)
        # since must be 1st of the month
        since_val = since_args[0].split("=", 1)[1]
        self.assertTrue(since_val.endswith("-01"), f"since={since_val} should end in -01")

    def test_current_month_empty_fallback_uses_progression_monthly(self):
        """Empty current month → all-time paxel run → picks latest month → 1 upload."""
        prog = [
            {"month": "2025-01"},
            {"month": "2025-02"},
        ]
        # paxel call 1: current month → empty
        # paxel call 2: all-time → has progression_monthly
        # paxel call 3: latest month (2025-02) → non-empty
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[
                _make_summary(sessions=0),              # current month empty
                _make_summary(sessions=10,              # all-time with prog
                              progression_monthly=prog),
                _make_summary(sessions=4),              # fallback month window
            ],
            upload_return_values=["/report/fallback"],
        )
        self.assertEqual(mock_paxel.call_count, 3)
        self.assertEqual(mock_upload.call_count, 1)

    def test_current_month_empty_fallback_paxel_args_for_latest_month(self):
        """Fallback window paxel call uses --since/--until for the latest data month."""
        prog = [{"month": "2025-02"}]
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[
                _make_summary(sessions=0),
                _make_summary(sessions=8, progression_monthly=prog),
                _make_summary(sessions=2),
            ],
            upload_return_values=["/r"],
        )
        # Third paxel call must include --since=2025-02-01
        call3_args = mock_paxel.call_args_list[2][0][1]
        self.assertIn("--since=2025-02-01", call3_args)
        self.assertIn("--until=2025-03-01", call3_args)

    def test_current_month_empty_no_progression_exits_cleanly(self):
        """Empty current month + all-time has no data → clean exit, no upload."""
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[
                _make_summary(sessions=0),           # current month empty
                _make_summary(sessions=0),           # all-time empty too
            ],
            upload_return_values=[],
        )
        self.assertEqual(mock_upload.call_count, 0)

    def test_current_month_empty_progression_empty_list_exits_cleanly(self):
        """progression_monthly present but empty list → no upload."""
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[
                _make_summary(sessions=0),
                _make_summary(sessions=0, progression_monthly=[]),
            ],
            upload_return_values=[],
        )
        self.assertEqual(mock_upload.call_count, 0)


# ---------------------------------------------------------------------------
# Orchestration tests: --init mode (mocked)
# ---------------------------------------------------------------------------


class TestInitMode(unittest.TestCase):
    """--init runs the backfill loop with 12 months."""

    def _run_init(self, run_paxel_side_effect, upload_return_values):
        argv = ["--init", "--no-open"]
        tokens = [f"t{i}" for i in range(1, 13)]

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

    def test_init_runs_12_paxel_calls(self):
        summaries = [_make_summary(sessions=i + 1) for i in range(12)]
        upload_rets = [f"/r/{i}" for i in range(12)]
        mock_paxel, _ = self._run_init(summaries, upload_rets)
        self.assertEqual(mock_paxel.call_count, 12)

    def test_init_uploads_all_nonempty(self):
        summaries = [_make_summary(sessions=i + 1) for i in range(12)]
        upload_rets = [f"/r/{i}" for i in range(12)]
        _, mock_upload = self._run_init(summaries, upload_rets)
        self.assertEqual(mock_upload.call_count, 12)

    def test_init_skips_empty_months(self):
        # 12 months but first 2 are empty
        summaries = (
            [_make_summary(sessions=0)] * 2
            + [_make_summary(sessions=i + 1) for i in range(10)]
        )
        upload_rets = [f"/r/{i}" for i in range(10)]
        _, mock_upload = self._run_init(summaries, upload_rets)
        self.assertEqual(mock_upload.call_count, 10)

    def test_init_paxel_calls_include_since_until(self):
        summaries = [_make_summary(sessions=1) for _ in range(12)]
        upload_rets = [f"/r/{i}" for i in range(12)]
        mock_paxel, _ = self._run_init(summaries, upload_rets)
        for i, c in enumerate(mock_paxel.call_args_list):
            args = c[0][1]
            since_args = [a for a in args if a.startswith("--since=")]
            until_args = [a for a in args if a.startswith("--until=")]
            self.assertEqual(len(since_args), 1, f"call {i} missing --since")
            self.assertEqual(len(until_args), 1, f"call {i} missing --until")


class TestHeadlessAuthCleanExit(unittest.TestCase):
    """No-browser environments (headless/CI/SSH) must skip cleanly, never fail the job.

    README documents: "If the browser can't open (headless/CI) or the auth times out,
    the command prints a warning and exits cleanly — nothing is uploaded." So a
    webbrowser.open() that returns False or raises must exit 0 with no upload, mirroring
    the auth-timeout path — not exit 1.
    """

    def _run_headless(self, *, raises):
        with (
            patch.object(xl_ai_insights, "_capture_cli_token") as mock_capture,
            patch.object(xl_ai_insights, "webbrowser") as mock_wb,
            patch.object(xl_ai_insights, "_run_paxel") as mock_paxel,
            patch.object(xl_ai_insights, "_upload_summary") as mock_upload,
            patch.object(xl_ai_insights.os.path, "isfile", return_value=True),
            patch.object(xl_ai_insights.sys, "argv", ["xl-ai-insights", "--no-open"]),
        ):
            if raises:
                mock_wb.open.side_effect = RuntimeError("no display")
            else:
                mock_wb.open.return_value = False
            with self.assertRaises(SystemExit) as ctx:
                xl_ai_insights.main()
            return ctx.exception, mock_capture, mock_paxel, mock_upload

    def test_browser_returns_false_exits_zero_no_upload(self):
        exc, mock_capture, mock_paxel, mock_upload = self._run_headless(raises=False)
        self.assertEqual(exc.code, 0, "no-browser must exit cleanly (0), not fail the job")
        mock_capture.assert_not_called()  # never even waited for an auth callback
        mock_paxel.assert_not_called()
        mock_upload.assert_not_called()

    def test_browser_open_raises_exits_zero_no_upload(self):
        exc, mock_capture, mock_paxel, mock_upload = self._run_headless(raises=True)
        self.assertEqual(exc.code, 0)
        mock_capture.assert_not_called()
        mock_paxel.assert_not_called()
        mock_upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
