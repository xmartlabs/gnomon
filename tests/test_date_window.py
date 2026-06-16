"""Tests for --since/--until date-window filtering in paxel.main().

Strategy: a dedicated 3-month fixture (jan/feb/mar 2025) lives under
tests/fixtures/window-test/claude/.  We run paxel.main() with various
--since/--until combos and verify event counts, date_range, and no-window
identity (output identical to an unfiltered run on the same fixture).
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures", "window-test")

sys.path.insert(0, ROOT)
import paxel  # noqa: E402

# Only Claude fixtures in the window-test dir; disable every other source so
# codex/gemini/etc. are not looked up in their real locations.
_EMPTY = tempfile.mkdtemp(prefix="paxel-empty-")
WIN_SRC_DIRS = dict(
    BASE=os.path.join(FIX, "claude"),
    CODEX_DIR=os.path.join(_EMPTY, "codex"),
    GEMINI_DIR=os.path.join(_EMPTY, "gemini"),
    PI_DIR=os.path.join(_EMPTY, "pi"),
    OPENCODE_DIR=os.path.join(_EMPTY, "opencode"),
    CURSOR_DIR=os.path.join(_EMPTY, "cursor", "projects"),
    CURSOR_DB=os.path.join(_EMPTY, "cursor", "state.vscdb"),
)


def _run(testcase, args):
    """Run paxel.main() over the 3-month window fixture; return (stdout, stats_dict)."""
    out = tempfile.mkdtemp(prefix="paxel-win-test-")
    testcase.addCleanup(shutil.rmtree, out, ignore_errors=True)
    argv = ["paxel.py"] + list(args) + ["--no-open"]
    buf = io.StringIO()
    with mock.patch.multiple(paxel, OUT_DIR=out, **WIN_SRC_DIRS), \
            mock.patch.object(sys, "argv", argv), \
            io.StringIO() as _sink, \
            __import__("contextlib").redirect_stdout(buf):
        paxel.main()
    with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
        stats = json.load(fh)
    return buf.getvalue(), stats


class TestWindowParsing(unittest.TestCase):
    """Unit-level: parse_ts + flag parsing produce the right tz-aware datetimes."""

    def test_parse_ts_is_utc_aware(self):
        dt = paxel.parse_ts("2025-02-10T11:00:00.000Z")
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo, "parse_ts must return a tz-aware datetime")

    def test_bad_since_ignored_with_warning(self):
        """A malformed --since value prints a warning and is silently dropped."""
        out, stats = _run(self, ["--since=not-a-date"])
        self.assertIn("warning", out.lower())
        self.assertIn("--since", out)
        # no window active → all 3 months present
        dr = stats["corpus"]["date_range"]
        self.assertIn("2025-01", dr[0])

    def test_bad_until_ignored_with_warning(self):
        out, stats = _run(self, ["--until=2025/02/01"])
        self.assertIn("warning", out.lower())
        self.assertIn("--until", out)

    def test_good_since_no_warning(self):
        out, _stats = _run(self, ["--since=2025-02-01"])
        self.assertNotIn("--since value", out)

    def test_good_until_no_warning(self):
        out, _stats = _run(self, ["--until=2025-03-01"])
        self.assertNotIn("--until value", out)


class TestWindowFiltering(unittest.TestCase):
    """End-to-end: events outside the window are excluded from stats."""

    def test_middle_month_window_excludes_others(self):
        """--since=2025-02-01 --until=2025-03-01 → only February events count."""
        _, stats = _run(self, ["--since=2025-02-01", "--until=2025-03-01"])
        corpus = stats["corpus"]
        # date_range must reflect the *requested* bounds, not the actual data min/max
        dr = corpus["date_range"]
        self.assertIn("2025-02-01", dr[0])
        self.assertIn("2025-03-01", dr[1])
        # all prompts should belong to February sessions only
        vol = stats["volume"]
        # fixture has 2 genuine user prompts in feb
        self.assertEqual(vol["total_prompts"], 2,
                         f"expected 2 feb prompts, got {vol['total_prompts']}")

    def test_no_window_counts_all_months(self):
        """Without flags, all 6 genuine user prompts (2 each × 3 months) are counted."""
        _, stats = _run(self, [])
        vol = stats["volume"]
        self.assertEqual(vol["total_prompts"], 6,
                         f"expected 6 total prompts, got {vol['total_prompts']}")

    def test_since_only_excludes_before(self):
        """--since=2025-02-01 excludes January; Feb + Mar are kept."""
        _, stats = _run(self, ["--since=2025-02-01"])
        vol = stats["volume"]
        self.assertEqual(vol["total_prompts"], 4,
                         f"expected 4 prompts (feb+mar), got {vol['total_prompts']}")

    def test_until_only_excludes_after(self):
        """--until=2025-02-01 excludes February and beyond; only January kept."""
        _, stats = _run(self, ["--until=2025-02-01"])
        vol = stats["volume"]
        self.assertEqual(vol["total_prompts"], 2,
                         f"expected 2 prompts (jan only), got {vol['total_prompts']}")

    def test_no_window_date_range_is_actual_minmax(self):
        """Without a window, date_range reflects actual corpus min and max."""
        _, stats = _run(self, [])
        dr = stats["corpus"]["date_range"]
        # Jan 15 is the first event; Mar 15 is the last assistant event
        self.assertIn("2025-01", dr[0])
        self.assertIn("2025-03", dr[1])

    def test_windowed_date_range_uses_requested_bounds(self):
        """Windowed date_range = [since, until] regardless of actual event spread."""
        _, stats = _run(self, ["--since=2025-02-01", "--until=2025-03-01"])
        dr = stats["corpus"]["date_range"]
        self.assertIn("2025-02-01", dr[0])
        self.assertIn("2025-03-01", dr[1])

    def test_since_only_date_range_start(self):
        """With only --since, date_range[0] is the requested since bound."""
        _, stats = _run(self, ["--since=2025-02-01"])
        dr = stats["corpus"]["date_range"]
        self.assertIn("2025-02-01", dr[0])

    def test_until_only_date_range_end(self):
        """With only --until, date_range[1] is the requested until bound."""
        _, stats = _run(self, ["--until=2025-03-01"])
        dr = stats["corpus"]["date_range"]
        self.assertIn("2025-03-01", dr[1])


class TestWindowBoundary(unittest.TestCase):
    """Boundary correctness: since is inclusive, until is exclusive."""

    def test_since_is_inclusive(self):
        """An event exactly at 2025-02-10T11:00:00Z (since=2025-02-01) is included."""
        _, stats = _run(self, ["--since=2025-02-01", "--until=2025-03-01"])
        # Feb 10 events must be counted — verified via prompt count
        self.assertEqual(stats["volume"]["total_prompts"], 2)

    def test_until_is_exclusive(self):
        """--until=2025-03-01 excludes all March events (first march event is 2025-03-05)."""
        _, stats = _run(self, ["--since=2025-01-01", "--until=2025-03-01"])
        # Jan (2) + Feb (2) = 4; Mar excluded
        self.assertEqual(stats["volume"]["total_prompts"], 4,
                         "March events should be excluded when until=2025-03-01")

    def test_single_day_window_includes_that_day(self):
        """--until is inclusive: since=2025-03-05 until=2025-03-05 includes Mar 5."""
        _, stats = _run(self, ["--since=2025-03-05", "--until=2025-03-05"])
        # Mar 5 has 1 genuine user prompt — inclusive end means the day is kept
        self.assertEqual(stats["volume"]["total_prompts"], 1)

    def test_single_day_via_next_day_until(self):
        """since=2025-03-05 until=2025-03-06 also includes Mar 5 (and not Mar 6)."""
        _, stats = _run(self, ["--since=2025-03-05", "--until=2025-03-06"])
        # Mar 5 has 1 genuine user prompt
        self.assertEqual(stats["volume"]["total_prompts"], 1)


class TestWindowedGitChurnBounds(unittest.TestCase):
    """git_churn must be queried with the REQUESTED window bounds when a window is
    active — not the min/max of transcript events that happened to fall inside it.
    Otherwise a month with sparse transcript days undercounts commits made on the
    other days of that same month (it would only scan from the first/last event).
    """

    def _capture_churn_args(self, args):
        """Run paxel.main() with git_churn mocked; return (since_iso, until_iso)."""
        captured = {}

        def fake_git_churn(cwds, since_iso, until_iso):
            captured["since"] = since_iso
            captured["until"] = until_iso
            return {"repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
                    "deletions": 0, "churn": 0, "commits": 0, "per_repo": []}

        out = tempfile.mkdtemp(prefix="paxel-churn-")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        argv = ["paxel.py"] + list(args) + ["--no-open"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **WIN_SRC_DIRS), \
                mock.patch.object(paxel, "git_churn", fake_git_churn), \
                mock.patch.object(sys, "argv", argv), \
                __import__("contextlib").redirect_stdout(io.StringIO()):
            paxel.main()
        return captured["since"], captured["until"]

    def test_windowed_churn_uses_requested_bounds(self):
        """With --since/--until, churn is scanned over the full requested window —
        even though the earliest Feb event is Feb 10, the since bound must be Feb 1.
        --until is inclusive-end, so --until=2025-03-01 internally becomes 2025-03-02
        (exclusive next-midnight), and git churn gets 2025-03-02 to include March 1."""
        since, until = self._capture_churn_args(["--since=2025-02-01", "--until=2025-03-01"])
        self.assertTrue(since.startswith("2025-02-01"),
                        f"churn since should be the requested window start, got {since!r}")
        self.assertTrue(until.startswith("2025-03-02"),
                        f"churn until should be the day after the inclusive --until, got {until!r}")
        self.assertEqual(since, "2025-02-01")
        self.assertEqual(until, "2025-03-02")

    def test_no_window_churn_uses_data_minmax(self):
        """Without a window, churn bounds remain the actual corpus min/max (unchanged)."""
        since, until = self._capture_churn_args([])
        self.assertTrue(since.startswith("2025-01"),
                        f"churn since should be corpus min, got {since!r}")
        self.assertTrue(until.startswith("2025-03"),
                        f"churn until should be corpus max, got {until!r}")

    def test_since_only_churn_until_is_data_max(self):
        """With only --since, the until bound falls back to the actual corpus max."""
        since, until = self._capture_churn_args(["--since=2025-02-01"])
        self.assertTrue(since.startswith("2025-02-01"),
                        f"churn since should be requested start, got {since!r}")
        self.assertTrue(until.startswith("2025-03"),
                        f"churn until should fall back to corpus max, got {until!r}")


class TestNoWindowIdentity(unittest.TestCase):
    """Without flags, output must be identical to a baseline no-window run."""

    def _run_stats(self, args):
        out = tempfile.mkdtemp(prefix="paxel-ident-")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        argv = ["paxel.py"] + list(args) + ["--no-open"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **WIN_SRC_DIRS), \
                mock.patch.object(sys, "argv", argv), \
                __import__("contextlib").redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_no_flags_prompt_count_identical(self):
        s1 = self._run_stats([])
        s2 = self._run_stats([])
        self.assertEqual(s1["volume"]["total_prompts"], s2["volume"]["total_prompts"])

    def test_no_flags_tool_calls_identical(self):
        s1 = self._run_stats([])
        s2 = self._run_stats([])
        self.assertEqual(s1["volume"]["tool_calls_total"], s2["volume"]["tool_calls_total"])

    def test_no_flags_date_range_identical(self):
        s1 = self._run_stats([])
        s2 = self._run_stats([])
        self.assertEqual(s1["corpus"]["date_range"], s2["corpus"]["date_range"])


class TestWindowedCursorJsonlNotDropped(unittest.TestCase):
    """A JSONL-only Cursor session carries no per-event timestamps; paxel stamps them
    with the file mtime. A date window must keep the WHOLE session (all prompts AND tool
    calls), not just the first event — previously the window gate dropped every
    timestampless event past the first, so monthly/backfill runs undercounted Cursor.
    """

    def _run_cursor_stats(self, args, mtime):
        # Isolated cursor tree with ONLY the JSONL-only session, mtimed into Feb 2025.
        cur = tempfile.mkdtemp(prefix="paxel-cursor-")
        self.addCleanup(shutil.rmtree, cur, ignore_errors=True)
        sess_dir = os.path.join(cur, "projects", "Users-demo-cursorproj",
                                "agent-transcripts", "jsonl-only-session")
        os.makedirs(sess_dir)
        src = os.path.join(HERE, "fixtures", "cursor", "projects", "Users-demo-cursorproj",
                           "agent-transcripts", "jsonl-only-session", "jsonl-only-session.jsonl")
        dst = os.path.join(sess_dir, "jsonl-only-session.jsonl")
        shutil.copyfile(src, dst)
        os.utime(dst, (mtime, mtime))

        empty = tempfile.mkdtemp(prefix="paxel-empty-cur-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        src_dirs = dict(
            BASE=os.path.join(empty, "claude"),
            CODEX_DIR=os.path.join(empty, "codex"),
            GEMINI_DIR=os.path.join(empty, "gemini"),
            PI_DIR=os.path.join(empty, "pi"),
            OPENCODE_DIR=os.path.join(empty, "opencode"),
            CURSOR_DIR=os.path.join(cur, "projects"),
            CURSOR_DB=os.path.join(empty, "nonexistent.vscdb"),
        )
        out = tempfile.mkdtemp(prefix="paxel-curout-")
        self.addCleanup(shutil.rmtree, out, ignore_errors=True)
        argv = ["paxel.py"] + list(args) + ["--no-open"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **src_dirs), \
                mock.patch.object(sys, "argv", argv), \
                __import__("contextlib").redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_window_keeps_full_cursor_session(self):
        # mtime mid-February → inside the Feb window.
        feb15 = datetime(2025, 2, 15, 12, 0, 0).timestamp()
        full = self._run_cursor_stats([], feb15)
        windowed = self._run_cursor_stats(["--since=2025-02-01", "--until=2025-03-01"], feb15)
        # The windowed run must count the SAME prompts and tool calls as the unfiltered
        # run — the synthetic-timestamp events (assistant tool calls) must survive the gate.
        self.assertEqual(windowed["volume"]["total_prompts"], full["volume"]["total_prompts"])
        self.assertEqual(windowed["volume"]["tool_calls_total"], full["volume"]["tool_calls_total"])
        self.assertGreater(windowed["volume"]["tool_calls_total"], 0,
                           "windowed run dropped the Cursor tool calls (regression)")

    def test_window_excludes_cursor_session_outside_range(self):
        # mtime in January → the whole Feb-windowed run sees nothing (no partial keep).
        jan10 = datetime(2025, 1, 10, 12, 0, 0).timestamp()
        windowed = self._run_cursor_stats(["--since=2025-02-01", "--until=2025-03-01"], jan10)
        self.assertEqual(windowed["volume"]["total_prompts"], 0)
        self.assertEqual(windowed["volume"]["tool_calls_total"], 0)
