"""Bloque — pooling `actions_per_prompt` across sources weights it by its own DENOMINATOR.

`gnomon/scoring/aggregate.py::_synth_stats_for_aggregate` blends the per-source `behavior`
fields into a synthetic corpus so the aggregate's narrative pickers read numbers consistent
with the combined score. Nearly every field there is either a sum or a tool-volume-weighted
mean, and `wmean`'s single weight is `tool_calls_total` for all of them.

That was right for `actions_per_prompt` only while the field's own denominator WAS the tool
count's population. It is not, and since v12 it is not even close: the numerator counts
TOP-LEVEL calls while `tool_calls_total` stays deliberately sidechain-inclusive, so a
delegation-heavy source carries a large weight and a small value at the same time. The
weighted mean then sits far below the true pooled ratio.

The fix is not a different constant, it is the identity that makes a weighted mean of ratios
equal the pooled ratio:

    sum_i ( d_i * (n_i / d_i) ) / sum_i d_i  ==  sum_i n_i / sum_i d_i

which holds exactly when the weight IS each source's denominator. For this field that is
`volume.total_instructions`, so pooling becomes exact rather than merely less wrong.

Containment, recorded because it bounds how much this matters: `compute_aq` is never run on
the synth block (`_aggregate_profile` passes it the already-combined `agg_aq`), so the
published AQ does not move. What reads the pooled value is `steering_reading` and the
`score_breakdown` sub-percentages.
"""
import unittest

from gnomon.scoring.aggregate import _synth_stats_for_aggregate


def _block(prompts, instructions, top_level, sidechain, app):
    """A per-source window block carrying only what this pooling reads."""
    return {
        "volume": {"total_sessions": 5, "total_prompts": prompts,
                   "total_instructions": instructions,
                   "tool_calls_total": top_level + sidechain,
                   "sidechain_tool_calls": sidechain, "thinking_blocks": 0},
        "velocity": {}, "stack": {}, "tools": {},
        "behavior": {"actions_per_prompt": app,
                     "planning_ratio_explore_to_doing": 0.5},
    }


def _items(*blocks):
    """`_synth_stats_for_aggregate`'s input shape: [(source, {weight, block, profile}), ...].

    `weight` is what `score_by_source` computes -- the source's `tool_calls_total` -- and is
    left exactly that on purpose: the point of this contract is that ONE field stops using it,
    not that the aggregate weight changes for everything."""
    return [
        (f"src{i}", {"weight": (b["volume"]["tool_calls_total"]), "block": b,
                     "profile": {"aq": {"aq_0_100": 50, "pillars": []},
                                 "scores": {axis: {"value": 5.0} for axis in
                                            ("execution", "planning", "engineering")}}})
        for i, b in enumerate(blocks)
    ]


_AGG_AQ = {"aq_0_100": 50, "tier": "Adequate", "pillars": []}


class TestPooledActionsPerPromptUsesThePromptWeight(unittest.TestCase):
    # The reviewer's worked example. A: 10 instructions, 100 top-level, 0 sidechain -> 10.0.
    # B: 10 instructions, 10 top-level, 990 sidechain -> 1.0. Tool weights are 100 and 1000.
    _A = _block(prompts=10, instructions=10, top_level=100, sidechain=0, app=10.0)
    _B = _block(prompts=10, instructions=10, top_level=10, sidechain=990, app=1.0)

    def test_the_pooled_value_is_the_true_pooled_ratio(self):
        """(100 + 10) top-level calls over (10 + 10) instructions = 5.5.

        Weighted by `tool_calls_total` this read (100*10 + 1000*1) / 1100 = 1.82 -- a 3x
        understatement, and in the direction that matters: it pushes the reading down the
        Steering band's low-end ramp, so the aggregate narrative could report hand-holding for
        a corpus that pooled to a healthy 5.5."""
        synth = _synth_stats_for_aggregate(_items(self._A, self._B), _AGG_AQ)
        self.assertEqual(synth["behavior"]["actions_per_prompt"], 5.5)

    def test_the_tool_volume_weight_would_have_given_the_wrong_answer(self):
        """Pins the defect's magnitude rather than trusting the fix's own arithmetic: if the
        weight were still `tool_calls_total`, the same blocks would pool to 1.8."""
        items = _items(self._A, self._B)
        tool_weighted = sum(e["weight"] * e["block"]["behavior"]["actions_per_prompt"]
                            for _, e in items) / sum(e["weight"] for _, e in items)
        self.assertEqual(round(tool_weighted, 1), 1.8)
        synth = _synth_stats_for_aggregate(items, _AGG_AQ)
        self.assertNotEqual(synth["behavior"]["actions_per_prompt"],
                            round(tool_weighted, 1))

    def test_pooling_is_exact_for_an_arbitrary_split(self):
        """The weight-is-the-denominator identity is exact, not a closer approximation, so it
        must reproduce the pooled ratio for any split -- including uneven instruction counts,
        which is where a mean of ratios normally diverges from a ratio of sums."""
        a = _block(prompts=40, instructions=40, top_level=520, sidechain=30, app=13.0)
        b = _block(prompts=7, instructions=7, top_level=21, sidechain=4000, app=3.0)
        c = _block(prompts=1, instructions=1, top_level=88, sidechain=0, app=88.0)
        synth = _synth_stats_for_aggregate(_items(a, b, c), _AGG_AQ)
        pooled = (520 + 21 + 88) / (40 + 7 + 1)
        self.assertEqual(synth["behavior"]["actions_per_prompt"], round(pooled, 1))

    def test_a_source_with_no_instructions_contributes_no_weight(self):
        """A source that recorded no human instruction has no ratio to contribute. It must not
        drag the pooled value toward its own 0, which is exactly what a tool-volume weight did
        -- it could carry thousands of calls and still no instruction."""
        live = _block(prompts=10, instructions=10, top_level=120, sidechain=0, app=12.0)
        empty = _block(prompts=0, instructions=0, top_level=0, sidechain=5000, app=0)
        synth = _synth_stats_for_aggregate(_items(live, empty), _AGG_AQ)
        self.assertEqual(synth["behavior"]["actions_per_prompt"], 12.0)

    def test_a_single_source_pools_to_its_own_reading(self):
        only = _block(prompts=9, instructions=11, top_level=77, sidechain=12, app=7.0)
        synth = _synth_stats_for_aggregate(_items(only), _AGG_AQ)
        self.assertEqual(synth["behavior"]["actions_per_prompt"], 7.0)

    def test_a_legacy_block_without_the_denominator_falls_back_to_prompts(self):
        """A pre-v12 block carries no `total_instructions`. Its own ratio was built by dividing
        by `total_prompts`, so that is the weight which reconstructs it -- falling back to 0
        would silently drop the source from the pool entirely."""
        legacy = {"volume": {"total_sessions": 4, "total_prompts": 20,
                             "tool_calls_total": 400, "thinking_blocks": 0},
                  "velocity": {}, "stack": {}, "tools": {},
                  "behavior": {"actions_per_prompt": 20.0,
                               "planning_ratio_explore_to_doing": 0.5}}
        other = _block(prompts=20, instructions=20, top_level=200, sidechain=0, app=10.0)
        synth = _synth_stats_for_aggregate(_items(legacy, other), _AGG_AQ)
        self.assertEqual(synth["behavior"]["actions_per_prompt"], 15.0)

    def test_the_other_behavior_means_keep_the_tool_volume_weight(self):
        """Scoped change. Only `actions_per_prompt` has a per-source denominator that the tool
        count misrepresents; the other `wmean` fields are per-tool-call quantities for which
        tool volume IS the right weight, and re-weighting them would be an unmeasured
        recalibration smuggled in beside a bug fix."""
        a = _block(prompts=10, instructions=10, top_level=100, sidechain=0, app=10.0)
        b = _block(prompts=10, instructions=10, top_level=10, sidechain=990, app=1.0)
        a["behavior"]["planning_ratio_explore_to_doing"] = 1.0
        b["behavior"]["planning_ratio_explore_to_doing"] = 0.0
        synth = _synth_stats_for_aggregate(_items(a, b), _AGG_AQ)
        # tool-volume weighted: (100*1.0 + 1000*0.0) / 1100 = 0.0909 -> 0.09.
        # An instruction weight would have made this 0.5.
        self.assertEqual(synth["behavior"]["planning_ratio_explore_to_doing"], 0.09)

    def test_the_combination_block_still_declares_the_aggregate_rule_honestly(self):
        """`aggregate.combination.weight` is the documented contract mirdash mirrors in TS. It
        must not keep claiming a single tool-volume weight now that one field departs from
        it."""
        from gnomon.scoring.aggregate import _aggregate_profile
        per_source = dict(_items(self._A, self._B))
        aggregate = _aggregate_profile(per_source)
        combination = aggregate["combination"]
        self.assertEqual(combination["weight"], "tool_calls_total")
        self.assertEqual(
            combination["weight_exceptions"],
            {"behavior.actions_per_prompt": "total_instructions"})


if __name__ == "__main__":
    unittest.main()
