"""End-to-end scoring vector: synthetic TRANSCRIPT EVENTS -> Accumulator -> compute_aq.

Why this file exists
--------------------
tests/test_scoring_vectors.py feeds HAND-BUILT stats dicts straight into scoring
(see tests/_scoring_vectors_cases.py -- it imports `copy` and nothing else), so it
never runs the accumulator and therefore never sees what the accumulator ACTUALLY
puts in front of `compute_aq`. tests/test_skill_dedup.py does run the accumulator,
but stops at `acc.skill_counter` and never scores anything. Between the two, the
skill-counting dedup shipped in 28d3bda changed the numerator of two scored rate
terms by roughly two orders of magnitude with zero test coverage of the
consequence: on a real corpus one skill collapsed 517 -> 1 and
`skills_total / tool_call` fell from 1.50 to 0.0021 against a target of 0.25.

This module closes that hole. It starts from synthetic transcript events, runs the
REAL pipeline (`begin_file` -> `observe` -> `end_file` -> `to_corpus_stats`), calls
`compute_aq()`, and reads the two rates back out of the published axis `signals` --
the same numbers the report and the upload payload carry.

Why `@unittest.expectedFailure` on the two band tests
-----------------------------------------------------
The band tests assert what a CORRECTLY calibrated setup would produce, and today's
constants are known-misaligned, so they must fail on the current tree -- a green
band test here would mean the test is not exercising the misalignment and is
worthless. They are marked `expectedFailure` rather than left hard-red for two
reasons, and the marking is only safe because of the second one:

  1. A permanently red suite is not a signal, it is noise: it hides the NEXT real
     regression. `expectedFailure` keeps the misalignment machine-checked without
     turning the whole 1305-test baseline red.
  2. It is a self-clearing tripwire in BOTH directions, so nothing is hidden:
     - after the re-fit the band assertion starts passing, unittest reports an
       "unexpected success", and `wasSuccessful()` returns False (Python >= 3.4) --
       the suite goes red until the decorator is removed;
     - `TestTodaysBrokenValuesArePinned` pins the exact broken rates the current
       tree produces, so the re-fit ALSO has to come here and update them.

Read the pinned values in `TestTodaysBrokenValuesArePinned` as the measured
evidence of the misalignment, and the bands below as the acceptance criterion for
the pending re-fit. The fix is the re-fit (see aq.py's per-tool-call rate targets
and gnomon/scoring/calibration.py), NOT loosening these bands.
"""
import unittest

from gnomon.analysis.metrics import _is_review_skill_name
from gnomon.cli.accumulator import Accumulator
from gnomon.scoring.aq import (REVIEW_SKILLS_PER_CALL_TARGET,
                               SKILLS_TOTAL_PER_CALL_TARGET,
                               TEST_RUNS_PER_CALL_TARGET, compute_aq)
from tests.test_skill_dedup import _attribution_turn, _feed, _skill_tool_event, _ts

# ---- corpus shape -----------------------------------------------------------
# 40 top-level sessions whose tool-call counts average ~68, the median Claude
# session size documented in aq.py's rate rationale. Session size VARIES because
# the dedup credits a skill once per (session, skill) span regardless of how many
# tool calls the session carried -- a fixed size would hide that interaction.
SESSIONS = 40
SESSION_CALL_SIZES = (34, 52, 68, 76, 110)
# Every third session invokes 2 skills (one review-class, one not). That is
# deliberately HEAVY practice, not average practice: 14 of 40 sessions carrying a
# skill invocation is ~5x the population figure implied by the 0.0021 measurement
# above. Scoring a heavy user near zero is the bug; scoring an average user near
# zero could be honest.
SKILLS_EVERY = 3
SKILLS_PER_SESSION = 2
# Each invocation carries a 20-turn `attributionSkill` span in a sidechain file.
# Real spans are far longer (the /judgment-day ground truth in test_skill_dedup is
# 196 turns); 20 is enough to prove the span collapses to 1 and keeps the fixture
# cheap.
SPAN_TURNS = 20

REVIEW_SKILLS = ("judgment-day", "code-review:code-review", "sdd-verify",
                 "review-reliability", "caveman-review",
                 # Recognised by a human as verification, MISSED by
                 # _is_review_skill_name's exact-tail `verify` rule -- the second,
                 # compounding cause of the review-rate collapse.
                 "superpowers:verification-before-completion")
OTHER_SKILLS = ("superpowers:test-driven-development", "brainstorming", "writing-plans",
                "superpowers:systematic-debugging", "sdd-tasks", "skill-creator")

# A plausible working mix: reads, searches, edits, shell. One in 34 calls is a test
# run, which puts `test_runs_per_call` on its own target -- see
# TestSyntheticCorpusVolumeIsHonest, the control that proves the fixture's volume
# is right and the two skill rates are what is wrong.
TOOL_CYCLE = (
    ("Read", {"file_path": "/repo/gnomon/analysis/metrics.py"}),
    ("Grep", {"pattern": "compute_aq"}),
    ("Edit", {"file_path": "/repo/gnomon/scoring/aq.py",
              "old_string": "a\nb", "new_string": "a\nb\nc"}),
    ("Bash", {"command": "rg -n compute_aq gnomon"}),
    ("Read", {"file_path": "/repo/tests/test_scoring_vectors.py"}),
    ("Glob", {"pattern": "tests/*.py"}),
    ("Edit", {"file_path": "/repo/gnomon/cli/report.py",
              "old_string": "x", "new_string": "y"}),
    ("Bash", {"command": "git status"}),
)
TEST_RUN = ("Bash", {"command": "python3 -m unittest discover -s tests"})
TEST_RUN_EVERY = 34


def _prompt(sid, seq):
    return {"type": "user", "sessionId": sid, "timestamp": _ts(seq), "isSidechain": False,
            "message": {"role": "user", "content": "implement the thing"}}


def _tool_turn(sid, seq, name, inp):
    return {
        "type": "assistant", "sessionId": sid, "timestamp": _ts(seq),
        "isSidechain": False,
        "message": {"role": "assistant", "model": "claude-opus-4-8", "content": [
            {"type": "tool_use", "id": f"tu-{sid}-{seq}", "name": name, "input": inp}]},
    }


def _synthetic_corpus():
    """Returns [(filepath, events), ...] for one month of synthetic Claude transcripts.

    Skills are drawn round-robin from the two pools so every name appears, keeping
    the review-class share stable and the fixture independent of pool ordering.
    """
    files = []
    picks = {"review": 0, "other": 0}
    for s in range(SESSIONS):
        sid = f"sess-{s:03d}"
        base = s * 100_000          # per-session timestamp block, no cross-session overlap
        events = [_prompt(sid, base)]
        session_skills = []
        if s % SKILLS_EVERY == 0:
            for k in range(SKILLS_PER_SESSION):
                kind = "review" if k % 2 == 0 else "other"
                pool = REVIEW_SKILLS if kind == "review" else OTHER_SKILLS
                session_skills.append(pool[picks[kind] % len(pool)])
                picks[kind] += 1
        for k, skill in enumerate(session_skills):
            events.append(_skill_tool_event(sid, base + 1 + k, skill))
        for c in range(SESSION_CALL_SIZES[s % len(SESSION_CALL_SIZES)]):
            name, inp = (TEST_RUN if c % TEST_RUN_EVERY == TEST_RUN_EVERY - 1
                         else TOOL_CYCLE[c % len(TOOL_CYCLE)])
            events.append(_tool_turn(sid, base + 100 + c, name, inp))
        files.append((f"{sid}.jsonl", events))
        for k, skill in enumerate(session_skills):
            files.append((f"subagents/agent-{s}-{k}.jsonl", [
                _attribution_turn(sid, base + 50_000 + k * 100 + i, skill,
                                  is_sidechain=True, agent_id=f"agent-{s}-{k}")
                for i in range(SPAN_TURNS)]))
    return files


def _score_synthetic_corpus():
    """Run the whole real pipeline and return (accumulator, stats, aq)."""
    acc = Accumulator()
    for fp, events in _synthetic_corpus():
        _feed(acc, fp, events)
    stats = acc.to_corpus_stats(None, None, False)
    return acc, stats, compute_aq(stats)


def _axis_signals(aq, axis_name):
    for pillar in aq["pillars"]:
        for axis in pillar["axes"]:
            if axis["name"] == axis_name:
                return axis["signals"]
    raise AssertionError(f"axis {axis_name!r} was dropped from the AQ payload")


class _ScoredCorpus(unittest.TestCase):
    """Builds and scores the corpus once for the whole module (~3.3k events)."""

    @classmethod
    def setUpClass(cls):
        cls.acc, cls.stats, cls.aq = _score_synthetic_corpus()
        cls.skill_fluency = _axis_signals(cls.aq, "Skill fluency")
        cls.verification = _axis_signals(cls.aq, "Verification")

    def _band(self, target):
        """A rate within a factor of two of its target, either way.

        Each per-tool-call target in aq.py is fitted at p40-p50 of the users who
        record the signal at all. This corpus models deliberately heavy-but-
        plausible practice at the documented median session size, so its rate
        belongs at or above such a target -- and certainly not 20x below it. The
        upper bound is not decoration: a target so low that heavy practice blows
        past it by more than 2x cannot discriminate at the top of the range, which
        is the same failure mode in the opposite direction, and it is the one an
        over-corrected re-fit would produce.
        """
        return (0.5 * target, 2.0 * target)


class TestRatesReachTheScoringLayer(_ScoredCorpus):
    """The plumbing: the accumulator's deduped counts really do become scored rates."""

    def test_skills_total_is_the_deduped_span_count_not_the_turn_count(self):
        """28 invocations, not 28 + 280 attribution turns."""
        expected_invocations = (SESSIONS + SKILLS_EVERY - 1) // SKILLS_EVERY * SKILLS_PER_SESSION
        self.assertEqual(self.stats["stack"]["skills_total"], expected_invocations)
        self.assertEqual(self.skill_fluency["skills_total"], expected_invocations)

    def test_both_skill_rates_are_measured_not_dropped(self):
        """A None rate would be renormalized away by wsum and prove nothing. These
        are MEASURED numbers scored against a target, which is what makes the band
        assertions below meaningful."""
        self.assertIsNotNone(self.skill_fluency["skills_total_per_call"])
        self.assertIsNotNone(self.verification["review_skills_per_call"])
        self.assertEqual(self.skill_fluency["skills_total_per_call_target"],
                         SKILLS_TOTAL_PER_CALL_TARGET)
        self.assertEqual(self.verification["review_skills_per_call_target"],
                         REVIEW_SKILLS_PER_CALL_TARGET)

    def test_review_matcher_drops_a_real_verification_skill(self):
        """The second, compounding cause: `superpowers:verification-before-completion`
        is in the corpus and in `skills_all`, but _is_review_skill_name's exact-tail
        `verify` rule excludes it, so those invocations never reach the review rate."""
        skills_all = dict(self.stats["stack"]["skills_all"])
        missed = "superpowers:verification-before-completion"
        self.assertGreater(skills_all.get(missed, 0), 0)
        self.assertFalse(_is_review_skill_name(missed))
        counted = sum(n for k, n in skills_all.items() if _is_review_skill_name(k))
        review_class = sum(n for k, n in skills_all.items() if k in REVIEW_SKILLS)
        self.assertEqual(self.verification["review_skills"], counted)
        self.assertLess(counted, review_class,
                        "fixture must contain at least one review skill the matcher misses")


class TestSyntheticCorpusVolumeIsHonest(_ScoredCorpus):
    """The control. Every rate term shares ONE denominator (tool_calls_total), so if
    this corpus were simply too tool-heavy, EVERY rate would land far below target.
    `test_runs_per_call` lands ON its target, which localizes the misalignment to the
    two skill terms rather than to the fixture's volume."""

    def test_test_runs_per_call_lands_on_target(self):
        lo, hi = self._band(TEST_RUNS_PER_CALL_TARGET)
        rate = self.verification["test_runs_per_call"]
        self.assertTrue(lo <= rate <= hi,
                        f"control term off target: test_runs_per_call={rate} "
                        f"not in [{lo}, {hi}] -- the fixture's tool volume is wrong, "
                        f"fix the fixture before trusting the band tests below")

    def test_denominator_is_the_documented_median_session_size(self):
        calls = self.stats["volume"]["tool_calls_total"]
        sessions = self.stats["volume"]["total_sessions"]
        self.assertEqual(sessions, SESSIONS)
        self.assertTrue(60 <= calls / sessions <= 76,
                        f"{calls / sessions:.1f} calls/session is outside the ~68 "
                        f"median documented in aq.py's rate rationale")


class TestScoreableBands(_ScoredCorpus):
    """MUST FAIL on the current tree -- see the module docstring."""

    @unittest.expectedFailure
    def test_skills_total_per_call_reaches_a_scoreable_band(self):
        rate = self.skill_fluency["skills_total_per_call"]
        lo, hi = self._band(SKILLS_TOTAL_PER_CALL_TARGET)
        self.assertTrue(
            lo <= rate <= hi,
            f"skills_total_per_call={rate} is outside the scoreable band "
            f"[{lo}, {hi}] around SKILLS_TOTAL_PER_CALL_TARGET="
            f"{SKILLS_TOTAL_PER_CALL_TARGET} "
            f"({rate / SKILLS_TOTAL_PER_CALL_TARGET:.1%} of target from "
            f"{self.skill_fluency['skills_total']} deduped skill invocations over "
            f"{self.skill_fluency['tool_calls']} tool calls). "
            "The target was fitted against a PRE-dedup numerator; commit 28d3bda "
            "made a skill count once per (session, skill) span instead of once per "
            "attributed turn, which is correct behaviour and left the target ~2 "
            "orders of magnitude too high. FIX: re-fit the per-tool-call rate "
            "targets in gnomon/scoring/aq.py and bump SCORE_CONTRACT_ID "
            "(gnomon/scoring/calibration.py binds them). Do NOT widen this band.")

    @unittest.expectedFailure
    def test_review_skills_per_call_reaches_a_scoreable_band(self):
        rate = self.verification["review_skills_per_call"]
        lo, hi = self._band(REVIEW_SKILLS_PER_CALL_TARGET)
        self.assertTrue(
            lo <= rate <= hi,
            f"review_skills_per_call={rate} is outside the scoreable band "
            f"[{lo}, {hi}] around REVIEW_SKILLS_PER_CALL_TARGET="
            f"{REVIEW_SKILLS_PER_CALL_TARGET} "
            f"({rate / REVIEW_SKILLS_PER_CALL_TARGET:.1%} of target from "
            f"{self.verification['review_skills']} counted review invocations over "
            f"{self.verification['tool_calls']} tool calls). "
            "TWO compounding causes: (1) the same span dedup as skills_total, and "
            "(2) _is_review_skill_name (gnomon/analysis/metrics.py) narrowed to an "
            "exact-tail `verify` match, which drops real verification skills such "
            "as `superpowers:verification-before-completion`. FIX: widen the "
            "matcher AND re-fit REVIEW_SKILLS_PER_CALL_TARGET together, then bump "
            "SCORE_CONTRACT_ID. Do NOT widen this band.")


class TestTodaysBrokenValuesArePinned(_ScoredCorpus):
    """The other half of the tripwire: the misalignment is documented as a number,
    not only as an expected failure. When the re-fit lands these go red and must be
    updated in the same change that removes the `expectedFailure` decorators above."""

    # Measured on HEAD ca55882 (score contract v8) from the fixture above:
    #   28 deduped skill invocations / 2748 tool calls = 0.010189  (4.1% of 0.25)
    #   12 counted review invocations / 2748 tool calls = 0.004367 (7.3% of 0.060)
    TODAYS_SKILLS_TOTAL_PER_CALL = 0.010189
    TODAYS_REVIEW_SKILLS_PER_CALL = 0.004367

    def test_skills_total_per_call_is_pinned_near_zero(self):
        self.assertAlmostEqual(self.skill_fluency["skills_total_per_call"],
                               self.TODAYS_SKILLS_TOTAL_PER_CALL, places=6)
        self.assertLess(self.skill_fluency["skills_total_per_call"],
                        0.10 * SKILLS_TOTAL_PER_CALL_TARGET,
                        "heavy skill practice still scores under a tenth of target")

    def test_review_skills_per_call_is_pinned_near_zero(self):
        self.assertAlmostEqual(self.verification["review_skills_per_call"],
                               self.TODAYS_REVIEW_SKILLS_PER_CALL, places=6)
        self.assertLess(self.verification["review_skills_per_call"],
                        0.10 * REVIEW_SKILLS_PER_CALL_TARGET,
                        "heavy review practice still scores under a tenth of target")


if __name__ == "__main__":
    unittest.main()
