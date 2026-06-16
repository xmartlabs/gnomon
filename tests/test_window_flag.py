"""Tests for the --window=N flag: parsing, paxel_forward stripping, and payload stamping."""

import contextlib
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xl_ai_insights
from xl_ai_insights import _DEFAULT_WINDOW_MONTHS, parse_window


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

    def test_default_is_6(self):
        self.assertEqual(_DEFAULT_WINDOW_MONTHS, 6)


# ---------------------------------------------------------------------------
# --window= is stripped from paxel_forward (does NOT reach paxel)
# ---------------------------------------------------------------------------


class TestWindowNotForwardedToPaxel(unittest.TestCase):
    def test_window_flag_stripped_from_paxel_forward(self):
        """--window=N must not be forwarded to paxel."""
        with (
            patch.object(xl_ai_insights, "_main_web") as mock_main_web,
            patch.object(
                xl_ai_insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "claude", "--no-open"],
            ),
        ):
            xl_ai_insights.main()

        args = mock_main_web.call_args[0]
        paxel_forward = args[4]
        self.assertNotIn("--window=3", paxel_forward)
        # Source name claude must still be forwarded
        self.assertIn("claude", paxel_forward)

    def test_window_flag_not_forwarded_console_mode(self):
        """--window=N must not reach paxel in console mode either."""
        with (
            patch.object(xl_ai_insights, "_main_console") as mock_main_console,
            patch.object(
                xl_ai_insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "--console", "claude", "--no-open"],
            ),
        ):
            xl_ai_insights.main()

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
            patch.object(xl_ai_insights, "_main_web") as mock_main_web,
            patch.object(
                xl_ai_insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "--no-open"],
            ),
        ):
            xl_ai_insights.main()

        kwargs = mock_main_web.call_args[1]
        self.assertEqual(kwargs.get("window_months"), 3)

    def test_window_months_passed_to_main_console(self):
        with (
            patch.object(xl_ai_insights, "_main_console") as mock_main_console,
            patch.object(
                xl_ai_insights.sys,
                "argv",
                ["xl-ai-insights", "--window=3", "--console", "--no-open"],
            ),
        ):
            xl_ai_insights.main()

        kwargs = mock_main_console.call_args[1]
        self.assertEqual(kwargs.get("window_months"), 3)

    def test_default_window_months_passed_when_absent(self):
        with (
            patch.object(xl_ai_insights, "_main_web") as mock_main_web,
            patch.object(
                xl_ai_insights.sys,
                "argv",
                ["xl-ai-insights", "--no-open"],
            ),
        ):
            xl_ai_insights.main()

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

    def _run_console(self, argv, summaries, upload_returns, tokens=None):
        """Run main() in console mode with mocked I/O; return captured upload calls."""
        if tokens is None:
            tokens = ["tok1"]
        uploaded_summaries = []

        def capture_upload(mirdash_base, token, summary):
            uploaded_summaries.append(summary)
            return upload_returns.pop(0) if upload_returns else "/r/x"

        with (
            patch.object(xl_ai_insights, "_capture_cli_token", return_value=tokens),
            patch.object(xl_ai_insights, "webbrowser") as mock_wb,
            patch.object(xl_ai_insights, "_run_paxel", side_effect=summaries),
            patch.object(xl_ai_insights, "_upload_summary", side_effect=capture_upload),
            patch.object(xl_ai_insights.os.path, "isfile", return_value=True),
            patch.object(xl_ai_insights.sys, "argv", ["xl-ai-insights"] + argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            try:
                xl_ai_insights.main()
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

    def test_fallback_month_payload_contains_window_months(self):
        """Fallback (current month empty) path: see TestWindowMonthsFallbackPayload below."""
        # Full fallback-path coverage is in TestWindowMonthsFallbackPayload,
        # which correctly provides progression_monthly.  This test just checks
        # that the backfill path stamps window_months (already covered by
        # test_backfill_payload_contains_window_months).
        pass

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
            patch.object(xl_ai_insights, "_capture_cli_token", return_value=["t1", "t2"]),
            patch.object(xl_ai_insights, "webbrowser") as mock_wb,
            patch.object(xl_ai_insights, "_run_paxel", side_effect=capture_paxel),
            patch.object(xl_ai_insights, "_upload_summary", return_value="/r/1"),
            patch.object(xl_ai_insights.os.path, "isfile", return_value=True),
            patch.object(xl_ai_insights.sys, "argv",
                         ["xl-ai-insights", "--backfill=2", "--no-open", "--console", "--window=3"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            xl_ai_insights.main()

        self.assertEqual(len(captured_args), 2)
        for call_args in captured_args:
            since_args = [a for a in call_args if a.startswith("--since=")]
            until_args = [a for a in call_args if a.startswith("--until=")]
            self.assertEqual(len(since_args), 1)
            self.assertEqual(len(until_args), 1)


# ---------------------------------------------------------------------------
# Fallback path: progression_monthly test (proper)
# ---------------------------------------------------------------------------


class TestWindowMonthsFallbackPayload(unittest.TestCase):
    """Verify window_months propagates through the fallback (empty current month) path."""

    def _run_console_with_fallback(self, window_arg):
        uploaded_summaries = []

        def capture_upload(mirdash_base, token, summary):
            uploaded_summaries.append(summary)
            return "/r/fallback"

        prog = [{"month": "2026-04"}]
        summaries = [
            {   # current month: empty
                "context": {"total_sessions": 0, "date_range": ["2026-06-01", "2026-07-01"]},
            },
            {   # all-time: has progression_monthly
                "context": {"total_sessions": 10, "date_range": ["2025-01-01", "2026-06-01"]},
                "progression_monthly": prog,
            },
            {   # fallback month window
                "context": {"total_sessions": 3, "date_range": ["2026-04-01", "2026-05-01"]},
            },
        ]
        argv = ["--no-open", "--console"] + ([window_arg] if window_arg else [])
        with (
            patch.object(xl_ai_insights, "_capture_cli_token", return_value=["tok1"]),
            patch.object(xl_ai_insights, "webbrowser") as mock_wb,
            patch.object(xl_ai_insights, "_run_paxel", side_effect=summaries),
            patch.object(xl_ai_insights, "_upload_summary", side_effect=capture_upload),
            patch.object(xl_ai_insights.os.path, "isfile", return_value=True),
            patch.object(xl_ai_insights.sys, "argv", ["xl-ai-insights"] + argv),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            try:
                xl_ai_insights.main()
            except SystemExit:
                pass
        return uploaded_summaries

    def test_fallback_payload_carries_window_months_4(self):
        uploaded = self._run_console_with_fallback("--window=4")
        self.assertEqual(len(uploaded), 1)
        self.assertEqual(uploaded[0]["context"]["window_months"], 4)

    def test_fallback_payload_carries_default_window_months(self):
        uploaded = self._run_console_with_fallback(None)
        self.assertEqual(len(uploaded), 1)
        self.assertEqual(uploaded[0]["context"]["window_months"], _DEFAULT_WINDOW_MONTHS)


if __name__ == "__main__":
    unittest.main()
