"""The blend must read the SAME calibration constants the scorer does.

`aggregate.blend_model_mix_components` used to carry its own copies of AQ's Model mix
targets as bare literals. That is the exact defect the calibration fingerprint exists to
prevent, one module further out: a retune of `MODELS_DISTINCT_CEILING` or
`OFFLOAD_SHARE_TARGET` moves every AQ the scorer computes and moves the fingerprint,
while a private copy here keeps scoring against the stale value -- publishing numbers
that disagree with the live scorer under a contract id claiming they are comparable.

SCOPE, stated honestly: this blend is REPLAY-ONLY since v11. `_blend_profiles`'s
docstring is explicit that a live run supplies no bucket components, so `score_by_source`
never reaches it. It is still reachable when `gnomon/scoring/replay.py` is handed a
pre-v11 payload carrying `bucket_scoring_inputs`, which is data gnomon already published
and still promises to reproduce. Lower stakes than a live path, not zero.

These tests pin the coupling by MOVING the constant and requiring the blend to follow.
A copied literal cannot pass them.
"""
import unittest
from unittest import mock

from gnomon.scoring import aq as aq_module
from gnomon.scoring import aggregate as aggregate_module
from gnomon.scoring.aggregate import blend_model_mix_components


def _components(distinct_models, offload_share):
    """One fully-measured source, so the blend reduces to the two target terms."""
    return [(1.0, {"distinct_models": distinct_models,
                   "offload_share": offload_share,
                   "routing": {"state": "measured", "score": 1.0}})]


class TestBlendReadsTheRegisteredModelMixTargets(unittest.TestCase):
    # (constant name, signal key, a value BELOW the shipped target, the raised target)
    CASES = (
        ("MODELS_DISTINCT_CEILING", "distinct_models", 3, 6),
        ("OFFLOAD_SHARE_TARGET", "offload_share", 0.30, 0.60),
    )

    def test_raising_a_target_lowers_the_blended_score(self):
        for name, signal, at_target, raised in self.CASES:
            with self.subTest(constant=name):
                signals = {"distinct_models": aq_module.MODELS_DISTINCT_CEILING,
                           "offload_share": aq_module.OFFLOAD_SHARE_TARGET}
                signals[signal] = at_target
                baseline = blend_model_mix_components(
                    _components(signals["distinct_models"], signals["offload_share"]))
                with mock.patch.object(aq_module, name, raised):
                    moved = blend_model_mix_components(
                        _components(signals["distinct_models"], signals["offload_share"]))
                self.assertLess(
                    moved, baseline,
                    f"{name} moved but the blend did not follow -- aggregate.py is still "
                    f"scoring against its own copy of the literal")

    def test_the_blend_saturates_exactly_at_the_registered_target(self):
        """At the target the term is full marks; a hair below it is not."""
        full = blend_model_mix_components(
            _components(aq_module.MODELS_DISTINCT_CEILING, aq_module.OFFLOAD_SHARE_TARGET))
        under = blend_model_mix_components(
            _components(aq_module.MODELS_DISTINCT_CEILING - 1,
                        aq_module.OFFLOAD_SHARE_TARGET))
        self.assertEqual(full, 1.0)
        self.assertLess(under, full)

    def test_overshooting_the_target_does_not_exceed_full_marks(self):
        """Without this, dropping the `min(1.0, ...)` clamp still passes the test above:
        every case there sits AT or BELOW the target, so the clamp never engages."""
        over = blend_model_mix_components(
            _components(aq_module.MODELS_DISTINCT_CEILING * 100,
                        min(1.0, aq_module.OFFLOAD_SHARE_TARGET * 3)))
        self.assertEqual(over, 1.0)

    def test_the_registered_values_are_pinned_by_value_and_type(self):
        """`assertEqual(3, 3.0)` passes, so equality alone would not notice a retype that
        changes what downstream publishes. Pin `repr`, which distinguishes them."""
        self.assertEqual(repr(aq_module.MODELS_DISTINCT_CEILING), "3")
        self.assertEqual(repr(aq_module.OFFLOAD_SHARE_TARGET), "0.3")

    def test_aggregate_reads_the_live_module_not_a_bound_copy(self):
        """`from aq import X` binds a COPY of the reference at import time, so patching the
        registered constant would move compute_aq and leave this blend on the stale value.
        Reading through the module object is what makes the coupling hold at runtime, and
        it is the same technique calibration.py's `_registered_value` uses."""
        self.assertIs(aggregate_module._aq, aq_module)
        for name in ("MODELS_DISTINCT_CEILING", "OFFLOAD_SHARE_TARGET"):
            with self.subTest(constant=name):
                self.assertFalse(
                    name in vars(aggregate_module),
                    f"{name} is bound directly in aggregate.py -- that is a copy of the "
                    f"reference, and a retune would not reach the blend at runtime")


if __name__ == "__main__":
    unittest.main()
