"""Tests for the --window=N flag: parsing, paxel_forward stripping, and payload stamping."""

import contextlib
import datetime
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import gnomon.cli.insights as _insights
_RELEASE_CURRENT = {"status": "current", "current": "0.4.0", "latest": "0.4.0"}

import gnomon.upload.mirdash as _mirdash
from gnomon.upload.mirdash import _DEFAULT_WINDOW_MONTHS, parse_window


def _ms(dt):
    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)


def _current_only_uploaded(today=None):
    """Server-state pinning months_to_upload to exactly [current month]."""
    today = today or datetime.date.today()
    cur_total = today.year * 12 + (today.month - 1)
    cur = f"{cur_total // 12:04d}-{cur_total % 12 + 1:02d}"
    prev_total = cur_total - 1
    prev = f"{prev_total // 12:04d}-{prev_total % 12 + 1:02d}"
    fresh_prev = _ms(datetime.datetime(today.year, today.month, 1))
    return [
        {"monthKey": cur, "uploadedAt": _ms(datetime.datetime(2999, 1, 1))},
        {"monthKey": prev, "uploadedAt": fresh_prev},
    ]


# ---------------------------------------------------------------------------
# parse_window — pure unit tests
# ---------------------------------------------------------------------------


class TestParseWindow(unittest.TestCase):
    def test_absent_returns_default(self):
        self.assertEqual(parse_window([]), _DEFAULT_WINDOW_MONTHS)

    def test_valid_value_3(self):
        self.assertEqual(parse_window(["--window=3"]), 3)

    def test_valid_value_1(self):
        self.assertEqual(parse_window(["--window=1"]), 1)

    def test_valid_value_12(self):
        self.assertEqual(parse_window(["--window=12"]), 12)

    def test_non_int_warns_and_returns_default(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = parse_window(["--window=abc"])
        self.assertEqual(result, _DEFAULT_WINDOW_MONTHS)
        self.assertIn("warning", buf.getvalue())

    def test_zero_warns_and_returns_default(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = parse_window(["--window=0"])
        self.assertEqual(result, _DEFAULT_WINDOW_MONTHS)
        self.assertIn("warning", buf.getvalue())

    def test_negative_warns_and_returns_default(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = parse_window(["--window=-2"])
        self.assertEqual(result, _DEFAULT_WINDOW_MONTHS)
        self.assertIn("warning", buf.getvalue())

    def test_among_other_flags(self):
        self.assertEqual(parse_window(["--quiet", "--window=4", "--no-open"]), 4)

    def test_absent_with_other_flags(self):
        self.assertEqual(parse_window(["--quiet", "--no-open"]), _DEFAULT_WINDOW_MONTHS)

    def test_default_is_3(self):
        self.assertEqual(_DEFAULT_WINDOW_MONTHS, 3)

    def test_bare_window_warns_and_returns_default(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = parse_window(["--window", "6"])
        self.assertEqual(result, _DEFAULT_WINDOW_MONTHS)
        self.assertIn("warning", buf.getvalue())


# ---------------------------------------------------------------------------
# --window= is stripped from paxel_forward (does NOT reach paxel)
# ---------------------------------------------------------------------------


class TestWindowNotForwardedToPaxel(unittest.TestCase):
    def test_window_flag_stripped_from_paxel_forward(self):
        """--window=N must not be forwarded to paxel."""
        with (
            patch.object(_insights, "_main_web") as mock_main_web,
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(
                _insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "claude", "--no-open"],
            ),
        ):
            _insights.main()

        args = mock_main_web.call_args[0]
        paxel_forward = args[4]
        self.assertNotIn("--window=3", paxel_forward)
        # Source name claude must still be forwarded
        self.assertIn("claude", paxel_forward)

    def test_window_flag_not_forwarded_console_mode(self):
        """--window=N must not reach paxel in console mode either."""
        with (
            patch.object(_insights, "_main_console") as mock_main_console,
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(
                _insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "--console", "claude", "--no-open"],
            ),
        ):
            _insights.main()

        args = mock_main_console.call_args[0]
        paxel_forward = args[4]
        self.assertNotIn("--window=3", paxel_forward)
        self.assertIn("claude", paxel_forward)


# ---------------------------------------------------------------------------
# window_months is threaded into main() calls
# ---------------------------------------------------------------------------


class TestWindowMonthsPassedToHandlers(unittest.TestCase):
    def test_window_months_passed_to_main_web(self):
        with (
            patch.object(_insights, "_main_web") as mock_main_web,
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(
                _insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "--no-open"],
            ),
        ):
            _insights.main()

        kwargs = mock_main_web.call_args[1]
        self.assertEqual(kwargs.get("window_months"), 3)

    def test_window_months_passed_to_main_console(self):
        with (
            patch.object(_insights, "_main_console") as mock_main_console,
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(
                _insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "--console", "--no-open"],
            ),
        ):
            _insights.main()

        kwargs = mock_main_console.call_args[1]
        self.assertEqual(kwargs.get("window_months"), 3)

    def test_default_window_months_passed_when_absent(self):
        with (
            patch.object(_insights, "_main_web") as mock_main_web,
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(
                _insights.sys,
                "argv",
                ["xl-ai-insights", "--no-open"],
            ),
        ):
            _insights.main()

        kwargs = mock_main_web.call_args[1]
        self.assertEqual(kwargs.get("window_months"), _DEFAULT_WINDOW_MONTHS)


# ---------------------------------------------------------------------------
# context.window_months is stamped into uploaded payload (console mode)
# ---------------------------------------------------------------------------


def _make_summary(sessions=5, since="2026-01-01", until="2026-07-01"):
    return {
        "context": {
            "total_sessions": sessions,
            "date_range": [since, until],
        },
    }


class TestWindowMonthsInPayload(unittest.TestCase):
    """Verify context.window_months is stamped before upload in console mode."""

    def _run_console(self, argv, summaries, upload_returns, tokens=None, uploaded=None):
        """Run main() in console mode with mocked I/O; return captured upload calls.

        Patches both _insights and _mirdash for _run_paxel / _upload_summary so
        the helper works regardless of which module the call resolves through.
        """
        if tokens is None:
            tokens = ["tok1"]
        if uploaded is None:
            uploaded = _current_only_uploaded()
        uploaded_summaries = []

        # Use a shared list for side effects so both patches draw from the same pool.
        remaining_summaries = list(summaries)
        remaining_uploads = list(upload_returns)

        def fake_run_paxel(paxel_src, args, verbose, **kwargs):
            if not remaining_summaries:
                raise StopIteration("unexpected _run_paxel call")
            return remaining_summaries.pop(0)

        def capture_upload(mirdash_base, token, summary):
            uploaded_summaries.append(summary)
            if not remaining_uploads:
                return "/r/x"
            return remaining_uploads.pop(0)

        with (
            patch.object(_insights, "_capture_cli_token", return_value=(tokens, uploaded)),
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_insights, "_run_paxel", side_effect=fake_run_paxel),
            patch.object(_insights, "_upload_summary", side_effect=capture_upload),
            patch.object(_mirdash, "_run_paxel", side_effect=fake_run_paxel),
            patch.object(_mirdash, "_upload_summary", side_effect=capture_upload),
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_insights.sys, "argv", ["xl-ai-insights"] + argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            try:
                _insights.main()
            except SystemExit:
                pass
        return uploaded_summaries

    def test_current_month_payload_contains_window_months(self):
        """Default mode: uploaded summary has context.window_months = 3."""
        uploaded = self._run_console(
            argv=["--no-open", "--console", "--window=3"],
            summaries=[_make_summary(sessions=5)],
            upload_returns=["/r/1"],
        )
        self.assertEqual(len(uploaded), 1)
        self.assertEqual(uploaded[0]["context"]["window_months"], 3)

    def test_current_month_default_window_months_in_payload(self):
        """When --window is absent, payload carries context.window_months = default."""
        uploaded = self._run_console(
            argv=["--no-open", "--console"],
            summaries=[_make_summary(sessions=5)],
            upload_returns=["/r/1"],
        )
        self.assertEqual(len(uploaded), 1)
        self.assertEqual(uploaded[0]["context"]["window_months"], _DEFAULT_WINDOW_MONTHS)

    def test_backfill_payload_contains_window_months(self):
        """--backfill mode: every uploaded summary has context.window_months."""
        summaries = [_make_summary(sessions=i + 1) for i in range(3)]
        uploaded = self._run_console(
            argv=["--backfill=3", "--no-open", "--console", "--window=2"],
            summaries=summaries,
            upload_returns=["/r/1", "/r/2", "/r/3"],
            tokens=["t1", "t2", "t3"],
        )
        self.assertEqual(len(uploaded), 3)
        for s in uploaded:
            self.assertEqual(s["context"]["window_months"], 2)

    def test_window_months_threaded_into_month_windows_calls(self):
        """--window=3 with backfill=2 produces windows spanning 3 months each."""
        captured_args = []

        def capture_paxel(paxel_src, args, verbose, **kwargs):
            captured_args.append(list(args))
            return _make_summary(sessions=1)

        with (
            patch.object(_insights, "_capture_cli_token", return_value=(["t1", "t2"], [])),
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_mirdash, "_run_paxel", side_effect=capture_paxel),
            patch.object(_mirdash, "_upload_summary", return_value="/r/1"),
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_insights.sys, "argv",
                         ["xl-ai-insights", "--backfill=2", "--no-open", "--console", "--window=3"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            _insights.main()

        self.assertEqual(len(captured_args), 2)
        for call_args in captured_args:
            since_args = [a for a in call_args if a.startswith("--since=")]
            until_args = [a for a in call_args if a.startswith("--until=")]
            self.assertEqual(len(since_args), 1)
            self.assertEqual(len(until_args), 1)


# ---------------------------------------------------------------------------
# Auto mode (multi-month sweep): window_months stamped on every payload
# ---------------------------------------------------------------------------


class TestWindowMonthsAutoSweepPayload(unittest.TestCase):
    """In auto mode with empty server-state (full 12-month sweep), every uploaded
    summary must carry context.window_months — replaces the removed fallback path."""

    def _run_auto_sweep(self, window_arg):
        uploaded_summaries = []

        def capture_upload(mirdash_base, token, summary):
            uploaded_summaries.append(summary)
            return "/r/x"

        # Empty server-state → months_to_upload returns 12 windows; make 3 of them
        # non-empty so they get uploaded (and stamped), the rest skipped.
        summaries = []
        for i in range(12):
            sessions = 5 if i in (2, 5, 9) else 0
            summaries.append({
                "context": {"total_sessions": sessions, "date_range": ["2026-01-01", "2026-02-01"]},
            })

        argv = ["--no-open", "--console"] + ([window_arg] if window_arg else [])
        with (
            patch.object(_insights, "_capture_cli_token", return_value=([f"t{i}" for i in range(12)], [])),
            patch.object(_insights, "_check_latest_cli_release", return_value=_RELEASE_CURRENT),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_mirdash, "_run_paxel", side_effect=list(summaries)),
            patch.object(_mirdash, "_upload_summary", side_effect=capture_upload),
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_insights.sys, "argv", ["xl-ai-insights"] + argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            try:
                _insights.main()
            except SystemExit:
                pass
        return uploaded_summaries

    def test_auto_sweep_payload_carries_window_months_4(self):
        uploaded = self._run_auto_sweep("--window=4")
        self.assertEqual(len(uploaded), 3)
        for s in uploaded:
            self.assertEqual(s["context"]["window_months"], 4)

    def test_auto_sweep_payload_carries_default_window_months(self):
        uploaded = self._run_auto_sweep(None)
        self.assertEqual(len(uploaded), 3)
        for s in uploaded:
            self.assertEqual(s["context"]["window_months"], _DEFAULT_WINDOW_MONTHS)


if __name__ == "__main__":
    unittest.main()
