"""Bloque 2.A — a published month is scored on THAT month.

Until this change every published monthly point was a trailing SIX-month window, so a
month's score was dominated by the five months before it: a real behavioural change
showed up as a slow drift, and a step change (June -> July) read as a jump. The scoring
window is now ONE calendar month.

Three things that are NOT obvious and are what these tests pin:

1. **The monthly evidence series must stay multi-month.** mirdash self-heals its
   per-calendar-month series from `noticed_stats_monthly`
   (`buildMetricMonthlyStats`, deduped per monthKey keeping the greatest
   `anchorMonthKey`). A one-month scoring window collapses that block to a single
   entry, which silently ends the self-heal. A SECOND, corpus-only accumulator with a
   TRAILING MULTI-MONTH window keeps it alive. If `_self_heal_monthly_noticed_stats`
   carries one entry, the second accumulator was not built and every other assertion
   here passes in false.

2. **Scoring on fewer terms must be disclosed.** `wsum` drops an unmeasurable term and
   renormalizes the rest, with no axis-level N/A. At six months that almost never
   fired; at one month it fires constantly (measured on the real population: the
   `compounding_writes` rate evidence floor drops 18/75 month slices, `review_skills`
   14/75, against 0/16 six-month corpora -- and separately 38% of month slices fall
   below `MIN_ELIGIBLE_SESSIONS`). An axis whose whole weight has collapsed onto one
   surviving term must say so.

3. **The window is a calibration input.** It decides the corpus every absolute count
   ceiling and every eligibility floor is judged against, so it belongs under the
   calibration fingerprint like the ceilings do.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paxel  # noqa: E402
from gnomon.cli import local  # noqa: E402
from gnomon.cli.accumulator import Accumulator  # noqa: E402
from gnomon.scoring import aq as aq_mod  # noqa: E402
from gnomon.scoring.aq import DEFAULT_SCORING_WINDOW_MONTHS, compute_aq  # noqa: E402
from gnomon.scoring.calibration import (  # noqa: E402
    CALIBRATION_CONSTANT_NAMES, CALIBRATION_FINGERPRINTS, calibration_fingerprint,
)
from gnomon.scoring.versioning import (  # noqa: E402
    SCORE_CONTRACT_ID, SCORING_INPUTS_VERSION, SKILL_DEDUP_INPUTS_VERSION,
)
from gnomon.upload.mirdash import _DEFAULT_WINDOW_MONTHS, _upload_window


def _turn(sid, ts, cwd="/repo"):
    return {"type": "user", "sessionId": sid, "timestamp": ts, "cwd": cwd,
            "message": {"role": "user", "content": "do the thing"}}


_NO_CHURN = {"repos_seen": 0, "repos_with_commits": 0, "insertions": 0,
             "deletions": 0, "churn": 0, "commits": 0, "per_repo": []}


class TestTheScoringWindowIsOneCalendarMonth(unittest.TestCase):
    def test_default_window_is_one_month(self):
        self.assertEqual(_DEFAULT_WINDOW_MONTHS, 1)

    def test_the_window_is_owned_by_the_scoring_module_it_calibrates(self):
        # The window decides the corpus the five absolute ceilings and the two
        # eligibility floors are judged against, so it is a scoring parameter, not an
        # upload detail. mirdash.py re-exports it for its existing importers.
        self.assertEqual(aq_mod.DEFAULT_SCORING_WINDOW_MONTHS, _DEFAULT_WINDOW_MONTHS)

    def test_the_window_is_under_the_calibration_fingerprint(self):
        # Documented rule of gnomon/scoring/calibration.py: anything that moves a
        # published score without moving the contract is a silent cohort merge. The
        # window was score-affecting and unfingerprinted -- that hole closes here.
        self.assertIn("DEFAULT_SCORING_WINDOW_MONTHS", CALIBRATION_CONSTANT_NAMES)

    def test_upload_stamps_the_scoring_window_not_the_self_heal_window(self):
        """`context.window_months` has real consumers (the ingest route, the Convex
        schema, and the evolution chart, which branches on `> 1` vs `== 1` to label a
        point "Trailing N months" vs "1 month"). It must describe the window the SCORE
        was computed over -- 1 -- never the wider window the monthly evidence block was
        read back over, which scores nothing."""
        summary = {"context": {"total_sessions": 3, "date_range": ["2026-07-01", "2026-07-31"]}}
        with mock.patch("gnomon.upload.mirdash._run_paxel", return_value=summary), \
                mock.patch("gnomon.upload.mirdash._upload_summary", return_value="url"):
            _upload_window("https://base", "tok", "paxel.py", [],
                           "2026-07-01", "2026-08-01", "2026-07",
                           verbose=False, quiet=True)
        self.assertEqual(summary["context"]["window_months"], 1)


class TestSelfHealWindow(unittest.TestCase):
    def test_the_self_heal_window_is_wider_than_the_scoring_window(self):
        self.assertGreater(local.MONTHLY_SELF_HEAL_MONTHS, _DEFAULT_WINDOW_MONTHS)

    def test_self_heal_since_rolls_back_whole_calendar_months(self):
        since = datetime(2026, 7, 1, tzinfo=timezone.utc)
        got = local._self_heal_since(since, months=6)
        self.assertEqual(got, datetime(2026, 2, 1, tzinfo=timezone.utc))

    def test_self_heal_since_crosses_the_year_boundary(self):
        since = datetime(2026, 2, 1, tzinfo=timezone.utc)
        self.assertEqual(local._self_heal_since(since, months=6),
                         datetime(2025, 9, 1, tzinfo=timezone.utc))

    def test_a_mid_month_since_still_lands_on_a_month_start(self):
        since = datetime(2026, 7, 15, 13, 45, tzinfo=timezone.utc)
        self.assertEqual(local._self_heal_since(since, months=3),
                         datetime(2026, 5, 1, tzinfo=timezone.utc))

    def test_no_scoring_since_needs_no_second_accumulator(self):
        # An open-ended run already reads everything; a wider window would be identical
        # work for an identical answer.
        self.assertIsNone(local._self_heal_since(None, months=6))

    def test_a_one_month_self_heal_window_needs_no_second_accumulator(self):
        since = datetime(2026, 7, 1, tzinfo=timezone.utc)
        self.assertIsNone(local._self_heal_since(since, months=1))

    def test_the_reach_is_read_from_the_module_constant_at_call_time(self):
        """Binding MONTHLY_SELF_HEAL_MONTHS as a default argument would freeze it into the
        signature at import, so overriding the constant -- the obvious way to tune or test
        the reach -- would silently keep the old value. Caught by an actual measurement
        that did not change when the constant was patched."""
        since = datetime(2026, 7, 1, tzinfo=timezone.utc)
        with mock.patch.object(local, "MONTHLY_SELF_HEAL_MONTHS", 3):
            self.assertEqual(local._self_heal_since(since),
                             datetime(2026, 5, 1, tzinfo=timezone.utc))
        with mock.patch.object(local, "MONTHLY_SELF_HEAL_MONTHS", 1):
            self.assertIsNone(local._self_heal_since(since))


class TestSelfHealAccumulatorKeepsTheMonthlySeriesAlive(unittest.TestCase):
    """The load-bearing test. `noticed_stats_monthly` MUST carry more than one month
    entry under a one-month scoring window."""

    def _run(self, since, until):
        anchor = datetime(2026, 7, 20, tzinfo=timezone.utc)
        events = [_turn(f"s-{n}", (anchor - timedelta(days=n * 30)).isoformat())
                  for n in range(5)]
        with tempfile.NamedTemporaryFile() as transcript, \
                mock.patch.object(local, "iter_events", return_value=events), \
                mock.patch("gnomon.cli.accumulator.git_churn", return_value=_NO_CHURN), \
                mock.patch("gnomon.output.summary.git_churn", return_value=_NO_CHURN):
            os.utime(transcript.name, (anchor.timestamp(), anchor.timestamp()))
            return local._accumulate(
                [("claude", transcript.name, "claude")],
                since_dt=since, until_dt=until, cursor_twins=set(),
                antigravity=None, verbose=False)

    def test_scoring_corpus_sees_only_the_anchor_month(self):
        stats, _ = self._run(datetime(2026, 7, 1, tzinfo=timezone.utc),
                             datetime(2026, 8, 1, tzinfo=timezone.utc))
        months = [entry["month"] for entry in stats["monthly_noticed_stats"]]
        self.assertEqual(months, ["2026-07"])

    def test_self_heal_series_carries_more_than_one_month(self):
        _stats, narrative = self._run(datetime(2026, 7, 1, tzinfo=timezone.utc),
                                      datetime(2026, 8, 1, tzinfo=timezone.utc))
        series = narrative["_self_heal_monthly_noticed_stats"]
        self.assertIsNotNone(
            series,
            "the second, corpus-only accumulator was never built -- with a one-month "
            "scoring window the monthly evidence block collapses to one entry and "
            "mirdash's per-month self-heal silently stops")
        months = [entry["month"] for entry in series]
        self.assertGreater(
            len(months), 1,
            f"self-heal series carries {months} -- one entry means the second "
            f"accumulator ran on the scoring window, not on the trailing one")
        self.assertEqual(months, sorted(months))
        self.assertIn("2026-07", months)
        self.assertIn("2026-03", months)

    def test_no_second_accumulator_on_an_open_ended_run(self):
        _stats, narrative = self._run(None, None)
        self.assertIsNone(narrative["_self_heal_monthly_noticed_stats"])

    def test_self_heal_entries_are_shaped_by_the_same_builder(self):
        _stats, narrative = self._run(datetime(2026, 7, 1, tzinfo=timezone.utc),
                                      datetime(2026, 8, 1, tzinfo=timezone.utc))
        entry = narrative["_self_heal_monthly_noticed_stats"][0]
        self.assertEqual(set(entry), {"month", "range_start", "range_end",
                                      "stats", "token_usage"})
        self.assertIn("volume", entry["stats"])
        self.assertIn("shipping", entry["stats"])


class TestSelfHealShapingSkipsTheScoringPipeline(unittest.TestCase):
    def test_shaping_the_monthly_block_does_not_score_the_corpus(self):
        """Going through `to_corpus_stats` would run a duplicate windowed `git_churn`,
        a second `compute_aq` and a `to_monthly` -- all discarded. Only the monthly
        shaper is wanted."""
        accumulator = Accumulator()
        accumulator.begin_file("claude", "/tmp/x.jsonl")
        accumulator.observe(_turn("s1", "2026-06-10T10:00:00Z"), None, None)
        accumulator.observe(_turn("s2", "2026-07-10T10:00:00Z"), None, None)
        accumulator.end_file()
        with mock.patch("gnomon.cli.accumulator.compute_aq") as scored, \
                mock.patch("gnomon.output.summary.git_churn", return_value=_NO_CHURN):
            series = accumulator.to_monthly_noticed_stats()
        scored.assert_not_called()
        self.assertEqual([entry["month"] for entry in series], ["2026-06", "2026-07"])

    def test_corpus_shaping_and_standalone_shaping_agree(self):
        """One shaper, no drift: `to_corpus_stats` must publish exactly what the
        standalone method builds from the same accumulator."""
        accumulator = Accumulator()
        accumulator.begin_file("claude", "/tmp/x.jsonl")
        accumulator.observe(_turn("s1", "2026-06-10T10:00:00Z"), None, None)
        accumulator.end_file()
        with mock.patch("gnomon.cli.accumulator.git_churn", return_value=_NO_CHURN), \
                mock.patch("gnomon.output.summary.git_churn", return_value=_NO_CHURN):
            stats = accumulator.to_corpus_stats(None, None, None)
            standalone = accumulator.to_monthly_noticed_stats()
        self.assertEqual(stats["monthly_noticed_stats"], standalone)


class TestSummaryPublishesTheSelfHealSeries(unittest.TestCase):
    def test_summary_noticed_stats_monthly_spans_more_than_the_scored_month(self):
        tmp = tempfile.mkdtemp(prefix="gnomon-2a-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        empty = tempfile.mkdtemp(prefix="gnomon-2a-empty-")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        claude_dir = os.path.join(tmp, "claude", "proj")
        os.makedirs(claude_dir)
        with open(os.path.join(claude_dir, "s.jsonl"), "w", encoding="utf-8") as fh:
            for month in ("04", "05", "06", "07"):
                fh.write(json.dumps(_turn(f"s{month}", f"2026-{month}-10T12:00:00Z")) + "\n")
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
        argv = ["paxel.py", "--summary", "--no-open",
                "--since=2026-07-01", "--until=2026-07-31"]
        with mock.patch.multiple(paxel, OUT_DIR=out, **src_dirs), \
                mock.patch("gnomon.coverage.HISTORY_PATH",
                           os.path.join(tmp, "no-history.jsonl")), \
                mock.patch("gnomon.cli.accumulator.git_churn", return_value=_NO_CHURN), \
                mock.patch("gnomon.output.summary.git_churn", return_value=_NO_CHURN), \
                mock.patch.object(sys, "argv", argv), \
                redirect_stdout(io.StringIO()):
            paxel.main()
        with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)

        months = [entry["month"] for entry in summary["noticed_stats_monthly"]]
        self.assertGreater(
            len(months), 1,
            "noticed_stats_monthly carries a single entry -- mirdash's per-month "
            f"self-heal is dead. Got {months}")
        self.assertEqual(months, sorted(set(months)))
        self.assertIn("2026-07", months)
        self.assertIn("2026-04", months)
        # The SCORE is still one month: only July's sessions reach the corpus.
        self.assertEqual(summary["context"]["total_sessions"], 1)


class TestPartialScoringIsDisclosed(unittest.TestCase):
    """`wsum` drops an unmeasurable term and renormalizes the survivors. At one month
    that happens constantly, and today the axis publishes a score that is
    indistinguishable from a fully-measured one."""

    def _axis(self, stats, pillar_name, axis_name):
        profile = compute_aq(stats)
        pillar = next(p for p in profile["pillars"] if p["name"] == pillar_name)
        return next(a for a in pillar["axes"] if a["name"] == axis_name)

    def _stats(self, tool_calls, **behavior):
        base_behavior = {
            "planning_ratio_explore_to_doing": 0.5, "actions_per_prompt": 8,
            "shell_test_runs": 20, "ordered_facts_state": "measured",
            "eligible_change_sessions": 40, "planned_eligible_sessions": 20,
            "evidence_eligible_sessions": 18, "orchestratable_sessions": 10,
            "delegated_orchestratable_sessions": 8,
            "planning_skill_sessions": 30, "planning_skill_eligible_sessions": 100,
            "planning_skill_unmeasured_sessions": 0,
            "linked_model_pairs": [], "linked_model_routing_state": "unmeasured",
        }
        base_behavior.update(behavior)
        return {
            "corpus": {"sources": {"claude": {}}},
            "volume": {"total_sessions": 120, "tool_calls_total": tool_calls},
            "behavior": base_behavior,
            "tools": {"toolsearch_calls": 30, "task_tool_calls": 40, "clis_distinct": 10,
                      "mcp_servers_distinct": 5, "cli_calls": 100, "mcp_calls": 30},
            "stack": {"skills_total": 60, "skills_distinct": 12, "compounding_writes": 5,
                      "subagent_types_distinct": 4, "max_session_subagent_types": 3,
                      "models": [], "top_skills": [], "skills_all": []},
        }

    def test_a_fully_scored_axis_says_nothing(self):
        axis = self._axis(self._stats(20_000), "Craft", "Verification")
        self.assertNotIn("partial_terms", axis)

    def test_a_rate_term_below_the_evidence_floor_is_disclosed(self):
        # 300 tool calls: review_skills needs > 250 (scored), compounding needs > 555.6
        # (dropped). Compounding then rests entirely on its binary has_skill flag.
        axis = self._axis(self._stats(300), "Craft", "Compounding")
        self.assertIn(
            "partial_terms", axis,
            "the Compounding rate term dropped below RATE_MIN_EXPECTED_AT_TARGET and "
            "100% of the axis weight silently moved onto the presence flag")
        self.assertEqual(axis["partial_terms"]["scored"], 1)
        self.assertEqual(axis["partial_terms"]["total"], 2)
        self.assertAlmostEqual(axis["partial_terms"]["weight_scored"], 0.4)

    def test_an_eligibility_floor_drop_is_disclosed(self):
        # eligible_change_sessions < MIN_ELIGIBLE_SESSIONS drops ordered_planning -- the
        # measured 1-month failure mode. v18 dropped Discipline's third term (the task-tool
        # rate), so only two terms remain: planning_habit (.40) survives on the default
        # 30/100 share (above its own floor), and Discipline renormalizes onto it alone.
        axis = self._axis(
            self._stats(20_000, eligible_change_sessions=3, planned_eligible_sessions=1,
                        evidence_eligible_sessions=1,
                        # Fully qualify the planning-skill scope (all 6 fields) so
                        # planning_habit is genuinely MEASURED rather than dropped for
                        # incomplete evidence -- the base fixture only sets 3 of the 6
                        # `_PLANNING_SKILL_NEW_FIELDS`, which `_planning_skill_evidence`
                        # treats as unmeasured.
                        planning_skill_sessions=30, planning_skill_eligible_sessions=100,
                        planning_skill_unmeasured_sessions=0,
                        planning_skill_session_scope_state="measured",
                        planning_skill_session_share=0.3,
                        planning_skill_session_coverage=1.0),
            "Breadth", "Discipline")
        self.assertIn("partial_terms", axis)
        self.assertEqual(axis["partial_terms"]["scored"], 1)
        self.assertEqual(axis["partial_terms"]["total"], 2)
        self.assertAlmostEqual(axis["partial_terms"]["weight_scored"], round(0.4 / 0.6, 4))

    def test_disclosure_never_moves_the_score(self):
        stats = self._stats(300)
        axis = self._axis(stats, "Craft", "Compounding")
        self.assertIn("partial_terms", axis)
        # Same axis, disclosure stripped: the number is untouched by the disclosure.
        self.assertEqual(axis["score"], round(axis["weight"] * axis["normalized_score"], 1))

    def test_every_wsum_axis_can_actually_disclose(self):
        """`wsum` attaches its disclosure by AXIS NAME, so a name that does not match the
        axis tuple would leave that axis permanently silent and nothing else would fail.
        Force every term that can drop to drop -- 1 tool call is under all six rate
        evidence floors, zero eligible sessions is under both session floors, and cursor
        cannot record toolsearch/tasktool/skills -- then assert each wsum-scored axis that
        still survives says so."""
        stats = self._stats(1, eligible_change_sessions=0, planned_eligible_sessions=0,
                            evidence_eligible_sessions=0,
                            planning_skill_eligible_sessions=0, planning_skill_sessions=0)
        profile = compute_aq(stats)
        disclosed = {axis["name"] for pillar in profile["pillars"]
                     for axis in pillar["axes"] if "partial_terms" in axis}
        dropped = {name for pillar in profile["pillars"]
                   for name in pillar.get("not_applicable", [])}
        # Tool command and Token economy are intentionally absent: v17 dropped the only
        # rate/cap term either axis carried (toolsearch), so both are now pure absolute-count
        # wsum axes that can never lose a term and thus never disclose or drop.
        wsum_axes = {"Skill fluency", "Discipline",
                     "Verification", "Compounding", "Orchestration"}
        for name in wsum_axes:
            with self.subTest(axis=name):
                self.assertTrue(
                    name in disclosed or name in dropped,
                    f"{name} is wsum-scored and lost terms, but published neither a "
                    f"partial_terms disclosure nor an axis-level N/A -- most likely the "
                    f"`axis=` label passed to wsum does not match the axis tuple's name")

    def test_disclosure_is_not_a_numeric_signal(self):
        """mirdash reads `signals` as Record<string, number> and shows the LOWEST value
        as the axis bottleneck (`pickDrivingSignal`). A fractional weight share inside
        `signals` would be read as a phantom bottleneck on almost every axis, so the
        disclosure is an axis sibling -- a key mirdash's `parseAxis` whitelist ignores."""
        axis = self._axis(self._stats(300), "Craft", "Compounding")
        self.assertNotIn("partial_terms", axis["signals"])
        for value in axis["signals"].values():
            self.assertNotIsInstance(value, dict)


class TestDisclosureSurvivesTheRecencyBlend(unittest.TestCase):
    """`_blend_aq` copies each axis dict from the highest-weight component (recent_30d at
    0.65), so a `partial_terms` recorded on the 0.35 full-window component would vanish.

    That was not hypothetical. Measured on this machine's real corpus, a thin scoring
    window makes the full-window component drop the Compounding rate term (its normalized
    score lands exactly on the 0.6 presence flag) while recent_30d -- a wider span, more
    tool calls -- keeps it. The blended axis then published a score that was 35% built
    from a one-term axis, with nothing saying so.

    v11 removed the blend from the scoring path, so this no longer describes a PUBLISHED
    score -- it describes `replay()` recomputing a payload captured under v8-v10, which
    still carries a blend block and must still disclose partial scoring when it does."""

    def _blended(self, recent_partial, full_partial):
        def axis_aq(normalized, partial):
            axis = {"name": "Compounding", "base_weight": 20, "weight": 100,
                    "normalized_score": normalized, "score": round(100 * normalized, 1),
                    "signals": {"tool_calls": 1}}
            if partial is not None:
                axis["partial_terms"] = partial
            return {"aq_0_100": 50, "score_contract_id": SCORE_CONTRACT_ID,
                    "pillars": [{"name": "Craft", "weight": 35, "score": axis["score"],
                                 "axes": [axis]}]}

        recent = axis_aq(0.48, recent_partial)
        full = axis_aq(0.60, full_partial)
        from gnomon.scoring import aggregate
        blended = aggregate._blend_aq(full, [
            {"id": "recent_30d", "configured_weight": 0.65, "aq": recent},
            {"id": "full_window", "configured_weight": 0.35, "aq": full},
        ])
        return blended["pillars"][0]["axes"][0]

    def test_a_partial_component_is_disclosed_even_when_the_primary_is_complete(self):
        axis = self._blended(recent_partial=None,
                             full_partial={"scored": 1, "total": 2, "weight_scored": 0.4})
        self.assertIn(
            "partial_terms", axis,
            "the 0.35 full-window component scored this axis on one of two terms and the "
            "blend published it as fully measured")
        # weight_scored blends with the same effective weights the score does:
        # 0.65*1.0 + 0.35*0.4 = 0.79.
        self.assertAlmostEqual(axis["partial_terms"]["weight_scored"], 0.79)
        # `scored` is a count, so it reports the WORST component rather than an average.
        self.assertEqual(axis["partial_terms"]["scored"], 1)
        self.assertEqual(axis["partial_terms"]["total"], 2)

    def test_each_component_carries_its_own_disclosure(self):
        axis = self._blended(recent_partial=None,
                             full_partial={"scored": 1, "total": 2, "weight_scored": 0.4})
        by_id = {c["id"]: c for c in axis["components"]}
        self.assertIsNone(by_id["recent_30d"]["partial_terms"])
        self.assertEqual(by_id["full_window"]["partial_terms"],
                         {"scored": 1, "total": 2, "weight_scored": 0.4})

    def test_a_fully_measured_blend_stays_silent(self):
        axis = self._blended(recent_partial=None, full_partial=None)
        self.assertNotIn("partial_terms", axis)
        self.assertTrue(all(c["partial_terms"] is None for c in axis["components"]))

    def test_disclosure_survives_when_only_the_primary_is_partial(self):
        axis = self._blended(recent_partial={"scored": 1, "total": 2, "weight_scored": 0.4},
                             full_partial=None)
        self.assertAlmostEqual(axis["partial_terms"]["weight_scored"], 0.61)
        self.assertEqual(axis["partial_terms"]["scored"], 1)


class TestScoreContractMovesWithTheWindow(unittest.TestCase):
    def test_the_window_change_kept_its_own_contract_entry(self):
        """v10 pinned `SCORE_CONTRACT_ID == "10:10:10"` because the window change WAS the
        current contract. Later bumps are legitimate, so what this file still owns is the
        audit trail: the entry v10 published must stay in the registry, byte for byte,
        whatever the live contract has become. Re-pointing the pin at the registry rather
        than deleting it keeps the guarantee that made it worth writing -- an in-place
        edit of a published fingerprint stays impossible."""
        self.assertIn("10:10:10", CALIBRATION_FINGERPRINTS)
        self.assertEqual(CALIBRATION_FINGERPRINTS["10:10:10"], "7a2c444ff5c26f06")
        self.assertGreaterEqual(SCORING_INPUTS_VERSION, 10)

    def test_new_contract_has_its_own_fingerprint_entry(self):
        self.assertIn(SCORE_CONTRACT_ID, CALIBRATION_FINGERPRINTS)
        self.assertEqual(calibration_fingerprint(),
                         CALIBRATION_FINGERPRINTS[SCORE_CONTRACT_ID])

    def test_older_contract_entries_are_untouched(self):
        self.assertEqual(CALIBRATION_FINGERPRINTS["8:8:8"], "38bf1d623bea1517")
        self.assertEqual(CALIBRATION_FINGERPRINTS["9:9:9"], "2e7638d58c2b26e4")

    def test_the_v10_bump_did_not_narrow_the_counter_gate(self):
        """v10 changed the corpus SPAN, not what a counter means, so it added no counter-
        version refusal of its own: v8/v9/v10 all clear the pre-dedup gate.

        Scoped to the pre-dedup gate deliberately. This test used to assert that v8-v10
        reached `scoring_inputs_by_source` -- i.e. that nothing at all stopped them -- which
        made it a test of the LIVE floor rather than of v10's contribution to it. v12 narrowed
        that floor for a reason of its own (`actions_per_prompt` changed basis; see
        tests/test_top_level_actions_per_prompt.py), so the old form would now fail while
        the fact it was written to protect is untouched. What v10 must not have done is
        introduce a COUNTER-definition refusal, and that is what is asserted here.

        The payload carries the two things replay() checks BEFORE the version gate --
        `payload_features` and the corpus-scale declaration -- because without them a bare
        {"scoring_inputs_version": N} never reaches that gate at all, and the assertion
        would hold for a reason that has nothing to do with the version."""
        from gnomon.scoring.replay import replay, ReplayError
        self.assertEqual(SKILL_DEDUP_INPUTS_VERSION, 8)
        for version in (8, 9, 10):
            with self.subTest(version=version):
                payload = {
                    "payload_features": {"version": 1, "supported": [],
                                         "emitted": [], "omitted": []},
                    "context": {"window_months": DEFAULT_SCORING_WINDOW_MONTHS},
                    "scoring_inputs_version": version,
                }
                with self.assertRaises(ReplayError) as caught:
                    replay(payload)
                # Never refused as PRE-DEDUP, and never for the window it declares.
                self.assertNotIn("dedup", str(caught.exception))
                self.assertNotIn("window_months", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
