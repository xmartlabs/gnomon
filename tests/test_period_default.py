import contextlib
import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from gnomon.cli import local
from gnomon.cli.period import Period, resolve_period
from tests._clock import pinned_now
from tests._fixture_months import claude_corpus_across_months, codex_corpus_across_months


class TestCurrentMonthDefault(unittest.TestCase):
    def test_default_resolves_to_pinned_calendar_month(self):
        with pinned_now("2026-06-30"):
            period = resolve_period([])
        self.assertEqual(period, Period(
            "current_month", period.since, None, "2026-06",
            "Jun 2026 · in progress · 30 days", 30, 30))

    def test_fixture_helpers_make_month_specific_sessions(self):
        root = tempfile.mkdtemp(prefix="gnomon-months-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        claude = claude_corpus_across_months(root, ["2026-05", "2026-06"])
        codex = codex_corpus_across_months(root, ["2026-05", "2026-06"])

        self.assertEqual(sorted(os.listdir(claude)), ["2026-05", "2026-06"])
        self.assertEqual(sorted(os.listdir(codex)), ["2026-05", "2026-06"])
        with open(os.path.join(claude, "2026-06", "proj-demo", "session-claude.jsonl"),
                  encoding="utf-8") as handle:
            self.assertIn("202606", handle.read())
        with open(os.path.join(codex, "2026-06", "session-codex.jsonl"),
                  encoding="utf-8") as handle:
            self.assertIn("202606", handle.read())

    def test_local_default_uses_only_current_month(self):
        root = tempfile.mkdtemp(prefix="gnomon-months-")
        out = tempfile.mkdtemp(prefix="gnomon-period-out-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        claude = claude_corpus_across_months(root, ["2026-05", "2026-06"])

        with pinned_now("2026-06-30"), \
                mock.patch.object(local, "_open_in_browser"), \
                mock.patch.object(local, "OUT_DIR", out):
            local.main([
                "claude", "--include-low-volume", "--no-open",
                "--claude-dir=" + claude,
            ], output_dir=out)

        with open(os.path.join(out, "stats.json"), encoding="utf-8") as handle:
            stats = json.load(handle)
        self.assertEqual(stats["volume"]["total_sessions"], 1)
        self.assertEqual(stats["corpus"]["date_range"][0][:7], "2026-06")
        self.assertEqual(stats["corpus"]["date_range"][1][:7], "2026-06")

    def test_cursor_only_default_completes_and_records_legacy_count(self):
        root = tempfile.mkdtemp(prefix="gnomon-cursor-months-")
        current_out = tempfile.mkdtemp(prefix="gnomon-cursor-current-")
        legacy_out = tempfile.mkdtemp(prefix="gnomon-cursor-legacy-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, current_out, ignore_errors=True)
        self.addCleanup(shutil.rmtree, legacy_out, ignore_errors=True)

        cursor_root = os.path.join(root, "projects")
        shutil.copytree(os.path.join(os.path.dirname(__file__), "fixtures", "cursor", "projects"),
                        cursor_root)
        may = datetime.datetime(2026, 5, 15, tzinfo=datetime.timezone.utc).timestamp()
        june = datetime.datetime(2026, 6, 15, tzinfo=datetime.timezone.utc).timestamp()
        for dirpath, _dirnames, filenames in os.walk(cursor_root):
            for filename in filenames:
                if not filename.endswith(".jsonl"):
                    continue
                path = os.path.join(dirpath, filename)
                stamp = june if "jsonl-only" not in path else may
                os.utime(path, (stamp, stamp))

        missing_db = os.path.join(root, "missing.vscdb")

        def run(output_dir, default_period):
            with pinned_now("2026-06-30"), \
                    mock.patch.object(local, "_open_in_browser"), \
                    mock.patch("gnomon.sources.discovery.CURSOR_DB", missing_db), \
                    mock.patch("gnomon.cli.period.DEFAULT_PERIOD", default_period), \
                    contextlib.redirect_stdout(io.StringIO()):
                local.main([
                    "cursor", "--include-low-volume", "--no-open",
                    "--cursor-dir=" + cursor_root,
                ], output_dir=output_dir)
            with open(os.path.join(output_dir, "stats.json"), encoding="utf-8") as handle:
                return json.load(handle)

        current = run(current_out, "current_month")
        legacy = run(legacy_out, "all_history")
        self.assertEqual(current["volume"]["total_sessions"], 1)
        self.assertEqual(legacy["volume"]["total_sessions"], 2)


if __name__ == "__main__":
    unittest.main()
