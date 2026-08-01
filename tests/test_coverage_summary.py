"""Coverage-index projection into build_summary()'s payload (honest-aq-series
Phase 2, tasks 2.5-2.8):
  - top-level `coverage` key (test_smoke.py:181's exhaustive key-set pin is
    the deliberate-ceremony anchor for this).
  - `context.observed_range`, projected from stats["corpus"]["observed_range"]
    (already computed by accumulator.py, never uploaded before).
"""
import unittest

from gnomon.output.summary import build_summary
from tests.test_gnomon import _full_stats


class TestObservedRangeProjection(unittest.TestCase):
    def test_observed_range_projected_from_corpus_block(self):
        stats = _full_stats()
        stats["corpus"]["observed_range"] = ["2026-01-05T00:00:00+00:00",
                                              "2026-05-28T00:00:00+00:00"]
        summary = build_summary(stats)
        self.assertEqual(summary["context"]["observed_range"],
                         ["2026-01-05T00:00:00+00:00", "2026-05-28T00:00:00+00:00"])

    def test_observed_range_defaults_to_none_pair_when_absent(self):
        stats = _full_stats()  # corpus block has no "observed_range" key
        summary = build_summary(stats)
        self.assertEqual(summary["context"]["observed_range"], [None, None])

    def test_context_key_set_is_exhaustive(self):
        """Ceremony anchor for context (design.md decision A'): no prior test
        pins this key set exhaustively (test_gnomon.py uses issubset/assertIn),
        so any future addition to `context` must deliberately update this."""
        stats = _full_stats()
        summary = build_summary(stats)
        self.assertEqual(set(summary["context"]), {
            "date_range", "window", "window_months", "sources", "total_sessions",
            "total_prompts", "client_version", "observed_range",
        })

    def test_window_months_declares_the_corpus_scale_unconditionally(self):
        """`context.window_months` is the payload's declaration of the SPAN its counters
        were pooled over, and gnomon/scoring/replay.py refuses to re-score a payload that
        does not state one. It is derived from the bounds the run actually had, so a
        stats dict with no window at all declares null (unknown scale) rather than
        silently omitting the key -- see gnomon/output/summary.py::_scoring_window_months."""
        stats = _full_stats()
        stats["corpus"].pop("window", None)
        self.assertIsNone(build_summary(stats)["context"]["window_months"])

        stats["corpus"]["window"] = {"since": "2026-06-01T00:00:00-03:00",
                                     "until": "2026-07-01T00:00:00-03:00"}
        self.assertEqual(build_summary(stats)["context"]["window_months"], 1)


class TestTopLevelCoverageKey(unittest.TestCase):
    def test_coverage_key_present_when_supplied_on_stats(self):
        stats = _full_stats()
        stats["coverage"] = {"2026-05": {
            "flag": "partial", "indexed_interactive_sessions": 10,
            "available_transcripts": 4, "interactive_coverage": 0.4,
            "transcript_only_sessions": 0,
        }}
        summary = build_summary(stats)
        self.assertIn("coverage", summary)
        self.assertEqual(summary["coverage"], stats["coverage"])

    def test_coverage_key_defaults_to_empty_dict_when_absent(self):
        stats = _full_stats()
        summary = build_summary(stats)
        self.assertIn("coverage", summary)
        self.assertEqual(summary["coverage"], {})


if __name__ == "__main__":
    unittest.main()
