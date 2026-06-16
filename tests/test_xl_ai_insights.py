import os
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import xl_ai_insights


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
        result = xl_ai_insights._format_summary(_full_summary(), quiet=True)
        self.assertEqual(result, "")

    def test_quiet_false_is_default(self):
        # Calling without quiet should return a non-empty string
        result = xl_ai_insights._format_summary(_full_summary())
        self.assertNotEqual(result, "")


class TestFormatSummaryContent(unittest.TestCase):
    def setUp(self):
        self.out = xl_ai_insights._format_summary(_full_summary())

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
        result = xl_ai_insights._format_summary({})
        self.assertIsInstance(result, str)

    def test_missing_context_keys(self):
        result = xl_ai_insights._format_summary({"context": {}})
        self.assertIsInstance(result, str)

    def test_missing_errors_block(self):
        s = _full_summary()
        del s["errors"]
        result = xl_ai_insights._format_summary(s)
        self.assertNotIn("recovery", result.lower())

    def test_missing_iteration_depth(self):
        s = _full_summary()
        del s["iteration_depth"]
        result = xl_ai_insights._format_summary(s)
        self.assertNotIn("edits/file", result)

    def test_missing_orchestration(self):
        s = _full_summary()
        del s["orchestration"]
        result = xl_ai_insights._format_summary(s)
        self.assertNotIn("fanout", result)

    def test_none_values_in_errors(self):
        # Both ratio fields set to None: only error block lines should be suppressed
        s = _full_summary()
        s["errors"] = {"error_recovery_ratio": None, "error_rate_per_100_tools": None}
        result = xl_ai_insights._format_summary(s)
        self.assertIsInstance(result, str)
        self.assertNotIn("Error recovery", result)
        self.assertNotIn("errors / 100 tools", result)

    def test_partial_ecosystem(self):
        s = _full_summary()
        s["ecosystem"] = {"skills_distinct": 5}
        result = xl_ai_insights._format_summary(s)
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

    def test_default_removes_artifact_directory(self):
        with tempfile.TemporaryDirectory() as src_dir:
            paxel_src = self._write_fake_paxel(src_dir)
            summary = xl_ai_insights._run_paxel(
                paxel_src, ["--summary", "--no-open"], verbose=False, keep_artifacts=False
            )
        self.assertIsNotNone(summary)
        self.assertFalse(os.path.exists(summary["artifact_dir"]))

    def test_keep_artifacts_preserves_artifact_directory_and_prints_path(self):
        with tempfile.TemporaryDirectory() as src_dir:
            paxel_src = self._write_fake_paxel(src_dir)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                summary = xl_ai_insights._run_paxel(
                    paxel_src, ["--summary", "--no-open"], verbose=False, keep_artifacts=True
                )

        artifact_dir = summary["artifact_dir"]
        self.addCleanup(lambda: os.path.isdir(artifact_dir) and shutil.rmtree(artifact_dir))
        self.assertTrue(os.path.isdir(artifact_dir))
        self.assertTrue(os.path.isfile(os.path.join(artifact_dir, "summary.json")))
        self.assertTrue(os.path.isfile(os.path.join(artifact_dir, "narrative_input.md")))
        printed_path = buf.getvalue().split("Artifacts kept at:", 1)[1].strip()
        self.assertEqual(os.path.realpath(printed_path), os.path.realpath(artifact_dir))


class TestKeepArtifactsArgParsing(unittest.TestCase):
    def test_keep_artifacts_is_consumed_by_wrapper_not_forwarded_to_paxel(self):
        with (
            patch.object(xl_ai_insights, "_main_web") as mock_main_web,
            patch.object(
                xl_ai_insights.sys,
                "argv",
                ["xl-ai-insights", "--keep-artifacts", "claude", "--no-open"],
            ),
        ):
            xl_ai_insights.main()

        args = mock_main_web.call_args[0]
        paxel_forward = args[4]
        keep_artifacts = args[8]
        self.assertNotIn("--keep-artifacts", paxel_forward)
        self.assertIn("claude", paxel_forward)
        self.assertTrue(keep_artifacts)


class TestKeepArtifactsPropagation(unittest.TestCase):
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
            patch.object(xl_ai_insights, "_capture_cli_token", return_value=["tok"] * max(token_count, 1)),
            patch.object(xl_ai_insights, "webbrowser") as mock_wb,
            patch.object(xl_ai_insights.os.path, "isfile", return_value=True),
            patch.object(xl_ai_insights, "_run_paxel", side_effect=run_paxel_side_effect) as mock_run,
            patch.object(xl_ai_insights, "_upload_summary", return_value="/r/1"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            mock_wb.open.return_value = True
            xl_ai_insights._main_console(
                [], "https://mirdash.example", mode, token_count, [], True, True, False,
                keep_artifacts=True,
            )
        return mock_run

    def test_console_current_passes_keep_artifacts_to_run_paxel(self):
        mock_run = self._run_console(run_paxel_side_effect=[self._summary()])
        self.assertTrue(mock_run.call_args.kwargs["keep_artifacts"])

    def test_console_fallback_passes_keep_artifacts_to_all_run_paxel_calls(self):
        mock_run = self._run_console(
            run_paxel_side_effect=[
                self._summary(sessions=0),
                self._summary(progression_monthly=[{"month": "2026-01"}]),
                self._summary(),
            ]
        )
        self.assertEqual(mock_run.call_count, 3)
        self.assertTrue(all(c.kwargs["keep_artifacts"] for c in mock_run.call_args_list))

    def test_batch_upload_window_passes_keep_artifacts_to_run_paxel(self):
        with (
            patch.object(xl_ai_insights, "_run_paxel", return_value=self._summary()) as mock_run,
            patch.object(xl_ai_insights, "_upload_summary", return_value="/r/1"),
        ):
            xl_ai_insights._upload_window(
                "https://mirdash.example", "tok", __file__, [], "2026-01-01", "2026-02-01",
                "2026-01", False, True, keep_artifacts=True,
            )
        self.assertTrue(mock_run.call_args.kwargs["keep_artifacts"])

    def test_web_upload_window_passes_keep_artifacts_to_run_paxel(self):
        server = MagicMock()
        with (
            patch.object(xl_ai_insights, "_run_paxel", return_value=self._summary()) as mock_run,
            patch.object(xl_ai_insights, "_upload_summary", return_value="/r/1"),
        ):
            xl_ai_insights._upload_window_web(
                "https://mirdash.example", "tok", __file__, [], "2026-01-01", "2026-02-01",
                "2026-01", False, server, 0, 1, keep_artifacts=True,
            )
        self.assertTrue(mock_run.call_args.kwargs["keep_artifacts"])


if __name__ == "__main__":
    unittest.main()
