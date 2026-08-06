"""Coverage-index capability (honest-aq-series, Phase 2 gnomon).

gnomon/coverage.py is a top-level LEAF module: it never imports from
gnomon.sources or gnomon.cli.accumulator, and history.jsonl (a sibling of
BASE) is structurally unreachable by discover_sources's _walk_ext(BASE, ...).
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from gnomon.coverage import (
    HISTORY_PATH, COVERAGE_RANK, month_index, coverage_for, flag_for_counts,
    probe_month,
)


def _write_history(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _row(sid, ts, project="/Users/dev/myproject"):
    return {"display": "hi", "pastedContents": {}, "timestamp": ts,
            "project": project, "sessionId": sid}


class TestFlagLadder(unittest.TestCase):
    """GIVEN 0 transcripts and >0 indexed -> insufficient, never complete.
    GIVEN no history.jsonl -> unknown, never treated as insufficient."""

    def test_insufficient_never_complete(self):
        self.assertEqual(flag_for_counts(50, 0), "insufficient")
        self.assertNotEqual(flag_for_counts(50, 0), "complete")

    def test_partial_when_some_but_not_all(self):
        self.assertEqual(flag_for_counts(50, 24), "partial")

    def test_complete_when_transcripts_meet_or_exceed_indexed(self):
        self.assertEqual(flag_for_counts(50, 50), "complete")
        self.assertEqual(flag_for_counts(50, 80), "complete")

    def test_unknown_when_no_history_at_all(self):
        self.assertEqual(flag_for_counts(None, 12), "unknown")

    def test_unknown_distinct_from_insufficient(self):
        # Both are "quiet" states but MUST be different values.
        self.assertNotEqual(flag_for_counts(None, 0), flag_for_counts(50, 0))
        self.assertEqual(flag_for_counts(None, 0), "unknown")

    def test_unknown_when_indexed_is_zero(self):
        # indexed==0 means "no evidence for this month", not a real positive
        # zero to compare transcripts against -- unknown, not insufficient.
        self.assertEqual(flag_for_counts(0, 5), "unknown")

    def test_coverage_rank_excludes_unknown(self):
        self.assertEqual(COVERAGE_RANK, {"insufficient": 0, "partial": 1, "complete": 2})
        self.assertNotIn("unknown", COVERAGE_RANK)


class TestMonthIndex(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "history.jsonl")

    def _ts_ms(self, dt):
        return int(dt.timestamp() * 1000)

    def test_missing_file_returns_empty_dict_not_none(self):
        self.assertEqual(month_index(os.path.join(self._tmp.name, "nope.jsonl")), {})

    def test_distinct_session_ids_per_month(self):
        dt = datetime(2026, 6, 15, 10, 0, 0).astimezone()
        _write_history(self.path, [
            _row("s1", self._ts_ms(dt)),
            _row("s1", self._ts_ms(dt + timedelta(minutes=5))),  # same session, same month
            _row("s2", self._ts_ms(dt)),
        ])
        idx = month_index(self.path)
        self.assertEqual(len(idx["2026-06"]), 2)

    def test_codexbar_claudeprobe_project_excluded(self):
        dt = datetime(2026, 6, 15, 10, 0, 0).astimezone()
        _write_history(self.path, [
            _row("real-session", self._ts_ms(dt), project="/Users/dev/real"),
            _row("probe-session", self._ts_ms(dt), project="/Users/dev/CodexBar/ClaudeProbe"),
        ])
        idx = month_index(self.path)
        self.assertEqual(idx["2026-06"], {"real-session"})

    def test_malformed_lines_are_skipped_not_fatal(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("not json at all\n")
            fh.write(json.dumps(_row("s1", self._ts_ms(
                datetime(2026, 6, 1).astimezone()))) + "\n")
        idx = month_index(self.path)
        self.assertEqual(idx["2026-06"], {"s1"})


class TestCoverageFor(unittest.TestCase):
    def test_uses_sets_and_computes_overlap(self):
        indexed = {"a", "b", "c"}
        transcripts = {"a", "b"}
        result = coverage_for(indexed, transcripts)
        self.assertEqual(result["flag"], "partial")
        self.assertEqual(result["indexed_interactive_sessions"], 3)
        self.assertEqual(result["available_transcripts"], 2)
        self.assertEqual(result["interactive_coverage"], round(2 / 3, 3))
        self.assertEqual(result["transcript_only_sessions"], 0)

    def test_transcript_only_sessions_counts_sessions_absent_from_history(self):
        # Conductor-style sessions: on-disk transcripts that never wrote to
        # history.jsonl at all (lower bound property).
        indexed = {"a"}
        transcripts = {"a", "conductor-1", "conductor-2"}
        result = coverage_for(indexed, transcripts)
        self.assertEqual(result["transcript_only_sessions"], 2)
        self.assertEqual(result["flag"], "complete")

    def test_unknown_when_indexed_is_none(self):
        result = coverage_for(None, {"x", "y"})
        self.assertEqual(result["flag"], "unknown")
        self.assertIsNone(result["indexed_interactive_sessions"])
        self.assertIsNone(result["interactive_coverage"])
        self.assertEqual(result["available_transcripts"], 2)


class TestProbeMonthMtimeBug(unittest.TestCase):
    """probe_month is bucketed by st_mtime (LAST-WRITE time), not event time --
    documented as bidirectionally wrong, never a lower-bound estimate."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _touch_with_mtime(self, name, dt):
        fp = os.path.join(self._tmp.name, name)
        with open(fp, "w") as fh:
            fh.write("irrelevant content, e.g. June events\n")
        ts = dt.timestamp()
        os.utime(fp, (ts, ts))
        return fp

    def test_july_mtime_file_with_june_events_counts_in_july_only(self):
        july_dt = datetime(2026, 7, 3, 12, 0, 0)
        fp = self._touch_with_mtime("session-with-june-content.jsonl", july_dt)
        history_index = {}  # no history.jsonl evidence either way for this test

        _, july_transcripts = probe_month("2026-07", [fp], history_index=history_index)
        _, june_transcripts = probe_month("2026-06", [fp], history_index=history_index)

        self.assertEqual(july_transcripts, 1)
        self.assertEqual(june_transcripts, 0)

    def test_indexed_comes_from_the_supplied_history_index(self):
        history_index = {"2026-06": {"a", "b", "c"}}
        indexed, _ = probe_month("2026-06", [], history_index=history_index)
        self.assertEqual(indexed, 3)

    def test_indexed_is_none_when_month_absent_from_history_index(self):
        indexed, _ = probe_month("2026-06", [], history_index={})
        self.assertIsNone(indexed)


class TestDiscoverySourcesBoundary(unittest.TestCase):
    """Structural invariant: history.jsonl is a sibling of BASE, so
    discover_sources(ALL_SOURCES) can never yield HISTORY_PATH."""

    def test_history_path_never_discovered_as_a_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = os.path.join(tmp, ".claude")
            base = os.path.join(cfg_dir, "projects")
            os.makedirs(os.path.join(base, "proj1"), exist_ok=True)
            with open(os.path.join(base, "proj1", "session.jsonl"), "w") as fh:
                fh.write("{}\n")
            history_path = os.path.join(cfg_dir, "history.jsonl")
            with open(history_path, "w") as fh:
                fh.write(json.dumps(_row("s1", 1)) + "\n")

            import gnomon.sources.discovery as discovery
            with mock.patch.object(discovery, "BASE", base):
                found = [fp for _, fp, _ in discovery.discover_sources(discovery.ALL_SOURCES)]
            self.assertNotIn(history_path, found)


class TestHistoryPathIsSiblingOfBase(unittest.TestCase):
    def test_history_path_geometry(self):
        from gnomon.config import BASE
        self.assertEqual(HISTORY_PATH, os.path.join(os.path.dirname(BASE), "history.jsonl"))


if __name__ == "__main__":
    unittest.main()
