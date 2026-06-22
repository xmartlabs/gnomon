"""Tests for the monthly-dashboard mode introduced in v0.5.0.

Covers:
  - decide_mode: arg-parsing precedence (--force, --backfill=N, neither)
  - month_windows(1, ...) for current-month window + year rollover
  - latest_month_with_data: picks most recent month with data, handles edge cases
  - force/backfill loop: N windows produced (reuses month_windows)
  - current-month orchestration: non-empty upload, empty-fallback, total-empty exit
"""

import datetime
import calendar
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import gnomon.cli.insights as _insights
import gnomon.upload.mirdash as _mirdash
from gnomon.upload.mirdash import (
    decide_mode,
    latest_month_with_data,
    month_windows,
    _is_report_url,
    _PAXEL_ERROR,
    _UPLOAD_ERROR,
    _absolutize_dir_flags,
)


# ---------------------------------------------------------------------------
# decide_mode
# ---------------------------------------------------------------------------


class TestDecideMode(unittest.TestCase):
    """decide_mode(argv) -> ('force', 12) | ('backfill', N) | ('auto', 12)"""

    def test_no_flags_returns_auto(self):
        mode, n = decide_mode([])
        self.assertEqual(mode, "auto")
        self.assertEqual(n, 12)

    def test_force_flag_returns_force_12(self):
        mode, n = decide_mode(["--force"])
        self.assertEqual(mode, "force")
        self.assertEqual(n, 12)

    def test_backfill_3_returns_backfill_3(self):
        mode, n = decide_mode(["--backfill=3"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 3)

    def test_backfill_bare_flag_returns_backfill_6(self):
        mode, n = decide_mode(["--backfill"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 6)

    def test_force_takes_precedence_over_backfill(self):
        # --force wins if both are present
        mode, n = decide_mode(["--force", "--backfill=5"])
        self.assertEqual(mode, "force")
        self.assertEqual(n, 12)

    def test_auto_with_other_flags(self):
        mode, n = decide_mode(["--quiet", "--no-open", "claude"])
        self.assertEqual(mode, "auto")
        self.assertEqual(n, 12)

    def test_backfill_with_other_flags(self):
        mode, n = decide_mode(["--quiet", "--backfill=7", "--no-open"])
        self.assertEqual(mode, "backfill")
        self.assertEqual(n, 7)

    def test_force_with_other_flags(self):
        mode, n = decide_mode(["--no-open", "--quiet", "--force"])
        self.assertEqual(mode, "force")
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
# month_windows for --force (n=12) and --backfill=N
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


def _ms(dt):
    """datetime.datetime → epoch-ms int."""
    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)


def _current_only_uploaded(today):
    """Server-state that makes months_to_upload(today, ...) return exactly [current].

    current is present and fresh; prev is present and NOT stale (uploadedAt >=
    first day of the month after prev), so neither gap-fill nor stale-refresh adds it.
    """
    cur_total = today.year * 12 + (today.month - 1)
    cur = f"{cur_total // 12:04d}-{cur_total % 12 + 1:02d}"
    prev_total = cur_total - 1
    prev = f"{prev_total // 12:04d}-{prev_total % 12 + 1:02d}"
    # Bound = first day of the month after prev = current month's first day.
    fresh_prev = _ms(datetime.datetime(today.year, today.month, 1))
    return [
        {"monthKey": cur, "uploadedAt": _ms(datetime.datetime(2999, 1, 1))},
        {"monthKey": prev, "uploadedAt": fresh_prev},
    ]


class TestCurrentMonthOrchestration(unittest.TestCase):
    """Light integration tests for the default (no-flag) auto mode.

    In auto mode the months to upload come from months_to_upload(today, uploaded).
    These tests pin a single-window (current month) run by supplying server-state
    where current is fresh and prev is not stale, so [current] is the only anchor.
    """

    def _run_main(self, argv, run_paxel_side_effect, upload_return_values,
                  tokens=None, uploaded=None):
        if tokens is None:
            tokens = ["tok1"]
        if uploaded is None:
            uploaded = _current_only_uploaded(datetime.date.today())
        if "--console" not in argv:
            argv = argv + ["--console"]
        with (
            patch.object(_insights, "_capture_cli_token", return_value=(tokens, uploaded)),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(
                _mirdash,
                "_run_paxel",
                side_effect=run_paxel_side_effect,
            ) as mock_paxel,
            patch.object(
                _mirdash,
                "_upload_summary",
                side_effect=upload_return_values,
            ) as mock_upload,
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_insights.sys, "argv", ["xl-ai-insights"] + argv),
        ):
            mock_wb.open.return_value = True
            try:
                _insights.main()
            except SystemExit:
                pass
            return mock_paxel, mock_upload

    def test_current_month_nonempty_uploads_once(self):
        """auto + server-state pinned to [current] → exactly 1 paxel run + 1 upload."""
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[_make_summary(sessions=5)],
            upload_return_values=["/report/m"],
        )
        self.assertEqual(mock_paxel.call_count, 1)
        self.assertEqual(mock_upload.call_count, 1)
        self.assertEqual(mock_upload.call_args[0][1], "tok1")

    def test_current_month_nonempty_paxel_args_contain_since_until(self):
        """Paxel is called with an inclusive month window for paxel.py."""
        mock_paxel, _ = self._run_main(
            argv=["--no-open", "--window=1"],
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
        since_d = datetime.date.fromisoformat(since_val)
        until_val = until_args[0].split("=", 1)[1]
        until_d = datetime.date.fromisoformat(until_val)
        last_day = calendar.monthrange(since_d.year, since_d.month)[1]
        self.assertEqual(until_d, datetime.date(since_d.year, since_d.month, last_day))

    def test_auto_empty_server_sweeps_twelve_months(self):
        """auto + empty server-state → full backfill of 12 windows (oldest first)."""
        # 12 windows; make every one empty so no token is consumed and we just
        # count paxel runs.
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[_make_summary(sessions=0)] * 12,
            upload_return_values=[],
            tokens=[f"t{i}" for i in range(12)],
            uploaded=[],   # empty server-state → months_to_upload returns 12 months
        )
        self.assertEqual(mock_paxel.call_count, 12)
        self.assertEqual(mock_upload.call_count, 0)

    def test_auto_current_pinned_empty_uploads_nothing_no_fallback(self):
        """auto pinned to [current], current empty → no upload, no historical fallback.

        Exactly one paxel run for the current window; the old empty-month fallback
        (all-time scan + latest_month_with_data) no longer exists.
        """
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[_make_summary(sessions=0)],
            upload_return_values=[],
        )
        self.assertEqual(mock_paxel.call_count, 1)
        self.assertEqual(mock_upload.call_count, 0)

    def test_auto_prev_stale_uploads_prev_and_current(self):
        """auto + prev present-but-stale → windows = [prev, current], both uploaded."""
        today = datetime.date.today()
        cur_total = today.year * 12 + (today.month - 1)
        cur = f"{cur_total // 12:04d}-{cur_total % 12 + 1:02d}"
        prev_total = cur_total - 1
        prev = f"{prev_total // 12:04d}-{prev_total % 12 + 1:02d}"
        # prev present but stale: uploadedAt strictly before the start of current month.
        stale_prev = _ms(datetime.datetime(today.year, today.month, 1)) - 1
        uploaded = [
            {"monthKey": cur, "uploadedAt": _ms(datetime.datetime(2999, 1, 1))},
            {"monthKey": prev, "uploadedAt": stale_prev},
        ]
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[_make_summary(sessions=2), _make_summary(sessions=3)],
            upload_return_values=["/r/prev", "/r/cur"],
            tokens=["t1", "t2"],
            uploaded=uploaded,
        )
        self.assertEqual(mock_paxel.call_count, 2)
        self.assertEqual(mock_upload.call_count, 2)

    def test_current_month_paxel_error_does_not_fall_back(self):
        """A paxel run FAILURE (None) for the only window must NOT trigger any
        historical-month fallback — that path no longer exists. Expect exactly 1
        paxel run and 0 uploads."""
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open"],
            run_paxel_side_effect=[None],   # current-month paxel run failed
            upload_return_values=[],
        )
        self.assertEqual(mock_paxel.call_count, 1)   # no all-time run, no fallback run
        self.assertEqual(mock_upload.call_count, 0)

    def test_current_month_paxel_error_console_no_fallback(self):
        """Same guard on the console path (--console): paxel failure → no fallback, no upload."""
        mock_paxel, mock_upload = self._run_main(
            argv=["--no-open", "--console"],
            run_paxel_side_effect=[None],
            upload_return_values=[],
        )
        self.assertEqual(mock_paxel.call_count, 1)
        self.assertEqual(mock_upload.call_count, 0)


# ---------------------------------------------------------------------------
# Orchestration tests: --force mode (mocked)
# ---------------------------------------------------------------------------


class TestForceMode(unittest.TestCase):
    """--force runs the backfill loop with 12 months."""

    def _run_init(self, run_paxel_side_effect, upload_return_values):
        argv = ["--force", "--no-open", "--console"]
        tokens = [f"t{i}" for i in range(1, 13)]

        with (
            patch.object(_insights, "_capture_cli_token", return_value=(tokens, [])),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(
                _mirdash,
                "_run_paxel",
                side_effect=run_paxel_side_effect,
            ) as mock_paxel,
            patch.object(
                _mirdash,
                "_upload_summary",
                side_effect=upload_return_values,
            ) as mock_upload,
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_insights.sys, "argv", ["xl-ai-insights"] + argv),
        ):
            mock_wb.open.return_value = True
            _insights.main()
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
            patch.object(_insights, "_capture_cli_token") as mock_capture,
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_insights, "_run_paxel") as mock_paxel,
            patch.object(_insights, "_upload_summary") as mock_upload,
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_insights.sys, "argv", ["xl-ai-insights", "--no-open", "--console"]),
        ):
            if raises:
                mock_wb.open.side_effect = RuntimeError("no display")
            else:
                mock_wb.open.return_value = False
            with self.assertRaises(SystemExit) as ctx:
                _insights.main()
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


# ---------------------------------------------------------------------------
# Failure-mode plumbing: report-url sentinels, dir-flag absolutization
# ---------------------------------------------------------------------------


class TestIsReportUrl(unittest.TestCase):
    def test_real_url_is_report_url(self):
        self.assertTrue(_is_report_url("/report/abc"))

    def test_none_is_not_report_url(self):
        self.assertFalse(_is_report_url(None))

    def test_paxel_error_sentinel_is_not_report_url(self):
        self.assertFalse(_is_report_url(_PAXEL_ERROR))

    def test_upload_error_sentinel_is_not_report_url(self):
        self.assertFalse(_is_report_url(_UPLOAD_ERROR))


class TestUploadWindowWebSentinels(unittest.TestCase):
    """_upload_window_web distinguishes paxel failure / empty / upload failure / success."""

    def _call(self, run_paxel_return=None, run_paxel_side=None, upload_side=None):
        server = MagicMock()
        with (
            patch.object(_mirdash, "_run_paxel",
                         return_value=run_paxel_return, side_effect=run_paxel_side),
            patch.object(_mirdash, "_upload_summary", side_effect=upload_side),
        ):
            from gnomon.upload.mirdash import _upload_window_web
            return _upload_window_web(
                "https://m", "tok", "/paxel.py", [], "2025-12-01", "2026-01-01",
                "2025-12", False, server, 0, 1,
            )

    def test_paxel_failure_returns_paxel_error_sentinel(self):
        self.assertEqual(self._call(run_paxel_return=None), _PAXEL_ERROR)

    def test_empty_summary_returns_none(self):
        empty = _make_summary(sessions=0)
        self.assertIsNone(self._call(run_paxel_return=empty))

    def test_upload_exception_returns_upload_error_sentinel(self):
        good = _make_summary(sessions=5)
        result = self._call(run_paxel_return=good, upload_side=RuntimeError("boom"))
        self.assertEqual(result, _UPLOAD_ERROR)

    def test_success_returns_report_url(self):
        good = _make_summary(sessions=5)
        result = self._call(run_paxel_return=good, upload_side=["/report/m"])
        self.assertEqual(result, "/report/m")

    def _events(self, **kw):
        """Run _upload_window_web and return the list of pushed event types."""
        server = MagicMock()
        with (
            patch.object(_mirdash, "_run_paxel",
                         return_value=kw.get("run_paxel_return"),
                         side_effect=kw.get("run_paxel_side")),
            patch.object(_mirdash, "_upload_summary", side_effect=kw.get("upload_side")),
        ):
            from gnomon.upload.mirdash import _upload_window_web
            _upload_window_web(
                "https://m", "tok", "/paxel.py", [], "2025-12-01", "2026-01-01",
                "2025-12", False, server, 0, 1,
            )
        return [c.args[0] for c in server.push_event.call_args_list]

    def test_paxel_failure_pushes_error_not_skipped(self):
        # paxel error must surface as a failure (error_msg), not a skip — the UI
        # reserves "skipped" for genuinely empty windows.
        events = self._events(run_paxel_return=None)
        self.assertIn("error_msg", events)
        self.assertNotIn("skipped", events)

    def test_empty_summary_pushes_skipped(self):
        events = self._events(run_paxel_return=_make_summary(sessions=0))
        self.assertIn("skipped", events)
        self.assertNotIn("error_msg", events)

    def test_upload_failure_pushes_error_msg(self):
        events = self._events(run_paxel_return=_make_summary(sessions=5),
                              upload_side=RuntimeError("boom"))
        self.assertIn("error_msg", events)


class TestAbsolutizeDirFlags(unittest.TestCase):
    def test_relative_dir_flag_made_absolute(self):
        out = _absolutize_dir_flags(["--claude-dir=./backup/.claude"])
        self.assertEqual(out[0], "--claude-dir=" + os.path.abspath("./backup/.claude"))
        self.assertTrue(out[0].split("=", 1)[1].startswith("/"))

    def test_absolute_dir_flag_unchanged(self):
        out = _absolutize_dir_flags(["--codex-dir=/abs/path"])
        self.assertEqual(out, ["--codex-dir=/abs/path"])

    def test_home_dir_flag_expanded(self):
        out = _absolutize_dir_flags(["--gemini-dir=~/x"])
        self.assertEqual(out[0], "--gemini-dir=" + os.path.abspath(os.path.expanduser("~/x")))

    def test_non_dir_flags_and_sources_untouched(self):
        args = ["claude", "--mirdash-base=https://m", "--quiet"]
        self.assertEqual(_absolutize_dir_flags(args), args)


if __name__ == "__main__":
    unittest.main()
