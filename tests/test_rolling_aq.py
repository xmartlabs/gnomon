import unittest
import copy
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest import mock

from gnomon.cli import local
from gnomon.scoring import aggregate
from tests._scoring_vectors_cases import CLAUDE_BLOCK


def _aq(first, second, first_signal, second_signal):
    pillar_score = round(first + second, 1)
    total = round(pillar_score)
    return {
        "aq_0_100": total,
        "tier": aggregate._aq_tier_for(total),
        "pillars": [
            {
                "name": "Craft",
                "weight": 100,
                "score": pillar_score,
                "axes": [
                    {
                        "name": "Verification",
                        "weight": 50,
                        "score": first,
                        "signals": {"test_runs": first_signal},
                    },
                    {
                        "name": "Grounding",
                        "weight": 50,
                        "score": second,
                        "signals": {"planning_ratio": second_signal},
                    },
                ],
            }
        ],
        "mcp_vs_cli": {"cli_calls": 1},
        "tool_diversity": {"distinct": 1},
    }


def _component(bucket_id, configured_weight, aq, lower_days, upper_days):
    return {
        "id": bucket_id,
        "configured_weight": configured_weight,
        "day_bounds": {"lower": lower_days, "upper": upper_days},
        "aq": aq,
    }


class TestRollingBucketWindows(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 9, 12, 30, tzinfo=timezone.utc)

    def test_current_or_future_window_anchors_at_now(self):
        windows = local._rolling_aq_bucket_windows(
            until_dt=self.now + timedelta(days=5), now=self.now)

        self.assertEqual(windows[0]["until"], self.now)
        self.assertEqual(windows[0]["since"], self.now - timedelta(days=30))
        self.assertEqual(windows[-1]["since"], self.now - timedelta(days=180))

    def test_historical_window_anchors_at_past_until(self):
        historical_until = datetime(2025, 3, 1, tzinfo=timezone.utc)
        windows = local._rolling_aq_bucket_windows(
            until_dt=historical_until, now=self.now)

        self.assertEqual(windows[0]["until"], historical_until)
        self.assertEqual(windows[-1]["since"], historical_until - timedelta(days=180))

    def test_no_until_anchors_at_now_and_preserves_timezone(self):
        local_now = self.now.astimezone(timezone(timedelta(hours=-3)))
        windows = local._rolling_aq_bucket_windows(until_dt=None, now=local_now)

        self.assertEqual(windows[0]["until"], local_now)
        self.assertEqual(windows[0]["until"].utcoffset(), timedelta(hours=-3))

    def test_exact_boundaries_are_disjoint_and_cover_180_days(self):
        windows = local._rolling_aq_bucket_windows(until_dt=self.now, now=self.now)
        cases = {
            self.now: None,
            self.now - timedelta(microseconds=1): "recent_30d",
            self.now - timedelta(days=30): "recent_30d",
            self.now - timedelta(days=90): "middle_60d",
            self.now - timedelta(days=180): "older_90d",
            self.now - timedelta(days=180, microseconds=1): None,
        }

        for timestamp, expected in cases.items():
            with self.subTest(timestamp=timestamp):
                matches = [w["id"] for w in windows if w["since"] <= timestamp < w["until"]]
                self.assertEqual(matches, [] if expected is None else [expected])

        self.assertEqual(
            [(w["id"], w["day_bounds"]) for w in windows],
            [
                ("recent_30d", {"lower": 0, "upper": 30}),
                ("middle_60d", {"lower": 30, "upper": 90}),
                ("older_90d", {"lower": 90, "upper": 180}),
            ],
        )


class TestWeightedAQBlend(unittest.TestCase):
    def setUp(self):
        self.full = _aq(5.0, 5.0, 1, 1)
        self.recent = _aq(50.0, 40.0, 50, 40)
        self.middle = _aq(25.0, 20.0, 25, 20)
        self.older = _aq(0.0, 10.0, 0, 10)
        self.components = [
            _component("recent_30d", 0.50, self.recent, 0, 30),
            _component("middle_60d", 0.30, self.middle, 30, 90),
            _component("older_90d", 0.20, self.older, 90, 180),
        ]

    def test_blends_axes_then_recomputes_pillar_total_and_tier(self):
        blended = aggregate._blend_aq(self.full, self.components)

        pillar = blended["pillars"][0]
        axes = {axis["name"]: axis for axis in pillar["axes"]}
        self.assertEqual(axes["Verification"]["score"], 32.5)
        self.assertEqual(axes["Grounding"]["score"], 28.0)
        self.assertEqual(pillar["score"], 60.5)
        self.assertEqual(blended["aq_0_100"], 60)
        self.assertEqual(blended["tier"], "Proficient")

    def test_axis_signals_come_from_highest_effective_weight_bucket(self):
        blended = aggregate._blend_aq(self.full, self.components)
        axes = {axis["name"]: axis for axis in blended["pillars"][0]["axes"]}

        self.assertEqual(axes["Verification"]["signals"], {"test_runs": 50})
        self.assertEqual(
            [component["id"] for component in axes["Verification"]["components"]],
            ["recent_30d", "middle_60d", "older_90d"],
        )
        self.assertEqual(
            [component["effective_weight"] for component in axes["Verification"]["components"]],
            [0.5, 0.3, 0.2],
        )

    def test_axis_available_in_lower_weight_bucket_is_not_marked_not_applicable(self):
        recent = copy.deepcopy(self.recent)
        recent["pillars"][0]["axes"] = recent["pillars"][0]["axes"][:1]
        recent["pillars"][0]["score"] = 50.0
        recent["pillars"][0]["not_applicable"] = ["Grounding"]
        components = [dict(self.components[0], aq=recent), self.components[1], self.components[2]]

        pillar = aggregate._blend_aq(self.full, components)["pillars"][0]

        self.assertIn("Grounding", [axis["name"] for axis in pillar["axes"]])
        self.assertNotIn("Grounding", pillar.get("not_applicable", []))

    def test_missing_bucket_weights_are_renormalized(self):
        blended = aggregate._blend_aq(self.full, [self.components[0], self.components[2]])
        buckets = blended["blend"]["buckets"]

        self.assertAlmostEqual(buckets[0]["effective_weight"], 5 / 7)
        self.assertAlmostEqual(buckets[1]["effective_weight"], 2 / 7)
        self.assertAlmostEqual(sum(b["effective_weight"] for b in buckets), 1.0)
        self.assertEqual(blended["pillars"][0]["score"], 67.1)

    def test_single_available_bucket_receives_full_weight(self):
        blended = aggregate._blend_aq(self.full, [self.components[1]])

        self.assertEqual(blended["blend"]["buckets"][0]["effective_weight"], 1.0)
        self.assertEqual(blended["aq_0_100"], self.middle["aq_0_100"])

    def test_full_window_is_informational_not_a_blend_component(self):
        blended = aggregate._blend_aq(_aq(50.0, 50.0, 99, 99), self.components)

        self.assertEqual(blended["aq_0_100"], 60)
        self.assertEqual(blended["blend"]["full_aq"], 100)
        self.assertEqual(
            [bucket["id"] for bucket in blended["blend"]["buckets"]],
            ["recent_30d", "middle_60d", "older_90d"],
        )


class TestRollingBucketAccumulation(unittest.TestCase):
    def test_current_partial_month_report_since_does_not_clip_180_day_aq_horizon(self):
        anchor = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)
        report_since = datetime(2026, 2, 1, tzinfo=timezone.utc)
        report_until = datetime(2026, 8, 1, tzinfo=timezone.utc)
        old_timestamp = anchor - timedelta(days=170)
        event = {
            "type": "user",
            "sessionId": "older-only",
            "timestamp": old_timestamp.isoformat(),
            "cwd": "/repo",
            "message": {"role": "user", "content": "include the full aq horizon"},
        }
        windows = local._rolling_aq_bucket_windows(until_dt=report_until, now=anchor)

        with tempfile.NamedTemporaryFile() as transcript:
            os.utime(transcript.name, (old_timestamp.timestamp(), old_timestamp.timestamp()))
            with mock.patch.object(local, "_rolling_aq_bucket_windows", return_value=windows), \
                    mock.patch.object(local, "iter_events", return_value=[event]):
                stats, narrative = local._accumulate(
                    [("claude", transcript.name, "claude")],
                    since_dt=report_since,
                    until_dt=report_until,
                    cursor_twins=set(),
                    antigravity=None,
                    verbose=False,
                )

        self.assertEqual(stats["volume"]["total_sessions"], 0)
        counts = {
            bucket_id: bucket_stats["volume"]["total_sessions"]
            for bucket_id, bucket_stats in narrative["_aq_bucket_stats"].items()
        }
        self.assertEqual(counts, {"recent_30d": 0, "middle_60d": 0, "older_90d": 1})

    def test_events_are_routed_to_exactly_one_bucket(self):
        anchor = datetime(2025, 7, 1, 12, tzinfo=timezone.utc)
        timestamps = [
            anchor - timedelta(microseconds=1),
            anchor - timedelta(days=30),
            anchor - timedelta(days=30, microseconds=1),
            anchor - timedelta(days=90),
            anchor - timedelta(days=90, microseconds=1),
            anchor - timedelta(days=180),
            anchor - timedelta(days=180, microseconds=1),
            anchor,
        ]
        events = [
            {
                "type": "user",
                "sessionId": f"session-{index}",
                "timestamp": timestamp.isoformat(),
                "cwd": "/repo",
                "message": {"role": "user", "content": "test the rolling bucket"},
            }
            for index, timestamp in enumerate(timestamps)
        ]
        with tempfile.NamedTemporaryFile() as transcript, \
                mock.patch.object(local, "iter_events", return_value=events), \
                mock.patch.object(local, "git_churn", return_value={
                    "repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
                    "deletions": 0, "churn": 0, "commits": 0, "per_repo": [],
                }):
            _stats, narrative = local._accumulate(
                [("claude", transcript.name, "claude")],
                since_dt=None,
                until_dt=anchor,
                cursor_twins=set(),
                antigravity=None,
                verbose=False,
            )

        counts = {
            bucket_id: stats["volume"]["total_sessions"]
            for bucket_id, stats in narrative["_aq_bucket_stats"].items()
        }
        self.assertEqual(counts, {"recent_30d": 2, "middle_60d": 2, "older_90d": 2})
        self.assertEqual(sum(counts.values()), 6)

    def test_corpus_bucket_preserves_each_source_capability_key(self):
        anchor = datetime(2025, 7, 1, 12, tzinfo=timezone.utc)

        def event(source):
            return {
                "type": "user",
                "sessionId": f"{source}-session",
                "timestamp": (anchor - timedelta(days=1)).isoformat(),
                "cwd": "/repo",
                "message": {"role": "user", "content": "preserve source capabilities"},
            }

        with tempfile.NamedTemporaryFile() as claude_file, \
                tempfile.NamedTemporaryFile() as cursor_file, \
                mock.patch.object(local, "iter_events", side_effect=[[event("claude")], [event("cursor")]]):
            _stats, narrative = local._accumulate(
                [
                    ("claude", claude_file.name, "claude"),
                    ("cursor", cursor_file.name, "cursor"),
                ],
                since_dt=None,
                until_dt=anchor,
                cursor_twins=set(),
                antigravity=None,
                verbose=False,
            )

        recent_sources = narrative["_aq_bucket_stats"]["recent_30d"]["corpus"]["sources"]
        self.assertEqual(set(recent_sources), {"claude", "cursor"})


class TestPerSourceRollingBlend(unittest.TestCase):
    def _block(self, *, sessions, tests, planning_ratio):
        block = copy.deepcopy(CLAUDE_BLOCK)
        block["volume"]["total_sessions"] = sessions
        block["behavior"]["shell_test_runs"] = tests
        block["behavior"]["planning_ratio_explore_to_doing"] = planning_ratio
        return block

    def test_per_source_uses_bucket_aq_but_keeps_full_window_profile_fields(self):
        full_inputs = {"claude": {"window": self._block(sessions=30, tests=0, planning_ratio=0)}}
        bucket_inputs = {
            "recent_30d": {"claude": {"window": self._block(sessions=10, tests=100, planning_ratio=1)}},
            "middle_60d": {"claude": {"window": self._block(sessions=10, tests=50, planning_ratio=0.5)}},
            "older_90d": {"claude": {"window": self._block(sessions=10, tests=0, planning_ratio=0)}},
        }
        metadata = [
            {"id": "recent_30d", "configured_weight": 0.5, "day_bounds": {"lower": 0, "upper": 30}},
            {"id": "middle_60d", "configured_weight": 0.3, "day_bounds": {"lower": 30, "upper": 90}},
            {"id": "older_90d", "configured_weight": 0.2, "day_bounds": {"lower": 90, "upper": 180}},
        ]

        full_only = aggregate.score_by_source(full_inputs)["by_source"]["claude"]
        profile = aggregate.score_by_source(
            full_inputs,
            bucket_scoring_inputs_by_source=bucket_inputs,
            bucket_metadata=metadata,
        )["by_source"]["claude"]

        self.assertEqual(profile["scores"], full_only["scores"])
        self.assertEqual(profile["archetype"], full_only["archetype"])
        self.assertEqual(profile["steering"], full_only["steering"])
        self.assertEqual([b["id"] for b in profile["aq"]["blend"]["buckets"]], list(bucket_inputs))
        for pillar in profile["aq"]["pillars"]:
            self.assertEqual(pillar["score"], round(sum(axis["score"] for axis in pillar["axes"]), 1))
        expected_total = round(sum(
            pillar["weight"] / 100 * pillar["score"] for pillar in profile["aq"]["pillars"]
        ))
        self.assertEqual(profile["aq"]["aq_0_100"], expected_total)
        self.assertEqual(profile["aq"]["tier"], aggregate._aq_tier_for(expected_total))


if __name__ == "__main__":
    unittest.main()
