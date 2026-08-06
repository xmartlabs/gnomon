"""git_churn scoping (honest-aq-series step 5, design decision D): scope, not
winsorize. The window handed to git_churn is the INTERSECTION of the
requested window and the corpus's own observed span, so numerator (churn)
and denominator (active_hours, already corpus-scoped) are commensurate. An
empty corpus emits a zeroed churn dict and invokes no git subprocess."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from gnomon.cli.accumulator import Accumulator

BASE_DT = datetime(2026, 6, 10, 12, 0, 0)


def _ts(i):
    return (BASE_DT + timedelta(days=i)).isoformat() + "Z"


def _prompt(sid, i, cwd="/repo"):
    return {
        "type": "user", "sessionId": sid, "timestamp": _ts(i), "cwd": cwd,
        "message": {"role": "user", "content": f"hello {i}"},
    }


class TestEmptyCorpusNoSubprocess(unittest.TestCase):
    def test_empty_corpus_emits_zero_and_never_calls_git(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        acc.end_file()
        with mock.patch("subprocess.run") as run:
            stats = acc.to_corpus_stats(None, None, False)
        run.assert_not_called()
        self.assertEqual(stats["velocity"]["git_churn_total"], 0)


class TestWindowIntersectsCorpus(unittest.TestCase):
    def test_scoped_since_until_are_intersection_not_raw_window(self):
        acc = Accumulator()
        acc.begin_file("claude", "f.jsonl")
        # Observed activity spans days 0..2 only.
        for i in range(3):
            acc.observe(_prompt("s1", i), None, None)
        acc.end_file()

        # Requested window is much wider than what was actually observed.
        since_dt = (BASE_DT - timedelta(days=100)).astimezone()
        until_dt = (BASE_DT + timedelta(days=100)).astimezone()

        with mock.patch("gnomon.cli.accumulator.git_churn") as gc:
            gc.return_value = {"repos_seen": 0, "repos_with_commits": 0,
                                "insertions": 0, "deletions": 0, "churn": 0,
                                "commits": 0, "per_repo": []}
            acc.to_corpus_stats(since_dt, until_dt, False)
            self.assertEqual(gc.call_count, 1)
            _, call_since, call_until = gc.call_args[0]
        # The scoped since/until must be narrower than the raw 200-day window --
        # bounded by the corpus's own observed span (days 0..2 around BASE_DT).
        self.assertGreater(call_since, since_dt.strftime("%Y-%m-%d"))
        self.assertLess(call_until, until_dt.strftime("%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
