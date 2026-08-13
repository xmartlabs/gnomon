import unittest
from copy import deepcopy
from unittest import mock

from gnomon.scoring import aq, gstack
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.gstack import compute_scores, score_breakdown
from tests.test_scoring_v5 import _v5_scoring_stats


GSTACK_SENSITIVITY_CASES = (
    ("EXECUTION_OUTPUT_LINES_PER_HOUR_TARGET", 500, "Execution", "Tool output rate", True),
    ("DELEGATION_RUNS_PER_PROMPT_TARGET", 0.60, "Execution", "Delegation & parallelism", True),
    ("PLANNING_EXPLORE_RATIO_TARGET", 0.50, "Planning", "Explore-before-build", True),
    ("THINKING_BLOCKS_PER_SESSION_TARGET", 6.0, "Planning", "Reasoning depth", True),
    ("ITERATION_DEPTH_MEAN_TARGET", 4.0, "Engineering", "Low rework", True),
    ("ITERATION_DEPTH_MEAN_DECAY_SPAN", 1, "Engineering", "Low rework", False),
    ("ITERATION_DEPTH_P90_TARGET", 6.0, "Engineering", "Clean iteration", True),
    ("ITERATION_DEPTH_P90_DECAY_SPAN", 1, "Engineering", "Clean iteration", False),
    ("FILES_HAMMERED_PER_SESSION_TARGET", 0.01, "Engineering", "Focus", True),
    ("QUALITY_CEREMONY_PER_SESSION_TARGET", 100.0, "Engineering", "Quality ceremony", True),
    ("ERROR_RATE_PER_100_TOOLS_TARGET", 5.0, "Engineering", "Low errors", True),
    ("EVIDENCE_SATURATION_TOOL_CALLS", 50, "Engineering", "Low rework", False),
)

AQ_SENSITIVITY_CASES = (
    ("LINKED_ROUTING_SUCCESS_RATE_TARGET", 0.80, "Savvy", "Model mix"),
    ("API_RETRIES_PER_100_TOOLS_TARGET", 1.0, "Efficiency", "Recovery"),
    ("MODELS_DISTINCT_CEILING", 1, "Savvy", "Model mix"),
    ("OFFLOAD_SHARE_TARGET", 0.40, "Savvy", "Model mix"),
    ("CLI_SHARE_TARGET", 1.0, "Savvy", "Token economy"),
)

PUBLISHED_GSTACK_TARGET_TYPES = (
    ("EXECUTION_OUTPUT_LINES_PER_HOUR_TARGET", 1000, "Tool output rate"),
    ("DELEGATION_RUNS_PER_PROMPT_TARGET", 0.30, "Delegation & parallelism"),
    ("PLANNING_EXPLORE_RATIO_TARGET", 0.65, "Explore-before-build"),
    ("THINKING_BLOCKS_PER_SESSION_TARGET", 12.0, "Reasoning depth"),
    ("ITERATION_DEPTH_MEAN_TARGET", 2.0, "Low rework"),
    ("ITERATION_DEPTH_P90_TARGET", 3.0, "Clean iteration"),
    ("FILES_HAMMERED_PER_SESSION_TARGET", 0.25, "Focus"),
    ("QUALITY_CEREMONY_PER_SESSION_TARGET", 3.0, "Quality ceremony"),
    ("ERROR_RATE_PER_100_TOOLS_TARGET", 10.0, "Low errors"),
)


def _breakdown_sub(breakdown, label):
    return next(sub for axis in breakdown.values() for sub in axis["subs"]
                if sub["label"] == label)


def _aq_axis(aq_result, pillar_name, axis_name):
    pillar = next(p for p in aq_result["pillars"] if p["name"] == pillar_name)
    return next(axis for axis in pillar["axes"] if axis["name"] == axis_name)


def _zero_activity_stats():
    stats = _v5_scoring_stats()
    stats["volume"]["total_sessions"] = 0
    stats["volume"]["tool_calls_total"] = 0
    return stats


class TestGstackCalibrationConstants(unittest.TestCase):
    def test_patched_gstack_constants_move_owning_score_and_breakdown(self):
        for name, patched_value, axis_name, sub_label, published in GSTACK_SENSITIVITY_CASES:
            with self.subTest(constant=name):
                baseline_stats = _v5_scoring_stats()
                # Inverse engineering terms are evidence-gated. Use a well-populated
                # corpus to expose target movement; keep the saturation row thin so its
                # own denominator change is what the test observes.
                if name != "EVIDENCE_SATURATION_TOOL_CALLS":
                    baseline_stats["volume"]["tool_calls_total"] = 2000
                baseline_scores = compute_scores(baseline_stats)
                baseline_breakdown = score_breakdown(baseline_stats)
                zero_stats = _zero_activity_stats()
                with mock.patch.object(gstack, name, patched_value):
                    scores = compute_scores(deepcopy(baseline_stats))
                    breakdown = score_breakdown(deepcopy(baseline_stats))
                    self.assertNotEqual(scores[axis_name], baseline_scores[axis_name])
                    self.assertNotEqual(
                        _breakdown_sub(breakdown, sub_label)["pct"],
                        _breakdown_sub(baseline_breakdown, sub_label)["pct"],
                    )
                    if published:
                        self.assertEqual(
                            _breakdown_sub(breakdown, sub_label)["target"], patched_value)
                        zero = score_breakdown(deepcopy(zero_stats))
                        self.assertEqual(
                            _breakdown_sub(zero, sub_label)["target"], patched_value)


class TestAqCalibrationConstants(unittest.TestCase):
    def test_patched_aq_constants_move_owning_axis(self):
        baseline_stats = _v5_scoring_stats()
        baseline = compute_aq(baseline_stats)
        routing_stats = deepcopy(baseline_stats)
        routing_stats["behavior"].update({
            "linked_model_routing_state": "measured",
            "linked_model_pairs": [
                {"completed": True, "provider": "openai", "lead_model": "gpt-5.4",
                 "child_model": "mini", "writes": 1},
                {"completed": True, "provider": "openai", "lead_model": "mini",
                 "child_model": "pro", "writes": 1},
            ],
        })

        for name, patched_value, pillar_name, axis_name in AQ_SENSITIVITY_CASES:
            with self.subTest(constant=name):
                stats = deepcopy(routing_stats if name == "LINKED_ROUTING_SUCCESS_RATE_TARGET"
                                 else baseline_stats)
                with mock.patch.object(aq, name, patched_value):
                    actual = _aq_axis(compute_aq(stats), pillar_name, axis_name)
                expected = _aq_axis(
                    compute_aq(routing_stats if name == "LINKED_ROUTING_SUCCESS_RATE_TARGET"
                               else baseline_stats),
                    pillar_name, axis_name)
                self.assertNotEqual(actual["score"], expected["score"])


class TestPublishedTargetTypesAreUnchanged(unittest.TestCase):
    def test_live_breakdown_targets_keep_published_json_types(self):
        live = score_breakdown(_v5_scoring_stats())
        for name, expected, label in PUBLISHED_GSTACK_TARGET_TYPES:
            with self.subTest(constant=name, path="live"):
                self.assertEqual(repr(getattr(gstack, name)), repr(expected))
                self.assertEqual(repr(_breakdown_sub(live, label)["target"]), repr(expected))

    def test_zero_axis_targets_keep_published_json_types(self):
        zero = score_breakdown(_zero_activity_stats())
        for name, expected, label in PUBLISHED_GSTACK_TARGET_TYPES:
            with self.subTest(constant=name, path="zero"):
                self.assertEqual(repr(getattr(gstack, name)), repr(expected))
                self.assertEqual(repr(_breakdown_sub(zero, label)["target"]), repr(expected))


if __name__ == "__main__":
    unittest.main()
