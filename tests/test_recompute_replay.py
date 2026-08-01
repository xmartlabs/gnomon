"""tests/test_recompute_replay.py -- recompute-grade-payload capability.

Proves a persisted summary payload alone (no local transcripts) can reproduce
profile.aq via gnomon.scoring.replay.replay() -- EXACTLY for single-source
payloads, APPROXIMATELY (tool-volume-weighted mean of per-source scores) for
multi-source payloads -- and that the payload fields (bucket_scoring_inputs,
payload_features) are wired correctly end-to-end through the real CLI.

No `scoring_inputs_corpus` block ships for any payload (scope relaxation:
approximate multi-source recompute is acceptable, so the ~487 KB merged-corpus
block that bought only exactness was dropped entirely -- see
gnomon/scoring/replay.py's module docstring).
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paxel
from tests.test_smoke import FIX, SRC_DIRS, _claude_turn

from gnomon.scoring.replay import (
    replay, ReplayError, IncompatibleScoringInputs, IncompatibleScoringWindow, AQ_EXACT,
    AQ_APPROXIMATE_WEIGHTED_MEAN, AQ_APPROXIMATE_WEIGHTED_MEAN_UNBLENDED,
)
from gnomon.scoring.aq import DEFAULT_SCORING_WINDOW_MONTHS, compute_aq
from gnomon.scoring.profiles import stats_from_scoring_block
from gnomon.scoring.versioning import (
    IncompatibleScoreContract, SCORE_CONTRACT_ID, SCORING_INPUTS_VERSION,
    SKILL_DEDUP_INPUTS_VERSION,
)

# Sentinel for "this payload has no `context.window_months` key at all", which is a
# different case from one that declares None -- see
# WiderWindowPayloadIsNotLaunderedIntoTheLiveContract.
_UNSET = object()

# The committed claude fixture's transcripts all fall on 2026-06-01, so this is a REAL
# one-calendar-month run over them, not a narrowed one: paxel's own `parse_window` turns
# the inclusive `--until` day into the exclusive 2026-07-01 midnight, which is exactly the
# shape `gnomon/upload/mirdash.py::_anchor_window` requests for a monthly upload.
_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE = ("--since=2026-06-01", "--until=2026-06-30")
_SIX_MONTHS_OVER_THE_CLAUDE_FIXTURE = ("--since=2026-01-01", "--until=2026-06-30")


def _run_summary(testcase, sources, extra_argv=None):
    """Run paxel over the committed multi-source fixtures (tests/fixtures/), which
    all carry fixed historical dates well outside any rolling 30-day window relative
    to "now" -- so this gives a clean, un-blended multi-source corpus.

    `extra_argv` forwards real CLI flags (`--since=`/`--until=`) so a caller can run the
    same fixtures over a genuine calendar-month window instead of an unbounded read --
    see PayloadDeclaresTheCorpusScaleItWasBuiltOver for why that difference is now
    visible in the payload."""
    out = tempfile.mkdtemp(prefix="paxel-replay-")
    testcase.addClassCleanup(shutil.rmtree, out, ignore_errors=True)
    argv = (["paxel.py"] + list(sources) + ["--summary", "--no-open"]
            + list(extra_argv or []))
    buf = io.StringIO()
    with (
        mock.patch.multiple(paxel, OUT_DIR=out, **SRC_DIRS),
        mock.patch.object(sys, "argv", argv),
        contextlib.redirect_stdout(buf),
    ):
        paxel.main()
    with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
        stats = json.load(fh)
    with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    return stats, summary


def _declaring_the_live_window(summary):
    """Return a copy of `summary` that declares the LIVE scoring window.

    The corpora behind it are SHAPE fixtures, not calendar months: the committed
    multi-source set spans 2025-06 to 2026-07, and the recency-blend fixtures place
    sessions ~200 days apart on purpose, because what they exercise is per-source pooling,
    bucket trimming and blending -- never corpus scale. `build_summary` now stamps the span
    each run actually covered (null for an unbounded read), so replaying one of these
    verbatim would only re-prove the corpus-scale gate, which
    PayloadDeclaresTheCorpusScaleItWasBuiltOver and
    WiderWindowPayloadIsNotLaunderedIntoTheLiveContract already pin from both sides.
    Declaring the window here keeps each of these classes about its own subject.

    Classes whose fixture genuinely fits inside one calendar month do NOT use this -- they
    pass real `--since`/`--until` flags instead, so their payload declares its scale the
    way a real one does.
    """
    payload = json.loads(json.dumps(summary))
    payload.setdefault("context", {})["window_months"] = DEFAULT_SCORING_WINDOW_MONTHS
    return payload


def _run_claude_summary(testcase, rows, extra_argv=None):
    """Like tests.test_smoke._run_claude_transcript, but also writes/returns
    summary.json (needed for the recency-blend tests, which need dynamically
    recent timestamps a committed fixture cannot provide)."""
    proj = tempfile.mkdtemp(prefix="paxel-replay-claude-")
    testcase.addClassCleanup(shutil.rmtree, proj, ignore_errors=True)
    sess_dir = os.path.join(proj, "proj-x")
    os.makedirs(sess_dir, exist_ok=True)
    with open(os.path.join(sess_dir, "session.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    empty = tempfile.mkdtemp(prefix="paxel-replay-empty-")
    testcase.addClassCleanup(shutil.rmtree, empty, ignore_errors=True)
    dirs = dict(
        BASE=proj, CODEX_DIR=empty, GEMINI_DIR=empty, PI_DIR=empty,
        ANTIGRAVITY_CLI_DIR=empty, ANTIGRAVITY_IDE_DIR=empty,
        ANTIGRAVITY_DB=os.path.join(empty, "nope.vscdb"),
        OPENCODE_DIR=empty, CURSOR_DIR=empty,
        CURSOR_DB=os.path.join(empty, "nope.vscdb"),
    )
    out = tempfile.mkdtemp(prefix="paxel-replay-out-")
    testcase.addClassCleanup(shutil.rmtree, out, ignore_errors=True)
    argv = ["paxel.py", "claude", "--summary", "--no-open"] + (extra_argv or [])
    buf = io.StringIO()
    with (
        mock.patch.multiple(paxel, OUT_DIR=out, **dirs),
        mock.patch.object(sys, "argv", argv),
        contextlib.redirect_stdout(buf),
    ):
        paxel.main()
    with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
        stats = json.load(fh)
    with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    return stats, summary


_ISO_TS_RE = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z')


def _shift_iso_timestamps(text, delta):
    """Shift every bare ISO-8601 UTC timestamp in `text` by `delta`, preserving
    fractional-second suffixes untouched. Used to turn a committed, fixed-date
    fixture into a genuinely RECENT one without hand-authoring a source's event
    schema from scratch -- the fixture already round-trips through the real
    parser with its original dates, so only the dates need to move."""
    def repl(match):
        base, frac = match.group(1), match.group(2) or ""
        dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return (dt + delta).strftime("%Y-%m-%dT%H:%M:%S") + frac + "Z"
    return _ISO_TS_RE.sub(repl, text)


def _recent_codex_fixture_dir(testcase, base_ts):
    """Build a CODEX_DIR combining the committed (fixed-historical-date) codex
    fixture -- which stays outside any 30-day recency window as time passes --
    with a SECOND copy of the exact same session whose timestamps are shifted
    to `base_ts`, giving codex genuine recent_30d activity distinct from its
    historical baseline. Session identity for codex is derived from the FILE
    basename (see gnomon/sources/codex.py::_codex_events), so two differently
    named files parse as two independent sessions."""
    src = os.path.join(FIX, "codex", "session-codex.jsonl")
    with open(src, encoding="utf-8") as fh:
        original_text = fh.read()
    first_match = _ISO_TS_RE.search(original_text)
    first_ts = datetime.strptime(first_match.group(1), "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc)
    recent_text = _shift_iso_timestamps(original_text, base_ts - first_ts)

    out_dir = tempfile.mkdtemp(prefix="paxel-replay-codex-recent-")
    testcase.addClassCleanup(shutil.rmtree, out_dir, ignore_errors=True)
    shutil.copy(src, os.path.join(out_dir, "session-codex-history.jsonl"))
    with open(os.path.join(out_dir, "session-codex-recent.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(recent_text)
    return out_dir


def _run_blended_multisource_summary(testcase):
    """A genuinely multi-source, genuinely blended payload, built through the
    real CLI end-to-end: claude carries only the committed (fixed-historical)
    fixture, codex carries that SAME committed fixture PLUS one copy shifted
    into the last 5 days (see _recent_codex_fixture_dir). This exercises the
    exact condition test_replayed_aq_matches_the_payloads_own_aggregate_diagnostic's
    docstring argued "would not add new coverage" for `aq` -- a real recency
    blend firing for a multi-source corpus -- which is precisely the condition
    Fix 1 (round 2) needed and did not have a fixture for."""
    now = datetime.now(timezone.utc)
    codex_dir = _recent_codex_fixture_dir(testcase, now - timedelta(days=5))
    dirs = dict(SRC_DIRS)
    dirs["CODEX_DIR"] = codex_dir
    out = tempfile.mkdtemp(prefix="paxel-replay-blend-")
    testcase.addClassCleanup(shutil.rmtree, out, ignore_errors=True)
    argv = ["paxel.py", "claude", "codex", "--summary", "--no-open"]
    buf = io.StringIO()
    with (
        mock.patch.multiple(paxel, OUT_DIR=out, **dirs),
        mock.patch.object(sys, "argv", argv),
        contextlib.redirect_stdout(buf),
    ):
        paxel.main()
    with open(os.path.join(out, "stats.json"), encoding="utf-8") as fh:
        stats = json.load(fh)
    with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    return stats, summary


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _dense_session(sid, base_ts, calls, tool):
    """A single session running `calls` tool invocations of `tool`, dense enough
    that a handful of these sessions dominate an AQ computation -- needed so the
    history/recent slices genuinely differ, not just in session count."""
    rows = []
    for i in range(calls):
        ts = _iso(base_ts + timedelta(minutes=i))
        tu = {"type": "tool_use", "name": tool, "input": {}}
        if tool == "Edit":
            tu["input"] = {"file_path": "/repo/a.py", "old_string": "", "new_string": "x" * 60}
        elif tool == "Read":
            tu["input"] = {"file_path": "/repo/a.py"}
        rows.append({"type": "user", "sessionId": sid, "cwd": "/repo", "timestamp": ts,
                     "message": {"role": "user", "content": "go"}})
        rows.append({"type": "assistant", "sessionId": sid, "cwd": "/repo", "timestamp": ts,
                     "message": {"role": "assistant", "model": "claude-opus-4-8",
                                 "content": [tu]}})
        rows.append({"type": "user", "sessionId": sid, "cwd": "/repo", "timestamp": ts,
                     "message": {"role": "user", "content": [
                         {"type": "tool_result", "content": "ok", "is_error": False}]}})
    return rows


class MultisourceApproximateAq(unittest.TestCase):
    """Test #1 (reworked -- scope relaxation, then review remediation round 2):
    multi-source replay is APPROXIMATE. No scoring_inputs_corpus block ships,
    so replay() cannot reproduce the merged-corpus profile.aq exactly; instead
    it composes the same tool-volume-weighted mean of per-source AQs that
    score_by_source's aggregate.aq_diagnostic already implements.

    This fixture's committed transcripts use FIXED historical dates well
    outside any rolling 30-day window (see _run_summary's docstring), so no
    recency blend ever fires here -- deliberately: this class exists to prove
    the UNBLENDED base composition is correct from STABLE, git-committed
    fixtures. The genuinely blended regime (`aq_exactness ==
    "approximate_weighted_mean"`, Fix 1 round 2) is covered by
    MultisourceBlendedApproximateAq below, which needs dynamically recent
    timestamps a committed fixture cannot provide."""

    @classmethod
    def setUpClass(cls):
        cls._stats, summary = _run_summary(cls, ["claude", "codex", "gemini"])
        cls._summary = _declaring_the_live_window(summary)

    def test_fixture_is_genuinely_multi_source(self):
        by_source = self._summary["scoring_inputs_by_source"]
        active = {s for s, b in by_source.items() if b["window"]["volume"]["total_sessions"]}
        self.assertGreaterEqual(len(active), 2, f"expected 2+ active sources, saw {active}")

    def test_no_corpus_block_ships(self):
        self.assertNotIn("scoring_inputs_corpus", self._summary)

    def test_replay_is_marked_unblended(self):
        """No bucket in this fixture ever carries a real session (fixed historical
        dates), so there is nothing to blend the base value against."""
        result = replay(self._summary)
        self.assertEqual(result["aq_exactness"], AQ_APPROXIMATE_WEIGHTED_MEAN_UNBLENDED)

    def test_replayed_aq_matches_the_payloads_own_aggregate_diagnostic(self):
        """The reconstruction reads ONLY payload-shipped per-source blocks -- for this
        fixture (no recency blend fires anywhere, see the class docstring), that is
        the identical computation the payload's own
        profiles_by_source.aggregate.aq_diagnostic already ran, so the two must match
        bit-for-bit -- proving the unblended base composition is correct, not just
        well-formed. This equality is NOT expected to hold once a blend fires (see
        MultisourceBlendedApproximateAq): aq_diagnostic is computed from the FULL,
        untrimmed per-source bucket breakdown, which a shipped payload never carries."""
        result = replay(self._summary)
        self.assertEqual(result["aq"],
                          self._summary["profiles_by_source"]["aggregate"]["aq_diagnostic"])

    def test_replayed_aq_is_well_formed_but_not_claimed_exact_to_canonical(self):
        """Deliberately does NOT assert equality with payload["profile"]["aq"] --
        that is the merged-corpus canonical value (distinct counts as unions), while
        this is a weighted MEAN of per-source scores. See aggregate.py's module
        docstring: the two are documented to diverge by several points on a real
        multi-source corpus. This test only proves the approximate value is a
        genuine, complete AQ dict, not a stub."""
        result = replay(self._summary)
        self.assertIn("aq_0_100", result["aq"])
        self.assertIn("pillars", result["aq"])

    def test_replayed_profiles_by_source_matches(self):
        """NOTE on coverage: this fixture's committed transcripts use FIXED
        historical dates well outside any rolling 30-day window (see
        _run_summary's docstring), so no recency blend fires here -- this is
        deliberate, not an oversight: this class exists to prove exact
        profiles_by_source replay from STABLE, git-committed multi-source
        fixtures, which requires dates far enough in the past to never enter
        a "recent" bucket as time passes. It therefore exercises the
        `profiles_by_source_status == "exact"` / no-blend-fired branch of
        _profiles_by_source_status, NOT the blend-fired-and-trimmed branch --
        that is ProfilesBySourceGuardIsStructuralNotMarkerDependent's coverage
        (which needs a genuinely blended MULTI-source fixture; a single-source
        one is always exact after the corpus-equivalence fix, see BlendedAqExact).

        For `profiles_by_source` specifically, a genuinely blended multi-source
        case exercises the IDENTICAL replay.py code path this test already
        covers (detection is source-count-agnostic: it only inspects
        bucket_scoring_inputs.corpus, never `sources`), so it adds no new
        coverage for THIS field. That is NOT true for `aq` -- see
        MultisourceBlendedApproximateAq, which is the case a genuinely blended
        multi-source fixture DOES newly cover."""
        result = replay(self._summary)
        self.assertEqual(result["profiles_by_source"], self._summary["profiles_by_source"])
        self.assertEqual(result["profiles_by_source_status"], "exact")


class MultisourceBlendedApproximateAq(unittest.TestCase):
    """Review remediation round 2, Fix 1 + Fix 4: exercises the merged
    bucket-corpus blend for a GENUINELY blended multi-source payload, through
    the real CLI end-to-end (claude static history + codex with a real
    recent_30d session) -- the exact condition MultisourceApproximateAq's
    docstring used to argue "would not add new coverage" for `aq`. It does:
    aq_diagnostic takes a different branch (score_by_source WITHOUT the
    per-source bucket breakdown) whose blend behavior only diverges from the
    unblended base value when a blend actually fires."""

    @classmethod
    def setUpClass(cls):
        cls._stats, summary = _run_blended_multisource_summary(cls)
        cls._summary = _declaring_the_live_window(summary)

    def test_fixture_has_a_real_recency_blend(self):
        bucket = self._summary["bucket_scoring_inputs"]["corpus"]["recent_30d"]["window"]
        self.assertGreater(bucket["volume"]["total_sessions"], 0)
        self.assertIn("blend", self._summary["profile"]["aq"],
                      "fixture produced no blend at all for the canonical profile.aq either")

    def test_replay_blends_the_merged_bucket_corpus(self):
        result = replay(self._summary)
        self.assertEqual(result["aq_exactness"], AQ_APPROXIMATE_WEIGHTED_MEAN)

    def test_blended_value_diverges_from_the_unblended_base_value(self):
        """Proves the blend genuinely fired and moved the number -- not just that
        the code path executed without raising."""
        sibs = self._summary["scoring_inputs_by_source"]
        payload_features = self._summary["payload_features"]
        bucket_by_source = self._summary.get("bucket_scoring_inputs", {}).get("by_source") or {}
        bucket_metadata = self._summary.get("bucket_scoring_inputs", {}).get("metadata") or []
        from gnomon.scoring.replay import _replay_multisource_approximate_aq
        unblended_aq, unblended_exactness = _replay_multisource_approximate_aq(
            sibs, bucket_by_source, bucket_metadata, bucket_corpus=None)
        self.assertEqual(unblended_exactness, AQ_APPROXIMATE_WEIGHTED_MEAN_UNBLENDED)

        blended = replay(self._summary)["aq"]
        self.assertNotEqual(
            blended["aq_0_100"], unblended_aq["aq_0_100"],
            "the merged-corpus blend fired but did not move the score -- Fix 1 regressed")

    def test_replayed_aq_is_a_well_formed_aq_dict(self):
        result = replay(self._summary)
        self.assertIn("aq_0_100", result["aq"])
        self.assertIn("pillars", result["aq"])
        self.assertIn("blend", result["aq"], "the blended result should carry a blend record")


class SingleSourceAqExact(unittest.TestCase):
    """Test #2: single-source payload has no corpus block (none ships for any
    source count now -- see module docstring), and replay is EXACT: the source's
    own window block IS the corpus block, so nothing was pooled away."""

    @classmethod
    def setUpClass(cls):
        cls._stats, cls._summary = _run_summary(
            cls, ["claude"], extra_argv=list(_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE))

    def test_no_corpus_block_key(self):
        self.assertNotIn("scoring_inputs_corpus", self._summary)

    def test_replay_is_exact_for_single_source(self):
        result = replay(self._summary)
        self.assertEqual(result["aq_exactness"], AQ_EXACT)
        self.assertEqual(result["aq"], self._summary["profile"]["aq"])


class BlendedAqExact(unittest.TestCase):
    """Test #3: recent_30d bucket block reproduces the blended AQ exactly, AND the
    blend must be non-vacuous (blended != full_window_aq) so the test cannot pass
    by construction alone."""

    @classmethod
    def setUpClass(cls):
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(days=200)
        recent_ts = now - timedelta(days=5)
        rows = []
        # History slice: dense but purely exploratory (Read-only).
        for i in range(5):
            rows += _dense_session(f"hist-{i}", old_ts + timedelta(hours=i), calls=40, tool="Read")
        # Recent slice (inside the 30-day bucket): equally dense but pure Edit --
        # a deliberately different behavioral shape so the blend actually moves
        # the score (full-window dilutes the two; recent_30d sees only the edits).
        for i in range(5):
            rows += _dense_session(f"recent-{i}", recent_ts + timedelta(hours=i), calls=40, tool="Edit")
        cls._stats, summary = _run_claude_summary(cls, rows)
        cls._summary = _declaring_the_live_window(summary)

    def test_bucket_has_recent_sessions(self):
        bucket = self._summary["bucket_scoring_inputs"]["corpus"]["recent_30d"]["window"]
        self.assertGreater(bucket["volume"]["total_sessions"], 0)

    def test_blend_is_non_vacuous(self):
        """Guard the fixture: the recency blend must actually have moved the score,
        or this test proves nothing about exact replay of a REAL blend. `blend` is
        set by aggregate.py's _blend_aq only when blending actually happened
        (stats.json strips the internal _full_window_agentic field, so read the
        published aq_diagnostic's own blend record instead)."""
        aq = self._summary["profile"]["aq"]
        self.assertIn("blend", aq, "fixture produced no blend at all")
        self.assertNotEqual(aq["blend"]["full_aq"], aq["aq_0_100"])

    def test_replayed_blended_aq_matches_canonical_exactly(self):
        result = replay(self._summary)
        self.assertEqual(result["aq_exactness"], AQ_EXACT)
        self.assertEqual(result["aq"], self._summary["profile"]["aq"])

    def test_replayed_profiles_by_source_matches_via_single_source_corpus_equivalence(self):
        """Review remediation, round 2, Fix 3 (supersedes the original Fix 1
        regression test for single-source payloads): a single source's own
        bucket_scoring_inputs.corpus window block IS that one source's
        per-source bucket block -- nothing was pooled away, the exact same
        equivalence _replay_single_source_aq already exploits for `aq`
        (local.py's own single_source optimization). Trimming by_source
        therefore must NOT force profiles_by_source: None for single-source
        payloads: replay() synthesizes the per-source breakdown from
        bucket_corpus instead of giving up. This fixture is single-source
        claude with a REAL blend (see test_blend_is_non_vacuous) and
        gnomon/cli/local.py unconditionally trims bucket_scoring_inputs.by_source
        (see payload_features.omitted), so it is exactly the shape that used
        to fall back to profiles_by_source: None -- now it must not."""
        omitted = self._summary["payload_features"]["omitted"]
        self.assertTrue(
            any(o["feature"] == "bucket_scoring_inputs.by_source" for o in omitted),
            "fixture assumption broken: by_source must be trimmed for this test to be meaningful")
        result = replay(self._summary)
        self.assertEqual(result["profiles_by_source_status"], "exact")
        self.assertEqual(result["profiles_by_source"], self._summary["profiles_by_source"])


class ProfilesBySourceGuardIsStructuralNotMarkerDependent(unittest.TestCase):
    """Review remediation, round 2, Fix 2: the not-replayable guard must rest on
    the payload's OWN observable shape (bucket_by_source empty + a bucket that
    genuinely carried recent sessions), never on a self-reported omission
    marker string. Relying on the marker means any future rename of
    "bucket_scoring_inputs.by_source", or any hand-built/foreign payload that
    never emits one, silently restores the exact silently-wrong-dict bug the
    previous review round already fixed -- just without the marker present to
    trigger the guard.

    Uses a genuinely BLENDED MULTI-source fixture: single-source payloads are
    always exact now (Fix 3's bucket_corpus equivalence), so only multi-source
    exercises the not-replayable branch this guard protects."""

    @classmethod
    def setUpClass(cls):
        cls._stats, summary = _run_blended_multisource_summary(cls)
        cls._summary = _declaring_the_live_window(summary)

    def test_status_still_refuses_when_the_omission_marker_is_removed(self):
        omitted = self._summary["payload_features"]["omitted"]
        self.assertTrue(
            any(o["feature"] == "bucket_scoring_inputs.by_source" for o in omitted),
            "fixture assumption broken: by_source must be trimmed for this test to be meaningful")
        payload = json.loads(json.dumps(self._summary))
        payload["payload_features"]["omitted"] = []  # marker gone; structural risk unchanged
        result = replay(payload)
        self.assertIsNone(
            result["profiles_by_source"],
            "removing the self-reported marker must NOT make a genuinely "
            "trimmed-and-blended payload look replayable")
        self.assertEqual(result["profiles_by_source_status"],
                          "not_replayable_by_source_bucket_trimmed")


class BucketInputsWithoutMetadataRaises(unittest.TestCase):
    """Test #4: the aggregate.py:674 silent-fallback trap -- replay.py must raise,
    not silently fall back to the full-window AQ, when bucket data is malformed."""

    @classmethod
    def setUpClass(cls):
        cls._stats, cls._summary = _run_summary(
            cls, ["claude"], extra_argv=list(_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE))

    def _payload_with_bucket_corpus(self, metadata):
        payload = json.loads(json.dumps(self._summary))
        payload["bucket_scoring_inputs"] = {
            "metadata": metadata,
            "corpus": {
                "recent_30d": {"window": dict(payload["scoring_inputs_by_source"]["claude"]["window"])},
            },
        }
        return payload

    def test_missing_metadata_raises(self):
        payload = self._payload_with_bucket_corpus([])
        with self.assertRaises(ReplayError):
            replay(payload)

    def test_zero_weight_metadata_raises(self):
        payload = self._payload_with_bucket_corpus(
            [{"id": "recent_30d", "configured_weight": 0, "day_bounds": {"lower": 0, "upper": 30}}])
        with self.assertRaises(ReplayError):
            replay(payload)

    def test_missing_payload_features_raises(self):
        payload = json.loads(json.dumps(self._summary))
        del payload["payload_features"]
        with self.assertRaises(ReplayError):
            replay(payload)

    def test_empty_scoring_inputs_by_source_raises(self):
        payload = json.loads(json.dumps(self._summary))
        payload["scoring_inputs_by_source"] = {}
        with self.assertRaises(ReplayError):
            replay(payload)


class UnknownSourceIdentityRaises(unittest.TestCase):
    """Review remediation round 2, Fix 5: gnomon/config.py::available_caps([])
    and available_caps(["unknown"]) both fail OPEN to the full capability set
    -- a block whose declared source resolves to no id replay() recognizes
    would otherwise score with FULL capabilities and still get labelled
    exact/approximate, as if it were a real, capability-bounded source.
    replay() is explicitly a foreign-payload entry point (see its module
    docstring) and must raise loudly instead of silently over-crediting it."""

    @classmethod
    def setUpClass(cls):
        cls._stats, cls._summary = _run_summary(
            cls, ["claude"], extra_argv=list(_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE))

    def _payload_with_window_source(self, source_key, window_overrides):
        payload = json.loads(json.dumps(self._summary))
        window = payload["scoring_inputs_by_source"].pop("claude")["window"]
        window.pop("source", None)
        window.pop("corpus", None)
        window.update(window_overrides)
        payload["scoring_inputs_by_source"] = {source_key: {"window": window, "monthly": []}}
        return payload

    def test_raises_when_block_has_no_source_and_no_corpus_sources(self):
        payload = self._payload_with_window_source("mystery-tool", {})
        with self.assertRaises(ReplayError):
            replay(payload)

    def test_raises_when_block_source_is_unrecognized(self):
        payload = self._payload_with_window_source("mystery-tool", {"source": "mystery-tool"})
        with self.assertRaises(ReplayError):
            replay(payload)

    def test_succeeds_when_block_source_is_recognized(self):
        payload = self._payload_with_window_source("claude", {"source": "claude"})
        result = replay(payload)
        self.assertIn("aq_0_100", result["aq"])


class SingleActiveSourceAmongZeroSessionKeysIsExact(unittest.TestCase):
    """Review remediation round 2, Fix 5 (lower-severity variant): the single/
    multi split used len(sibs.keys()) rather than source ACTIVITY, so a
    payload carrying one genuinely active source plus zero-session keys took
    the approximate path even though the merged corpus equals that one active
    source exactly (the same equivalence _replay_single_source_aq already
    exploits). replay() must resolve activity, not raw key count."""

    def test_exact_when_only_one_of_several_keys_is_active(self):
        active_block = _minimal_scoring_block("claude", sessions=5, tool_calls=50)
        zero_block = _minimal_scoring_block("codex", sessions=0, tool_calls=0)
        sibs = {
            "claude": {"window": active_block, "monthly": []},
            "codex": {"window": zero_block, "monthly": []},
        }
        payload = {
            "payload_features": {"version": 1, "supported": [], "emitted": [], "omitted": []},
            # Stamped like a real payload (output/summary.py always emits all three):
            # replay() refuses a payload that does not declare which inputs version
            # produced its counters -- see PreDedupPayloadIsRefusedRatherThanRescored --
            # nor the corpus SPAN they were pooled over, which is what the corpus-scale
            # gate reads (WiderWindowPayloadIsNotLaunderedIntoTheLiveContract).
            "scoring_inputs_version": SCORING_INPUTS_VERSION,
            "score_contract_id": SCORE_CONTRACT_ID,
            "context": {"window_months": DEFAULT_SCORING_WINDOW_MONTHS},
            "scoring_inputs_by_source": sibs,
        }
        result = replay(payload)
        self.assertEqual(result["aq_exactness"], AQ_EXACT)
        self.assertEqual(result["aq"], compute_aq(stats_from_scoring_block(active_block)))


def _minimal_scoring_block(source, sessions=1, tool_calls=1):
    """A structurally-complete scoring-input block for a synthetic payload,
    built through the real build_scoring_inputs so every field score_breakdown
    / compute_aq reads directly (not via .get) is genuinely present."""
    from gnomon.scoring.inputs import build_scoring_inputs
    stats = {
        "corpus": {"sources": {source: {}}},
        "volume": {"total_sessions": sessions, "total_prompts": sessions,
                   "tool_calls_total": tool_calls, "thinking_blocks": 0},
        "velocity": {"active_hours": 1.0, "tool_churn_edit_write": 0,
                     "shell_authored_lines_est": 0},
        "behavior": {
            "planning_ratio_explore_to_doing": 0, "actions_per_prompt": 1.0,
            "questions_asked": 0, "error_recovery_ratio": None,
            "error_rate_per_100_tools": None, "api_errors_retries": 0,
            "fanout_median": None, "max_session_fanout": 0,
            "parallel_dispatch_turns": 0, "delegating_sessions": 0,
            "parallel_session_share": None, "shell_test_runs": 0,
            "plan_sessions": 0, "planning_skill_sessions": 0,
            "eligible_change_sessions": 0, "planned_eligible_sessions": 0,
            "evidence_eligible_sessions": 0, "ordered_facts_state": "unmeasured",
            "linked_model_pairs": [], "linked_model_routing_state": "unsupported",
            "delegate_actions": 0, "background_tasks": 0,
            "iteration_depth_mean": None, "iteration_depth_p90": None,
            "iteration_depth_max": None, "files_hammered_over_15x": 0,
            "no_tool_activity": False, "orchestratable_sessions": 0,
            "delegated_orchestratable_sessions": 0,
        },
        "stack": {
            "skills_distinct": 0, "skills_total": 0, "compounding_writes": 0,
            "subagent_types_distinct": 0, "max_session_subagent_types": 0,
            "subagent_types": [], "top_skills": [], "skills_all": [],
            "models": [("some-model", tool_calls)],
        },
        "tools": {
            "agent_calls": 0, "mcp_servers_distinct": 0, "clis_distinct": 0,
            "toolsearch_calls": 0, "task_tool_calls": 0, "cli_calls": 0,
            "mcp_calls": 0, "tool_diversity": 1, "tool_entropy_normalized": 0,
            "mcp_knowledge_calls": 0, "mcp_knowledge_servers": 0,
            "mcp_knowledge_server_names": [], "mcp_grounded_sessions": 0,
            "mcp_write_sessions": 0, "mcp_subcategory_breakdown": {},
            "top_tools": [("Read", tool_calls)],
        },
        "token_usage": {"by_model": []},
    }
    return build_scoring_inputs(stats)


class MultisourceModellessSourceApproximatesInsteadOfRaising(unittest.TestCase):
    """Superseded regression (scope relaxation): an earlier revision raised
    ReplayError for a multi-source corpus containing a model-less source when
    bucket_scoring_inputs.by_source was trimmed, because that per-source
    breakdown was required to reconstruct the merged-corpus AQ EXACTLY. Multi-
    source replay no longer attempts an exact reconstruction at all -- it
    composes a tool-volume-weighted mean of per-source scores
    (score_by_source's own documented aggregation), which already treats a
    missing per-source capability as N/A rather than a defect. There is
    nothing left to raise on: this must succeed for a model-less source, and
    for an all-model-capable source set alike."""

    def _payload(self, sources):
        sibs = {s: {"window": _minimal_scoring_block(s), "monthly": []} for s in sources}
        bucket_window = _minimal_scoring_block(sources[0], sessions=1, tool_calls=1)
        bucket_window["corpus"] = {"sources": {s: {} for s in sources}}
        return {
            "payload_features": {"version": 1, "supported": [], "emitted": [], "omitted": []},
            # See the note in SingleActiveSourceAmongZeroSessionKeysIsExact: a real payload
            # always declares the inputs version its counters came from and the corpus SPAN
            # they were pooled over (output/summary.py stamps both unconditionally), and
            # replay() refuses a payload that states neither -- see
            # PreDedupPayloadIsRefusedRatherThanRescored and
            # WiderWindowPayloadIsNotLaunderedIntoTheLiveContract.
            "scoring_inputs_version": SCORING_INPUTS_VERSION,
            "score_contract_id": SCORE_CONTRACT_ID,
            "context": {"window_months": DEFAULT_SCORING_WINDOW_MONTHS},
            "scoring_inputs_by_source": sibs,
            "bucket_scoring_inputs": {
                "metadata": [{"id": "recent_30d", "configured_weight": 0.65,
                              "day_bounds": {"lower": 0, "upper": 30}}],
                "corpus": {"recent_30d": {"window": bucket_window}},
            },
        }

    def test_does_not_raise_when_a_present_source_lacks_model_cap(self):
        # cursor lacks the "model" capability -- approximate mode simply weighs
        # it in, no raise (unlike the retired exact-reconstruction path).
        payload = self._payload(["claude", "cursor"])
        result = replay(payload)
        self.assertEqual(result["aq_exactness"], AQ_APPROXIMATE_WEIGHTED_MEAN)
        self.assertIn("aq_0_100", result["aq"])

    def test_does_not_raise_when_every_source_has_model_cap(self):
        # claude+codex both have the "model" capability -- unaffected either way.
        payload = self._payload(["claude", "codex"])
        result = replay(payload)
        self.assertEqual(result["aq_exactness"], AQ_APPROXIMATE_WEIGHTED_MEAN)
        self.assertIn("aq_0_100", result["aq"])

    def test_zero_weight_bucket_metadata_raises_instead_of_silently_ignoring(self):
        """Fix 1 (round 2): the new merged-corpus blend in
        _replay_multisource_approximate_aq must raise on malformed bucket
        metadata rather than silently skip it, mirroring the single-source
        path's own BucketInputsWithoutMetadataRaises coverage."""
        payload = self._payload(["claude", "cursor"])
        payload["bucket_scoring_inputs"]["metadata"][0]["configured_weight"] = 0
        with self.assertRaises(ReplayError):
            replay(payload)


class PreDedupPayloadIsRefusedRatherThanRescored(unittest.TestCase):
    """replay() recomputes a persisted payload with the LIVE aq module, which is the
    feature (commit be07bf5: "persist scoring inputs so metric changes can be replayed").
    A formula change SHOULD reach an old payload.

    A COUNTER change must not. v8's skill dedup (28d3bda) made a Skill invocation count
    once per (session, skill) span instead of once per attributed turn, and
    `stats_from_scoring_block` reads the frozen block verbatim -- it never re-derives
    `skills_total` from transcripts. So a payload captured under scoring_inputs_version < 8
    carries counters 4.0x larger pooled (25.8x on Claude), and dividing them by v9's 28x
    smaller targets is severe over-saturation presented as a score.

    The invariant is exactly that narrow: refuse when the payload's OWN
    `scoring_inputs_version` predates the dedup, keep replaying everything from v8 on.
    """

    def _payload(self, inputs_version, tool_calls=900):
        block = _minimal_scoring_block("claude", sessions=12, tool_calls=tool_calls)
        payload = {
            "payload_features": {"version": 1, "supported": [], "emitted": [], "omitted": []},
            # These payloads carry an OLDER inputs version on purpose, so they also carry
            # a foreign contract as far as replay() is concerned. Declaring the window
            # keeps this class about the counter gate alone: `--window=1` predates its
            # becoming the default, so a v8/v9 payload really can be a one-month corpus,
            # and the separate corpus-scale gate
            # (WiderWindowPayloadIsNotLaunderedIntoTheLiveContract) must not swallow the
            # round trip these tests are here to pin.
            "context": {"window_months": DEFAULT_SCORING_WINDOW_MONTHS},
            "scoring_inputs_by_source": {"claude": {"window": block, "monthly": []}},
        }
        if inputs_version is not None:
            payload["scoring_inputs_version"] = inputs_version
        return payload

    def test_pre_dedup_payload_does_not_silently_produce_a_score(self):
        for version in range(1, SKILL_DEDUP_INPUTS_VERSION):
            with self.subTest(scoring_inputs_version=version):
                with self.assertRaises(IncompatibleScoringInputs):
                    replay(self._payload(version))

    def test_the_refusal_is_catchable_as_both_a_replay_and_a_contract_failure(self):
        """A caller enumerating stored payloads catches ReplayError and skips; a
        contract-aware caller catches IncompatibleScoreContract. Neither may get a number."""
        payload = self._payload(SKILL_DEDUP_INPUTS_VERSION - 1)
        with self.assertRaises(ReplayError):
            replay(payload)
        with self.assertRaises(IncompatibleScoreContract):
            replay(payload)

    def test_the_message_names_the_payloads_version_and_the_dedup_boundary(self):
        with self.assertRaises(IncompatibleScoringInputs) as caught:
            replay(self._payload(7))
        message = str(caught.exception)
        self.assertIn("scoring_inputs_version", message)
        self.assertIn("7", message)
        self.assertIn(str(SKILL_DEDUP_INPUTS_VERSION), message)

    def test_a_payload_that_does_not_declare_its_inputs_version_is_refused(self):
        """gnomon stamps the field unconditionally (output/summary.py), so an absent or
        non-integer one is a foreign/hand-built payload whose counter semantics are
        unknown -- the one thing this module's docstring refuses to guess about."""
        for version in (None, "9", 9.5, True):
            with self.subTest(scoring_inputs_version=version):
                with self.assertRaises(IncompatibleScoringInputs):
                    replay(self._payload(version))

    def test_a_payload_from_a_newer_inputs_version_is_refused(self):
        """Symmetric fail-closed: counters defined by an inputs version this code does not
        implement are equally incomparable to the live targets."""
        with self.assertRaises(IncompatibleScoringInputs):
            replay(self._payload(SCORING_INPUTS_VERSION + 1))

    def test_post_dedup_payloads_still_replay_and_still_round_trip(self):
        """The feature stays intact: every version from the dedup onwards replays, and the
        result is the live scorer's own number for that block (bit-for-bit round trip)."""
        for version in range(SKILL_DEDUP_INPUTS_VERSION, SCORING_INPUTS_VERSION + 1):
            with self.subTest(scoring_inputs_version=version):
                payload = self._payload(version)
                block = payload["scoring_inputs_by_source"]["claude"]["window"]
                result = replay(payload)
                self.assertEqual(result["aq_exactness"], AQ_EXACT)
                self.assertEqual(result["aq"], compute_aq(stats_from_scoring_block(block)))


class WiderWindowPayloadIsNotLaunderedIntoTheLiveContract(unittest.TestCase):
    """A payload captured under a WIDER scoring window must not be re-stamped with the
    live contract id.

    The counter guard above (`_require_comparable_scoring_inputs`) only asks what the
    stored numbers MEAN. v10 changed something it cannot see: the SPAN those numbers
    cover. `DEFAULT_SCORING_WINDOW_MONTHS` went 6 -> 1, so the same behaviour now
    produces roughly a sixth of the sessions, tool calls and absolute totals that every
    ceiling and both eligibility floors are judged against -- which is exactly why v10
    registered the window as a calibration constant (gnomon/scoring/calibration.py).

    A v9 payload captured at six months passes the counter gate (9 is in
    [8, 10]), gets re-scored with v10's calibration, and `compute_aq` stamps the CURRENT
    `SCORE_CONTRACT_ID`. Under `COMPARISON_POLICY = same_score_contract_id_only` that
    result is indistinguishable from a genuine one-month row -- a six-month corpus
    laundered into the one-month cohort. Replaying an old FORMULA is the feature;
    promoting an old CORPUS SCALE into the live cohort is not.

    The guard reads the payload's own declaration and infers nothing:
      * a DECLARED `context.window_months` that differs from the live default is refused,
        whatever contract the payload carries;
      * a declaration that is not an integer -- including the null an UNBOUNDED run stamps
        -- is refused for the same reason;
      * an UNDECLARED window (no key at all) is refused too: the payload predates the
        stamp, so its scale is unknown, and unknown scale cannot be certified comparable.
        An earlier revision exempted an undeclared window when the payload carried the
        live `score_contract_id`, on the argument that replay re-stamps nothing there.
        That held only while a locally built payload never declared a window --
        `build_summary` stamps `score_contract_id` unconditionally whatever the span, so a
        locally built SEVEN-month payload took the exemption and was pooled into the
        one-month cohort anyway. The scale is now declared at the source
        (PayloadDeclaresTheCorpusScaleItWasBuiltOver), and the exemption is gone with it.
    """

    def _payload(self, contract, window_months=_UNSET, inputs_version=None):
        block = _minimal_scoring_block("claude", sessions=12, tool_calls=900)
        payload = {
            "payload_features": {"version": 1, "supported": [], "emitted": [], "omitted": []},
            "scoring_inputs_version": (SCORING_INPUTS_VERSION if inputs_version is None
                                       else inputs_version),
            "scoring_inputs_by_source": {"claude": {"window": block, "monthly": []}},
        }
        if contract is not None:
            payload["score_contract_id"] = contract
        if window_months is not _UNSET:
            payload["context"] = {"window_months": window_months}
        return payload

    def test_a_six_month_payload_from_an_older_contract_does_not_produce_a_score(self):
        payload = self._payload("9:9:9", window_months=6, inputs_version=9)
        with self.assertRaises(IncompatibleScoringWindow):
            replay(payload)

    def test_the_refusal_is_catchable_as_both_a_replay_and_a_contract_failure(self):
        """Same argument as the pre-dedup guard: a caller walking a store of payloads
        already catches ReplayError, a contract-aware caller already catches
        IncompatibleScoreContract, and neither may end up holding the laundered number."""
        payload = self._payload("9:9:9", window_months=6, inputs_version=9)
        for expected in (ReplayError, IncompatibleScoreContract, IncompatibleScoringInputs):
            with self.subTest(exception=expected.__name__):
                with self.assertRaises(expected):
                    replay(payload)

    def test_the_message_names_both_windows_and_the_live_default(self):
        with self.assertRaises(IncompatibleScoringWindow) as caught:
            replay(self._payload("9:9:9", window_months=6, inputs_version=9))
        message = str(caught.exception)
        self.assertIn("window_months", message)
        self.assertIn("6", message)
        self.assertIn(str(DEFAULT_SCORING_WINDOW_MONTHS), message)

    def test_an_older_contract_payload_that_carried_a_one_month_window_still_replays(self):
        """`--window=1` existed long before it became the default, so a v9 payload can
        genuinely be a one-month corpus. Refusing that one would delete the feature the
        counter guard was careful to preserve."""
        payload = self._payload("9:9:9", window_months=1, inputs_version=9)
        block = payload["scoring_inputs_by_source"]["claude"]["window"]
        result = replay(payload)
        self.assertEqual(result["aq_exactness"], AQ_EXACT)
        self.assertEqual(result["aq"], compute_aq(stats_from_scoring_block(block)))

    def test_an_undeclared_window_is_refused_whatever_contract_it_carries(self):
        """Absent is not "matches". A payload that never says what span it covers is
        exactly the case that must not be guessed at -- and carrying the LIVE contract id
        does not answer the question, because build_summary stamps that unconditionally
        however wide the corpus was."""
        for contract in ("9:9:9", None, SCORE_CONTRACT_ID):
            with self.subTest(score_contract_id=contract):
                with self.assertRaises(IncompatibleScoringWindow):
                    replay(self._payload(contract, inputs_version=9))

    def test_a_non_integer_window_declaration_is_refused(self):
        """Fail closed on a foreign shape, the same way the inputs-version gate does --
        `True` is an int in Python and would otherwise read as one month."""
        for value in (None, "1", 1.0, True):
            with self.subTest(window_months=value):
                with self.assertRaises(IncompatibleScoringWindow):
                    replay(self._payload("9:9:9", window_months=value, inputs_version=9))

    def test_a_live_contract_payload_round_trips_bit_for_bit(self):
        """The gate must not cost the feature: a payload that carries the live contract id
        AND declares the live one-month corpus scale is comparable on both counts, so the
        result must be exactly the live scorer's own number for that block."""
        payload = self._payload(SCORE_CONTRACT_ID,
                                window_months=DEFAULT_SCORING_WINDOW_MONTHS)
        block = payload["scoring_inputs_by_source"]["claude"]["window"]
        result = replay(payload)
        self.assertEqual(result["aq_exactness"], AQ_EXACT)
        self.assertEqual(result["aq"], compute_aq(stats_from_scoring_block(block)))

    def test_a_live_contract_payload_that_declares_a_wider_window_is_still_refused(self):
        """`--window=6` is still a supported flag, so this code can itself emit a
        six-month corpus stamped 10:10:10. replay() will not hand that number back as if
        it were comparable to the one-month cohort its calibration assumes."""
        with self.assertRaises(IncompatibleScoringWindow):
            replay(self._payload(SCORE_CONTRACT_ID, window_months=6))

    def test_a_real_summary_payload_declares_the_live_window_and_replays(self):
        """The common case, end to end: a summary built over one calendar month declares
        that month and replays. `context.window_months` is stamped by
        `gnomon/output/summary.py::build_summary` from the bounds the run actually
        covered, so a locally built payload states its own scale -- see
        PayloadDeclaresTheCorpusScaleItWasBuiltOver for the full argument."""
        _stats, summary = _run_summary(
            self, ["claude"], extra_argv=list(_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE))
        self.assertEqual(summary["score_contract_id"], SCORE_CONTRACT_ID)
        self.assertEqual(summary["context"]["window_months"],
                         DEFAULT_SCORING_WINDOW_MONTHS)
        self.assertIn("aq_0_100", replay(summary)["aq"])


class PayloadDeclaresTheCorpusScaleItWasBuiltOver(unittest.TestCase):
    """A payload STATES the corpus span it was pooled over; the gate never guesses it.

    The corpus-scale gate above used to exempt a payload that declared no window but
    carried the live `score_contract_id`, on the argument that only the upload path
    stamps `context.window_months`, so a locally built summary.json never declares one
    and always carries the live contract. The first half was true and the conclusion was
    still wrong: `build_summary` stamps `score_contract_id` unconditionally regardless of
    the span the run covered, and `gnomon/sources/discovery.py::parse_window` accepts an
    unbounded `--since`/`--until` (or `--last=Nm` for any N). A locally built payload
    spanning seven months therefore carried the live contract, declared no window, hit the
    exemption, and was pooled into the one-month cohort -- the same laundering the gate
    exists to stop, arriving through a second door.

    The root cause was that a payload did not state its own scale, so the gate had to
    infer one. `build_summary` now derives `context.window_months` from the bounds the run
    genuinely had, which makes the declaration a fact about the corpus rather than an echo
    of a flag someone may not have passed:

      * a run bounded to a whole number of calendar months declares that number -- the
        shape every uploaded payload has, since `_anchor_window` only ever requests
        calendar-aligned bounds;
      * a run that cannot state a whole number of calendar months declares None. That
        covers the UNBOUNDED local run (no `--since`, no `--until`: its span is whatever
        survived transcript retention, decided by disk contents rather than by the run),
        the half-bounded run, and `--last=Nd`-style rolling windows that do not land on
        calendar boundaries. None is a DECLARATION of unknown scale, not an absence: the
        key is present and the gate refuses it, which is the fail-closed answer this
        module's docstring already argues for everywhere else.

    Deriving the number from the observed EVENTS instead was rejected: it would make
    replayability depend on where a corpus happens to fall relative to a month boundary
    (two sessions on Jun 30 and Jul 1 would read as a two-month corpus, the same two
    sessions a week later as a one-month one), and it would give the field two different
    meanings depending on how the run was invoked.
    """

    def test_a_calendar_month_run_declares_one_month(self):
        _stats, summary = _run_summary(
            self, ["claude"], extra_argv=list(_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE))
        self.assertEqual(summary["context"]["window_months"], 1)

    def test_a_calendar_month_payload_replays_exactly(self):
        """The scale declaration must not cost the feature: a genuine one-month payload
        still round-trips to the number the payload itself published."""
        _stats, summary = _run_summary(
            self, ["claude"], extra_argv=list(_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE))
        result = replay(summary)
        self.assertEqual(result["aq_exactness"], AQ_EXACT)
        self.assertEqual(result["aq"], summary["profile"]["aq"])

    def test_a_multi_month_run_declares_the_span_it_actually_covered(self):
        _stats, summary = _run_summary(
            self, ["claude"], extra_argv=list(_SIX_MONTHS_OVER_THE_CLAUDE_FIXTURE))
        self.assertEqual(summary["context"]["window_months"], 6)

    def test_a_locally_built_multi_month_payload_is_refused(self):
        """The hole this closes, exactly: no flag was passed, nothing on the upload path
        ran, and the payload still carries the LIVE contract id -- which is what the old
        undeclared-window exemption keyed on. It is a six-month corpus and it must not
        pool with the one-month cohort."""
        _stats, summary = _run_summary(
            self, ["claude"], extra_argv=list(_SIX_MONTHS_OVER_THE_CLAUDE_FIXTURE))
        self.assertEqual(summary["score_contract_id"], SCORE_CONTRACT_ID)
        with self.assertRaises(IncompatibleScoringWindow):
            replay(summary)

    def test_an_unbounded_run_declares_an_unknown_span_rather_than_none_at_all(self):
        """A plain `--local` run reads every transcript on disk. It cannot state a span in
        months, so it says so explicitly -- the key is PRESENT and null, which is what
        keeps "unknown" distinguishable from "predates this stamp"."""
        _stats, summary = _run_summary(self, ["claude"])
        self.assertIn("window_months", summary["context"])
        self.assertIsNone(summary["context"]["window_months"])

    def test_an_unbounded_payload_is_refused_rather_than_read_as_one_month(self):
        _stats, summary = _run_summary(self, ["claude"])
        self.assertEqual(summary["score_contract_id"], SCORE_CONTRACT_ID)
        with self.assertRaises(IncompatibleScoringWindow):
            replay(summary)

    def test_a_half_bounded_run_cannot_state_a_span(self):
        """`--since` with no `--until` is open-ended on the right: the corpus runs to
        whatever the last transcript happens to be, so there is no span to declare."""
        _stats, summary = _run_summary(self, ["claude"], extra_argv=["--since=2026-06-01"])
        self.assertIsNone(summary["context"]["window_months"])


class RecomputeGradeFieldsExcludedFromStatsAndNarrative(unittest.TestCase):
    """Fix 6 (persist-recompute-grade-inputs review remediation): the design
    promised "stats.json byte-identical -- new stats fields are underscore-
    prefixed and added to the local.py stats_for_disk filter." No such
    prefix/filter existed for bucket_scoring_inputs / payload_features, so both
    leaked into BOTH stats.json AND narrative_input.md (the archetype/traits
    LLM prompt input) -- inflating a prompt that never needed the replay
    blocks in the first place. summary.json is the only place these keys
    belong. (scoring_inputs_corpus, the third field this fix originally
    covered, no longer exists at all -- see module docstring.)"""

    @classmethod
    def setUpClass(cls):
        cls._out = tempfile.mkdtemp(prefix="paxel-fix6-")
        testcase = cls
        testcase.addClassCleanup(shutil.rmtree, cls._out, ignore_errors=True)
        argv = ["paxel.py", "claude", "codex", "gemini", "--summary", "--no-open"]
        buf = io.StringIO()
        with (
            mock.patch.multiple(paxel, OUT_DIR=cls._out, **SRC_DIRS),
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(buf),
        ):
            paxel.main()
        with open(os.path.join(cls._out, "stats.json"), encoding="utf-8") as fh:
            cls._stats = json.load(fh)
        with open(os.path.join(cls._out, "summary.json"), encoding="utf-8") as fh:
            cls._summary = json.load(fh)
        with open(os.path.join(cls._out, "narrative_input.md"), encoding="utf-8") as fh:
            cls._narrative = fh.read()

    def test_fixture_actually_emits_the_new_blocks(self):
        """Guard: this fixture must be multi-source + recency-blend-capable so
        both keys are genuinely present in summary.json -- otherwise the
        "excluded from stats.json/narrative" assertions below would be vacuous."""
        for key in ("bucket_scoring_inputs", "payload_features"):
            self.assertIn(key, self._summary, f"fixture never emitted {key!r} in summary.json")
        self.assertNotIn("scoring_inputs_corpus", self._summary,
                          "scoring_inputs_corpus should never ship for any source count")

    def test_new_payload_keys_absent_from_stats_json(self):
        for key in ("bucket_scoring_inputs", "payload_features"):
            self.assertNotIn(key, self._stats,
                              f"{key!r} leaked into stats.json -- it belongs only in summary.json")

    def test_new_payload_blocks_absent_from_narrative_prompt(self):
        # Match the exact JSON key form (quoted, followed by a colon) -- a bare
        # substring match would also (falsely) hit the pre-existing, unrelated
        # internal key "_aq_bucket_scoring_inputs_by_source", which legitimately
        # belongs in the narrative and predates this change.
        for key in ("bucket_scoring_inputs", "payload_features"):
            needle = f'"{key}":'
            self.assertNotIn(needle, self._narrative,
                              f"{key!r} leaked into narrative_input.md (the archetype/traits "
                              f"LLM prompt) -- these replay blocks are needed in summary.json "
                              f"only, not in the narrative prompt")


class PayloadFeaturesOmittedCoversRecencyBlendDisabled(unittest.TestCase):
    """Review remediation, Fix 7 minor: docs/metrics-by-source.md documents
    `payload_features.omitted[].reason` as explaining why any of the
    recompute-grade blocks is absent from a given payload -- but when the
    recency blend is disabled (RECENCY_BLEND_ENABLED False),
    `bucket_scoring_inputs` is absent from the payload while `omitted` stays
    empty; only the separate `recency_blend.enabled` marker reveals it. Fix
    1(b)'s explicit blend signal depends on that absence being legible from
    `omitted` alone, so a recompute job branching on it can tell "blend
    disabled for this payload" apart from "budget-trimmed" without also
    having to know to check a second, unrelated field."""

    @classmethod
    def setUpClass(cls):
        with mock.patch("gnomon.cli.local.RECENCY_BLEND_ENABLED", False):
            cls._stats, cls._summary = _run_summary(
            cls, ["claude"], extra_argv=list(_ONE_MONTH_OVER_THE_CLAUDE_FIXTURE))

    def test_bucket_scoring_inputs_absent_when_blend_disabled(self):
        self.assertNotIn("bucket_scoring_inputs", self._summary)

    def test_omitted_names_the_recency_blend_disabled_reason(self):
        omitted = self._summary["payload_features"]["omitted"]
        self.assertTrue(
            any(o["feature"] == "bucket_scoring_inputs" and o["reason"] == "recency_blend_disabled"
                for o in omitted),
            f"expected an omitted entry naming recency_blend_disabled, got {omitted!r}")


class SummaryFallbackPayloadFeaturesOmitsRecencyBlendMarker(unittest.TestCase):
    """Review remediation, Fix 7 minor: gnomon/output/summary.py::build_summary's
    fallback `payload_features` (used whenever `stats` never went through
    local.py's main() -- e.g. any test or caller that builds a stats dict by
    hand and calls build_summary() directly) positively asserted
    'recency_blend': {'enabled': False, 'history_weight': 0}. build_summary()
    cannot actually know that -- it never computed a blend decision for this
    stats dict at all -- so that was a confident but unfounded claim, not a
    fact. The field must be omitted (unknown), not answered with a guess."""

    def test_fallback_payload_features_omits_recency_blend_marker(self):
        from tests.test_gnomon import _zero_stats
        summary = paxel.build_summary(_zero_stats())
        payload_features = summary["payload_features"]
        # Confirms this exercised the FALLBACK branch, not local.py's real
        # _payload_features computation -- otherwise the assertion below
        # would be vacuous.
        self.assertEqual(payload_features["emitted"], [])
        self.assertNotIn(
            "recency_blend", payload_features,
            "build_summary() cannot know whether a recency blend was "
            "computed for a stats dict it never built _payload_features "
            "for -- it must not assert a confident enabled/disabled marker")


if __name__ == "__main__":
    unittest.main()
