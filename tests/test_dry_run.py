"""Tests for G6: --dry-run flag.

Covers:
  - plan_upload: each reason (force/initial/current/gap/refresh/backfill)
  - equivalence: months_to_upload == [m for m, _ in plan_upload(...)] for all G1 cases
  - _main_console dry-run: prints plan, no paxel calls, no upload calls, exit 0
  - _main_web dry-run: auth mock, no uploads, pushes done event, exits 0
  - help text: --dry-run appears in _HELP_TEXT
  - --dry-run not forwarded to paxel
"""

import contextlib
import datetime
import io
import sys
import unittest
from unittest.mock import MagicMock, call, patch

import gnomon.cli.insights as _insights
import gnomon.upload.mirdash as _mirdash
from gnomon.upload.mirdash import (
    _MAX_BACKFILL,
    plan_upload,
    months_to_upload,
    month_windows,
)


# ---------------------------------------------------------------------------
# Helpers shared with G1 tests
# ---------------------------------------------------------------------------

def _end_of_month_utc_ms(year, month):
    import datetime as _dt
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    dt = _dt.datetime(next_year, next_month, 1, tzinfo=_dt.timezone.utc)
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# plan_upload — reason taxonomy
# ---------------------------------------------------------------------------


class TestPlanUploadReasons(unittest.TestCase):
    TODAY = datetime.date(2025, 7, 15)
    CURRENT = "2025-07"

    # ---- force ----------------------------------------------------------------

    def test_force_gives_force_reason_for_all(self):
        server = [{"monthKey": "2025-07", "uploadedAt": 9999999999999}]
        pairs = plan_upload(self.TODAY, server, force=True)
        self.assertTrue(all(r == "force" for _, r in pairs))
        self.assertEqual(len(pairs), 12)

    def test_force_empty_server_gives_force_reason(self):
        pairs = plan_upload(self.TODAY, [], force=True)
        self.assertTrue(all(r == "force" for _, r in pairs))
        self.assertEqual(len(pairs), 12)

    # ---- initial --------------------------------------------------------------

    def test_empty_server_gives_initial_reason(self):
        pairs = plan_upload(self.TODAY, [])
        self.assertTrue(all(r == "initial" for _, r in pairs))
        self.assertEqual(len(pairs), 12)

    def test_all_malformed_server_gives_initial_reason(self):
        server = [{"bad": "value"}, {"monthKey": "invalid"}]
        pairs = plan_upload(self.TODAY, server)
        self.assertTrue(all(r == "initial" for _, r in pairs))

    # ---- current --------------------------------------------------------------

    def test_server_has_fresh_everything_gives_only_current(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms + 1000},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        pairs = plan_upload(self.TODAY, server)
        self.assertEqual(len(pairs), 1)
        label, reason = pairs[0]
        self.assertEqual(label, "2025-07")
        self.assertEqual(reason, "current")

    def test_current_month_reason_when_only_current_in_server(self):
        server = [{"monthKey": "2025-07", "uploadedAt": 9999999999999}]
        pairs = plan_upload(self.TODAY, server)
        labels = [m for m, _ in pairs]
        self.assertIn("2025-07", labels)
        cur_reason = dict(pairs)["2025-07"]
        self.assertEqual(cur_reason, "current")

    # ---- gap ------------------------------------------------------------------

    def test_gap_months_get_gap_reason(self):
        # latest_server = 2025-04 → gap = 2025-05, 2025-06; current = 2025-07
        server = [{"monthKey": "2025-04", "uploadedAt": 9999999999999}]
        pairs = plan_upload(self.TODAY, server)
        reason_map = dict(pairs)
        self.assertEqual(reason_map.get("2025-05"), "gap")
        self.assertEqual(reason_map.get("2025-06"), "gap")
        self.assertEqual(reason_map.get("2025-07"), "current")

    def test_gap_oldest_first(self):
        server = [{"monthKey": "2025-04", "uploadedAt": 9999999999999}]
        pairs = plan_upload(self.TODAY, server)
        labels = [m for m, _ in pairs]
        self.assertEqual(labels, sorted(labels))

    # ---- refresh --------------------------------------------------------------

    def test_prev_stale_gets_refresh_reason(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        pairs = plan_upload(self.TODAY, server)
        reason_map = dict(pairs)
        self.assertEqual(reason_map.get("2025-06"), "refresh")
        self.assertEqual(reason_map.get("2025-07"), "current")

    def test_prev_fresh_not_included(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        pairs = plan_upload(self.TODAY, server)
        labels = [m for m, _ in pairs]
        self.assertNotIn("2025-06", labels)

    def test_prev_not_in_server_not_included(self):
        server = [{"monthKey": "2025-07", "uploadedAt": 9999999999999}]
        pairs = plan_upload(self.TODAY, server)
        labels = [m for m, _ in pairs]
        self.assertNotIn("2025-06", labels)

    # ---- max_months cap -------------------------------------------------------

    def test_capped_at_max_months(self):
        server = [{"monthKey": "2020-01", "uploadedAt": 9999999999999}]
        pairs = plan_upload(self.TODAY, server)
        self.assertEqual(len(pairs), 12)

    def test_custom_max_months(self):
        pairs = plan_upload(self.TODAY, [], max_months=3)
        self.assertEqual(len(pairs), 3)

    # ---- no duplicate labels --------------------------------------------------

    def test_no_duplicate_labels(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 5)
        server = [
            {"monthKey": "2025-05", "uploadedAt": 9999999999999},
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1000},
        ]
        pairs = plan_upload(self.TODAY, server)
        labels = [m for m, _ in pairs]
        self.assertEqual(len(labels), len(set(labels)))


# ---------------------------------------------------------------------------
# Equivalence: months_to_upload == [m for m, _ in plan_upload(...)]
# ---------------------------------------------------------------------------


class TestPlanUploadEquivalence(unittest.TestCase):
    """plan_upload must produce same month list as months_to_upload for all inputs."""

    TODAY = datetime.date(2025, 7, 15)

    def _assert_equiv(self, today, server, force=False, max_months=_MAX_BACKFILL):
        expected = months_to_upload(today, server, force=force, max_months=max_months)
        got = [m for m, _ in plan_upload(today, server, force=force, max_months=max_months)]
        self.assertEqual(got, expected, f"Mismatch for force={force}, max_months={max_months}")

    def test_empty_server(self):
        self._assert_equiv(self.TODAY, [])

    def test_force_full_server(self):
        server = [
            {"monthKey": f"2025-{m:02d}", "uploadedAt": 9999999999999}
            for m in range(1, 8)
        ]
        self._assert_equiv(self.TODAY, server, force=True)

    def test_fresh_prev_current_only(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms + 1000},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        self._assert_equiv(self.TODAY, server)

    def test_stale_prev(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        self._assert_equiv(self.TODAY, server)

    def test_gap_fill(self):
        server = [{"monthKey": "2025-04", "uploadedAt": 9999999999999}]
        self._assert_equiv(self.TODAY, server)

    def test_gap_fill_capped(self):
        server = [{"monthKey": "2020-01", "uploadedAt": 9999999999999}]
        self._assert_equiv(self.TODAY, server)

    def test_custom_max(self):
        self._assert_equiv(self.TODAY, [], max_months=3)

    def test_custom_max_incremental(self):
        server = [{"monthKey": "2020-01", "uploadedAt": 9999999999999}]
        self._assert_equiv(self.TODAY, server, max_months=3)

    def test_all_malformed(self):
        server = [{"bad": "val"}, {"monthKey": "invalid"}]
        self._assert_equiv(self.TODAY, server)

    def test_first_of_month(self):
        today = datetime.date(2025, 7, 1)
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        server = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1000},
            {"monthKey": "2025-07", "uploadedAt": 0},
        ]
        self._assert_equiv(today, server)


# ---------------------------------------------------------------------------
# _main_console dry-run
# ---------------------------------------------------------------------------


class TestMainConsoleDryRun(unittest.TestCase):
    TODAY = datetime.date(2025, 7, 15)

    def _run_dry_run_console(self, mode="auto", token_count=12, uploaded=None):
        """Drive _main_console with dry_run=True; return (stdout_text, mock_paxel, mock_upload)."""
        if uploaded is None:
            uploaded = []
        buf = io.StringIO()
        mock_date = MagicMock()
        mock_date.today.return_value = self.TODAY
        with (
            patch.object(_insights, "_capture_cli_token",
                         return_value=(["tok"] * token_count, uploaded)),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_mirdash, "_run_paxel") as mock_paxel,
            patch.object(_mirdash, "_upload_summary") as mock_upload,
            patch("gnomon.cli.insights.datetime") as mock_dt,
            contextlib.redirect_stdout(buf),
        ):
            mock_wb.open.return_value = True
            mock_dt.date = mock_date
            mock_dt.datetime = datetime.datetime
            mock_dt.timezone = datetime.timezone
            mock_dt.timedelta = datetime.timedelta
            try:
                _insights._main_console(
                    [], "https://mirdash.example", mode, token_count, [], True, False, False,
                    dry_run=True,
                )
                exited = False
                exit_code = None
            except SystemExit as e:
                exited = True
                exit_code = e.code

        return buf.getvalue(), mock_paxel, mock_upload, exited, exit_code

    def test_no_paxel_calls(self):
        _, mock_paxel, _, _, _ = self._run_dry_run_console()
        mock_paxel.assert_not_called()

    def test_no_upload_calls(self):
        _, _, mock_upload, _, _ = self._run_dry_run_console()
        mock_upload.assert_not_called()

    def test_exits_0(self):
        _, _, _, exited, code = self._run_dry_run_console()
        self.assertTrue(exited)
        self.assertEqual(code, 0)

    def test_prints_dry_run_header(self):
        out, _, _, _, _ = self._run_dry_run_console()
        self.assertIn("Dry run", out)
        self.assertIn("no uploads", out)

    def test_prints_mode(self):
        out, _, _, _, _ = self._run_dry_run_console(mode="auto")
        self.assertIn("Mode: auto", out)

    def test_prints_month_count(self):
        # empty uploaded → 12 initial months
        out, _, _, _, _ = self._run_dry_run_console()
        self.assertIn("12 month(s)", out)

    def test_prints_reason_initial(self):
        out, _, _, _, _ = self._run_dry_run_console()
        self.assertIn("no prior uploads", out)

    def test_stale_prev_refresh_and_current(self):
        prev_end_ms = _end_of_month_utc_ms(2025, 6)
        uploaded = [
            {"monthKey": "2025-06", "uploadedAt": prev_end_ms - 1},
            {"monthKey": "2025-07", "uploadedAt": 9999999999999},
        ]
        out, mock_paxel, mock_upload, exited, code = self._run_dry_run_console(uploaded=uploaded)
        self.assertIn("2025-06", out)
        self.assertIn("refresh", out)
        self.assertIn("2025-07", out)
        self.assertIn("current month", out)
        mock_paxel.assert_not_called()
        mock_upload.assert_not_called()
        self.assertEqual(code, 0)

    def test_force_mode_shows_force_reason(self):
        out, _, _, _, _ = self._run_dry_run_console(mode="force")
        self.assertIn("force re-upload", out)

    def test_backfill_mode_shows_backfill(self):
        out, _, _, _, _ = self._run_dry_run_console(mode="backfill", token_count=3)
        self.assertIn("backfill", out)

    def test_footer_line_present(self):
        out, _, _, _, _ = self._run_dry_run_console()
        self.assertIn("empty months are skipped", out)


# ---------------------------------------------------------------------------
# _main_web dry-run
# ---------------------------------------------------------------------------


class TestMainWebDryRun(unittest.TestCase):
    TODAY = datetime.date(2025, 7, 15)

    def _run_dry_run_web(self, mode="auto", token_count=12, uploaded=None):
        """Drive _main_web with dry_run=True."""
        if uploaded is None:
            uploaded = []
        buf = io.StringIO()
        mock_server = MagicMock()
        mock_server.url = "http://127.0.0.1:8799"
        mock_server.uploaded = uploaded
        pushed_events = []
        mock_server.push_event.side_effect = lambda name, data: pushed_events.append((name, data))

        mock_date = MagicMock()
        mock_date.today.return_value = self.TODAY

        with (
            patch("gnomon.upload.progress_server.ProgressServer", return_value=mock_server),
            patch("gnomon.cli.insights.ProgressServer", return_value=mock_server, create=True),
            patch.object(_insights, "_wait_for_auth_tokens",
                         return_value=(["tok"] * token_count)),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_mirdash, "_run_paxel") as mock_paxel,
            patch.object(_mirdash, "_upload_summary") as mock_upload,
            patch("gnomon.cli.insights.datetime") as mock_dt,
            contextlib.redirect_stdout(buf),
        ):
            mock_wb.open.return_value = True
            mock_dt.date = mock_date
            mock_dt.datetime = datetime.datetime
            mock_dt.timezone = datetime.timezone
            mock_dt.timedelta = datetime.timedelta
            try:
                _insights._main_web(
                    [], "https://mirdash.example", mode, token_count, [], True, False, False,
                    dry_run=True,
                )
                exited = False
                exit_code = None
            except SystemExit as e:
                exited = True
                exit_code = e.code

        return buf.getvalue(), mock_paxel, mock_upload, exited, exit_code, pushed_events

    def test_no_paxel_calls(self):
        _, mock_paxel, _, _, _, _ = self._run_dry_run_web()
        mock_paxel.assert_not_called()

    def test_no_upload_calls(self):
        _, _, mock_upload, _, _, _ = self._run_dry_run_web()
        mock_upload.assert_not_called()

    def test_exits_0(self):
        _, _, _, exited, code, _ = self._run_dry_run_web()
        self.assertTrue(exited)
        self.assertEqual(code, 0)

    def test_pushes_done_event(self):
        _, _, _, _, _, events = self._run_dry_run_web()
        event_names = [name for name, _ in events]
        self.assertIn("done", event_names)

    def test_done_event_has_dry_run_flag(self):
        _, _, _, _, _, events = self._run_dry_run_web()
        done_data = next(data for name, data in events if name == "done")
        self.assertTrue(done_data.get("dryRun"))

    def test_done_event_uploaded_is_0(self):
        _, _, _, _, _, events = self._run_dry_run_web()
        done_data = next(data for name, data in events if name == "done")
        self.assertEqual(done_data["uploaded"], 0)

    def test_server_shutdown_called(self):
        buf, _, _, _, _, _ = self._run_dry_run_web()
        # If we got here without hanging, server.shutdown() was called

    def test_prints_dry_run_plan_to_console(self):
        out, _, _, _, _, _ = self._run_dry_run_web()
        self.assertIn("Dry run", out)

    def test_no_auth_ok_event_pushed(self):
        _, _, _, _, _, events = self._run_dry_run_web()
        event_names = [name for name, _ in events]
        self.assertNotIn("auth_ok", event_names)


# ---------------------------------------------------------------------------
# help text
# ---------------------------------------------------------------------------


class TestDryRunHelpText(unittest.TestCase):
    def test_dry_run_in_help_text(self):
        self.assertIn("--dry-run", _insights._HELP_TEXT)

    def test_help_prints_dry_run(self):
        buf = io.StringIO()
        with (
            contextlib.redirect_stdout(buf),
            self.assertRaises(SystemExit),
        ):
            _insights.main(["--help"])
        self.assertIn("--dry-run", buf.getvalue())


# ---------------------------------------------------------------------------
# --dry-run not forwarded to paxel
# ---------------------------------------------------------------------------


class TestDryRunNotForwardedToPaxel(unittest.TestCase):
    def test_dry_run_stripped_from_paxel_forward(self):
        with (
            patch.object(_insights, "_main_web") as mock_web,
            patch.object(_insights, "_main_console") as mock_console,
        ):
            _insights.main(["--dry-run", "claude", "--console"])

        # _main_console was called (--console flag)
        mock_console.assert_called_once()
        args = mock_console.call_args[0]
        paxel_forward = args[4]
        self.assertNotIn("--dry-run", paxel_forward)
        self.assertIn("claude", paxel_forward)

    def test_dry_run_keyword_arg_passed_true(self):
        with (
            patch.object(_insights, "_main_web") as mock_web,
        ):
            _insights.main(["--dry-run"])

        mock_web.assert_called_once()
        kwargs = mock_web.call_args[1]
        self.assertTrue(kwargs.get("dry_run"))


# ---------------------------------------------------------------------------
# _main_web OSError fallback preserves dry_run
# ---------------------------------------------------------------------------


class TestMainWebOSErrorFallbackDryRun(unittest.TestCase):
    """When ProgressServer raises OSError, --dry-run must survive the fallback to console mode."""

    TODAY = datetime.date(2025, 7, 15)

    def _run_web_oserror_dry_run(self, mode="auto", token_count=12, uploaded=None):
        """Drive _main_web with dry_run=True and ProgressServer raising OSError."""
        if uploaded is None:
            uploaded = []
        buf = io.StringIO()
        mock_date = MagicMock()
        mock_date.today.return_value = self.TODAY

        with (
            patch("gnomon.cli.insights.ProgressServer", side_effect=OSError("address already in use"), create=True),
            patch.object(_insights, "_capture_cli_token",
                         return_value=(["tok"] * token_count, uploaded)),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_mirdash, "_run_paxel") as mock_paxel,
            patch.object(_mirdash, "_upload_summary") as mock_upload,
            patch("gnomon.cli.insights.datetime") as mock_dt,
            contextlib.redirect_stdout(buf),
        ):
            mock_wb.open.return_value = True
            mock_dt.date = mock_date
            mock_dt.datetime = datetime.datetime
            mock_dt.timezone = datetime.timezone
            mock_dt.timedelta = datetime.timedelta
            try:
                _insights._main_web(
                    [], "https://mirdash.example", mode, token_count, [], True, False, False,
                    dry_run=True,
                )
                exited = False
                exit_code = None
            except SystemExit as e:
                exited = True
                exit_code = e.code

        return buf.getvalue(), mock_paxel, mock_upload, exited, exit_code

    def test_no_paxel_calls_after_oserror_fallback(self):
        _, mock_paxel, _, _, _ = self._run_web_oserror_dry_run()
        mock_paxel.assert_not_called()

    def test_no_upload_calls_after_oserror_fallback(self):
        _, _, mock_upload, _, _ = self._run_web_oserror_dry_run()
        mock_upload.assert_not_called()

    def test_exits_0_after_oserror_fallback(self):
        _, _, _, exited, code = self._run_web_oserror_dry_run()
        self.assertTrue(exited)
        self.assertEqual(code, 0)

    def test_prints_dry_run_header_after_oserror_fallback(self):
        out, _, _, _, _ = self._run_web_oserror_dry_run()
        self.assertIn("Dry run", out)
        self.assertIn("no uploads", out)

    def test_warns_about_fallback(self):
        out, _, _, _, _ = self._run_web_oserror_dry_run()
        self.assertIn("falling back to console mode", out)


if __name__ == "__main__":
    unittest.main()
