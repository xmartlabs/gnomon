"""AQ rate denominators: tool calls, not sessions.

`compute_aq`'s `rate()` used to divide a corpus-pooled count by the corpus-pooled SESSION
count. On a mixed corpus that is a volume artifact: 540 one-shot `codex exec` sessions of
~2.7 active minutes each weigh exactly as much in the denominator as a 37-minute Claude
session, so they act as near-pure denominator and collapse every rate. Measured on a real
three-source corpus, Verification scored 34.4/35 on the Claude slice alone and 22.9/35 on
the merged corpus — same behavior, different session mix.

The fix pools numerator and denominator over the SAME unit: `Σ x / Σ tool_calls`. A session
is not a unit of work; a tool call is the unit every adapter records exactly, so the ratio
is a quantity and the pooled rate is always the tool-call-share-weighted mean of the
per-source rates. That makes the "one quiet source drags the corpus below its own worst
slice" inversion impossible by construction — no per-source weighting needed.

These tests pin the arithmetic of every converted term, the segmentation-indifference that
was the point of the change, the betweenness guarantee, the zero-activity fail-closed, and
the published denominator that makes a moved score explainable.
"""
import copy
import unittest

from gnomon.scoring.aq import (
    COMPOUNDING_WRITES_PER_CALL_TARGET, RATE_MIN_EXPECTED_AT_TARGET,
    REVIEW_SKILLS_PER_CALL_TARGET, SKILLS_TOTAL_PER_CALL_TARGET,
    TASK_CALLS_PER_CALL_TARGET, TEST_RUNS_PER_CALL_TARGET,
    TOOLSEARCH_PER_CALL_TARGET, compute_aq,
)

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


def _signals(stats, pillar, axis):
    return _axis(compute_aq(stats), pillar, axis)["signals"]


# One long-session source (Claude-shaped) and one many-tiny-sessions source
# (codex-shaped: 90 sessions carrying a ninth of the tool volume).
LONG = _block(source="claude", sessions=10, tool_calls=900, test_runs=12,
              review_uses=6, task_skill_uses=3, other_skill_uses=51,
              skills_distinct=8, toolsearch=2, task_tool=3, compounding=2,
              cli_calls=700, mcp_calls=200, mcp_servers=3, clis=4)
TINY = _block(source="codex", sessions=90, tool_calls=100, mcp_servers=1, clis=1,
              cli_calls=80, mcp_calls=20)
CALLS = 1000  # LONG + TINY pooled tool calls


def _sat(x, target):
    return min(1.0, x / target)


class TestRatesAreScoredPerToolCall(unittest.TestCase):
    """Every rate term is `pooled count / pooled tool calls` against a per-tool-call target."""

    def test_verification_terms_score_counts_over_tool_calls(self):
        expected = (0.5 * _sat(12 / CALLS, TEST_RUNS_PER_CALL_TARGET)
                    + 0.5 * _sat(6 / CALLS, REVIEW_SKILLS_PER_CALL_TARGET))
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Craft", "Verification"),
                               expected, places=9)

    def test_skill_fluency_scores_skills_over_tool_calls(self):
        # .40*sat(8,40) + .30*rate(60 skill uses) + .30*0.6 (no signature planning skill)
        expected = (.40 * (8 / 40)
                    + .30 * _sat(60 / CALLS, SKILLS_TOTAL_PER_CALL_TARGET)
                    + .30 * 0.6)
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Breadth", "Skill fluency"),
                               expected, places=9)

    def test_tool_command_scores_toolsearch_over_tool_calls(self):
        expected = (.40 * (3 / 15) + .40 * (4 / 40)
                    + .20 * _sat(2 / CALLS, TOOLSEARCH_PER_CALL_TARGET))
        self.assertAlmostEqual(
            _norm(_corpus([LONG, TINY]), "Breadth", "Tool command (MCP + CLI)"),
            expected, places=9)

    def test_discipline_scores_task_calls_over_tool_calls(self):
        # task_calls = task tool calls (3) + SDD task-skill uses (3)
        expected = _sat(6 / CALLS, TASK_CALLS_PER_CALL_TARGET)
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Breadth", "Discipline"),
                               expected, places=9)

    def test_compounding_scores_writes_over_tool_calls(self):
        expected = (.6 * _sat(2 / CALLS, COMPOUNDING_WRITES_PER_CALL_TARGET)
                    + .4 * 0.6)
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Craft", "Compounding"),
                               expected, places=9)

    def test_token_economy_scores_toolsearch_over_tool_calls(self):
        # cli_share = 780/1000 = 0.78 -> saturated against the 0.70 target.
        expected = .5 * _sat(2 / CALLS, TOOLSEARCH_PER_CALL_TARGET) + .5 * 1.0
        self.assertAlmostEqual(_norm(_corpus([LONG, TINY]), "Savvy", "Token economy"),
                               expected, places=9)


class TestSegmentationIndifference(unittest.TestCase):
    """The point of the change: identical work scores identically however it is cut into
    sessions. A session boundary is a UI artifact of the tool that produced it."""

    def test_splitting_the_same_work_into_ten_times_more_sessions_changes_nothing(self):
        few = _block(source="claude", sessions=10, tool_calls=900, test_runs=12,
                     review_uses=6, task_skill_uses=3, other_skill_uses=51,
                     skills_distinct=8, toolsearch=2, task_tool=3, compounding=2,
                     cli_calls=700, mcp_calls=200, mcp_servers=3, clis=4)
        many = dict(copy.deepcopy(few),
                    volume=dict(few["volume"], total_sessions=100, total_prompts=300))
        for pillar, axis in (("Craft", "Verification"), ("Craft", "Compounding"),
                             ("Breadth", "Skill fluency"), ("Breadth", "Discipline"),
                             ("Breadth", "Tool command (MCP + CLI)"),
                             ("Savvy", "Token economy")):
            with self.subTest(axis=axis):
                self.assertAlmostEqual(_norm(_corpus([few]), pillar, axis),
                                       _norm(_corpus([many]), pillar, axis), places=12)

    def test_many_tiny_sessions_no_longer_collapse_a_practised_habit(self):
        """The dilution case from the review: 90 one-shot sessions carrying a tenth of the
        tool volume must not bury the source that did the verification work."""
        merged = _norm(_corpus([LONG, TINY]), "Craft", "Verification")
        long_alone = _norm(_corpus([LONG]), "Craft", "Verification")
        self.assertGreater(merged, long_alone * 0.85)
        self.assertLessEqual(merged, long_alone)


class TestNoCrossSourceInversion(unittest.TestCase):
    """Pooling over one unit makes the corpus rate a tool-call-share-weighted mean of the
    per-source rates, so it can never fall outside the range they span."""

    def test_merged_score_is_the_tool_call_share_weighted_mean_of_per_source_scores(self):
        # Deliberately below target on both sides so nothing saturates and the identity
        # `Σx/Σc = Σ (c_s/C)·(x_s/c_s)` is visible in the SCORES, not just the rates.
        a = _block(source="claude", sessions=5, tool_calls=2000, test_runs=20)
        b = _block(source="codex", sessions=50, tool_calls=500, test_runs=10)
        term = lambda stats: _signals(stats, "Craft", "Verification")["test_runs_per_call"]
        rate_a, rate_b = term(_corpus([a])), term(_corpus([b]))
        merged = term(_corpus([a, b]))
        self.assertAlmostEqual(merged, 0.8 * rate_a + 0.2 * rate_b, places=12)
        self.assertGreaterEqual(merged, min(rate_a, rate_b))
        self.assertLessEqual(merged, max(rate_a, rate_b))

    def test_adversarial_corpus_does_not_invert(self):
        """The case that rejected the activity-weighted-per-session design: a quiet, very
        tool-heavy source next to a source sitting exactly on target. The merged reading
        must not land BELOW what the productive source earns on its own share of the work."""
        a = _block(source="claude", sessions=5, tool_calls=2000, test_runs=0)
        b = _block(source="codex", sessions=50, tool_calls=500, test_runs=75)
        merged = _norm(_corpus([a, b]), "Craft", "Verification")
        a_alone = _norm(_corpus([a]), "Craft", "Verification")
        b_alone = _norm(_corpus([b]), "Craft", "Verification")
        self.assertGreaterEqual(merged, a_alone)
        self.assertLessEqual(merged, b_alone)
        # 75 test runs over 2500 pooled calls = 0.03/call, above the target -> full credit
        # on the test-run half of the axis. The rejected design scored this 0.1.
        self.assertAlmostEqual(merged, 0.5, places=9)


class TestFailClosedAndObservability(unittest.TestCase):
    def test_corpus_with_no_tool_activity_scores_zero_not_a_phantom_maximum(self):
        """No tool calls means no rate to read. Clamping the denominator to 1 instead would
        turn any stray count into a saturated score."""
        idle = _block(source="claude", sessions=40, tool_calls=0, test_runs=7,
                      review_uses=7)
        self.assertEqual(_norm(_corpus([idle]), "Craft", "Verification"), 0.0)

    def test_every_rate_axis_publishes_the_denominator_it_used(self):
        """A score that moved must be attributable to numerator or denominator. Only
        Discipline used to export its driver; a rate with an invisible denominator is not
        an explainable score."""
        stats = _corpus([LONG, TINY])
        for pillar, axis, key, target in (
            ("Craft", "Verification", "test_runs", TEST_RUNS_PER_CALL_TARGET),
            ("Craft", "Verification", "review_skills", REVIEW_SKILLS_PER_CALL_TARGET),
            ("Craft", "Compounding", "compounding_writes",
             COMPOUNDING_WRITES_PER_CALL_TARGET),
            ("Breadth", "Skill fluency", "skills_total", SKILLS_TOTAL_PER_CALL_TARGET),
            ("Breadth", "Discipline", "task_tool_calls", TASK_CALLS_PER_CALL_TARGET),
            ("Breadth", "Tool command (MCP + CLI)", "toolsearch",
             TOOLSEARCH_PER_CALL_TARGET),
            ("Savvy", "Token economy", "toolsearch", TOOLSEARCH_PER_CALL_TARGET),
        ):
            with self.subTest(axis=axis, key=key):
                sig = _signals(stats, pillar, axis)
                self.assertEqual(sig["tool_calls"], CALLS)
                self.assertAlmostEqual(sig[f"{key}_per_call"], sig[key] / CALLS, places=9)
                self.assertEqual(sig[f"{key}_per_call_target"], target)


class TestTargetsStayInsideTheirMeasuredBands(unittest.TestCase):
    """Pin each per-tool-call target inside the [p40, p50] band its comment cites.

    The bands are HARDCODED here on purpose. Every other test in this file imports the
    constants into its own expected values, so both sides move together and a mistyped
    target stays green — a 10x fat-finger on TEST_RUNS_PER_CALL_TARGET would surface only
    as a scoring_vectors.json diff, in the very commit that caused it, reading as
    intentional. Same convention as test_scoring_v5's band guard on
    PLANNING_PRACTICE_TARGET: pin the range the measurement supports rather than the exact
    value, so recalibration stays free but walking outside the measured population does not.
    """

    # (constant, p40, p50, n) exactly as documented at aq.py's module top. The two skill
    # bands are the 9:9:9 POST-dedup projection; the other four are the v7 pre-dedup
    # measurement, unchanged because the dedup moved numerators and not the shared
    # denominator (aq.py records that decision and the re-measured drift).
    BANDS = (
        ("skills_total", SKILLS_TOTAL_PER_CALL_TARGET, 0.00865, 0.00981, 16),
        ("toolsearch", TOOLSEARCH_PER_CALL_TARGET, 0.00732, 0.00773, 15),
        ("task_calls", TASK_CALLS_PER_CALL_TARGET, 0.00817, 0.01475, 13),
        ("test_runs", TEST_RUNS_PER_CALL_TARGET, 0.02219, 0.02715, 16),
        ("review_skills", REVIEW_SKILLS_PER_CALL_TARGET, 0.00338, 0.00440, 13),
        ("compounding_writes", COMPOUNDING_WRITES_PER_CALL_TARGET, 0.00170, 0.00207, 16),
    )

    def test_every_target_sits_between_its_measured_p40_and_p50(self):
        for name, value, p40, p50, n in self.BANDS:
            with self.subTest(target=name, n=n):
                self.assertGreaterEqual(value, p40)
                self.assertLessEqual(value, p50)

    def test_each_band_is_a_real_split_of_a_usable_sample(self):
        """A band only means something with the n it was drawn from. Guards against a
        later recalibration quietly pasting a narrower band or a smaller population."""
        for name, value, p40, p50, n in self.BANDS:
            with self.subTest(target=name):
                self.assertGreaterEqual(n, 13, "n < 13 cannot support a p40/p50 split")
                self.assertLess(p40, p50, "p40 must sit below p50")


class TestRateEvidenceFloorDropsNoiseInsteadOfSaturating(unittest.TestCase):
    """A rate term is `min(1, x / (tool_calls · target))`, so it maxes out at
    x = tool_calls · target. Once that product falls to 1, ONE occurrence saturates the
    term — the same failure mode `MIN_ELIGIBLE_SESSIONS` already fixes for the two
    session-share terms ("one planning-skill invocation maxed the term forever").

    The v9 re-fit is what made it reachable: SKILLS_TOTAL_PER_CALL_TARGET 0.25 -> 0.009
    moved the boundary from tool_calls <= 4 (unreachable) to <= 111, and
    REVIEW_SKILLS_PER_CALL_TARGET 0.060 -> 0.004 from <= 16 to <= 250. Below the floor the
    term must be DROPPED (None -> wsum renormalizes), never scored.
    """

    # 100 tool calls over 2 sessions: below the implied floor for skills_total (>111),
    # review_skills (>250) and compounding_writes (>556); above it for test_runs (>40)
    # and task calls (>91). One occurrence of each thin signal is exactly the pathology.
    THIN = dict(source="claude", sessions=2, tool_calls=100)

    def test_one_skill_use_in_a_thin_corpus_drops_the_term_instead_of_maxing_it(self):
        thin = _corpus([_block(**self.THIN, other_skill_uses=1, skills_distinct=1)])
        self.assertIsNone(_signals(thin, "Breadth", "Skill fluency")["skills_total_per_call"],
                          "a rate the scorer refused must not be published as a number")
        # The two surviving terms, renormalized over their own weights (.40 + .30).
        expected = (.40 * (1 / 40) + .30 * 0.6) / 0.70
        self.assertAlmostEqual(_norm(thin, "Breadth", "Skill fluency"), expected, places=9)
        # What it replaces: 1 use / 100 calls = 0.010/call is 111% of the 0.009 target, so
        # the old code credited the full .30 weight on a single skill invocation.
        phantom = .40 * (1 / 40) + .30 * 1.0 + .30 * 0.6
        self.assertLess(_norm(thin, "Breadth", "Skill fluency"), phantom)

    def test_one_review_use_in_a_thin_corpus_leaves_the_axis_on_its_measurable_half(self):
        thin = _corpus([_block(**self.THIN, review_uses=1, test_runs=2)])
        sig = _signals(thin, "Craft", "Verification")
        self.assertIsNone(sig["review_skills_per_call"])
        self.assertIsNotNone(sig["test_runs_per_call"],
                             "test_runs' own floor is 40 calls — it stays measurable here")
        # Renormalized onto the one live term (test runs), NOT half a phantom 1.0.
        self.assertAlmostEqual(_norm(thin, "Craft", "Verification"),
                               _sat(2 / 100, TEST_RUNS_PER_CALL_TARGET), places=9)
        self.assertLess(_norm(thin, "Craft", "Verification"),
                        .5 * _sat(2 / 100, TEST_RUNS_PER_CALL_TARGET) + .5 * 1.0)

    def test_a_corpus_above_the_floor_scores_exactly_as_before(self):
        """The floor must not touch a corpus that carries real evidence: same counts, a
        denominator above every implied floor, and both halves score normally."""
        thick = _corpus([_block(source="claude", sessions=12, tool_calls=900,
                                review_uses=4, test_runs=12)])
        sig = _signals(thick, "Craft", "Verification")
        self.assertIsNotNone(sig["review_skills_per_call"])
        expected = (.5 * _sat(12 / 900, TEST_RUNS_PER_CALL_TARGET)
                    + .5 * _sat(4 / 900, REVIEW_SKILLS_PER_CALL_TARGET))
        self.assertAlmostEqual(_norm(thick, "Craft", "Verification"), expected, places=9)

    def test_a_measured_zero_denominator_keeps_its_existing_fail_closed_zero(self):
        """The floor only applies where a rate is computable at all. Zero tool calls stays
        the deliberate 0.0 of TestFailClosedAndObservability above (no numerator can
        saturate a term that is never divided), so that decision is not silently reversed."""
        idle = _corpus([_block(source="claude", sessions=40, tool_calls=0, test_runs=7,
                               review_uses=7)])
        self.assertEqual(_norm(idle, "Craft", "Verification"), 0.0)


class TestRateEvidenceFloorIsCalibratedFromThePopulation(unittest.TestCase):
    """The floor is expressed in occurrences-implied-by-the-target, not in tool calls, so
    it cannot drift out from under a re-fit (a hardcoded call count would silently stop
    covering any target later re-fitted downwards — the exact bug under repair).

    Hardcoded here, like the band guard above: both bounds come from the population, so a
    later value change has to come and re-argue them.
    """

    # Smallest of the 16 real 6-month corpora in .context/population-pre-dedup.psv,
    # pooled across every source the user runs: 2,036 tool calls over 17 sessions
    # (119.8 calls/session).
    SMALLEST_REAL_CORPUS_TOOL_CALLS = 2036

    def test_the_floor_is_at_least_the_single_occurrence_invariant(self):
        """Below 1.0 a single occurrence can still max a term, which is the whole finding."""
        self.assertGreaterEqual(RATE_MIN_EXPECTED_AT_TARGET, 1.0)

    def test_the_floor_moves_no_real_corpus(self):
        """Every rate term of the LIGHTEST real corpus must stay scored. The tightest
        target (compounding, 0.0018) is what binds: 2036 · 0.0018 = 3.66, so the data
        permits [1.0, 3.66) and anything at or above 3.66 would start dropping terms for a
        real, uploaded user."""
        for name, target, _p40, _p50, _n in (
                TestTargetsStayInsideTheirMeasuredBands.BANDS):
            with self.subTest(target=name):
                self.assertLess(RATE_MIN_EXPECTED_AT_TARGET,
                                self.SMALLEST_REAL_CORPUS_TOOL_CALLS * target)

    def test_each_target_implies_the_documented_minimum_denominator(self):
        """The floor a reader can check against aq.py's comment block."""
        implied = {name: RATE_MIN_EXPECTED_AT_TARGET / target
                   for name, target, _p40, _p50, _n in
                   TestTargetsStayInsideTheirMeasuredBands.BANDS}
        for name, calls in (("skills_total", 111), ("toolsearch", 133),
                            ("task_calls", 90), ("test_runs", 40),
                            ("review_skills", 250), ("compounding_writes", 555)):
            with self.subTest(target=name):
                self.assertAlmostEqual(implied[name], calls, delta=1.0)


if __name__ == "__main__":
    unittest.main()
