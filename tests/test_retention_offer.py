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
from unittest import mock

from gnomon.cli import insights as _insights
from gnomon.cli.insights import offer_retention_config


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
    """The offer is worthless unless `main()` actually reaches it. An interactive
    real run offers it exactly once (with no path override, i.e. the user's real
    settings file); `--dry-run` promises zero side effects so it never offers;
    non-interactive runs never prompt and never write."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings_path = os.path.join(self._tmp.name, "settings.json")

    def _run_main(self, argv, *, isatty=True, stub_offer=True, answer=None):
        """Drive `main()` with the freshness check, auth and upload stubbed out.

        Returns (offer_mock_or_None, stdout). `answer=None` makes any prompt an
        outright failure instead of a silent hang.
        """
        stdout = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                _insights, "_check_latest_cli_release", return_value={"status": "current"}))
            stack.enter_context(mock.patch.object(_insights, "_main_web"))
            stack.enter_context(mock.patch.object(_insights, "_main_console"))
            stack.enter_context(mock.patch.object(
                _insights, "_DEFAULT_SETTINGS_PATH", self.settings_path))
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
