"""Bloque — `actions_per_prompt` counts TOP-LEVEL actions only, as contract 12:12:12.

Until v12 the ratio divided `tool_use_total` (which counts sidechain/subagent tool calls)
by `prompts_count` (which explicitly excludes sidechain user turns), so the two sides of one
ratio described two different populations BY CONSTRUCTION rather than by workload. The
consequence was not cosmetic: `aq.py`'s Steering-leverage band tops out at 20 actions per
prompt and decays to zero at 60, so one delegation of 200 subagent calls from a single
prompt read as `app = 200` and scored 0.0 — the same behaviour the Orchestration axis
rewards. Measured on a real corpus the ratio read 25.3 (all sources), which is a Steering
leverage of 0.868 instead of 1.000.

v12 removes the sidechain calls from the NUMERATOR, not by adding dispatches to the
denominator: a dispatch is not a human instruction, and 200 subagent calls over 1 dispatch is
still 200 calls that the human did not individually steer. After the fix the field means what
its name says — actions taken per instruction given — and the subagent work is still measured
in Orchestration and in all six per-tool-call rate numerators (none of which is
sidechain-gated).

`volume.tool_calls_total` is deliberately UNCHANGED and stays sidechain-inclusive: it is the
denominator all six rate targets were fitted against and the cross-source aggregation weight
in `gnomon/scoring/aggregate.py`. What v12 adds beside it is `volume.sidechain_tool_calls`, a
diagnostic sibling nothing scores, so the dilution of a fully-scored term is visible in the
payload — `partial_terms` cannot express it, because that only fires when `wsum` DROPS a term.
"""
import unittest
from unittest import mock

from gnomon.cli import accumulator as accumulator_module
from gnomon.cli.accumulator import Accumulator
from gnomon.scoring import aq as aq_module
from gnomon.scoring.calibration import (
    CALIBRATION_CONSTANT_NAMES, CALIBRATION_FINGERPRINTS, calibration_fingerprint,
)
from gnomon.scoring.inputs import build_scoring_inputs
from gnomon.scoring.versioning import (
    AQ_VERSION, GSTACK_VERSION, IncompatibleScoreContract, SCORE_CONTRACT_ID,
    SCORING_INPUTS_VERSION, SKILL_DEDUP_INPUTS_VERSION,
    TOP_LEVEL_ACTIONS_INPUTS_VERSION,
)

_CWD = "/Users/demo/proj"
_NO_CHURN = {"repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
             "deletions": 0, "churn": 0, "commits": 0, "per_repo": []}


def _ts(seq):
    return f"2026-07-06T10:{seq // 60:02d}:{seq % 60:02d}.000Z"


def _prompt(seq, text, sidechain=False, sid="s1"):
    return {"type": "user", "sessionId": sid, "cwd": _CWD, "timestamp": _ts(seq),
            "isSidechain": sidechain,
            "message": {"role": "user", "content": text}}


def _tool_turn(seq, calls, sidechain=False, sid="s1", tool="Read"):
    """One assistant turn carrying `calls` tool_use blocks (each one tool call)."""
    ev = {"type": "assistant", "sessionId": sid, "cwd": _CWD, "timestamp": _ts(seq),
          "isSidechain": sidechain,
          "message": {"role": "assistant", "model": "claude-opus-4-8",
                      "content": [{"type": "tool_use", "name": tool,
                                   "input": {"file_path": f"{_CWD}/f{i}.py"}}
                                  for i in range(calls)]}}
    if sidechain:
        ev["agentId"] = "agent-1"
    return ev


def _corpus(rows, source="claude"):
    """Drive the REAL accumulator over `rows` and return its corpus stats.

    Built through begin_file/observe/end_file/to_corpus_stats rather than from a hand-built
    stats dict on purpose: the whole point of this contract is that the ACCUMULATOR computes
    the field from the event stream, so a fixture that supplies `actions_per_prompt` directly
    would pass whichever way the numerator is defined."""
    acc = Accumulator()
    acc.begin_file(source, f"/c/{source}.jsonl")
    for row in rows:
        acc.observe(row, None, None)
    acc.end_file()
    with mock.patch.object(accumulator_module, "git_churn", lambda *a, **k: dict(_NO_CHURN)):
        stats = acc.to_corpus_stats(None, None, None)
        source_stats = acc.to_source_stats(source, None, None)
    return acc, stats, source_stats


def _steering_leverage(stats):
    """The Steering-leverage axis, re-scored with the band ENABLED.

    As of 12:12:12 the band is withheld (`STEERING_LEVERAGE_BAND_VALIDATED = False`) because it
    was never fitted -- see the PROVENANCE block in `gnomon/scoring/aq.py` and
    `tests/test_steering_band_not_validated.py`. That is a decision about the BAND, not about
    the numerator this file is contracting, so the assertions here are about what the corpus
    READS: they re-run `compute_aq` on the same corpus stats with the flag flipped, which is
    also what keeps the band's shape pinned for the round that fits it.
    """
    with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
        agentic = aq_module.compute_aq(stats)
    efficiency = next(p for p in agentic["pillars"] if p["name"] == "Efficiency")
    return next(a for a in efficiency["axes"] if a["name"] == "Steering leverage")


def _sidechain_heavy_rows():
    """10 human prompts + 100 top-level tool calls + 153 sidechain tool calls.

    The two readings of the same corpus are the two numbers this contract is about:
      top-level  100 / 10 = 10.0  -> inside the 5..20 band -> Steering leverage 1.000
      inclusive  253 / 10 = 25.3  -> past the band          -> Steering leverage 0.868
    25.3 is the figure measured on the real corpus (all sources) that motivated v12, so the
    fixture reproduces the production reading rather than an invented one."""
    rows = []
    seq = 0
    for i in range(10):
        rows.append(_prompt(seq, f"please handle step {i} of the migration"))
        seq += 1
        rows.append(_tool_turn(seq, 10))
        seq += 1
    # The subagent dispatch instruction. `prompts_count` already excludes it (it is not a
    # human turn), which is exactly why its tool calls must leave the numerator too.
    rows.append(_prompt(seq, "you are a subagent: map the call graph", sidechain=True))
    seq += 1
    rows.append(_tool_turn(seq, 153, sidechain=True))
    return rows


class TestActionsPerPromptCountsTopLevelOnly(unittest.TestCase):
    def setUp(self):
        self.acc, self.stats, self.source_stats = _corpus(_sidechain_heavy_rows())

    def test_the_corpus_reading_is_the_top_level_ratio(self):
        self.assertEqual(self.stats["volume"]["total_prompts"], 10)
        self.assertEqual(self.stats["behavior"]["actions_per_prompt"], 10.0)

    def test_steering_leverage_is_full_where_the_mixed_ratio_scored_it_down(self):
        axis = _steering_leverage(self.stats)
        # Asserted before the signal on purpose: the SCORE is the fact that moves, and a
        # failure here is the pre-v12 reading (0.8675 for this corpus) in the diff.
        self.assertEqual(axis["normalized_score"], 1.0)
        self.assertEqual(axis["signals"]["actions_per_prompt"], 10.0)

    def test_tool_calls_total_still_counts_sidechain(self):
        # The rate denominator and the cross-source aggregation weight must NOT move: the six
        # rate targets were fitted against this counter, so changing it is a re-fit.
        self.assertEqual(self.stats["volume"]["tool_calls_total"], 253)
        self.assertEqual(self.source_stats["volume"]["tool_calls_total"], 253)

    def test_the_per_source_projection_agrees_with_the_corpus(self):
        self.assertEqual(self.source_stats["behavior"]["actions_per_prompt"], 10.0)

    def test_the_monthly_projection_agrees_with_the_corpus(self):
        monthly = self.stats["_scoring_monthly_full"]
        self.assertEqual([m["month"] for m in monthly], ["2026-07"])
        month = monthly[0]["stats_full"]
        self.assertEqual(month["volume"]["tool_calls_total"], 253)
        self.assertEqual(month["behavior"]["actions_per_prompt"], 10.0)

    def test_the_contraction_can_push_a_corpus_BELOW_the_band_and_that_is_pinned(self):
        """The UNFAVOURABLE half of v12, which had no test at all before this one.

        Every other case here exercises the direction the change helps (a ratio above
        _BAND_MAX moving down into the flat interior) or the upper boundary. But
        `post = pre * (1 - sidechain_share)` is a contraction, and a contraction is only
        favourable above _BAND_MAX: it is neutral inside the band and it HARMS anything it
        pushes below _BAND_MIN, where the curve ramps linearly to zero. Leaving that untested
        is what let the change ship looking uniformly positive.

        This corpus reads 8.0 before the fix -- comfortably inside [5, 20], scoring a full
        1.000 -- and 2.0 after, which is below _BAND_MIN and scores 2.0 / 5 = 0.4. That is a
        0.6 lever drop, worth -6.0 AQ on a 50-weight axis in a 20-weight pillar, caused by the
        fix rather than by any change in behaviour. Measured on the real 48-user upload
        population four users move like this, losing 7.8-9.1 AQ (see the PROVENANCE block in
        gnomon/scoring/aq.py).

        The harm is what the withholding decision rests on, so this test now pins BOTH halves
        of it: the band still does that damage when it is applied, and it is not applied. The
        band-enabled half keeps the arithmetic honest -- a re-enable that quietly re-fitted the
        thresholds would turn this red rather than pass silently.
        """
        rows = []
        seq = 0
        for i in range(10):
            rows.append(_prompt(seq, f"handle step {i} of the migration please"))
            seq += 1
            rows.append(_tool_turn(seq, 2))       # 20 top-level calls over 10 instructions
            seq += 1
        rows.append(_prompt(seq, "you are a subagent: map the call graph", sidechain=True))
        seq += 1
        rows.append(_tool_turn(seq, 60, sidechain=True))
        _acc, stats, _src = _corpus(rows)
        volume = stats["volume"]
        self.assertEqual(volume["tool_calls_total"], 80)
        self.assertEqual(volume["sidechain_tool_calls"], 60)
        self.assertEqual(volume["total_instructions"], 10)

        # The pre-v12 reading of this same corpus, computed from the published counters so the
        # comparison cannot drift: 80 / 10 = 8.0, inside the band, lever 1.000.
        pre_v12 = volume["tool_calls_total"] / volume["total_instructions"]
        self.assertEqual(pre_v12, 8.0)
        self.assertTrue(aq_module.STEERING_LEVERAGE_BAND_MIN
                        <= pre_v12 <= aq_module.STEERING_LEVERAGE_BAND_MAX)

        # ...and the v12 reading, which the fix moved BELOW the band minimum.
        self.assertEqual(stats["behavior"]["actions_per_prompt"], 2.0)
        axis = _steering_leverage(stats)          # band ENABLED: what it would have scored
        self.assertLess(axis["signals"]["actions_per_prompt"],
                        aq_module.STEERING_LEVERAGE_BAND_MIN)
        self.assertAlmostEqual(axis["normalized_score"],
                               2.0 / aq_module.STEERING_LEVERAGE_BAND_MIN)
        # Stated as the AQ cost so the sign of this change is impossible to misread: the axis
        # carries 50 of the 100-weight Efficiency pillar, which carries 20 of AQ.
        lost_aq = (1.0 - axis["normalized_score"]) * 50 * 20 / 100
        self.assertAlmostEqual(lost_aq, 6.0)

        # ...and that 6.0 is NOT charged, because the band it comes from was never fitted. The
        # term is withheld and Efficiency renormalizes onto Recovery instead.
        efficiency = next(p for p in stats["agentic"]["pillars"]
                          if p["name"] == "Efficiency")
        self.assertEqual(efficiency.get("not_applicable"), ["Steering leverage"])
        self.assertEqual(stats["agentic"]["steering_leverage"],
                         {"state": "withheld_unvalidated_band", "actions_per_prompt": 2.0})
        recovery = next(a for a in efficiency["axes"] if a["name"] == "Recovery")
        self.assertEqual(recovery["weight"], 100)
        # What withholding substitutes for the 0.4 lever, as the closed form the population
        # cost was computed from: `d_AQ = 10 * (recovery - lever)`. The sign is the USER's own
        # Recovery, not a property of the change -- this fixture logs no errors at all, so its
        # Recovery is the bare 0.15 api-hygiene term and it does WORSE withheld. That is the
        # rec=0.138 outlier of the 48-user measurement reproduced in miniature, and it is
        # pinned here rather than hidden: the case for withholding is the population mean and
        # the removal of the delegator concentration, not a per-user guarantee.
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            scored = next(p for p in aq_module.compute_aq(stats)["pillars"]
                          if p["name"] == "Efficiency")
        self.assertAlmostEqual(
            (efficiency["score"] - scored["score"]) * 20 / 100,
            10 * (recovery["normalized_score"] - axis["normalized_score"]), places=1)

    def test_a_genuinely_high_top_level_ratio_still_decays(self):
        """The fix must not become a blanket exemption from the band. A corpus that really
        did take 30 top-level actions on one instruction is still low-leverage steering."""
        rows = [_prompt(0, "just go and do the whole thing yourself"), _tool_turn(1, 30)]
        _acc, stats, _src = _corpus(rows)
        self.assertEqual(stats["behavior"]["actions_per_prompt"], 30.0)
        axis = _steering_leverage(stats)
        self.assertAlmostEqual(axis["normalized_score"], 0.75)


class TestSidechainToolCallsIsPublished(unittest.TestCase):
    def setUp(self):
        self.acc, self.stats, self.source_stats = _corpus(_sidechain_heavy_rows())

    def test_the_corpus_volume_block_publishes_the_observed_sidechain_count(self):
        self.assertEqual(self.stats["volume"]["sidechain_tool_calls"], 153)

    def test_the_diagnostic_reconciles_against_the_scored_ratio(self):
        volume = self.stats["volume"]
        top_level = volume["tool_calls_total"] - volume["sidechain_tool_calls"]
        self.assertEqual(
            round(top_level / volume["total_prompts"], 1),
            self.stats["behavior"]["actions_per_prompt"])

    def test_the_per_source_block_publishes_it(self):
        self.assertEqual(self.source_stats["volume"]["sidechain_tool_calls"], 153)

    def test_the_monthly_block_publishes_it(self):
        month = self.stats["_scoring_monthly_full"][0]["stats_full"]
        self.assertEqual(month["volume"]["sidechain_tool_calls"], 153)

    def test_the_wire_projection_forwards_it(self):
        block = build_scoring_inputs(self.source_stats)
        self.assertEqual(block["volume"]["sidechain_tool_calls"], 153)

    def test_a_payload_that_predates_the_field_is_absent_safe(self):
        """A stats block captured before v12 carries no `sidechain_tool_calls`. It must
        project as 0 rather than raising, exactly as every other volume counter does."""
        legacy = {"corpus": {"sources": {"claude": {}}},
                  "volume": {"total_sessions": 3, "total_prompts": 10,
                             "tool_calls_total": 253, "thinking_blocks": 4},
                  "behavior": {"actions_per_prompt": 25.3}}
        block = build_scoring_inputs(legacy)
        self.assertEqual(block["volume"]["sidechain_tool_calls"], 0)
        self.assertEqual(block["volume"]["tool_calls_total"], 253)

    def test_a_corpus_with_no_sidechain_activity_publishes_a_real_zero(self):
        _acc, stats, _src = _corpus(
            [_prompt(0, "one small change please"), _tool_turn(1, 6)])
        self.assertEqual(stats["volume"]["sidechain_tool_calls"], 0)
        self.assertEqual(stats["volume"]["tool_calls_total"], 6)
        self.assertEqual(stats["behavior"]["actions_per_prompt"], 6.0)


def _slash(seq, name="/commit", tail="", sid="s1"):
    """A slash-command user turn, shaped the way Claude Code writes one.

    `strip_injections` removes the `<command-name>` wrapper, so a BARE command cleans to the
    empty string and a command with typed text after it does not."""
    body = f"<command-name>{name}</command-name>"
    if tail:
        body += "\n" + tail
    return _prompt(seq, body, sid=sid)


class TestTheDenominatorCoversEveryHumanInstruction(unittest.TestCase):
    """A bare slash command is a human instruction, and until v12 the ratio dropped it.

    `Accumulator.observe` splits a genuine user turn three ways: a BARE slash command
    increments `command_invocations` only, a command with typed text after it increments both
    `command_invocations` and `prompts_count`, and plain typed text increments `prompts_count`.
    So `prompts_count` is really "turns carrying human-typed TEXT", and that is not an
    accident -- everything guarded by the same branch consumes the text itself
    (`prompt_lengths` feeds `avg/median_prompt_length_chars`, `_POLITE_RE` feeds
    `polite_prompts`, and the narrative quote candidates need something to quote). Counting a
    bare command there would push a zero-length entry into the prompt-length histograms and
    misreport how long a human's prompts are.

    That reason is real and it is about the LENGTH statistics, not about the instruction
    count. Meanwhile the tool calls a slash command drives stay in the v12 numerator, so the
    two sides of the ratio described different populations a SECOND time -- and in the
    direction the band punishes hardest, because the denominator is the small side. So v12
    leaves `prompts_count` / `volume.total_prompts` exactly as they were, for the consumers
    that genuinely want typed-text turns, and gives the ratio its own denominator:
    `volume.total_instructions` = typed-text turns + bare slash commands.
    """

    def test_ten_bare_slash_commands_are_not_zero_instructions(self):
        """Reproduces the defect: 10 bare commands driving 300 top-level calls read as
        `total_prompts = 0`, so `actions_per_prompt` was 0 and `app <= 0` scores the axis
        0.0 -- strictly worse than the 200-subagent case v12 set out to fix, on a corpus
        with no sidechain activity at all."""
        rows = []
        seq = 0
        for _ in range(10):
            rows.append(_slash(seq))
            seq += 1
            rows.append(_tool_turn(seq, 30))
            seq += 1
        _acc, stats, source_stats = _corpus(rows)
        volume = stats["volume"]
        self.assertEqual(volume["tool_calls_total"], 300)
        self.assertEqual(volume["sidechain_tool_calls"], 0)
        # The typed-text count is deliberately UNCHANGED -- it is what the length
        # histograms are built from.
        self.assertEqual(volume["total_prompts"], 0)
        self.assertEqual(volume["command_invocations"], 10)
        # ...and the ratio now has a denominator that describes the same population its
        # numerator does.
        self.assertEqual(volume["total_instructions"], 10)
        self.assertEqual(stats["behavior"]["actions_per_prompt"], 30.0)
        self.assertEqual(source_stats["volume"]["total_instructions"], 10)
        self.assertEqual(source_stats["behavior"]["actions_per_prompt"], 30.0)

    def test_the_axis_stops_reading_a_slash_command_corpus_as_unsteered(self):
        rows = []
        seq = 0
        for _ in range(10):
            rows.append(_slash(seq))
            seq += 1
            rows.append(_tool_turn(seq, 30))
            seq += 1
        _acc, stats, _src = _corpus(rows)
        axis = _steering_leverage(stats)
        self.assertEqual(axis["signals"]["actions_per_prompt"], 30.0)
        # 30 is past the band, so it still DECAYS -- the fix is a correct denominator, not
        # an exemption. What it must not be any more is 0.0.
        self.assertAlmostEqual(axis["normalized_score"], 0.75)

    def test_a_mixed_corpus_counts_each_instruction_exactly_once(self):
        """2 typed prompts + 8 bare slash commands + 300 calls read `app = 150` before v12
        (300 / 2) and score 0.0. A slash command carrying typed text must count ONCE, not
        twice, even though it increments both underlying counters."""
        rows = []
        seq = 0
        for i in range(2):
            rows.append(_prompt(seq, f"please handle step {i} of the migration"))
            seq += 1
        for _ in range(8):
            rows.append(_slash(seq))
            seq += 1
        rows.append(_slash(seq, tail="and squash the fixups while you are there"))
        seq += 1
        rows.append(_tool_turn(seq, 300))
        _acc, stats, _src = _corpus(rows)
        volume = stats["volume"]
        self.assertEqual(volume["total_prompts"], 3)         # 2 typed + 1 command-with-text
        self.assertEqual(volume["command_invocations"], 9)   # 8 bare + 1 with text
        self.assertEqual(volume["total_instructions"], 11)   # 3 + 8, the with-text one once
        self.assertEqual(stats["behavior"]["actions_per_prompt"], round(300 / 11, 1))

    def test_the_prompt_length_histograms_are_untouched(self):
        """The reason the exclusion exists in the first place: a bare command has no typed
        text, so admitting it into `prompts_count` would average a 0 into the length
        stats. The new denominator must not reintroduce that."""
        typed = "please handle the migration end to end"
        rows = [_prompt(0, typed), _slash(1), _slash(2), _tool_turn(3, 10)]
        _acc, stats, _src = _corpus(rows)
        volume = stats["volume"]
        self.assertEqual(volume["avg_prompt_length_chars"], float(len(typed)))
        self.assertEqual(volume["median_prompt_length_chars"], float(len(typed)))
        self.assertEqual(volume["total_prompts"], 1)
        self.assertEqual(volume["total_instructions"], 3)

    def test_a_sidechain_slash_command_is_not_a_human_instruction(self):
        """The denominator widened to cover slash commands, not to cover subagent turns. A
        sidechain user turn is already excluded before the command split, and must stay so --
        otherwise v12 would re-mix the populations it just separated."""
        rows = [_prompt(0, "map the call graph for me"), _tool_turn(1, 10),
                _prompt(2, "<command-name>/inner</command-name>", sidechain=True),
                _tool_turn(3, 40, sidechain=True)]
        _acc, stats, _src = _corpus(rows)
        volume = stats["volume"]
        self.assertEqual(volume["total_prompts"], 1)
        self.assertEqual(volume["total_instructions"], 1)
        self.assertEqual(volume["sidechain_tool_calls"], 40)
        self.assertEqual(stats["behavior"]["actions_per_prompt"], 10.0)

    def test_the_monthly_projection_uses_the_same_denominator(self):
        rows = []
        seq = 0
        for _ in range(10):
            rows.append(_slash(seq))
            seq += 1
            rows.append(_tool_turn(seq, 30))
            seq += 1
        _acc, stats, _src = _corpus(rows)
        month = stats["_scoring_monthly_full"][0]["stats_full"]
        self.assertEqual(month["volume"]["total_instructions"], 10)
        self.assertEqual(month["behavior"]["actions_per_prompt"], 30.0)

    def test_the_wire_projection_forwards_the_denominator(self):
        rows = [_slash(0), _tool_turn(1, 12)]
        _acc, _stats, source_stats = _corpus(rows)
        block = build_scoring_inputs(source_stats)
        self.assertEqual(block["volume"]["total_instructions"], 1)
        self.assertEqual(block["behavior"]["actions_per_prompt"], 12.0)

    def test_a_payload_that_predates_the_field_falls_back_to_total_prompts(self):
        """A pre-v12 block carries no `total_instructions`. It must project as
        `total_prompts` -- the denominator that payload's own ratio was built with -- rather
        than as 0, which would make the ratio unrecomputable, or be invented."""
        legacy = {"corpus": {"sources": {"claude": {}}},
                  "volume": {"total_sessions": 3, "total_prompts": 10,
                             "tool_calls_total": 253, "thinking_blocks": 4},
                  "behavior": {"actions_per_prompt": 25.3}}
        block = build_scoring_inputs(legacy)
        self.assertEqual(block["volume"]["total_instructions"], 10)


class TestSteeringIsUnmeasuredWhereSidechainCannotBeLabelled(unittest.TestCase):
    """A source that CAN delegate but CANNOT label a call as delegated makes the v12 field
    mean something different, and nothing in the payload distinguishes the two meanings.

    `Accumulator.observe` reads `bool(ev.get("isSidechain"))`. Four adapters stamp it --
    claude (native), codex, cursor and opencode. Three never do: gemini, pi and antigravity.
    Of those three only `antigravity` carries the `delegate` capability in
    `gnomon/config.py::SOURCE_CAPS`, and it maps `invoke_subagent -> Agent`
    (gnomon/sources/antigravity.py), so it demonstrably delegates and demonstrably cannot
    label. Its subagent calls therefore stay in the top-level numerator and it reads exactly
    as it did before v12 -- an antigravity-shaped corpus of 1 prompt and 253 unlabelled calls
    scores `app = 253`, `sidechain_tool_calls = 0`, Steering leverage 0.0.

    So the honest reading there is that steering is UNMEASURED, not zero. That is what the
    codebase already does for the structurally identical case -- `PLANNING_SESSION_SCOPE_BY_
    SOURCE` ("whether a source adapter can authoritatively distinguish human-started root
    events from delegated child events") and the `*_state` string convention
    (`ordered_facts_state`, `linked_model_routing_state`) -- so v12 follows it: the term is
    dropped and the Efficiency axis weights renormalize via `build_pillar._live`, rather than
    a 0.0 that asserts a measurement nobody made.

    The gate is DELEGATION OBSERVED, not capability alone. A source that cannot label but
    recorded no dispatch has no subagent calls to misplace, so its ratio is exact and the term
    stays scored. That keeps gemini and pi out of it without a special case (neither carries
    `delegate` at all) and keeps an antigravity slice that never delegated fully scored.
    """

    def _antigravity_rows(self, dispatches, plain_calls):
        rows = [_prompt(0, "do the whole migration end to end")]
        seq = 1
        if dispatches:
            rows.append(_tool_turn(seq, dispatches, tool="Agent"))
            seq += 1
        if plain_calls:
            rows.append(_tool_turn(seq, plain_calls))
        return rows

    def test_the_pre_v12_reading_is_reproduced_before_the_guard_is_consulted(self):
        """The raw counters must be untouched: v12 does not invent a sidechain count it
        cannot see, it declines to SCORE the ratio built from it."""
        _acc, stats, _src = _corpus(self._antigravity_rows(253, 0), source="antigravity")
        volume = stats["volume"]
        self.assertEqual(volume["tool_calls_total"], 253)
        self.assertEqual(volume["sidechain_tool_calls"], 0)
        self.assertEqual(volume["total_instructions"], 1)
        self.assertEqual(stats["behavior"]["actions_per_prompt"], 253.0)

    def test_the_state_is_published_as_a_string_beside_the_ratio(self):
        _acc, stats, source_stats = _corpus(
            self._antigravity_rows(253, 0), source="antigravity")
        self.assertEqual(stats["behavior"]["sidechain_label_state"], "unmeasured")
        self.assertEqual(source_stats["behavior"]["sidechain_label_state"], "unmeasured")
        block = build_scoring_inputs(source_stats)
        self.assertEqual(block["behavior"]["sidechain_label_state"], "unmeasured")

    def test_the_reason_reported_is_the_adapter_one_not_the_band_one(self):
        """Both absences apply to an unlabelling delegator. The ADAPTER verdict is the one
        published, because it is the one still true after the band is fitted -- so this
        source's state does not flip meaning when the band flag does."""
        _acc, stats, _src = _corpus(self._antigravity_rows(253, 0), source="antigravity")
        self.assertEqual(stats["agentic"]["steering_leverage"]["state"],
                         "unmeasured_sidechain_labels")
        with mock.patch.object(aq_module, "STEERING_LEVERAGE_BAND_VALIDATED", True):
            after_fit = aq_module.compute_aq(stats)
        self.assertEqual(after_fit["steering_leverage"]["state"],
                         "unmeasured_sidechain_labels")
        efficiency = next(p for p in after_fit["pillars"] if p["name"] == "Efficiency")
        self.assertEqual(efficiency.get("not_applicable"), ["Steering leverage"])

    def test_the_term_is_dropped_rather_than_scored_zero(self):
        _acc, stats, _src = _corpus(self._antigravity_rows(253, 0), source="antigravity")
        efficiency = next(p for p in stats["agentic"]["pillars"]
                          if p["name"] == "Efficiency")
        self.assertEqual(efficiency.get("not_applicable"), ["Steering leverage"])
        names = [a["name"] for a in efficiency["axes"]]
        self.assertNotIn("Steering leverage", names)
        # Recovery is the only surviving axis, so its weight renormalizes 50 -> 100 and the
        # pillar becomes its score rather than half of it. A 0.0 would have HALVED the
        # pillar on a signal the source cannot emit.
        recovery = next(a for a in efficiency["axes"] if a["name"] == "Recovery")
        self.assertEqual(recovery["weight"], 100)
        self.assertEqual(efficiency["score"],
                         round(100 * recovery["normalized_score"], 1))

    def test_a_labelling_source_is_unaffected(self):
        """claude stamps `isSidechain`, so nothing about THIS guard may touch it. Its term is
        withheld for the other reason (the unfitted band), and the state says which."""
        _acc, stats, _src = _corpus(_sidechain_heavy_rows())
        self.assertEqual(stats["behavior"]["sidechain_label_state"], "measured")
        self.assertEqual(stats["agentic"]["steering_leverage"]["state"],
                         "withheld_unvalidated_band")
        axis = _steering_leverage(stats)
        self.assertEqual(axis["normalized_score"], 1.0)

    def test_an_unlabelling_source_that_never_delegated_stays_scored(self):
        """No dispatch means no subagent calls to misplace, so the top-level numerator is
        exact and declining to score it FOR THIS REASON would throw away a real measurement.
        The band verdict is what withholds it, and it is reported as such -- so when the band
        is fitted this corpus starts scoring again without any further change here."""
        _acc, stats, _src = _corpus(
            self._antigravity_rows(0, 12), source="antigravity")
        self.assertEqual(stats["behavior"]["sidechain_label_state"], "measured")
        self.assertEqual(stats["behavior"]["actions_per_prompt"], 12.0)
        self.assertEqual(stats["agentic"]["steering_leverage"]["state"],
                         "withheld_unvalidated_band")
        axis = _steering_leverage(stats)
        self.assertEqual(axis["normalized_score"], 1.0)

    def test_gemini_and_pi_need_no_special_case(self):
        """Neither carries `delegate` in SOURCE_CAPS, so neither can produce a dispatch, so
        the observed-delegation gate never fires for them. Asserted on the capability set
        directly as well as behaviourally, so a future cap change cannot silently make this
        claim false."""
        from gnomon.config import SOURCE_CAPS
        for source in ("gemini", "pi"):
            with self.subTest(source=source):
                self.assertNotIn("delegate", SOURCE_CAPS[source])
                _acc, stats, _src = _corpus(
                    self._antigravity_rows(0, 30), source=source)
                self.assertEqual(stats["behavior"]["sidechain_label_state"], "measured")
                self.assertEqual(stats["behavior"]["actions_per_prompt"], 30.0)

    def test_antigravity_is_the_one_source_that_can_delegate_but_not_label(self):
        """Pins the premise this whole class rests on, so a new adapter cannot join the
        can-delegate/cannot-label set unnoticed."""
        from gnomon.config import SIDECHAIN_LABELLING_SOURCES, SOURCE_CAPS
        unlabelled_delegators = {
            source for source, caps in SOURCE_CAPS.items()
            if "delegate" in caps and source not in SIDECHAIN_LABELLING_SOURCES}
        self.assertEqual(unlabelled_delegators, {"antigravity"})
        self.assertEqual(SIDECHAIN_LABELLING_SOURCES,
                         {"claude", "codex", "cursor", "opencode"})

    def test_an_unknown_source_fails_closed(self):
        """Opposite default from `available_caps`, which fails OPEN for an unmapped source so
        it is not penalized for a signal it might emit. Trusting a top-level count from an
        adapter nobody has checked is the other kind of mistake, so this one fails closed."""
        from gnomon.config import sidechain_label_scope
        self.assertEqual(sidechain_label_scope("some-new-ide"), "cannot_label")
        self.assertEqual(sidechain_label_scope(None), "cannot_label")
        for source in ("claude", "codex", "cursor", "opencode", "gemini", "pi",
                       "antigravity-ide"):
            with self.subTest(source=source):
                self.assertEqual(sidechain_label_scope(source), "measured")
        self.assertEqual(sidechain_label_scope("antigravity"), "cannot_label")

    def test_a_mixed_corpus_declines_the_term_when_any_slice_is_unlabelled(self):
        """The merged corpus pools every source's calls into one numerator, so an unlabelled
        delegating slice contaminates the whole ratio -- there is no per-source split left to
        rescue it at that point. Mirrors `ordered_facts_state`, which is "measured" only when
        every contributing source is. The per-source profiles keep their own verdicts, so the
        claude slice is still scored on its own in `profiles_by_source`."""
        acc = Accumulator()
        acc.begin_file("claude", "/c/s.jsonl")
        for row in _sidechain_heavy_rows():
            acc.observe(row, None, None)
        acc.end_file()
        acc.begin_file("antigravity", "/a/s.json")
        for row in self._antigravity_rows(20, 0):
            acc.observe(row, None, None)
        acc.end_file()
        with mock.patch.object(accumulator_module, "git_churn",
                               lambda *a, **k: dict(_NO_CHURN)):
            stats = acc.to_corpus_stats(None, None, None)
        self.assertEqual(stats["behavior"]["sidechain_label_state"], "unmeasured")
        efficiency = next(p for p in stats["agentic"]["pillars"]
                          if p["name"] == "Efficiency")
        self.assertEqual(efficiency.get("not_applicable"), ["Steering leverage"])

    def test_a_payload_that_predates_the_state_reads_as_measured(self):
        """A pre-v12 block carries no such key. It must project as "measured": those payloads
        were produced before the field existed, and the label state is a claim about the
        ADAPTER, not about the corpus -- inventing "unmeasured" would drop a term for every
        historical row rather than admit one honest gap."""
        legacy = {"corpus": {"sources": {"claude": {}}},
                  "volume": {"total_sessions": 3, "total_prompts": 10,
                             "tool_calls_total": 253},
                  "behavior": {"actions_per_prompt": 25.3}}
        block = build_scoring_inputs(legacy)
        self.assertEqual(block["behavior"]["sidechain_label_state"], "measured")


class TestScoreContractMovesWithTheNumeratorChange(unittest.TestCase):
    def test_contract_is_twelve(self):
        self.assertEqual(SCORE_CONTRACT_ID, "12:12:12")
        self.assertEqual(SCORING_INPUTS_VERSION, 12)
        self.assertEqual(AQ_VERSION, 12)
        self.assertEqual(GSTACK_VERSION, 12)

    def test_the_new_contract_has_its_own_fingerprint_entry(self):
        self.assertIn(SCORE_CONTRACT_ID, CALIBRATION_FINGERPRINTS)
        self.assertEqual(calibration_fingerprint(),
                         CALIBRATION_FINGERPRINTS[SCORE_CONTRACT_ID])

    def test_the_fingerprint_actually_moved(self):
        self.assertNotEqual(CALIBRATION_FINGERPRINTS[SCORE_CONTRACT_ID],
                            CALIBRATION_FINGERPRINTS["11:11:11"])

    def test_older_contract_entries_are_untouched(self):
        self.assertEqual(CALIBRATION_FINGERPRINTS["8:8:8"], "38bf1d623bea1517")
        self.assertEqual(CALIBRATION_FINGERPRINTS["9:9:9"], "2e7638d58c2b26e4")
        self.assertEqual(CALIBRATION_FINGERPRINTS["10:10:10"], "7a2c444ff5c26f06")
        self.assertEqual(CALIBRATION_FINGERPRINTS["11:11:11"], "888bec08099b6fbc")

    def test_the_steering_band_is_under_the_fingerprint(self):
        """No calibration VALUE moves in v12 — what moves is the population the Steering
        band judges. Had the band stayed three inline literals the digest would have equalled
        11:11:11's and `test_no_two_contracts_share_a_fingerprint` would have failed, which
        would have been informative: it means the score-affecting thing was outside the
        registry. So v12 names the band and registers it, exactly as v10 did with the
        scoring window and v11 with the blend weights."""
        for name in ("STEERING_LEVERAGE_BAND_MIN", "STEERING_LEVERAGE_BAND_MAX",
                     "STEERING_LEVERAGE_DECAY_SPAN"):
            with self.subTest(constant=name):
                self.assertIn(name, CALIBRATION_CONSTANT_NAMES)
                baseline = calibration_fingerprint()
                with mock.patch.object(aq_module, name, getattr(aq_module, name) + 1):
                    self.assertNotEqual(calibration_fingerprint(), baseline)

    def test_the_band_constants_hold_the_values_they_replaced(self):
        # Values unchanged from the inline literals: v12 renames, it does not re-fit.
        self.assertEqual(aq_module.STEERING_LEVERAGE_BAND_MIN, 5)
        self.assertEqual(aq_module.STEERING_LEVERAGE_BAND_MAX, 20)
        self.assertEqual(aq_module.STEERING_LEVERAGE_DECAY_SPAN, 40)

    def test_replay_refuses_a_pre_v12_actions_per_prompt_basis(self):
        """v12 DOES narrow the replay floor, and an earlier revision of this test asserted
        the opposite on a premise that is false for exactly one field.

        That premise was: "the persisted counters a v8-v11 payload carries still mean what
        they meant, so 8..12 all stay admissible". It holds for every counter in the payload
        EXCEPT `behavior.actions_per_prompt`, which is not a counter at all -- it is a
        derived RATIO, and v12 changed its numerator from the sidechain-INCLUSIVE tool total
        to the top-level-only one. `profiles.py::stats_from_scoring_block` copies `behavior`
        verbatim and `compute_aq` re-stamps the LIVE `SCORE_CONTRACT_ID`, so replaying a v11
        payload scored a frozen mixed-population ratio through the v12 Steering band and
        published it as a genuine 12:12:12 row. Under
        `COMPARISON_POLICY = same_score_contract_id_only` nothing downstream could tell it
        apart, and the systematic gap between the two bases reads as behaviour.

        This is verbatim the class `_require_comparable_scoring_window` was written for at
        v10 -- a quantity the live formula cannot repair from a persisted payload -- so v12
        follows that precedent: a second named boundary constant and a scoped refusal.
        """
        from gnomon.scoring.aq import DEFAULT_SCORING_WINDOW_MONTHS
        from gnomon.scoring.replay import (
            IncompatibleActionsPerPromptBasis, ReplayError, replay,
        )
        self.assertEqual(SKILL_DEDUP_INPUTS_VERSION, 8)
        self.assertEqual(TOP_LEVEL_ACTIONS_INPUTS_VERSION, 12)

        def _payload(version):
            return {"payload_features": {"version": 1, "supported": [],
                                         "emitted": [], "omitted": []},
                    "context": {"window_months": DEFAULT_SCORING_WINDOW_MONTHS},
                    "scoring_inputs_version": version}

        # v8-v11 carry a MIXED-population ratio: refused, and named for that reason.
        for version in range(SKILL_DEDUP_INPUTS_VERSION,
                             TOP_LEVEL_ACTIONS_INPUTS_VERSION):
            with self.subTest(version=version, expect="refused"):
                with self.assertRaises(IncompatibleActionsPerPromptBasis) as caught:
                    replay(_payload(version))
                self.assertIn("actions_per_prompt", str(caught.exception))
                # Still a ReplayError AND an IncompatibleScoreContract, so no existing
                # caller has to learn a new exception type to stay correct.
                self.assertIsInstance(caught.exception, ReplayError)
                self.assertIsInstance(caught.exception, IncompatibleScoreContract)

        # v12 onwards stays replayable: the gate narrowed, it did not close.
        for version in range(TOP_LEVEL_ACTIONS_INPUTS_VERSION,
                             SCORING_INPUTS_VERSION + 1):
            with self.subTest(version=version, expect="past the gate"):
                with self.assertRaises(ReplayError) as caught:
                    replay(_payload(version))
                self.assertNotIsInstance(
                    caught.exception, IncompatibleActionsPerPromptBasis)
                self.assertIn("scoring_inputs_by_source", str(caught.exception))

    def test_the_pre_dedup_refusal_still_names_the_dedup(self):
        """The v8 boundary keeps its own message. A v5 payload is inadmissible for BOTH
        reasons, and the older/more fundamental one has to be the one reported -- a caller
        enumerating an archive needs to know its counters are pre-dedup, not merely that one
        ratio changed basis."""
        from gnomon.scoring.aq import DEFAULT_SCORING_WINDOW_MONTHS
        from gnomon.scoring.replay import (
            IncompatibleActionsPerPromptBasis, IncompatibleScoringInputs, replay,
        )
        with self.assertRaises(IncompatibleScoringInputs) as caught:
            replay({"payload_features": {"version": 1, "supported": [],
                                         "emitted": [], "omitted": []},
                    "context": {"window_months": DEFAULT_SCORING_WINDOW_MONTHS},
                    "scoring_inputs_version": 5})
        self.assertIn("dedup", str(caught.exception))
        self.assertNotIsInstance(caught.exception, IncompatibleActionsPerPromptBasis)

    def test_the_window_guard_still_fires_for_a_v12_payload(self):
        """The new basis gate must not shadow the v10 corpus-SCALE gate: a v12 payload that
        declares the wrong window is still refused for the window, not waved through."""
        from gnomon.scoring.replay import IncompatibleScoringWindow, replay
        with self.assertRaises(IncompatibleScoringWindow):
            replay({"payload_features": {"version": 1, "supported": [],
                                         "emitted": [], "omitted": []},
                    "context": {"window_months": 6},
                    "scoring_inputs_version": SCORING_INPUTS_VERSION})


if __name__ == "__main__":
    unittest.main()
