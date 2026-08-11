"""Retention offer (honest-aq-series step 1, design decision F): an
interactive-only prompt to set `cleanupPeriodDays` in ~/.claude/settings.json.
Threat-matrix RED cases: non-tty skip, existing-key skip, backup-before-write,
malformed-JSON decline. Never a silent write."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from gnomon.cli import insights as _insights
from gnomon.cli.insights import offer_retention_config


RETENTION_SINCE = "2026-06-01"
RETENTION_UNTIL = "2026-06-30"


def _claude_event(session_id, timestamp):
    return {
        "type": "user",
        "sessionId": session_id,
        "timestamp": timestamp,
        "message": {"role": "user", "content": "do the work"},
    }


class TestRetentionOfferSafety(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings_path = os.path.join(self._tmp.name, "settings.json")

    def _write(self, obj):
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)

    def test_non_tty_skips_silently_no_write(self):
        self._write({})
        with mock.patch("sys.stdin.isatty", return_value=False), \
                mock.patch("builtins.input", side_effect=AssertionError("must not prompt")):
            result = offer_retention_config(self.settings_path)
        self.assertEqual(result, {"action": "skipped", "reason": "non-tty"})
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {})

    def test_existing_key_skips_without_prompting(self):
        self._write({"cleanupPeriodDays": 30})
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", side_effect=AssertionError("must not prompt")):
            result = offer_retention_config(self.settings_path)
        self.assertEqual(result, {"action": "skipped", "reason": "already_set"})
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["cleanupPeriodDays"], 30)

    def test_malformed_json_declines_without_writing(self):
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            fh.write("not valid json {{{")
        with mock.patch("sys.stdin.isatty", return_value=True):
            result = offer_retention_config(self.settings_path)
        self.assertEqual(result["action"], "declined")
        self.assertEqual(result["reason"], "malformed")
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "not valid json {{{")

    def test_decline_writes_nothing(self):
        self._write({})
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="n"):
            result = offer_retention_config(self.settings_path)
        self.assertEqual(result, {"action": "declined", "reason": "user"})
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {})

    def test_prompt_explains_default_retention_and_optional_recommendation(self):
        self._write({})
        output = io.StringIO()
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="n"), \
                contextlib.redirect_stdout(output):
            offer_retention_config(self.settings_path)

        self.assertIn(
            "We detected that you use Claude Code as an AI tool.",
            output.getvalue())
        self.assertNotIn("selected range", output.getvalue())
        self.assertNotIn("Claude Code detected.", output.getvalue())
        self.assertIn(
            'Gnomon can optionally add "cleanupPeriodDays": 180 to',
            output.getvalue())
        self.assertIn(
            "~/.claude/settings.json so Claude Code keeps your transcripts for 180 days.",
            output.getvalue())
        self.assertIn(
            "This controls transcript retention only; it does not change Gnomon's scoring window.",
            output.getvalue())
        self.assertIn("Press y to add this setting automatically.", output.getvalue())
        self.assertIn(
            "Press n or Enter to leave your settings unchanged. [y/N]",
            output.getvalue())

    def test_accept_backs_up_before_writing_and_records_undo(self):
        self._write({"otherKey": "kept"})
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="y"), \
                mock.patch("time.time", return_value=1234567890.0):
            result = offer_retention_config(self.settings_path)

        self.assertEqual(result["action"], "accepted")
        self.assertEqual(result["written"], {"cleanupPeriodDays": 180})

        backup_path = self.settings_path + ".gnomon-backup-1234567890"
        self.assertEqual(result["backup_path"], backup_path)
        self.assertTrue(os.path.isfile(backup_path), "backup must exist before the write")
        with open(backup_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"otherKey": "kept"})

        with open(self.settings_path, encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written["otherKey"], "kept")
        self.assertEqual(written["cleanupPeriodDays"], 180)

    def test_accept_on_missing_file_creates_settings_with_backup_none(self):
        with mock.patch("sys.stdin.isatty", return_value=True), \
                mock.patch("builtins.input", return_value="y"):
            result = offer_retention_config(self.settings_path)
        self.assertEqual(result["action"], "accepted")
        self.assertIsNone(result["backup_path"])
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"cleanupPeriodDays": 180})


class TestRetentionOfferWiring(unittest.TestCase):
    """The offer is shown only for eligible Claude history on a real interactive run.

    The source files below are real Claude/Codex event streams so the pre-login gate
    exercises the same source-admission path as local scoring rather than a boolean
    fixture or an executable-presence check.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings_path = os.path.join(self._tmp.name, "settings.json")
        self._source_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._source_tmp.cleanup)

    def _claude_sources(self, events):
        path = os.path.join(self._source_tmp.name, "claude.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for session_id, timestamp in events:
                fh.write(json.dumps(_claude_event(session_id, timestamp)) + "\n")
        return [("claude", path, "claude")]

    def _claude_config_dir(self, events):
        config_dir = os.path.join(self._source_tmp.name, "claude-home")
        projects_dir = os.path.join(config_dir, "projects", "demo")
        os.makedirs(projects_dir)
        path = os.path.join(projects_dir, "session.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for session_id, timestamp in events:
                fh.write(json.dumps(_claude_event(session_id, timestamp)) + "\n")
        return config_dir

    def _current_month_claude_sources(self, count=10):
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z")
        return self._claude_sources([
            (f"current-{index}", timestamp) for index in range(count)
        ])

    def _run_main(self, argv, *, isatty=True, stub_offer=True, answer=None, sources=None,
                  patch_sources=True):
        """Drive `main()` with the freshness check, auth and upload stubbed out.

        Returns (offer_mock_or_None, stdout). `answer=None` makes any prompt an
        outright failure instead of a silent hang.
        """
        if patch_sources and sources is None:
            sources = self._current_month_claude_sources()
        stdout = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                _insights, "_check_latest_cli_release", return_value={"status": "current"}))
            stack.enter_context(mock.patch.object(_insights, "_main_web"))
            stack.enter_context(mock.patch.object(_insights, "_main_console"))
            stack.enter_context(mock.patch.object(
                _insights, "_DEFAULT_SETTINGS_PATH", self.settings_path))
            if patch_sources:
                stack.enter_context(mock.patch(
                    "gnomon.cli.local.discover_sources", return_value=sources))
                stack.enter_context(mock.patch(
                    "gnomon.sources.discovery.discover_sources", return_value=sources))
            stack.enter_context(mock.patch("sys.stdin.isatty", return_value=isatty))
            if answer is None:
                stack.enter_context(mock.patch(
                    "builtins.input", side_effect=AssertionError("must not prompt")))
            else:
                stack.enter_context(mock.patch("builtins.input", return_value=answer))
            offer = None
            if stub_offer:
                offer = stack.enter_context(
                    mock.patch.object(_insights, "offer_retention_config"))
            stack.enter_context(contextlib.redirect_stdout(stdout))
            try:
                _insights.main(argv)
            except SystemExit:
                pass
        return offer, stdout.getvalue()

    def test_interactive_run_offers_the_retention_config(self):
        offer, _ = self._run_main([], isatty=True)
        offer.assert_called_once_with()

    def test_ten_unique_in_window_claude_sessions_offer_the_retention_config(self):
        sources = self._claude_sources([
            (f"session-{index}", "2026-06-15T12:00:00Z") for index in range(10)
        ])
        offer, _ = self._run_main([
            f"--since={RETENTION_SINCE}", f"--until={RETENTION_UNTIL}"
        ], sources=sources)
        offer.assert_called_once_with()

    def test_claude_dir_override_is_used_by_the_preflight(self):
        config_dir = self._claude_config_dir([
            (f"session-{index}", "2026-06-15T12:00:00Z") for index in range(10)
        ])
        from gnomon import config as config_module
        from gnomon.sources import discovery as discovery_module
        previous_discovery_base = discovery_module.BASE
        previous_config_base = config_module.BASE
        self.addCleanup(setattr, discovery_module, "BASE", previous_discovery_base)
        self.addCleanup(setattr, config_module, "BASE", previous_config_base)
        offer, _ = self._run_main([
            "claude", f"--claude-dir={config_dir}",
            f"--since={RETENTION_SINCE}", f"--until={RETENTION_UNTIL}",
        ], patch_sources=False)
        offer.assert_called_once_with()

    def test_nine_unique_sessions_duplicates_and_out_of_window_events_do_not_offer(self):
        events = [
            (f"inside-{index}", "2026-06-15T12:00:00Z") for index in range(9)
        ]
        events.extend([
            ("inside-0", "2026-06-15T12:00:00Z"),
            ("outside-a", "2026-05-31T23:59:59Z"),
            ("outside-b", "2026-05-31T23:59:59Z"),
        ])
        offer, _ = self._run_main([
            f"--since={RETENTION_SINCE}", f"--until={RETENTION_UNTIL}"
        ], sources=self._claude_sources(events))
        offer.assert_not_called()

    def test_no_claude_history_does_not_offer(self):
        offer, _ = self._run_main([], sources=[])
        offer.assert_not_called()

    def test_codex_only_history_does_not_offer(self):
        codex_fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "codex", "session-codex.jsonl")
        offer, _ = self._run_main(
            [f"--since={RETENTION_SINCE}", f"--until={RETENTION_UNTIL}"],
            sources=[("codex", codex_fixture, "codex")],
        )
        offer.assert_not_called()

    def test_include_low_volume_offers_for_any_in_window_claude_activity(self):
        sources = self._claude_sources([
            ("single-session", "2026-06-15T12:00:00Z"),
        ])
        offer, _ = self._run_main([
            f"--since={RETENTION_SINCE}", f"--until={RETENTION_UNTIL}",
            "--include-low-volume",
        ], sources=sources)
        offer.assert_called_once_with()

    def test_include_low_volume_does_not_offer_out_of_window_activity(self):
        sources = self._claude_sources([
            ("old-session", "2026-05-31T23:59:59Z"),
        ])
        offer, _ = self._run_main([
            f"--since={RETENTION_SINCE}", f"--until={RETENTION_UNTIL}",
            "--include-low-volume",
        ], sources=sources)
        offer.assert_not_called()

    def test_default_preflight_uses_the_current_scoring_window(self):
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=90)).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        sources = self._claude_sources([
            (f"old-{index}", old_timestamp) for index in range(10)
        ])
        offer, _ = self._run_main([], sources=sources)
        offer.assert_not_called()

    def test_local_preflight_uses_the_actual_explicit_range(self):
        events = [
            (f"inside-{index}", "2026-06-15T12:00:00Z") for index in range(9)
        ]
        events.extend([
            (f"outside-{index}", "2026-05-15T12:00:00Z") for index in range(10)
        ])
        offer, _ = self._run_main([
            "--local", f"--since={RETENTION_SINCE}",
            f"--until={RETENTION_UNTIL}",
        ], sources=self._claude_sources(events))
        offer.assert_not_called()

    def test_eligible_history_does_not_check_for_the_claude_executable(self):
        with mock.patch("shutil.which", side_effect=AssertionError(
                "retention eligibility must not probe the claude executable")) as which:
            offer, _ = self._run_main([], sources=self._current_month_claude_sources())
        offer.assert_called_once_with()
        which.assert_not_called()

    def test_interactive_console_run_offers_the_retention_config(self):
        offer, _ = self._run_main(["--console"], isatty=True)
        offer.assert_called_once_with()

    def test_dry_run_never_offers(self):
        for argv in (["--dry-run"], ["--dry-run", "--force"],
                     ["--dry-run", "--console"], ["--dry-run", "--backfill=3"]):
            with self.subTest(argv=argv):
                offer, _ = self._run_main(argv, isatty=True)
                offer.assert_not_called()

    def test_non_interactive_run_never_prompts_and_never_writes(self):
        _, out = self._run_main([], isatty=False, stub_offer=False)
        self.assertFalse(os.path.exists(self.settings_path))
        self.assertNotIn("retention", out)

    def test_accepted_offer_writes_the_default_path_and_reports_the_undo(self):
        _, out = self._run_main([], isatty=True, stub_offer=False, answer="y")
        with open(self.settings_path, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"cleanupPeriodDays": 180})
        self.assertIn("We detected that you use Claude Code as an AI tool.", out)
        self.assertNotIn("selected range", out)
        self.assertIn("Set cleanupPeriodDays=180", out)
        self.assertIn('Undo: remove "cleanupPeriodDays"', out)

    def test_local_run_offers_too(self):
        """--local analyses the same transcripts, so it has the same stake in retention.

        It returns before the upload path, so an offer wired only into the web/console
        branches would skip every --local-only user -- the exact truncation this change
        exists to prevent.
        """
        with mock.patch("gnomon.cli.local.main"):
            offer, _ = self._run_main(["--local"], isatty=True)
        offer.assert_called_once_with()

    def test_quiet_suppresses_the_offer(self):
        """--quiet promises only errors and the report URL, and the offer prints a prompt."""
        for argv in ([], ["--local"], ["--console"]):
            with self.subTest(argv=argv):
                with mock.patch("gnomon.cli.local.main"):
                    offer, _ = self._run_main([*argv, "--quiet"], isatty=True)
                offer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
