"""Bloque 2.A step 2 — the recency blend is removed, as contract 11:11:11.

`_blend_aq` published `0.65 * recent_30d + 0.35 * full_window` for every axis. v10
narrowed the scoring window to ONE calendar month, which made that pair degenerate: both
components end at the same anchor, `full_window` spans the calendar month (28-31 days) and
`recent_30d` the trailing 30, so they cover 93.3% to 100% of the same days. The blend
stopped damping a month against a longer baseline and started reading one month twice.

This change removes the PRODUCING side and keeps the READING side. The line is drawn at
the payload boundary:

  * nothing computes a new blend any more -- no bucket windows, no bucket accumulators, no
    corpus-level `_blend_aq` call, no `bucket_scoring_inputs` block in the payload;
  * `_blend_aq` / `_blend_partial_terms` / `_blend_profiles` / `HISTORY_WEIGHT` all stay,
    because `gnomon/scoring/replay.py` must keep replaying HISTORICAL payloads that carry
    a blend block, and refusing them would retire data this code already published.

Two things these tests pin that are not obvious:

1. **`--tools` was reading two different windows.** `tools_diagnostic` takes its counts
   from `stats["agentic"]`'s axis signals -- which `_blend_aq` copies verbatim from the
   highest-effective-weight component, i.e. `recent_30d` -- and divides them by
   `stats["volume"]["tool_calls_total"]`, which is the full scoring window and which the
   blend never touched. On a 31-day month the first day of the month sits outside the
   trailing-30-day bucket, so every count in the table silently dropped that day while the
   denominator kept it. Removing the blend fixes it by construction.

2. **The blend weights were score-affecting and unfingerprinted.** They multiplied the
   PUBLISHED corpus AQ and lived in `aggregate.py`, outside `calibration.py`'s aq.py-only
   registry -- the same hole `DEFAULT_SCORING_WINDOW_MONTHS` had until v10. Registering
   them is what makes 11:11:11's fingerprint differ from 10:10:10's, and the difference is
   real rather than cosmetic: `RECENT_WEIGHT` is gone.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paxel  # noqa: E402
from gnomon.cli import local  # noqa: E402
from gnomon.scoring import aggregate  # noqa: E402
from gnomon.scoring.aq import DEFAULT_SCORING_WINDOW_MONTHS  # noqa: E402
from gnomon.scoring.calibration import (  # noqa: E402
    BLEND_CALIBRATION_CONSTANT_NAMES, CALIBRATION_FINGERPRINTS, calibration_fingerprint,
)
from gnomon.scoring.versioning import (  # noqa: E402
    SCORE_CONTRACT_ID, SCORING_INPUTS_VERSION, SKILL_DEDUP_INPUTS_VERSION,
)


_NO_CHURN = {"repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
             "deletions": 0, "churn": 0, "commits": 0, "per_repo": []}

# A 31-day month, entirely in the past, so `min(until_dt, now)` always anchors on the
# window's own end and the arithmetic below never depends on the day the suite runs.
# parse_window turns `--until=2026-05-31` into the exclusive 2026-06-01T00:00, so the
# trailing-30-day bucket the blend used to build spanned [2026-05-02, 2026-06-01):
# 2026-05-01 was inside the SCORED month and outside the bucket. That one day is the whole
# experiment.
_MONTH_ARGS = ["--since=2026-05-01", "--until=2026-05-31"]
_OUTSIDE_THE_OLD_BUCKET = "2026-05-01T12:00:00Z"
_INSIDE_THE_OLD_BUCKET = "2026-05-20T12:00:00Z"
# Test runs authored on each of those two days -- `shell_test_runs` stays a published
# Verification diagnostic (v18 moved its SCORED half to a per-session coverage fraction,
# which this fixture never reaches -- no Edit/Write anywhere, so eligible_change_sessions
# is 0 and coverage is N/A). review-Skill calls are added alongside them so Verification's
# ONE remaining per-tool-call RATE term (review_skills) is genuinely scored on both sides of
# the old bucket boundary: `tool_calls_total` is the sum of every call below, split the same
# way, so the mixed-basis assertion stays non-vacuous -- a blend-primary reading would see
# only the mid-month day. Both slices are kept well above the rate evidence floor
# (REVIEW_SKILLS_PER_CALL_TARGET implies ~250 tool calls total), so the Verification axis is
# genuinely scored -- a thinner corpus drops the axis entirely and the comparison becomes
# 0 == 0.
_TEST_RUNS_OUTSIDE = 140
_TEST_RUNS_INSIDE = 60
_REVIEW_CALLS_OUTSIDE = 40
_REVIEW_CALLS_INSIDE = 20


def _prompt(sid, ts):
    return {"type": "user", "sessionId": sid, "timestamp": ts, "cwd": "/repo",
            "isSidechain": False,
            "message": {"role": "user", "content": "run the suite"}}


def _test_run(sid, ts):
    return {"type": "assistant", "sessionId": sid, "timestamp": ts, "cwd": "/repo",
            "isSidechain": False,
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": "python3 -m pytest tests/"}}]}}


def _review_call(sid, ts):
    return {"type": "assistant", "sessionId": sid, "timestamp": ts, "cwd": "/repo",
            "isSidechain": False,
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Skill",
                 "input": {"skill": "verify-changes"}}]}}


def _corpus_events():
    events = []
    for day, sid, test_runs, review_calls in (
            (_OUTSIDE_THE_OLD_BUCKET, "s-first-of-month",
             _TEST_RUNS_OUTSIDE, _REVIEW_CALLS_OUTSIDE),
            (_INSIDE_THE_OLD_BUCKET, "s-mid-month",
             _TEST_RUNS_INSIDE, _REVIEW_CALLS_INSIDE)):
        events.append(_prompt(sid, day))
        events.extend(_test_run(sid, day) for _ in range(test_runs))
        events.extend(_review_call(sid, day) for _ in range(review_calls))
    return events


class _RealRun(unittest.TestCase):
    """Runs the real CLI over a synthetic one-month corpus and exposes summary.json,
    stats.json and the `--tools` record. Everything below reads one of those three."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="gnomon-2a2-")
        cls.addClassCleanup(shutil.rmtree, tmp, ignore_errors=True)
        empty = tempfile.mkdtemp(prefix="gnomon-2a2-empty-")
        cls.addClassCleanup(shutil.rmtree, empty, ignore_errors=True)
        claude_dir = os.path.join(tmp, "claude", "proj")
        os.makedirs(claude_dir)
        with open(os.path.join(claude_dir, "s.jsonl"), "w", encoding="utf-8") as fh:
            for event in _corpus_events():
                fh.write(json.dumps(event) + "\n")
        out = os.path.join(tmp, "out")
        os.makedirs(out)
        src_dirs = dict(
            BASE=os.path.join(tmp, "claude"),
            CODEX_DIR=os.path.join(empty, "codex"),
            GEMINI_DIR=os.path.join(empty, "gemini"),
            ANTIGRAVITY_CLI_DIR=os.path.join(empty, "antigravity"),
            ANTIGRAVITY_IDE_DIR=os.path.join(empty, "antigravity-ide"),
            ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
            PI_DIR=os.path.join(empty, "pi"),
            OPENCODE_DIR=os.path.join(empty, "opencode"),
            CURSOR_DIR=os.path.join(empty, "cursor", "projects"),
            CURSOR_DB=os.path.join(empty, "cursor", "state.vscdb"),
        )
        argv = ["paxel.py", "--include-low-volume", "--summary", "--no-open",
                "--tools", *_MONTH_ARGS]
        captured = io.StringIO()
        with mock.patch.multiple(paxel, OUT_DIR=out, **src_dirs), \
                mock.patch("gnomon.coverage.HISTORY_PATH",
                           os.path.join(tmp, "no-history.jsonl")), \
                mock.patch("gnomon.cli.accumulator.git_churn", return_value=_NO_CHURN), \
                mock.patch("gnomon.output.summary.git_churn", return_value=_NO_CHURN), \
                mock.patch.object(sys, "argv", argv), \
                redirect_stdout(captured):
            paxel.main()
        with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
            cls.summary = json.load(fh)
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
            cls.stats = json.load(fh)
        line = next(l for l in captured.getvalue().splitlines()
                    if l.strip().startswith("json: "))
        cls.tools_record = json.loads(line.strip()[len("json: "):])

    def test_the_corpus_is_shaped_the_way_the_rest_of_this_file_assumes(self):
        """Guard against every assertion below passing for the wrong reason. If the
        synthetic corpus stops carrying test runs / review calls on BOTH sides of the old
        bucket boundary, the mixed-basis test cannot fail even while the bug is present."""
        self.assertEqual(self.stats["volume"]["total_sessions"], 2)
        self.assertEqual(self.stats["behavior"]["shell_test_runs"],
                         _TEST_RUNS_OUTSIDE + _TEST_RUNS_INSIDE)
        self.assertEqual(self.stats["volume"]["tool_calls_total"],
                         _TEST_RUNS_OUTSIDE + _TEST_RUNS_INSIDE
                         + _REVIEW_CALLS_OUTSIDE + _REVIEW_CALLS_INSIDE)
        # Both sides carry real weight, so a window mix-up cannot cancel out.
        self.assertGreater(_TEST_RUNS_OUTSIDE, 0)
        self.assertGreater(_TEST_RUNS_INSIDE, 0)
        self.assertGreater(_REVIEW_CALLS_OUTSIDE, 0)
        self.assertGreater(_REVIEW_CALLS_INSIDE, 0)
        # The Verification axis must actually be scored, or `review_skills` never reaches
        # `signals` in either component and the mixed-basis comparison reads 0 == 0.
        # `shell_test_runs` is a published diagnostic on the same axis (v18 dropped its
        # scored rate term), checked here too so both signals stay reachable.
        signals = {name: axis["signals"]
                   for pillar in self.stats["agentic"]["pillars"]
                   for name, axis in ((axis["name"], axis) for axis in pillar["axes"])}
        self.assertIn("Verification", signals)
        self.assertIn("shell_test_runs", signals["Verification"])
        self.assertIn("review_skills", signals["Verification"])


class TestThePublishedScoreIsNoLongerBlended(_RealRun):
    def test_the_published_aq_carries_no_blend_block(self):
        self.assertNotIn(
            "blend", self.summary["profile"]["aq"],
            "profile.aq still carries a `blend` block -- the published corpus score is "
            "still an average of one month against itself")

    def test_no_axis_carries_per_component_breakdowns(self):
        for pillar in self.summary["profile"]["aq"]["pillars"]:
            for axis in pillar["axes"]:
                with self.subTest(axis=axis["name"]):
                    self.assertNotIn("components", axis)

    def test_the_payload_ships_no_bucket_scoring_inputs(self):
        self.assertNotIn("bucket_scoring_inputs", self.summary)

    def test_the_payload_declares_that_no_blend_was_computed(self):
        # Kept as a declaration rather than dropped: a reader branching on
        # `payload_features` must be able to tell "this runtime no longer blends" apart
        # from "older client that never had the marker".
        self.assertIs(self.summary["payload_features"]["recency_blend"]["enabled"], False)
        reasons = {entry["feature"]: entry["reason"]
                   for entry in self.summary["payload_features"]["omitted"]}
        self.assertEqual(reasons.get("bucket_scoring_inputs"), "recency_blend_removed")

    def test_the_published_axis_signals_describe_the_scored_month(self):
        """`signals` is what mirdash renders under each axis. The blend copied them from
        `recent_30d`, so the payload described a 30-day slice while every count beside it
        described the calendar month."""
        verification = next(axis for pillar in self.summary["profile"]["aq"]["pillars"]
                            for axis in pillar["axes"] if axis["name"] == "Verification")
        self.assertEqual(verification["signals"]["shell_test_runs"],
                         self.stats["behavior"]["shell_test_runs"])
        self.assertEqual(verification["signals"]["tool_calls"],
                         self.stats["volume"]["tool_calls_total"])


class TestToolsDiagnosticReadsOneWindow(_RealRun):
    """The live bug. `--tools` divided a `recent_30d` numerator by a full-window
    denominator, so the table under-reported every count for any month whose first day
    fell outside the trailing 30 days -- silently, with no marker anywhere.

    Exercised through `review_skills`: v18 dropped `shell_test_runs`'s scored per-call rate
    from `_TOOLS_DIAG` (it moved to a per-session coverage fraction, not a per-call rate), so
    it no longer has a `--tools` row at all. review_skills is Verification's remaining
    per-tool-call rate and is still read straight off `stats['agentic']`, so it is exactly as
    exposed to the recency-blend bug this class pins."""

    def _verification_signals(self):
        return next(axis["signals"] for pillar in self.stats["agentic"]["pillars"]
                    for axis in pillar["axes"] if axis["name"] == "Verification")

    def test_counts_come_from_the_same_window_as_the_denominator(self):
        self.assertEqual(
            self.tools_record["counts"]["review_skills"],
            self._verification_signals()["review_skills"],
            "the --tools table counted review-skill calls over the trailing-30-day "
            "recency bucket while dividing by the full scoring window's tool calls")

    def test_the_denominator_is_the_scoring_window(self):
        self.assertEqual(self.tools_record["tool_calls"],
                         self.stats["volume"]["tool_calls_total"])

    def test_the_reported_rate_is_that_single_ratio(self):
        expected = round(self._verification_signals()["review_skills"]
                         / self.stats["volume"]["tool_calls_total"], 6)
        self.assertEqual(self.tools_record["rates"]["review_skills"], expected)


class TestTheProducingSideIsGone(unittest.TestCase):
    def test_the_bucket_definitions_are_deleted(self):
        for name in ("RECENCY_BLEND_ENABLED", "RECENT_WEIGHT", "RECENT_WINDOW_DAYS",
                     "AQ_BUCKETS"):
            with self.subTest(constant=name):
                self.assertFalse(
                    hasattr(aggregate, name),
                    f"aggregate.{name} only ever existed to BUILD a blend; leaving it "
                    f"dormant invites the machinery back without a contract move")

    def test_the_bucket_window_builder_is_deleted(self):
        self.assertFalse(hasattr(local, "_rolling_aq_bucket_windows"))

    def test_accumulate_no_longer_shapes_bucket_corpora(self):
        events = _corpus_events()
        with tempfile.NamedTemporaryFile() as transcript, \
                mock.patch.object(local, "iter_events", return_value=events), \
                mock.patch("gnomon.cli.accumulator.git_churn", return_value=_NO_CHURN), \
                mock.patch("gnomon.output.summary.git_churn", return_value=_NO_CHURN):
            _stats, narrative = local._accumulate(
                [("claude", transcript.name, "claude")],
                since_dt=None, until_dt=None, cursor_twins=set(),
                antigravity=None, verbose=False)
        for key in ("_aq_bucket_windows", "_aq_bucket_stats",
                    "_aq_bucket_per_source_stats"):
            with self.subTest(key=key):
                self.assertNotIn(key, narrative)


class TestTheReadingSideStays(unittest.TestCase):
    """A payload captured before this change still carries a blend block, and replaying it
    is the whole point of persisting scoring inputs. The composition helpers therefore stay
    exported and exercised."""

    def test_the_blend_helpers_are_still_available(self):
        for name in ("_blend_aq", "_blend_partial_terms", "_blend_profiles",
                     "HISTORY_WEIGHT"):
            with self.subTest(symbol=name):
                self.assertTrue(hasattr(aggregate, name))

    def test_score_by_source_still_blends_payload_supplied_buckets(self):
        from tests._scoring_vectors_cases import rolling_cases
        name, sibs, bucket_sibs, metadata = rolling_cases()[0]
        result = aggregate.score_by_source(
            sibs, bucket_scoring_inputs_by_source=bucket_sibs,
            bucket_metadata=metadata)
        blend = result["by_source"]["claude"]["aq"]["blend"]
        self.assertEqual([bucket["id"] for bucket in blend["buckets"]],
                         ["recent_30d", "full_window"])


class TestScoreContractMovesWithTheRemoval(unittest.TestCase):
    def test_the_blend_removal_kept_its_own_contract_entry(self):
        """v11 pinned `SCORE_CONTRACT_ID == "11:11:11"` because the blend removal WAS the
        current contract. Later bumps are legitimate, so what this file still owns is the
        audit trail: the entry v11 published must stay in the registry, byte for byte,
        whatever the live contract has become. Re-pointing the pin at the registry rather
        than deleting it keeps the guarantee that made it worth writing -- an in-place edit
        of a published fingerprint stays impossible. (Same move v11 made to v10's pin in
        tests/test_one_month_scoring_window.py.)"""
        self.assertIn("11:11:11", CALIBRATION_FINGERPRINTS)
        self.assertEqual(CALIBRATION_FINGERPRINTS["11:11:11"], "888bec08099b6fbc")
        self.assertGreaterEqual(SCORING_INPUTS_VERSION, 11)

    def test_the_live_contract_has_its_own_fingerprint_entry(self):
        self.assertIn(SCORE_CONTRACT_ID, CALIBRATION_FINGERPRINTS)
        self.assertEqual(calibration_fingerprint(),
                         CALIBRATION_FINGERPRINTS[SCORE_CONTRACT_ID])

    def test_the_fingerprint_actually_moved(self):
        # Pinned against v11's OWN entry, not the live one: this file owns the claim that
        # registering the blend weights is what made 11:11:11 differ from 10:10:10, and that
        # claim must keep holding after later bumps.
        self.assertNotEqual(CALIBRATION_FINGERPRINTS["11:11:11"],
                            CALIBRATION_FINGERPRINTS["10:10:10"])

    def test_older_contract_entries_are_untouched(self):
        self.assertEqual(CALIBRATION_FINGERPRINTS["8:8:8"], "38bf1d623bea1517")
        self.assertEqual(CALIBRATION_FINGERPRINTS["9:9:9"], "2e7638d58c2b26e4")
        self.assertEqual(CALIBRATION_FINGERPRINTS["10:10:10"], "7a2c444ff5c26f06")

    def test_the_blend_weights_are_under_the_fingerprint(self):
        """What moves the published score here is the disappearance of a multiplier, and
        the registry has to see it. `RECENT_WEIGHT` is registered as an ABSENT constant --
        the fingerprint records that it no longer exists, which is exactly the fact this
        contract publishes."""
        self.assertEqual(dict(BLEND_CALIBRATION_CONSTANT_NAMES)["RECENT_WEIGHT"],
                         "gnomon.scoring.aggregate")
        self.assertEqual(dict(BLEND_CALIBRATION_CONSTANT_NAMES)["HISTORY_WEIGHT"],
                         "gnomon.scoring.aggregate")

    def test_reintroducing_a_blend_weight_moves_the_fingerprint(self):
        baseline = calibration_fingerprint()
        with mock.patch.object(aggregate, "RECENT_WEIGHT", 0.65, create=True):
            self.assertNotEqual(
                calibration_fingerprint(), baseline,
                "RECENT_WEIGHT came back without moving the fingerprint -- the registry "
                "is hashing names, not the presence and value of the constants")

    def test_the_v11_bump_did_not_narrow_the_counter_gate(self):
        """v11 removed the recency blend -- a FORMULA move -- so it added no counter-version
        refusal of its own: v8..v11 all clear the pre-dedup gate.

        Scoped to the pre-dedup gate deliberately, for the same reason as the v10 twin in
        tests/test_one_month_scoring_window.py: the old form asserted these versions reached
        `scoring_inputs_by_source`, which tested the LIVE floor rather than v11's contribution
        to it. v12 narrowed that floor because `actions_per_prompt` changed basis (see
        tests/test_top_level_actions_per_prompt.py), which does not make this v11 fact any
        less true."""
        from gnomon.scoring.replay import replay, ReplayError
        self.assertEqual(SKILL_DEDUP_INPUTS_VERSION, 8)
        for version in (8, 9, 10, 11):
            with self.subTest(version=version):
                payload = {
                    "payload_features": {"version": 1, "supported": [],
                                         "emitted": [], "omitted": []},
                    "context": {"window_months": DEFAULT_SCORING_WINDOW_MONTHS},
                    "scoring_inputs_version": version,
                }
                with self.assertRaises(ReplayError) as caught:
                    replay(payload)
                self.assertNotIn("dedup", str(caught.exception))
                self.assertNotIn("window_months", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
