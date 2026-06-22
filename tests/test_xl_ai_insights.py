import os
import contextlib
import datetime
import io
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import gnomon.cli.insights as _insights
import gnomon.upload.mirdash as _mirdash
from gnomon.upload.mirdash import (
    _format_summary, _run_paxel, _absolutize_dir_flags,
    _upload_window, _upload_window_web,
)
from gnomon.upload.mirdash import month_windows


def _full_summary():
    return {
        "context": {
            "date_range": ["2026-01-01", "2026-06-01"],
            "sources": ["claude", "codex"],
            "total_sessions": 42,
        },
        "planning_ratio_explore_to_doing": 0.62,
        "errors": {
            "error_recovery_ratio": 0.87,
            "error_rate_per_100_tools": 3.5,
        },
        "iteration_depth": {
            "mean": 4.2,
            "median": 3.0,
            "p90": 11,
            "max": 28,
            "files_over_15x": 2,
        },
        "churn": {
            "git_churn_total": 1840,
            "tool_churn_edit_write": 950,
        },
        "orchestration": {
            "fanout_median": 3.5,
            "delegate_actions": 120,
        },
        "compounding_writes": 17,
        "ecosystem": {
            "skills_distinct": 39,
            "skills_total": 8000,
            "mcp_servers_distinct": 12,
        },
    }


class TestFormatSummaryQuiet(unittest.TestCase):
    def test_quiet_returns_empty_string(self):
        result = _format_summary(_full_summary(), quiet=True)
        self.assertEqual(result, "")

    def test_quiet_false_is_default(self):
        # Calling without quiet should return a non-empty string
        result = _format_summary(_full_summary())
        self.assertNotEqual(result, "")


class TestFormatSummaryContent(unittest.TestCase):
    def setUp(self):
        self.out = _format_summary(_full_summary())

    def test_session_count_present(self):
        self.assertIn("42", self.out)

    def test_date_range_present(self):
        self.assertIn("2026-01-01", self.out)
        self.assertIn("2026-06-01", self.out)

    def test_planning_ratio_as_percent(self):
        # 0.62 → 62%
        self.assertIn("62%", self.out)

    def test_error_recovery_as_percent(self):
        # 0.87 → 87%
        self.assertIn("87%", self.out)

    def test_error_rate_labeled(self):
        self.assertIn("3.5 errors / 100 tools", self.out)

    def test_iteration_depth_mean_and_p90(self):
        self.assertIn("4.2", self.out)
        self.assertIn("p90 11", self.out)

    def test_churn_git(self):
        self.assertIn("1840", self.out)
        self.assertIn("(git)", self.out)

    def test_orchestration_fanout_and_delegate(self):
        self.assertIn("3.5", self.out)
        self.assertIn("120", self.out)

    def test_compounding_writes(self):
        self.assertIn("17", self.out)

    def test_ecosystem_skills_and_mcp(self):
        self.assertIn("39", self.out)
        self.assertIn("12", self.out)

    def test_only_two_percent_signs(self):
        # Exactly the two real ratios render as %; everything else stays labeled
        pct_count = self.out.count("%")
        self.assertEqual(pct_count, 2, f"Expected 2 '%%' occurrences, got {pct_count}:\n{self.out}")


class TestFormatSummaryDefensive(unittest.TestCase):
    def test_empty_dict_does_not_crash(self):
        result = _format_summary({})
        self.assertIsInstance(result, str)

    def test_missing_context_keys(self):
        result = _format_summary({"context": {}})
        self.assertIsInstance(result, str)

    def test_missing_errors_block(self):
        s = _full_summary()
        del s["errors"]
        result = _format_summary(s)
        self.assertNotIn("recovery", result.lower())

    def test_missing_iteration_depth(self):
        s = _full_summary()
        del s["iteration_depth"]
        result = _format_summary(s)
        self.assertNotIn("edits/file", result)

    def test_missing_orchestration(self):
        s = _full_summary()
        del s["orchestration"]
        result = _format_summary(s)
        self.assertNotIn("fanout", result)

    def test_none_values_in_errors(self):
        # Both ratio fields set to None: only error block lines should be suppressed
        s = _full_summary()
        s["errors"] = {"error_recovery_ratio": None, "error_rate_per_100_tools": None}
        result = _format_summary(s)
        self.assertIsInstance(result, str)
        self.assertNotIn("Error recovery", result)
        self.assertNotIn("errors / 100 tools", result)

    def test_partial_ecosystem(self):
        s = _full_summary()
        s["ecosystem"] = {"skills_distinct": 5}
        result = _format_summary(s)
        self.assertIn("5 skills", result)
        self.assertNotIn("MCP", result)


class TestPaxelArtifacts(unittest.TestCase):
    def _write_fake_paxel(self, root):
        path = os.path.join(root, "paxel.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "import json, os\n"
                "for name in ('stats.json', 'report.md', 'narrative_input.md', 'profile.html'):\n"
                "    with open(name, 'w', encoding='utf-8') as out:\n"
                "        out.write(name)\n"
                "with open('summary.json', 'w', encoding='utf-8') as out:\n"
                "    json.dump({'context': {'total_sessions': 1}, 'artifact_dir': os.getcwd()}, out)\n"
            )
        return path

    def test_default_preserves_artifact_directory_and_prints_path(self):
        with tempfile.TemporaryDirectory() as src_dir:
            paxel_src = self._write_fake_paxel(src_dir)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                summary = _run_paxel(
                    paxel_src, ["--summary", "--no-open"], verbose=False
                )

        artifact_dir = summary["artifact_dir"]
        self.addCleanup(lambda: os.path.isdir(artifact_dir) and shutil.rmtree(artifact_dir))
        self.assertTrue(os.path.isdir(artifact_dir))
        self.assertTrue(os.path.isfile(os.path.join(artifact_dir, "summary.json")))
        self.assertTrue(os.path.isfile(os.path.join(artifact_dir, "narrative_input.md")))
        printed_path = buf.getvalue().split("Artifacts kept at:", 1)[1].strip()
        self.assertEqual(os.path.realpath(printed_path), os.path.realpath(artifact_dir))

    def test_quiet_suppresses_default_artifact_path(self):
        with tempfile.TemporaryDirectory() as src_dir:
            paxel_src = self._write_fake_paxel(src_dir)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                summary = _run_paxel(
                    paxel_src, ["--summary", "--no-open"], verbose=False, quiet=True
                )

        artifact_dir = summary["artifact_dir"]
        self.addCleanup(lambda: os.path.isdir(artifact_dir) and shutil.rmtree(artifact_dir))
        self.assertEqual(buf.getvalue(), "")

    def test_output_dir_copies_files_and_prints_destination(self):
        with tempfile.TemporaryDirectory() as src_dir:
            cwd = tempfile.mkdtemp()
            self.addCleanup(lambda: os.path.isdir(cwd) and shutil.rmtree(cwd))
            paxel_src = self._write_fake_paxel(src_dir)
            prev_cwd = os.getcwd()
            os.chdir(cwd)
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    summary = _run_paxel(
                        paxel_src, ["--summary", "--no-open"], verbose=False, output_dir="./exports"
                    )
            finally:
                os.chdir(prev_cwd)

        artifact_dir = summary["artifact_dir"]
        export_dir = os.path.join(cwd, "exports")
        self.addCleanup(lambda: os.path.isdir(artifact_dir) and shutil.rmtree(artifact_dir))
        self.assertTrue(os.path.isdir(export_dir))
        self.assertTrue(os.path.isfile(os.path.join(export_dir, "summary.json")))
        self.assertTrue(os.path.isfile(os.path.join(export_dir, "narrative_input.md")))
        self.assertIn(f"Artifacts copied to: {os.path.realpath(export_dir)}", buf.getvalue())

    def test_output_dir_overwrites_existing_files(self):
        with tempfile.TemporaryDirectory() as src_dir:
            dest = tempfile.mkdtemp()
            self.addCleanup(lambda: os.path.isdir(dest) and shutil.rmtree(dest))
            paxel_src = self._write_fake_paxel(src_dir)
            summary_path = os.path.join(dest, "summary.json")
            with open(summary_path, "w", encoding="utf-8") as fh:
                fh.write("old")
            summary = _run_paxel(
                paxel_src, ["--summary", "--no-open"], verbose=False, output_dir=dest, quiet=True
            )

        artifact_dir = summary["artifact_dir"]
        self.addCleanup(lambda: os.path.isdir(artifact_dir) and shutil.rmtree(artifact_dir))
        with open(summary_path, encoding="utf-8") as fh:
            self.assertIn("artifact_dir", fh.read())


class TestOutputDirArgParsing(unittest.TestCase):
    def test_output_dir_is_consumed_by_wrapper_not_forwarded_to_paxel(self):
        with (
            patch.object(_insights, "_main_web") as mock_main_web,
            patch.object(
                _insights.sys,
                "argv",
                ["xl-ai-insights", "--output-dir=.", "claude", "--no-open"],
            ),
        ):
            _insights.main()

        args = mock_main_web.call_args[0]
        paxel_forward = args[4]
        output_dir = args[8]
        self.assertNotIn("--output-dir=.", paxel_forward)
        self.assertIn("claude", paxel_forward)
        self.assertEqual(output_dir, ".")


class TestOutputDirPropagation(unittest.TestCase):
    def _summary(self, sessions=1, progression_monthly=None):
        summary = {
            "context": {
                "date_range": ["2026-01-01", "2026-02-01"],
                "total_sessions": sessions,
            }
        }
        if progression_monthly is not None:
            summary["progression_monthly"] = progression_monthly
        return summary

    def _run_console(self, *, mode="current", token_count=1, run_paxel_side_effect=None):
        with (
            patch.object(_insights, "_capture_cli_token", return_value=["tok"] * max(token_count, 1)),
            patch.object(_insights, "webbrowser") as mock_wb,
            patch.object(_insights.os.path, "isfile", return_value=True),
            patch.object(_insights, "_run_paxel", side_effect=run_paxel_side_effect) as mock_run,
            patch.object(_insights, "_upload_summary", return_value="/r/1"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            _insights._main_console(
                [], "https://mirdash.example", mode, token_count, [], True, True, False,
                output_dir="./exports",
            )
        return mock_run

    def test_console_current_passes_output_dir_to_run_paxel(self):
        mock_run = self._run_console(run_paxel_side_effect=[self._summary()])
        self.assertEqual(mock_run.call_args.kwargs["output_dir"], "./exports")

    def test_console_fallback_passes_output_dir_to_all_run_paxel_calls(self):
        mock_run = self._run_console(
            run_paxel_side_effect=[
                self._summary(sessions=0),
                self._summary(progression_monthly=[{"month": "2026-01"}]),
                self._summary(),
            ]
        )
        self.assertEqual(mock_run.call_count, 3)
        self.assertTrue(all(c.kwargs["output_dir"] == "./exports" for c in mock_run.call_args_list))

    def test_batch_upload_window_passes_output_dir_to_run_paxel(self):
        with (
            patch.object(_mirdash, "_run_paxel", return_value=self._summary()) as mock_run,
            patch.object(_mirdash, "_upload_summary", return_value="/r/1"),
        ):
            _upload_window(
                "https://mirdash.example", "tok", __file__, [], "2026-01-01", "2026-02-01",
                "2026-01", False, True, output_dir="./exports",
            )
        self.assertEqual(mock_run.call_args.kwargs["output_dir"], "./exports")

    def test_web_upload_window_passes_output_dir_to_run_paxel(self):
        server = MagicMock()
        with (
            patch.object(_mirdash, "_run_paxel", return_value=self._summary()) as mock_run,
            patch.object(_mirdash, "_upload_summary", return_value="/r/1"),
        ):
            _upload_window_web(
                "https://mirdash.example", "tok", __file__, [], "2026-01-01", "2026-02-01",
                "2026-01", False, server, 0, 1, output_dir="./exports",
            )
        self.assertEqual(mock_run.call_args.kwargs["output_dir"], "./exports")


class TestHelpOutput(unittest.TestCase):
    def test_help_prints_usage_and_exits_before_running(self):
        stdout = io.StringIO()
        with (
            patch.object(_insights, "_main_web") as mock_main_web,
            patch.object(_insights, "_main_console") as mock_main_console,
            patch.object(_insights.sys, "argv", ["xl-ai-insights", "--help"]),
            contextlib.redirect_stdout(stdout),
            self.assertRaises(SystemExit) as exc,
        ):
            _insights.main()

        self.assertEqual(exc.exception.code, 0)
        self.assertIn("Usage:", stdout.getvalue())
        self.assertIn("--output-dir=PATH", stdout.getvalue())
        self.assertIn("--force", stdout.getvalue())
        self.assertNotIn("--init", stdout.getvalue())
        self.assertNotIn("--keep-artifacts", stdout.getvalue())
        mock_main_web.assert_not_called()
        mock_main_console.assert_not_called()

    def test_short_help_alias_prints_usage_and_exits(self):
        stdout = io.StringIO()
        with (
            patch.object(_insights, "_main_web") as mock_main_web,
            patch.object(_insights, "_main_console") as mock_main_console,
            patch.object(_insights.sys, "argv", ["xl-ai-insights", "-h"]),
            contextlib.redirect_stdout(stdout),
            self.assertRaises(SystemExit) as exc,
        ):
            _insights.main()

        self.assertEqual(exc.exception.code, 0)
        self.assertIn("--output-dir=PATH", stdout.getvalue())
        self.assertIn("--force", stdout.getvalue())
        self.assertNotIn("--init", stdout.getvalue())
        mock_main_web.assert_not_called()
        mock_main_console.assert_not_called()


class TestMonthWindows(unittest.TestCase):
    """Test month_windows function with window_months parameter."""

    def test_window_months_1_legacy_single_month(self):
        """window_months=1 should produce single-calendar-month windows (legacy behavior)."""
        today = datetime.date(2026, 6, 16)
        windows = month_windows(3, today, window_months=1)

        # Should be 3 months: 2026-04, 2026-05, 2026-06 (oldest first)
        self.assertEqual(len(windows), 3)

        # Check 2026-04 (first/oldest)
        since, until, label = windows[0]
        self.assertEqual(label, "2026-04")
        self.assertEqual(since, "2026-04-01")
        self.assertEqual(until, "2026-05-01")

        # Check 2026-05 (middle)
        since, until, label = windows[1]
        self.assertEqual(label, "2026-05")
        self.assertEqual(since, "2026-05-01")
        self.assertEqual(until, "2026-06-01")

        # Check 2026-06 (last/newest, the current month)
        since, until, label = windows[2]
        self.assertEqual(label, "2026-06")
        self.assertEqual(since, "2026-06-01")
        self.assertEqual(until, "2026-07-01")

    def test_window_months_6_current_month(self):
        """window_months=6 with current month 2026-06 should span 6 months."""
        today = datetime.date(2026, 6, 16)
        windows = month_windows(1, today, window_months=6)

        self.assertEqual(len(windows), 1)
        since, until, label = windows[0]

        # Label should be the anchor (end) month
        self.assertEqual(label, "2026-06")
        # Window should span from 2026-01-01 to 2026-07-01 (6 months: Jan through Jun)
        self.assertEqual(since, "2026-01-01")
        self.assertEqual(until, "2026-07-01")

    def test_window_months_6_with_year_boundary(self):
        """window_months=6 with n=2 should handle year boundary crossing correctly."""
        today = datetime.date(2026, 6, 16)
        windows = month_windows(2, today, window_months=6)

        self.assertEqual(len(windows), 2)

        # First window: anchor 2026-05, spans 6 months (2025-12 through 2026-05)
        since, until, label = windows[0]
        self.assertEqual(label, "2026-05")
        self.assertEqual(since, "2025-12-01")
        self.assertEqual(until, "2026-06-01")

        # Second window: anchor 2026-06, spans 6 months (2026-01 through 2026-06)
        since, until, label = windows[1]
        self.assertEqual(label, "2026-06")
        self.assertEqual(since, "2026-01-01")
        self.assertEqual(until, "2026-07-01")

    def test_window_months_default_is_1(self):
        """Default window_months should be 1 (legacy behavior)."""
        today = datetime.date(2026, 6, 16)
        windows_default = month_windows(2, today)
        windows_explicit = month_windows(2, today, window_months=1)

        self.assertEqual(len(windows_default), len(windows_explicit))
        for d, e in zip(windows_default, windows_explicit):
            self.assertEqual(d, e)

    def test_window_months_label_always_anchor_month(self):
        """Label should always be the anchor (end) month, never the start month."""
        today = datetime.date(2026, 6, 16)
        windows = month_windows(3, today, window_months=4)

        # All labels should be the anchor months (oldest first in order)
        labels = [label for _, _, label in windows]
        self.assertEqual(labels, ["2026-04", "2026-05", "2026-06"])

        # Verify that the first window (anchor 2026-04) starts 3 months before (2026-01)
        since, _, _ = windows[0]
        self.assertEqual(since, "2026-01-01")

    def test_window_months_3_at_year_start(self):
        """window_months=3 with anchor near year start should handle year boundary."""
        today = datetime.date(2026, 2, 1)
        windows = month_windows(2, today, window_months=3)

        self.assertEqual(len(windows), 2)

        # First window: anchor 2026-01, spans 3 months (2025-11 through 2026-01)
        since, until, label = windows[0]
        self.assertEqual(label, "2026-01")
        self.assertEqual(since, "2025-11-01")
        self.assertEqual(until, "2026-02-01")

        # Second window: anchor 2026-02, spans 3 months (2025-12 through 2026-02)
        since, until, label = windows[1]
        self.assertEqual(label, "2026-02")
        self.assertEqual(since, "2025-12-01")
        self.assertEqual(until, "2026-03-01")

    def test_window_months_february_leap_year(self):
        """Verify correct handling of February in a leap year."""
        # 2024 is a leap year
        today = datetime.date(2024, 2, 15)
        windows = month_windows(1, today, window_months=1)

        self.assertEqual(len(windows), 1)
        since, until, label = windows[0]
        self.assertEqual(label, "2024-02")
        self.assertEqual(since, "2024-02-01")
        # February 2024 has 29 days, so until = 2024-03-01
        self.assertEqual(until, "2024-03-01")

    def test_window_months_february_non_leap_year(self):
        """Verify correct handling of February in a non-leap year."""
        today = datetime.date(2025, 2, 15)
        windows = month_windows(1, today, window_months=1)

        self.assertEqual(len(windows), 1)
        since, until, label = windows[0]
        self.assertEqual(label, "2025-02")
        self.assertEqual(since, "2025-02-01")
        # February 2025 has 28 days, so until = 2025-03-01
        self.assertEqual(until, "2025-03-01")

    def test_window_months_single_window_spanning_two_years(self):
        """window_months larger than 12 can span across year boundaries."""
        today = datetime.date(2026, 6, 15)
        windows = month_windows(1, today, window_months=12)

        self.assertEqual(len(windows), 1)
        since, until, label = windows[0]
        self.assertEqual(label, "2026-06")
        # 12 months before June 2026 is July 2025
        self.assertEqual(since, "2025-07-01")
        self.assertEqual(until, "2026-07-01")

    def test_window_months_n_equals_1_with_different_window_sizes(self):
        """n=1 with different window sizes should only return the current month window."""
        today = datetime.date(2026, 6, 16)

        for window_size in [1, 2, 3, 6, 12]:
            windows = month_windows(1, today, window_months=window_size)
            self.assertEqual(len(windows), 1, f"Failed for window_size={window_size}")
            _, _, label = windows[0]
            self.assertEqual(label, "2026-06", f"Failed for window_size={window_size}")


if __name__ == "__main__":
    unittest.main()
