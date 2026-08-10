"""End-to-end wiring of the coverage-index capability through
gnomon.cli.local._accumulate + main(): stats["coverage"] must be a per-month
dict built from the real accumulated session sets (NOT the mtime estimate --
that's probe_month's cheap pre-scoring approximation only)."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paxel  # noqa: E402
from gnomon.cli.local import _accumulate  # noqa: E402


def _claude_turn(sid, ts, cwd="/repo"):
    return {
        "type": "user", "sessionId": sid, "timestamp": ts, "cwd": cwd,
        "message": {"role": "user", "content": "hello"},
    }


class TestAccumulateExposesMonthSessions(unittest.TestCase):
    def test_narrative_carries_month_sessions_for_composition(self):
        tmp = tempfile.mkdtemp(prefix="paxel-cov-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        fp = os.path.join(tmp, "s.jsonl")
        with open(fp, "w") as fh:
            fh.write('{"type":"user","sessionId":"s1",'
                     '"timestamp":"2026-06-15T12:00:00Z","cwd":"/repo",'
                     '"message":{"role":"user","content":"hi"}}\n')
        stats, narrative = _accumulate(
            [("claude", fp, "claude")], None, None, {}, False, verbose=False)
        self.assertIn("month_sessions", narrative)
        self.assertEqual(narrative["month_sessions"].get("2026-06"), {"s1"})


class TestMainComposesCoverage(unittest.TestCase):
    def test_summary_json_has_coverage_and_context_observed_range(self):
        import json
        tmp = tempfile.mkdtemp(prefix="paxel-cov-main-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        claude_dir = os.path.join(tmp, "claude", "proj")
        os.makedirs(claude_dir)
        with open(os.path.join(claude_dir, "s.jsonl"), "w") as fh:
            fh.write('{"type":"user","sessionId":"s1",'
                     '"timestamp":"2026-06-15T12:00:00Z","cwd":"/repo",'
                     '"message":{"role":"user","content":"hi"}}\n')
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        empty = tempfile.mkdtemp(prefix="paxel-cov-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        src_dirs = dict(
            BASE=os.path.join(tmp, "claude"),
            CODEX_DIR=os.path.join(empty, "codex"),
            GEMINI_DIR=os.path.join(empty, "gemini"),
            ANTIGRAVITY_CLI_DIR=os.path.join(empty, "antigravity"),
            ANTIGRAVITY_IDE_DIR=os.path.join(empty, "antigravity-ide"),
            ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            PI_DIR=os.path.join(empty, "pi"),
            OPENCODE_DIR=os.path.join(empty, "opencode"),
            CURSOR_DIR=os.path.join(empty, "cursor", "projects"),
            CURSOR_DB=os.path.join(empty, "cursor", "state.vscdb"),
        )
        # No history.jsonl on this "machine" -> every month must read "unknown".
        with mock.patch.multiple(paxel, OUT_DIR=out, **src_dirs), \
                mock.patch("gnomon.coverage.HISTORY_PATH",
                            os.path.join(tmp, "no-history.jsonl")), \
                mock.patch.object(sys, "argv", ["paxel.py", "--summary",
                                                  "--include-low-volume", "--no-open"]), \
                redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        self.assertIn("coverage", summary)
        self.assertIn("2026-06", summary["coverage"])
        self.assertEqual(summary["coverage"]["2026-06"]["flag"], "unknown")
        self.assertEqual(summary["coverage"]["2026-06"]["available_transcripts"], 1)
        self.assertIn("observed_range", summary["context"])
        self.assertIsNotNone(summary["context"]["observed_range"][0])


if __name__ == "__main__":
    unittest.main()
