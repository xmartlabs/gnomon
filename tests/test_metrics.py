"""H10 — active-time fidelity: `_active_hours_and_longest_run` must compute total
active hours as the UNION of per-session active wall-clock intervals, not the sum of
independently-capped per-session durations. Two sessions that ran fully concurrently
must count that wall-clock time ONCE; disjoint sessions still sum; partial overlap
unions to the merged span. Per-session `longest_run` (burst detection) is unchanged.

Both the window path (accumulator.py:1337) and the per-month subset path
(inputs.py:201, accumulator.py:1786, summary.py:64) call this exact same helper with
a {sessionId: [epoch_seconds]} mapping, so a single unit test on the helper itself
covers both -- there is no separate per-month code path to drift.

gap_cap_s is passed as an effectively-unbounded value in the union tests below so the
merge/union logic is exercised in isolation from the (unchanged) idle-gap-capping
behavior, which is a separate, already-covered concern.
"""
import unittest

from gnomon.analysis.metrics import _active_hours_and_longest_run

_UNCAPPED = 10 ** 9  # gap_cap_s large enough that no consecutive-event gap is ever capped


class TestActiveHoursAreTheUnionOfEngagedWallClockTime(unittest.TestCase):
    def test_two_disjoint_sessions_sum(self):
        # Session A active 09:00-10:00, session B active 14:00-15:00 (no overlap).
        session_ts = {
            "A": [0, 3600],
            "B": [5 * 3600, 6 * 3600],
        }
        hours, _ = _active_hours_and_longest_run(session_ts, _UNCAPPED, _UNCAPPED)
        self.assertEqual(hours, 2.0)

    def test_two_fully_overlapping_sessions_count_once(self):
        # Session A and B both active 09:00-11:00 (full overlap) -> 2.0, NOT 4.0.
        session_ts = {
            "A": [0, 7200],
            "B": [0, 7200],
        }
        hours, _ = _active_hours_and_longest_run(session_ts, _UNCAPPED, _UNCAPPED)
        self.assertEqual(hours, 2.0)

    def test_partial_overlap_unions_the_merged_span(self):
        # Session A active 09:00-11:00, session B active 10:00-12:00 -> union
        # 09:00-12:00 = 3.0, NOT 4.0 (the naive sum of the two 2h durations).
        session_ts = {
            "A": [0, 7200],
            "B": [3600, 10800],
        }
        hours, _ = _active_hours_and_longest_run(session_ts, _UNCAPPED, _UNCAPPED)
        self.assertEqual(hours, 3.0)

    def test_three_way_overlap_still_counts_the_span_once(self):
        # Triangulation: a third fully-nested session must not add any extra hours
        # beyond the outer union already computed above.
        session_ts = {
            "A": [0, 7200],
            "B": [3600, 10800],
            "C": [1800, 5400],  # nested entirely inside A ∪ B
        }
        hours, _ = _active_hours_and_longest_run(session_ts, _UNCAPPED, _UNCAPPED)
        self.assertEqual(hours, 3.0)

    def test_per_month_subset_path_shares_the_identical_union_rule(self):
        """inputs.py:201 and accumulator.py:1786 call this exact function with a
        per-month-filtered {sessionId: [ts...]} mapping -- indistinguishable in shape
        from the window-scoped call at accumulator.py:1337 -- so the union rule
        applies to a monthly subset automatically, with no separate code path."""
        month_session_ts = {
            "A": [0, 7200],
            "B": [3600, 10800],
        }
        hours, _ = _active_hours_and_longest_run(month_session_ts, _UNCAPPED, _UNCAPPED)
        self.assertEqual(hours, 3.0)


class TestLongestRunStaysPerSessionAndUnaffectedByUnion(unittest.TestCase):
    """Per-session longest_run (burst detection) behavior is unchanged by the union
    merge -- it stays the max single-session contiguous burst, not a merged one."""

    def test_longest_run_is_the_max_single_session_burst_in_minutes(self):
        # Session A: one continuous 2h burst (events every hour, well under burst_gap_s).
        # Session B: a short 10-minute burst.
        session_ts = {
            "A": [0, 3600, 7200],
            "B": [100000, 100600],
        }
        _, longest_run_min = _active_hours_and_longest_run(session_ts, _UNCAPPED, _UNCAPPED)
        self.assertEqual(longest_run_min, 120.0)

    def test_longest_run_alone_matches_longest_run_combined_with_a_disjoint_session(self):
        # Adding a wholly-disjoint short session must not change A's own longest burst.
        a_only = {"A": [0, 3600, 7200]}
        combined = {"A": [0, 3600, 7200], "B": [100000, 100600]}
        _, longest_a_only = _active_hours_and_longest_run(a_only, _UNCAPPED, _UNCAPPED)
        _, longest_combined = _active_hours_and_longest_run(combined, _UNCAPPED, _UNCAPPED)
        self.assertEqual(longest_a_only, 120.0)
        self.assertEqual(longest_combined, 120.0)


if __name__ == "__main__":
    unittest.main()
