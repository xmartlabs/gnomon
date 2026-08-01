"""The recency-blend COMPOSITION, which survives v11 as a replay-only reader.

v11 removed everything that PRODUCED a blend -- the rolling bucket windows, the bucket
accumulators and the corpus-level blend call -- so the classes that exercised those are
gone (their replacement, `tests/test_recency_blend_removed.py`, asserts they stay gone).
What is left here is `_blend_aq` and the `score_by_source` bucket path, which
`gnomon/scoring/replay.py` still needs in order to recompute a payload captured BEFORE
v11: those payloads carry `bucket_scoring_inputs` blocks and must stay replayable.

Every `recent_30d` / 0.65 / 0.35 below therefore describes a HISTORICAL payload's shape,
not anything this runtime emits.
"""
import unittest
import copy

from gnomon.scoring import aggregate
from tests._scoring_vectors_cases import CLAUDE_BLOCK, CURSOR_BLOCK
from gnomon.scoring.versioning import SCORE_CONTRACT_ID


def _aq(first, second, first_signal, second_signal):
    pillar_score = round(first + second, 1)
    total = round(pillar_score)
    return {
        "score_contract_id": SCORE_CONTRACT_ID,
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
                        "base_weight": 50,
                        "normalized_score": first / 50,
                        "score": first,
                        "signals": {"test_runs": first_signal},
                    },
                    {
                        "name": "Grounding",
                        "weight": 50,
                        "base_weight": 50,
                        "normalized_score": second / 50,
                        "score": second,
                        "signals": {"planning_ratio": second_signal},
                    },
                ],
            }
        ],
        "mcp_vs_cli": {"cli_calls": 1},
        "tool_diversity": {"distinct": 1},
    }


def _component(bucket_id, configured_weight, aq, lower_days=None, upper_days=None):
    """Build a weighted blend component. `full_window` (appended at blend time by
    _blend_profiles) carries no day_bounds, so lower/upper_days default to None and the
    key is omitted, matching the shape a pre-v11 payload records."""
    entry = {"id": bucket_id, "configured_weight": configured_weight, "aq": aq}
    if lower_days is not None or upper_days is not None:
        entry["day_bounds"] = {"lower": lower_days, "upper": upper_days}
    return entry


class TestWeightedAQBlend(unittest.TestCase):
    """Exercises the generic `_blend_aq` weighted-blend mechanism (axis blending,
    renormalization, tier recompute, not_applicable handling). A pre-v11 payload carries
    exactly two components -- recent_30d (0.65) and full_window (0.35, appended at blend
    time by _blend_profiles) -- so most tests below mirror that shape. `_blend_aq` itself
    stays generic over any number of named, weighted components;
    test_missing_bucket_weights_are_renormalized uses two synthetic components (not real
    bucket ids) purely to prove that generic renormalization behavior still holds when
    configured weights don't sum to one."""

    def setUp(self):
        self.full = _aq(5.0, 5.0, 1, 1)
        self.recent = _aq(50.0, 40.0, 50, 40)
        self.history = _aq(0.0, 20.0, 0, 20)
        self.components = [
            _component("recent_30d", 0.65, self.recent, 0, 30),
            _component("full_window", 0.35, self.history),
        ]

    def test_blends_axes_then_recomputes_pillar_total_and_tier(self):
        blended = aggregate._blend_aq(self.full, self.components)

        pillar = blended["pillars"][0]
        axes = {axis["name"]: axis for axis in pillar["axes"]}
        self.assertEqual(axes["Verification"]["score"], 32.5)
        self.assertEqual(axes["Grounding"]["score"], 33.0)
        self.assertEqual(pillar["score"], 65.5)
        self.assertEqual(blended["aq_0_100"], 66)
        self.assertEqual(blended["tier"], "Proficient")

    def test_axis_signals_come_from_highest_effective_weight_bucket(self):
        blended = aggregate._blend_aq(self.full, self.components)
        axes = {axis["name"]: axis for axis in blended["pillars"][0]["axes"]}

        self.assertEqual(axes["Verification"]["signals"], {"test_runs": 50})
        self.assertEqual(
            [component["id"] for component in axes["Verification"]["components"]],
            ["recent_30d", "full_window"],
        )
        self.assertEqual(
            [component["effective_weight"] for component in axes["Verification"]["components"]],
            [0.65, 0.35],
        )

    def test_axis_available_in_lower_weight_bucket_is_not_marked_not_applicable(self):
        recent = copy.deepcopy(self.recent)
        recent["pillars"][0]["axes"] = recent["pillars"][0]["axes"][:1]
        recent["pillars"][0]["score"] = 50.0
        recent["pillars"][0]["not_applicable"] = ["Grounding"]
        components = [dict(self.components[0], aq=recent), self.components[1]]

        pillar = aggregate._blend_aq(self.full, components)["pillars"][0]

        self.assertIn("Grounding", [axis["name"] for axis in pillar["axes"]])
        self.assertNotIn("Grounding", pillar.get("not_applicable", []))

    def test_missing_bucket_weights_are_renormalized(self):
        # Synthetic components (not the real recent_30d/full_window pair) purely to
        # prove _blend_aq renormalizes configured weights that don't already sum to one.
        alpha = _component("alpha_sample", 0.50, self.recent, 0, 30)
        gamma = _component("gamma_sample", 0.20, _aq(0.0, 10.0, 0, 10), 90, 180)

        blended = aggregate._blend_aq(self.full, [alpha, gamma])
        buckets = blended["blend"]["buckets"]

        self.assertAlmostEqual(buckets[0]["effective_weight"], 5 / 7)
        self.assertAlmostEqual(buckets[1]["effective_weight"], 2 / 7)
        self.assertAlmostEqual(sum(b["effective_weight"] for b in buckets), 1.0)
        self.assertEqual(blended["pillars"][0]["score"], 67.1)

    def test_single_available_bucket_receives_full_weight(self):
        blended = aggregate._blend_aq(self.full, [self.components[1]])

        self.assertEqual(blended["blend"]["buckets"][0]["effective_weight"], 1.0)
        self.assertEqual(blended["aq_0_100"], self.history["aq_0_100"])

    def test_full_window_is_informational_not_a_blend_component(self):
        blended = aggregate._blend_aq(_aq(50.0, 50.0, 99, 99), self.components)

        self.assertEqual(blended["aq_0_100"], 66)
        self.assertEqual(blended["blend"]["full_aq"], 100)
        self.assertEqual(
            [bucket["id"] for bucket in blended["blend"]["buckets"]],
            ["recent_30d", "full_window"],
        )

    def test_model_mix_blends_signals_instead_of_axis_contributions(self):
        def model_mix_aq(distinct_models, offload_share, routing):
            aq = _aq(50.0, 0.0, 0, 0)
            aq["pillars"][0]["name"] = "Savvy"
            aq["pillars"][0]["axes"] = [{
                "name": "Model mix",
                "base_weight": 50,
                "weight": 100,
                # Deliberately contradictory: the blend must derive from signals.
                "normalized_score": 0.0,
                "score": 0.0,
                "signals": {
                    "distinct_models": distinct_models,
                    "offload_share": offload_share,
                    "routing": routing,
                },
            }]
            return aq

        recent = model_mix_aq(3, 0.30, {"state": "unsupported", "score": None})
        history = model_mix_aq(1, 0, {"state": "measured", "score": 1.0})
        blended = aggregate._blend_aq(recent, [
            _component("recent_30d", 0.65, recent, 0, 30),
            _component("full_window", 0.35, history),
        ])
        axis = blended["pillars"][0]["axes"][0]

        self.assertAlmostEqual(axis["normalized_score"], 0.7958333333)
        self.assertEqual(axis["score"], 79.6)


class TestPerSourceRollingBlend(unittest.TestCase):
    """`score_by_source`'s bucket path. No live caller supplies bucket inputs since v11;
    `gnomon/scoring/replay.py` does, from a pre-v11 payload's own
    `bucket_scoring_inputs.by_source` breakdown."""

    def _block(self, *, sessions, tests, planning_ratio, template=CLAUDE_BLOCK,
               tool_calls=None):
        block = copy.deepcopy(template)
        block["volume"]["total_sessions"] = sessions
        if tool_calls is not None:
            block["volume"]["tool_calls_total"] = tool_calls
        block["behavior"]["shell_test_runs"] = tests
        block["behavior"]["planning_ratio_explore_to_doing"] = planning_ratio
        return block

    def test_per_source_uses_bucket_aq_but_keeps_full_window_profile_fields(self):
        full_inputs = {"claude": {"window": self._block(sessions=30, tests=0, planning_ratio=0)}}
        bucket_inputs = {
            "recent_30d": {"claude": {"window": self._block(sessions=10, tests=100, planning_ratio=1)}},
        }
        metadata = [
            {"id": "recent_30d", "configured_weight": 0.65, "day_bounds": {"lower": 0, "upper": 30}},
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
        # recent_30d (configured) plus full_window (appended at blend time).
        self.assertEqual(
            [b["id"] for b in profile["aq"]["blend"]["buckets"]],
            ["recent_30d", "full_window"],
        )
        for pillar in profile["aq"]["pillars"]:
            self.assertEqual(pillar["score"], round(sum(axis["score"] for axis in pillar["axes"]), 1))
        expected_total = round(sum(
            pillar["weight"] / 100 * pillar["score"] for pillar in profile["aq"]["pillars"]
        ))
        self.assertEqual(profile["aq"]["aq_0_100"], expected_total)
        self.assertEqual(profile["aq"]["tier"], aggregate._aq_tier_for(expected_total))

    def test_na_mismatch_blends_normalized_axes_and_renormalizes_once(self):
        full = self._block(sessions=10, tests=10, planning_ratio=1)
        full["behavior"].update({
            "ordered_facts_state": "measured",
            "eligible_change_sessions": 10,
            "planned_eligible_sessions": 4,
            "evidence_eligible_sessions": 6,
            "planning_skill_sessions": 4,
            "linked_model_routing_state": "unsupported",
            "linked_model_pairs": [],
            "no_tool_activity": False,
        })
        recent = copy.deepcopy(full)
        recent["behavior"].update({
            "ordered_facts_state": "unmeasured",
            "eligible_change_sessions": 0,
            "planned_eligible_sessions": 0,
            "evidence_eligible_sessions": 0,
        })
        result = aggregate.score_by_source(
            {"claude": {"window": full}},
            {"recent_30d": {"claude": {"window": recent}}},
            [{"id": "recent_30d", "configured_weight": 0.65,
              "day_bounds": {"lower": 0, "upper": 30}}],
        )["by_source"]["claude"]["aq"]

        craft = next(p for p in result["pillars"] if p["name"] == "Craft")
        self.assertLessEqual(craft["score"], 100)
        self.assertTrue(all(0 <= p["score"] <= 100 for p in result["pillars"]))
        self.assertTrue(0 <= result["aq_0_100"] <= 100)

        # CI is measurable only in the 35% full-window component, so its normalized
        # score comes from that component alone. Other axes retain the 65/35 blend.
        axes = {axis["name"]: axis for axis in craft["axes"]}
        self.assertEqual(axes["Context Intelligence"]["normalized_score"], 1.0)
        self.assertEqual(sum(axis["weight"] for axis in craft["axes"]), 100)
        expected_craft = round(sum(
            axis["weight"] * axis["normalized_score"] for axis in craft["axes"]
        ), 1)
        self.assertEqual(craft["score"], expected_craft)
        expected_total = round(sum(
            pillar["weight"] / 100 * pillar["score"] for pillar in result["pillars"]
        ))
        self.assertEqual(result["aq_0_100"], expected_total)

    def test_aggregate_weights_recent_bucket_sources_by_recency_and_legacy_sources_by_full_window(self):
        full_inputs = {
            "claude": {"window": self._block(
                sessions=10, tests=120, planning_ratio=0.7, tool_calls=10)},
            "cursor": {"window": self._block(
                sessions=10, tests=5, planning_ratio=0.3,
                template=CURSOR_BLOCK, tool_calls=20)},
        }
        bucket_inputs = {
            "recent_30d": {"claude": {"window": self._block(
                sessions=10, tests=120, planning_ratio=0.7, tool_calls=10)}},
        }
        metadata = [
            {"id": "recent_30d", "configured_weight": 0.65,
             "day_bounds": {"lower": 0, "upper": 30}},
        ]

        result = aggregate.score_by_source(full_inputs, bucket_inputs, metadata)

        # claude has recent_30d bucket activity -> weighted by configured_weight * that
        # bucket's tool_calls_total. cursor has none -> falls back to the legacy
        # full-window tool_calls_total.
        self.assertEqual(
            result["aggregate"]["combination"]["weights"],
            {"claude": 0.65 * 10, "cursor": 20},
        )
        claude_aq = result["by_source"]["claude"]["aq"]["aq_0_100"]
        cursor_aq = result["by_source"]["cursor"]["aq"]["aq_0_100"]
        wa = result["aggregate"]["combination"]["weights"]["claude"]
        wu = result["aggregate"]["combination"]["weights"]["cursor"]
        expected_aggregate = round((claude_aq * wa + cursor_aq * wu) / (wa + wu))
        self.assertEqual(result["aggregate"]["aq_diagnostic"]["aq_0_100"], expected_aggregate)
        self.assertNotEqual(result["aggregate"]["aq_diagnostic"]["aq_0_100"], claude_aq)

    def test_aggregate_without_buckets_keeps_full_window_tool_volume_weights(self):
        full_inputs = {
            "claude": {"window": self._block(
                sessions=40, tests=120, planning_ratio=0.7, tool_calls=10)},
            "cursor": {"window": self._block(
                sessions=10, tests=5, planning_ratio=0.3,
                template=CURSOR_BLOCK, tool_calls=20)},
        }

        result = aggregate.score_by_source(full_inputs)

        self.assertEqual(
            result["aggregate"]["combination"]["weights"],
            {"claude": 10, "cursor": 20},
        )
        # Derive the aggregate from the per-source scores and those weights instead of
        # pinning a literal: this test is about the WEIGHTING, and a hardcoded AQ turns any
        # legitimate scoring change into a spurious failure here.
        claude_aq = result["by_source"]["claude"]["aq"]["aq_0_100"]
        cursor_aq = result["by_source"]["cursor"]["aq"]["aq_0_100"]
        self.assertEqual(result["aggregate"]["aq_diagnostic"]["aq_0_100"],
                         round((claude_aq * 10 + cursor_aq * 20) / 30))

    def test_nonempty_bucket_without_metadata_uses_full_profile_and_legacy_weight(self):
        full_inputs = {"claude": {"window": self._block(
            sessions=40, tests=0, planning_ratio=0, tool_calls=40)}}
        bucket_inputs = {"recent_30d": {"claude": {"window": self._block(
            sessions=10, tests=120, planning_ratio=1, tool_calls=10)}}}
        full_only = aggregate.score_by_source(full_inputs)

        result = aggregate.score_by_source(full_inputs, bucket_inputs)

        self.assertEqual(result["by_source"]["claude"], full_only["by_source"]["claude"])
        self.assertEqual(
            result["aggregate"]["combination"]["weights"],
            {"claude": 40},
        )

    def test_bucket_missing_from_partial_metadata_uses_legacy_fallbacks(self):
        full_inputs = {"claude": {"window": self._block(
            sessions=40, tests=0, planning_ratio=0, tool_calls=40)}}
        bucket_inputs = {"unscored_bucket": {"claude": {"window": self._block(
            sessions=10, tests=120, planning_ratio=1, tool_calls=10)}}}
        partial_metadata = [
            {"id": "recent_30d", "configured_weight": 0.65,
             "day_bounds": {"lower": 0, "upper": 30}},
        ]
        full_only = aggregate.score_by_source(full_inputs)

        result = aggregate.score_by_source(
            full_inputs, bucket_inputs, partial_metadata)

        self.assertEqual(result["by_source"]["claude"], full_only["by_source"]["claude"])
        self.assertEqual(
            result["aggregate"]["combination"]["weights"],
            {"claude": 40},
        )


if __name__ == "__main__":
    unittest.main()
