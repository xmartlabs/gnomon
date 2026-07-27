"""Activity-weighted rate denominators for AQ's per-session rate terms.

`compute_aq`'s `rate()` used to divide a corpus-pooled count by the corpus-pooled session
count. On a mixed corpus that is a volume artifact: 540 one-shot `codex exec` sessions of
~2.7 active minutes each weigh exactly as much in the denominator as a 37-minute Claude
session, so they act as near-pure denominator and collapse every rate. Measured on a real
three-source corpus, Verification scored 34.4/35 on the Claude slice alone and 22.9/35 on
the merged corpus — same behavior, different session mix.

The fix scores the TOOL-VOLUME-weighted mean of the PER-SOURCE rates instead, reusing the
same activity weight `gnomon.scoring.aggregate` already combines per-source scores with.
These tests pin the arithmetic of every converted term, the single-source no-op, the
capability guard, and the fail-closed fallbacks.
"""
import copy
import unittest

from gnomon.scoring.aq import compute_aq

# Planning practice deliberately reports "unmeasured" in these fixtures (all six selector
# fields present, empty denominator) so AQ's Discipline axis keeps exactly ONE live term —
# the task-tool rate — and its expected value stays hand-computable.
_UNMEASURED_PLANNING = {
    "planning_skill_sessions": 0,
    "planning_skill_eligible_sessions": 0,
    "planning_skill_unmeasured_sessions": 0,
    "planning_skill_session_scope_state": "unmeasured",
    "planning_skill_session_share": None,
    "planning_skill_session_coverage": None,
}
_MODELS = [["model-a", 30], ["model-b", 10]]


def _block(*, source, sessions, tool_calls, test_runs=0, review_uses=0,
           task_skill_uses=0, other_skill_uses=0, skills_distinct=0, toolsearch=0,
           task_tool=0, compounding=0, cli_calls=0, mcp_calls=0, mcp_servers=0,
           clis=0):
    """One source's scoring-input `window` block, in build_scoring_inputs' shape."""
    skills = []
    if review_uses:
        skills.append(["code-review", review_uses])
    if task_skill_uses:
        skills.append(["sdd-tasks", task_skill_uses])
    if other_skill_uses:
        skills.append(["some-plain-skill", other_skill_uses])
    return {
        "source": source,
        "volume": {"total_sessions": sessions, "total_prompts": sessions * 3,
                   "tool_calls_total": tool_calls, "thinking_blocks": 0},
        "velocity": {"active_hours": 10.0, "tool_churn_edit_write": 1000,
                     "shell_authored_lines_est": 100},
        "behavior": dict(
            _UNMEASURED_PLANNING,
            planning_ratio_explore_to_doing=0.5, actions_per_prompt=8.0,
            questions_asked=1, error_recovery_ratio=0.5,
            error_rate_per_100_tools=2.0, api_errors_retries=0,
            fanout_median=1, max_session_fanout=1, parallel_dispatch_turns=0,
            delegating_sessions=1, parallel_session_share=0.0,
            shell_test_runs=test_runs, plan_sessions=0,
            eligible_change_sessions=0, planned_eligible_sessions=0,
            evidence_eligible_sessions=0, ordered_facts_state="unmeasured",
            linked_model_pairs=[], linked_model_routing_state="unsupported",
            delegate_actions=1, background_tasks=0, iteration_depth_mean=2.0,
            iteration_depth_p90=3, iteration_depth_max=4,
            files_hammered_over_15x=0, no_tool_activity=False,
            orchestratable_sessions=0, delegated_orchestratable_sessions=0),
        "stack": {
            "skills_distinct": skills_distinct,
            "skills_total": sum(n for _, n in skills),
            "compounding_writes": compounding,
            "subagent_types_distinct": 1, "max_session_subagent_types": 1,
            "subagent_types": [], "top_skills": [list(p) for p in skills],
            "skills_all": [list(p) for p in skills],
            "models": copy.deepcopy(_MODELS),
        },
        "tools": {
            "agent_calls": 1, "mcp_servers_distinct": mcp_servers,
            "clis_distinct": clis, "toolsearch_calls": toolsearch,
            "task_tool_calls": task_tool, "cli_calls": cli_calls,
            "mcp_calls": mcp_calls, "tool_diversity": 5,
            "tool_entropy_normalized": 0.5, "mcp_knowledge_calls": 0,
            "mcp_knowledge_servers": 0, "mcp_knowledge_server_names": [],
            "mcp_grounded_sessions": 0, "mcp_write_sessions": 0,
            "mcp_subcategory_breakdown": {}, "top_tools": [],
        },
        "token_usage": {"by_model": []},
    }


def _corpus(blocks, per_source=True):
    """The merged-corpus stats dict `compute_aq` reads, pooled from `blocks` exactly the
    way the whole-corpus accumulator pools them (counts summed, sessions summed)."""
    def s(section, field):
        return sum((b[section] or {}).get(field, 0) for b in blocks)

    merged_skills = {}
    for b in blocks:
        for name, n in b["stack"]["skills_all"]:
            merged_skills[name] = merged_skills.get(name, 0) + n
    stats = {
        "corpus": {"sources": {b["source"]: {} for b in blocks}},
        "volume": {"total_sessions": s("volume", "total_sessions"),
                   "total_prompts": s("volume", "total_prompts"),
                   "tool_calls_total": s("volume", "tool_calls_total"),
                   "thinking_blocks": 0},
        "velocity": {"active_hours": s("velocity", "active_hours"),
                     "tool_churn_edit_write": s("velocity", "tool_churn_edit_write"),
                     "shell_authored_lines_est": s("velocity", "shell_authored_lines_est")},
        "behavior": dict(blocks[0]["behavior"], shell_test_runs=s("behavior", "shell_test_runs")),
        "stack": {
            "skills_distinct": s("stack", "skills_distinct"),
            "skills_total": s("stack", "skills_total"),
            "compounding_writes": s("stack", "compounding_writes"),
            "subagent_types_distinct": 1, "max_session_subagent_types": 1,
            "skills_all": [[k, n] for k, n in merged_skills.items()],
            "top_skills": [[k, n] for k, n in merged_skills.items()],
            "models": copy.deepcopy(_MODELS),
        },
        "tools": {
            "mcp_servers_distinct": max(b["tools"]["mcp_servers_distinct"] for b in blocks),
            "clis_distinct": max(b["tools"]["clis_distinct"] for b in blocks),
            "toolsearch_calls": s("tools", "toolsearch_calls"),
            "task_tool_calls": s("tools", "task_tool_calls"),
            "cli_calls": s("tools", "cli_calls"), "mcp_calls": s("tools", "mcp_calls"),
            "tool_diversity": 5, "tool_entropy_normalized": 0.5,
            "mcp_knowledge_calls": 0, "mcp_knowledge_servers": 0,
            "mcp_grounded_sessions": 0, "mcp_write_sessions": 0,
        },
    }
    if per_source:
        stats["scoring_inputs_by_source"] = {
            b["source"]: {"window": copy.deepcopy(b), "monthly": []} for b in blocks}
    return stats


def _axis(aq, pillar, axis):
    p = next(p for p in aq["pillars"] if p["name"] == pillar)
    return next(a for a in p["axes"] if a["name"] == axis)


def _norm(stats, pillar, axis):
    return _axis(compute_aq(stats), pillar, axis)["normalized_score"]


# One long-session source (Claude-shaped) and one many-tiny-sessions source
# (codex-shaped: 90 sessions carrying a ninth of the tool volume).
LONG = _block(source="claude", sessions=10, tool_calls=900, test_runs=12,
              review_uses=6, task_skill_uses=3, other_skill_uses=51,
              skills_distinct=8, toolsearch=2, task_tool=3, compounding=2,
              cli_calls=700, mcp_calls=200, mcp_servers=3, clis=4)
TINY = _block(source="codex", sessions=90, tool_calls=100, mcp_servers=1, clis=1,
              cli_calls=80, mcp_calls=20)
# Weights are tool volume: 900/1000 and 100/1000.
W_LONG, W_TINY = 0.9, 0.1


class TestActivityWeightedRates(unittest.TestCase):
    """Every converted rate term scores the tool-volume-weighted mean of per-source rates."""

    def test_verification_terms_score_the_weighted_mean_of_per_source_rates(self):
        # tests: 0.9 * (12/10) = 1.08 -> 1.08/1.5 = 0.72
        # review: 0.9 * (6/10)  = 0.54 -> 0.54/1.5 = 0.36   (both sources CAN record skills)
        expected = 0.5 * (W_LONG * 1.2 / 1.5) + 0.5 * (W_LONG * 0.6 / 1.5)
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Craft", "Verification"),
                               expected, places=9)

    def test_skill_fluency_scores_the_weighted_mean_of_per_source_rates(self):
        # .40*sat(8,40) + .30*sat(0.9*(60/10), 10) + .30*0.6 (no signature planning skill)
        expected = .40 * (8 / 40) + .30 * (W_LONG * 6.0 / 10) + .30 * 0.6
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Breadth", "Skill fluency"),
                               expected, places=9)

    def test_tool_command_scores_the_weighted_mean_of_per_source_toolsearch_rates(self):
        # Only claude can record ToolSearch, so codex is excluded (not weighted in as a
        # structural zero): the rate is claude's own 2/10 = 0.20 against the 0.30 target.
        expected = .40 * (3 / 15) + .40 * (4 / 40) + .20 * (0.2 / 0.30)
        self.assertAlmostEqual(
            _norm(_corpus([LONG, TINY]), "Breadth", "Tool command (MCP + CLI)"),
            expected, places=9)

    def test_discipline_scores_the_weighted_mean_of_per_source_task_rates(self):
        # task_calls is COMPUTED (task tool calls + SDD task-skill uses), so the per-source
        # extractor must recompute it per block: (3 + 3)/10 = 0.6 for claude, 0 for codex.
        expected = W_LONG * 0.6 / 1.0
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Breadth", "Discipline"),
                               expected, places=9)

    def test_compounding_scores_the_weighted_mean_of_per_source_rates(self):
        expected = .6 * (W_LONG * 0.2 / 0.25) + .4 * 0.6
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Craft", "Compounding"),
                               expected, places=9)

    def test_token_economy_scores_the_weighted_mean_of_per_source_toolsearch_rates(self):
        # cli_share = 780/1000 = 0.78 -> saturated; toolsearch as in Tool command.
        expected = .5 * (0.2 / 0.30) + .5 * 1.0
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Savvy", "Token economy"),
                               expected, places=9)

    def test_many_tiny_sessions_no_longer_collapse_the_rate(self):
        pooled = _norm(_corpus([LONG, TINY], per_source=False), "Craft", "Verification")
        weighted = _norm(_corpus([LONG, TINY]), "Craft", "Verification")
        long_source_alone = _norm(_corpus([LONG]), "Craft", "Verification")
        # Pooling over 100 sessions scores the same behavior an order of magnitude lower.
        self.assertAlmostEqual(pooled, 0.5 * (0.12 / 1.5) + 0.5 * (0.06 / 1.5), places=9)
        self.assertGreater(weighted, pooled * 5)
        # ...and the weighted number sits near the honest single-source reading.
        self.assertGreater(weighted, long_source_alone * 0.85)
        self.assertLessEqual(weighted, long_source_alone)

    def test_weight_is_tool_volume_not_session_count(self):
        """Swapping only the tool-call split moves the score; session counts are untouched."""
        flipped_long = dict(LONG, volume=dict(LONG["volume"], tool_calls_total=100))
        flipped_tiny = dict(TINY, volume=dict(TINY["volume"], tool_calls_total=900))
        self.assertLess(_norm(_corpus([flipped_long, flipped_tiny]), "Craft", "Verification"),
                        _norm(_corpus([LONG, TINY]), "Craft", "Verification"))

    def test_source_that_cannot_record_the_signal_is_excluded_not_scored_zero(self):
        """Cursor cannot emit ToolSearch at all. Weighting its zero in would fabricate a
        per-source value; the term is scored from the sources that CAN record it."""
        cursor = _block(source="cursor", sessions=90, tool_calls=100, mcp_servers=1,
                        clis=1, cli_calls=80, mcp_calls=20)
        term = (_axis(compute_aq(_corpus([LONG, cursor])), "Savvy", "Token economy")
                ["normalized_score"] - .5 * 1.0) / .5
        self.assertAlmostEqual(term, 0.2 / 0.30, places=9)


class TestSingleSourceAndFallbacks(unittest.TestCase):
    """The pooled path stays in force wherever per-source rates cannot be trusted."""

    def test_single_source_corpus_is_bit_identical_to_the_pooled_path(self):
        """The most important guarantee: no Claude-only user's score moves at all."""
        with_inputs = _corpus([LONG])
        without_inputs = _corpus([LONG], per_source=False)
        self.assertEqual(compute_aq(with_inputs), compute_aq(without_inputs))

    def test_single_source_scores_the_corpus_numbers_even_if_its_block_disagrees(self):
        """The single-source short-circuit is what makes the no-regression guarantee hold
        unconditionally. A one-source payload whose slice disagrees with the corpus totals
        (dedup, a foreign upload, a field the slice never carried) must still be scored from
        the corpus totals — otherwise "bit-identical for one source" would depend on the two
        never diverging."""
        stats = _corpus([LONG])
        stats["scoring_inputs_by_source"]["claude"]["window"]["behavior"]["shell_test_runs"] = 0
        self.assertAlmostEqual(_norm(stats, "Craft", "Verification"),
                               _norm(_corpus([LONG], per_source=False), "Craft", "Verification"),
                               places=9)

    def test_corpus_without_per_source_inputs_falls_back_to_pooled(self):
        """Legacy / external blocks predating scoring_inputs_by_source keep scoring."""
        stats = _corpus([LONG, TINY], per_source=False)
        self.assertNotIn("scoring_inputs_by_source", stats)
        self.assertAlmostEqual(_norm(stats, "Craft", "Verification"),
                               0.5 * (0.12 / 1.5) + 0.5 * (0.06 / 1.5), places=9)

    def test_malformed_per_source_block_falls_back_to_pooled_not_a_phantom_zero(self):
        pooled = _norm(_corpus([LONG, TINY], per_source=False), "Craft", "Verification")
        for label, by_source in (
            ("block is not a dict", {"claude": None, "codex": 7}),
            ("no window", {"claude": {"monthly": []}, "codex": {"monthly": []}}),
            ("window is not a dict", {"claude": {"window": 3}, "codex": {"window": 4}}),
            ("sessions missing", {"claude": {"window": {"volume": {}}},
                                  "codex": {"window": {"volume": {}}}}),
            ("sessions not a count", {"claude": {"window": {"volume": {
                                          "total_sessions": "ten", "tool_calls_total": 900}}},
                                      "codex": {"window": copy.deepcopy(TINY)}}),
            ("tool calls not a count", {"claude": {"window": {"volume": {
                                            "total_sessions": 10, "tool_calls_total": None}}},
                                        "codex": {"window": copy.deepcopy(TINY)}}),
        ):
            with self.subTest(case=label):
                stats = _corpus([LONG, TINY], per_source=False)
                stats["scoring_inputs_by_source"] = by_source
                self.assertAlmostEqual(_norm(stats, "Craft", "Verification"), pooled,
                                       places=9)

    def test_malformed_count_degrades_only_its_own_term(self):
        """A single unreadable count falls back per TERM, not per axis: the review-skill
        rate is still trustworthy when the test-run count is garbage."""
        stats = _corpus([LONG, TINY], per_source=False)
        stats["scoring_inputs_by_source"] = {
            "claude": {"window": dict(copy.deepcopy(LONG),
                                      behavior=dict(LONG["behavior"], shell_test_runs="lots"))},
            "codex": {"window": copy.deepcopy(TINY)},
        }
        expected = 0.5 * (0.12 / 1.5) + 0.5 * (W_LONG * 0.6 / 1.5)
        self.assertAlmostEqual(_norm(stats, "Craft", "Verification"), expected, places=9)

    def test_sources_without_tool_activity_fall_back_to_pooled(self):
        """Zero total weight must not silently become an unweighted mean."""
        idle_long = dict(LONG, volume=dict(LONG["volume"], tool_calls_total=0))
        idle_tiny = dict(TINY, volume=dict(TINY["volume"], tool_calls_total=0))
        stats = _corpus([idle_long, idle_tiny])
        pooled = _corpus([idle_long, idle_tiny], per_source=False)
        self.assertAlmostEqual(_norm(stats, "Craft", "Verification"),
                               _norm(pooled, "Craft", "Verification"), places=9)

    def test_source_with_no_sessions_contributes_nothing(self):
        """An empty source must neither divide by zero nor dilute the live ones."""
        empty = _block(source="cursor", sessions=0, tool_calls=0)
        expected = 0.5 * (W_LONG * 1.2 / 1.5) + 0.5 * (W_LONG * 0.6 / 1.5)
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY, empty]), "Craft", "Verification"),
                               expected, places=9)
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY, empty]), "Craft", "Verification"),
                               _norm(_corpus([LONG, TINY]), "Craft", "Verification"),
                               places=9)


class TestRecencyBucketPath(unittest.TestCase):
    """gnomon/cli/local.py hands each rolling AQ bucket its own per-source inputs
    (`bucket_stats["scoring_inputs_by_source"] = {src: {"window": <block>}}`), so the
    bucketed AQ must take the weighted path too — buckets are where a short window of
    one-shot sessions distorts a rate most."""

    def test_bucket_shaped_per_source_inputs_use_the_weighted_path(self):
        stats = _corpus([LONG, TINY], per_source=False)
        # Bucket blocks carry only "window" — no "monthly" key, unlike the window payload.
        stats["scoring_inputs_by_source"] = {
            "claude": {"window": copy.deepcopy(LONG)},
            "codex": {"window": copy.deepcopy(TINY)},
        }
        expected = 0.5 * (W_LONG * 1.2 / 1.5) + 0.5 * (W_LONG * 0.6 / 1.5)
        self.assertAlmostEqual(_norm(stats, "Craft", "Verification"), expected, places=9)


if __name__ == "__main__":
    unittest.main()
