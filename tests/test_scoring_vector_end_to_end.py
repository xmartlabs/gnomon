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

Status: the re-fit landed in contract 9:9:9
------------------------------------------
The two band tests below were shipped `@unittest.expectedFailure` as a self-clearing
tripwire while the targets were still the pre-dedup ones. The re-fit
(SKILLS_TOTAL_PER_CALL_TARGET 0.25 -> 0.009, REVIEW_SKILLS_PER_CALL_TARGET
0.060 -> 0.004, plus `_is_review_skill_name` admitting a `verif`-leading tail) cleared
them, so the decorators are gone and `TestScoredRatesArePinned` now pins the CORRECT
rates instead of the broken ones. The bands were not touched to make this pass -- both
rates land ~1.1-1.3x their target, inside the [0.5x, 2x] window the fixture's
heavy-but-plausible practice is supposed to land in.

Keep reading this file as the acceptance test for any FUTURE re-fit: change a target
and the pinned ratios move, which is the signal that the fixture's practice level has
to be re-argued rather than the band widened.
"""
import unittest

from gnomon.analysis.metrics import _is_review_skill_name
from gnomon.cli.accumulator import Accumulator
from gnomon.scoring.aq import (REVIEW_SKILLS_PER_CALL_TARGET,
                               SKILLS_TOTAL_PER_CALL_TARGET, compute_aq)
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
                 # The noun form. Missed by v8's exact-tail `verify` rule AND by the
                 # pre-v8 substring rule ("verification" does not contain "verify"), so
                 # it stayed in the corpus and out of the review numerator until 9:9:9
                 # widened the matcher to a `verif`-LEADING tail. Kept in the fixture as
                 # the regression guard for that.
                 "superpowers:verification-before-completion")
OTHER_SKILLS = ("superpowers:test-driven-development", "brainstorming", "writing-plans",
                "superpowers:systematic-debugging", "sdd-tasks", "skill-creator")

# A plausible working mix: reads, searches, edits, shell. One in 34 calls is a test
# run; every session both writes code (two distinct Edit targets) and runs a test, so
# under v18 these sessions are test-COVERED eligible change-sessions (Verification's
# coverage numerator), while the skill rates remain the focus of the band tests below.
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

    def test_review_matcher_reaches_every_review_skill_in_the_corpus(self):
        """`superpowers:verification-before-completion` is in the corpus and in
        `skills_all`; since 9:9:9 the matcher's `verif`-leading tail rule counts it, so the
        scored review numerator is the WHOLE review class rather than a lossy subset."""
        skills_all = dict(self.stats["stack"]["skills_all"])
        noun_form = "superpowers:verification-before-completion"
        self.assertGreater(skills_all.get(noun_form, 0), 0)
        self.assertTrue(_is_review_skill_name(noun_form))
        counted = sum(n for k, n in skills_all.items() if _is_review_skill_name(k))
        review_class = sum(n for k, n in skills_all.items() if k in REVIEW_SKILLS)
        self.assertEqual(self.verification["review_skills"], counted)
        self.assertEqual(counted, review_class,
                         "the matcher must not silently drop any review-class skill "
                         "the fixture invokes")


class TestSyntheticCorpusVolumeIsHonest(_ScoredCorpus):
    """The control. Every surviving rate term shares ONE denominator (tool_calls_total),
    so if this corpus were simply too tool-heavy, EVERY rate would land far below target.
    The fixture's calls/session sits on the documented median, which localizes any
    band failure to the skill terms rather than to the fixture's volume. (v18 removed the
    `test_runs_per_call` density control: Verification's test half is now per-session
    coverage, not a per-call rate, so it no longer shares this denominator.)"""

    def test_denominator_is_the_documented_median_session_size(self):
        calls = self.stats["volume"]["tool_calls_total"]
        sessions = self.stats["volume"]["total_sessions"]
        self.assertEqual(sessions, SESSIONS)
        self.assertTrue(60 <= calls / sessions <= 76,
                        f"{calls / sessions:.1f} calls/session is outside the ~68 "
                        f"median documented in aq.py's rate rationale")


class TestScoreableBands(_ScoredCorpus):
    """The acceptance criterion for the calibration -- see the module docstring."""

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
            "This band was red on contract 8:8:8 because the target was fitted against "
            "a PRE-dedup numerator; 9:9:9 re-fitted it. If it is red again, either the "
            "counting rule moved or a re-fit over-corrected. Re-fit the per-tool-call "
            "rate targets in gnomon/scoring/aq.py and bump SCORE_CONTRACT_ID "
            "(gnomon/scoring/calibration.py binds them). Do NOT widen this band.")

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
            "This band was red on contract 8:8:8 for TWO compounding reasons: the same "
            "span dedup as skills_total, and `_is_review_skill_name` dropping real "
            "verification skills. 9:9:9 fixed both together. If it is red again, re-fit "
            "REVIEW_SKILLS_PER_CALL_TARGET and bump SCORE_CONTRACT_ID. Do NOT widen "
            "this band.")


class TestScoredRatesArePinned(_ScoredCorpus):
    """The other half of the tripwire: the calibration is documented as a NUMBER, not only
    as a band. A target change moves these ratios, so a future re-fit has to come here and
    re-argue the fixture's practice level instead of quietly widening the band above."""

    # Measured on the 9:9:9 tree from the fixture above:
    #   28 deduped skill invocations  / 2748 tool calls = 0.010189 (113% of 0.009)
    #   14 counted review invocations / 2748 tool calls = 0.005095 (127% of 0.004)
    # The review count is 14, not 12: the 9:9:9 matcher also counts the two
    # `superpowers:verification-before-completion` spans (see REVIEW_SKILLS above).
    SKILLS_TOTAL_PER_CALL = 0.010189
    REVIEW_SKILLS_PER_CALL = 0.005095

    def test_skills_total_per_call_is_pinned_on_target(self):
        self.assertAlmostEqual(self.skill_fluency["skills_total_per_call"],
                               self.SKILLS_TOTAL_PER_CALL, places=6)
        self.assertGreater(self.skill_fluency["skills_total_per_call"],
                           SKILLS_TOTAL_PER_CALL_TARGET,
                           "heavy skill practice must score at or above target")

    def test_review_skills_per_call_is_pinned_on_target(self):
        self.assertAlmostEqual(self.verification["review_skills_per_call"],
                               self.REVIEW_SKILLS_PER_CALL, places=6)
        self.assertGreater(self.verification["review_skills_per_call"],
                           REVIEW_SKILLS_PER_CALL_TARGET,
                           "heavy review practice must score at or above target")


if __name__ == "__main__":
    unittest.main()
