"""Retention offer (honest-aq-series step 1, design decision F): an
interactive-only prompt to set `cleanupPeriodDays` in ~/.claude/settings.json.
Threat-matrix RED cases: non-tty skip, existing-key skip, backup-before-write,
malformed-JSON decline. Never a silent write."""
import json
import os
import tempfile
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
