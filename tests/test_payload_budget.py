"""Worst-case payload budget gate (persist-recompute-grade-inputs).

The mirdash ingest route stores the raw summary verbatim in a single Convex
document capped at 900 KB (binary KB = 921,600 bytes; see
gnomon/upload/mirdash.py::_INGEST_MAX_BYTES). This module measures the
recompute-grade-payload capability's own contribution to that budget --
`bucket_scoring_inputs` and `payload_features` -- against a synthetic
WORST-CASE summary (not a real corpus -- a real corpus is not reproducibly
worst-case).

SCOPE RELAXATION (persist-recompute-grade-inputs): an earlier revision of
this capability also shipped a `scoring_inputs_corpus` merged-corpus block so
a future recompute job could reproduce `profile.aq` EXACTLY for multi-source
corpora. Measured on real 8-source data that block cost ~487 KB and pushed a
real payload from ~89% to ~149% of this budget. The requirement was relaxed
(approximate multi-source recompute is acceptable -- see
gnomon/scoring/replay.py's module docstring), so `scoring_inputs_corpus` is
no longer built or shipped at all, for any source count. It never appears in
this module's fixtures.

Fixture construction (capability-aware, per gnomon/config.py::SOURCE_CAPS):
  - every source gnomon can discover (gnomon.sources.discovery.ALL_SOURCES)
  - `_DEFAULT_WINDOW_MONTHS` monthly blocks per source (one, since v10) plus a
    `noticed_stats_monthly` block MONTHLY_SELF_HEAL_MONTHS wide, since the
    per-POST worst case is the widest single window, not a 12-month backfill
    (that is 12 separate POSTs). The two counts differ on purpose: scoring
    window and evidence window are separate spans since v10
  - list-shaped fields (skills_all, top_skills, top_tools, subagent_types,
    mcp_knowledge_server_names, linked_model_pairs) filled to their real caps
    for capability-having sources; capability-lacking sources get an empty
    list for that field (SOURCE_CAPS-gated), matching what those adapters can
    actually record
  - names use a fixed length (_NAME_LEN) set to a DEFENSIBLE OBSERVED MAXIMUM
    (not a comfortable guess) -- names dominate block size, so this is the
    deliberate worst-case knob
  - monthly-block list caps are scaled down (_MONTHLY_DIV) ONLY for fields
    whose cap is a genuine corpus-window aggregate (skills_all, top_skills);
    fields whose cap is applied PER-BLOCK (top_tools, subagent_types) are
    NOT scaled down, since a single month can independently reach its own
    full cap regardless of the other months in the window

KNOWN RISK, documented rather than gated (see WorstCasePayloadBudget's class
docstring for the numbers): the mirdash 900 KB ingest cap is a PRE-EXISTING,
out-of-scope concern for gnomon's overall payload, not something this
capability created or can fix alone.
  1. Real 8-source data measures the baseline (everything EXCEPT this
     capability's two blocks) at ~89% of the cap already
     (docs/metrics-by-source.md's "Upload payload budget" section).
  2. In the fully-maxed SYNTHETIC worst case this module builds (every
     documented per-source/per-month list cap hit simultaneously across all
     8 sources, `_NAME_LEN=36` throughout), the PRE-EXISTING
     `scoring_inputs_by_source` + `profiles_by_source` fields used to exceed
     the cap on their own -- a scenario never observed on real data, and
     unrelated to `bucket_scoring_inputs`/`payload_features`. This module
     therefore gates on this capability's own bounded contribution (its
     absolute size and the delta it adds), not on the whole payload's total
     size.

     v10 UPDATE: the one-month scoring window shrank that pre-existing
     condition rather than fixing it by design. `scoring_inputs_by_source[*]
     .monthly` follows `_DEFAULT_WINDOW_MONTHS`, so it went from 6 blocks per
     source to 1, and the synthetic worst case fell from 1,052,917 bytes
     (1.14x the cap) to ~672 KB (0.73x). That is a real reduction, but it is a
     SIDE EFFECT of the window change and must not be read as the pre-existing
     risk being closed: `_MAX_SHIPPED_WORST_CASE_BYTES` was re-anchored to the
     new measurement precisely so the smaller number becomes the new ceiling
     instead of leaving 390 KB of silent slack in the ratchet.

     The same change is why `noticed_stats_monthly` is no longer `[]` in the
     fixture. It is shaped over the SELF-HEAL window
     (gnomon/cli/local.py MONTHLY_SELF_HEAL_MONTHS), not the scoring window, so
     it stays six months wide while everything else narrowed -- making it the
     widest multi-month block in the payload and the one the worst case now has
     to be built around. Leaving it empty would have turned this whole module
     into a measurement of a payload gnomon does not send.
"""
import json
import unittest
from unittest.mock import patch

from gnomon.config import SOURCE_CAPS
from gnomon.sources.discovery import ALL_SOURCES
from gnomon.scoring.inputs import build_scoring_inputs
from gnomon.scoring.aggregate import score_by_source, HISTORY_WEIGHT
from gnomon.scoring.profiles import stats_from_scoring_block, build_profile
from gnomon.scoring.aq import compute_aq
from gnomon.scoring.versioning import (
    SCORING_INPUTS_VERSION, AQ_VERSION, GSTACK_VERSION, SCORE_CONTRACT_ID,
)
from gnomon.output.source_usage import build_source_usage, build_source_usage_monthly
from gnomon.output.summary import _build_noticed_stats
from gnomon.cli.local import MONTHLY_SELF_HEAL_MONTHS
from gnomon.upload.mirdash import (
    _INGEST_MAX_BYTES, _DEFAULT_WINDOW_MONTHS, _upload_summary, PayloadTooLarge,
)


_NAME_LEN = 36  # defensible OBSERVED maximum, not a guess: real skill/subagent
                # identifiers in this ecosystem reach "architecture-blueprint-
                # generator" (32 chars) and "china-market-localization-strategist"
                # (36 chars) -- both longer than "systematic-debugging" (21). A
                # worst-case fixture must use the longest observed real name, not
                # a comfortable mid-range guess (review remediation, Fix 4).
_MAX_RECOMPUTE_GRADE_BYTES = 100 * 1024  # hard absolute cap (item 6a): this
                # capability's own blocks (bucket_scoring_inputs +
                # payload_features), shipped/trimmed shape, measured ~34 KB in
                # the synthetic worst case -- comfortably under this bound with
                # margin for growth, and a tiny fraction of the 900 KB total cap.
_MAX_RECOMPUTE_GRADE_DELTA_RATIO = 0.05  # hard relative cap (item 6b): the
                # marginal DELTA these blocks add to an otherwise-unchanged
                # payload must stay under 5% of the mirdash ingest budget, so a
                # future change to their contents cannot silently balloon the
                # payload again. Measured ~3.7% in the synthetic worst case.
_MAX_SHIPPED_WORST_CASE_BYTES = 678_000  # review remediation (round 2, Fix 6):
                # a GROWTH RATCHET on the full shipped/trimmed synthetic worst-case
                # payload. Before this ratchet the number was only PRINTED, so growth
                # in the pre-existing fields (scoring_inputs_by_source /
                # profiles_by_source) went undetected.
                #
                # v10 re-anchor: was 1_060_000 against a measured 1,052,898-1,052,902.
                # The one-month scoring window cut `scoring_inputs_by_source[*].monthly`
                # from 6 blocks per source to 1 and the same fixture now measures
                # ~672,500 bytes, so the old bound would have permitted 57% silent
                # growth. Re-anchored with the same discipline as before -- just above
                # the measurement, headroom for dict-ordering noise, NOT tuned to the
                # exact byte. It is still a ratchet, not a fit-under-the-cap claim,
                # even though the number now happens to sit at 0.73x the 900 KB cap
                # (see the module docstring's v10 UPDATE for why that is a side effect
                # and not a fix).
                #
                # v12 re-anchor, 680,000 -> 680,600, against a measured 680,441. Three fields
                # joined every per-source and per-month block, each one measured as it landed:
                #   `sidechain_tool_calls`   678,843 -> 679,302  (+459)  volume
                #   `total_instructions`     679,302 -> 679,812  (+510)  volume
                #   `sidechain_label_state`  679,812 -> 680,441  (+629)  behavior
                # (and 34,085 -> 34,122 on the recompute-grade blocks, which have their own
                # bound with ample room). The third one is what turned this test red, which is
                # the ratchet doing its job: the previous bound was left in place precisely so
                # the next field could not absorb silently.
                #
                # Re-anchored just above the measurement with ~160 bytes for dict-ordering
                # noise, NOT rounded up for comfort -- the next per-block field goes red again.
                #
                # The two v12 volume fields are the two sides of one ratio and the third is its
                # trust flag, so all three are load-bearing rather than diagnostics that could
                # be trimmed: `actions_per_prompt` cannot be reconciled from the payload
                # without `total_instructions` and `sidechain_tool_calls`, and cannot be known
                # to be trustworthy without `sidechain_label_state`.
                #
                # v12 re-anchor, DOWNWARD: 680,600 -> 678,000 against a measured 677,839.
                # Withholding the Steering-leverage term (STEERING_LEVERAGE_BAND_VALIDATED =
                # False in gnomon/scoring/aq.py) deletes a whole axis object from every
                # Efficiency pillar in the payload and adds back one `not_applicable` entry
                # plus one `agentic.steering_leverage` sibling -- a NET SAVING of 2,602 bytes.
                # Re-anchored rather than left at the old bound on purpose: a ratchet that sits
                # 2.6 KB above the measurement is 2.6 KB of silent growth this test would no
                # longer catch, and the whole point of the number is that the next per-block
                # field goes red. Same ~160 bytes of dict-ordering headroom as before.


def _name(prefix, i):
    return (f"{prefix}-{i:03d}-{'n' * _NAME_LEN}")[:_NAME_LEN + len(prefix) + 5]


def _corpus_sources_hook(sources):
    """The corpus.sources keys-only hook (design's "capability trap" fix):
    stats_from_scoring_block prefers block["corpus"]["sources"] over the
    composite `source` string, so available_caps sees real source ids."""
    return {"sources": {s: {} for s in sources}}


_MONTHLY_DIV = {
    # skills_all is a documented 200 CORPUS-WINDOW ceiling (aq.py:225's
    # skill_uses, gstack.py:176 both score off the corpus-wide distinct-skill
    # set) -- a single month cannot independently re-hit the full 6-month
    # aggregate, so scaling it down per month is correct.
    "skills_all": 6,
    # top_skills is built as a slice of the SAME skills_all counter in this
    # fixture (mirrors accumulator.py: both are most_common(N) reads off one
    # Counter) -- it shares skills_all's corpus-window scaling.
    "top_skills": 6,
    # top_tools' 100 cap is applied PER-BLOCK: gnomon/cli/accumulator.py /
    # gnomon/scoring/inputs.py build the monthly tool counter independently of
    # the window's own counter, so a single month CAN reach the cap on its
    # own -- dividing it by 6 silently under-measured the real worst case
    # (review remediation, Fix 4: this was the reviewer's specific finding).
    "top_tools": 1,
    # subagent_types' 10 cap is the same per-block situation as top_tools --
    # accumulator.py's month_subagent_counter is independent of the window's
    # subagent_counter, both capped at the same constant.
    "subagent_types": 1,
    # linked_model_pairs is NOT populated on monthly slices at all in
    # production today (accumulator.py's to_monthly()/build_monthly_scoring_stats
    # never sets it -- inputs.py defaults it to [] via .get(..., [])), so a
    # real monthly worst case is 0. Keeping the 6-month-window scaling here
    # is a deliberate, documented OVERESTIMATE, not a measured value -- safe
    # in the conservative direction.
    "linked_model_pairs": 6,
}


def _worst_case_stats(source, monthly=False):
    """monthly=True scales SOME list-shaped fields down to a per-month slice
    of the window's caps -- but only fields whose cap is a genuine CORPUS-
    WINDOW aggregate (see _MONTHLY_DIV). Fields whose cap is applied
    PER-BLOCK (top_tools, subagent_types) must NOT be divided, or the
    fixture silently under-measures the real per-POST worst case -- a
    monthly block can independently reach its own full cap regardless of
    what the other 5 months in the window contain."""
    caps = SOURCE_CAPS.get(source, set())
    has_skills = "skills" in caps or "skill_reads" in caps
    has_delegate = "delegate" in caps
    has_routing = "linked_model_routing" in caps

    def cap(n, field):
        div = _MONTHLY_DIV[field] if monthly else 1
        return max(1, -(-n // div)) if n else 0  # ceil(n/div), 0 stays 0

    skills_all = [(_name("skill", i), 999) for i in range(cap(200, "skills_all"))] if has_skills else []
    top_skills = skills_all[:cap(100, "top_skills")]
    top_tools = [(_name("tool", i), 999) for i in range(cap(100, "top_tools"))]
    subagent_types = ([(_name("agent", i), 50) for i in range(cap(10, "subagent_types"))]
                       if has_delegate else [])
    mcp_knowledge_server_names = [_name("mcp-knowledge", i) for i in range(15)]
    linked_model_pairs = [
        {"provider": "anthropic", "lead_model": _name("lead", i),
         "child_model": _name("child", i), "completed": 10,
         "lifecycle_known": True, "substantive_calls": 5, "writes": 3}
        for i in range(cap(20, "linked_model_pairs"))
    ] if has_routing else []
    models = [(_name("model", i), 500) for i in range(12)]
    by_model = [
        {"model_id": _name("model", i), "input": 10 ** 7, "output": 10 ** 7,
         "cache_read": 10 ** 6, "cache_creation": 10 ** 6}
        for i in range(12)
    ]

    return {
        "corpus": {"sources": {source: {}}},
        "volume": {"total_sessions": 50000, "total_prompts": 500000,
                   "tool_calls_total": 2000000, "thinking_blocks": 100000},
        "velocity": {"active_hours": 5000.0, "tool_churn_edit_write": 5000000,
                     "shell_authored_lines_est": 500000},
        "behavior": {
            "planning_ratio_explore_to_doing": 0.5, "actions_per_prompt": 4.0,
            "questions_asked": 1000, "error_recovery_ratio": 0.9,
            "error_rate_per_100_tools": 2.0, "api_errors_retries": 500,
            "fanout_median": 3.0, "max_session_fanout": 10,
            "parallel_dispatch_turns": 200, "delegating_sessions": 3000,
            "parallel_session_share": 0.3, "shell_test_runs": 10000,
            "plan_sessions": 5000, "planning_skill_sessions": 3000,
            "eligible_change_sessions": 40000, "planned_eligible_sessions": 20000,
            "evidence_eligible_sessions": 30000, "ordered_facts_state": "measured",
            "linked_model_pairs": linked_model_pairs,
            "linked_model_routing_state": "measured" if has_routing else "unsupported",
            "delegate_actions": 8000, "background_tasks": 2000,
            "iteration_depth_mean": 3.2, "iteration_depth_p90": 9,
            "iteration_depth_max": 40, "files_hammered_over_15x": 300,
            "no_tool_activity": False, "orchestratable_sessions": 20000,
            "delegated_orchestratable_sessions": 15000,
        },
        "stack": {
            "skills_distinct": len(skills_all), "skills_total": 400000 if has_skills else 0,
            "compounding_writes": 30000, "subagent_types_distinct": len(subagent_types),
            "max_session_subagent_types": 10 if has_delegate else 0,
            "subagent_types": subagent_types, "top_skills": top_skills,
            "skills_all": skills_all, "models": models,
        },
        "tools": {
            "agent_calls": 8000, "mcp_servers_distinct": 30, "clis_distinct": 40,
            "toolsearch_calls": 20000, "task_tool_calls": 15000, "cli_calls": 300000,
            "mcp_calls": 100000, "tool_diversity": 60, "tool_entropy_normalized": 0.9,
            "mcp_knowledge_calls": 50000, "mcp_knowledge_servers": len(mcp_knowledge_server_names),
            "mcp_knowledge_server_names": mcp_knowledge_server_names,
            "mcp_grounded_sessions": 20000, "mcp_write_sessions": 25000,
            "mcp_subcategory_breakdown": {
                cat: {"calls": 1000, "servers": 5}
                for cat in ("knowledge", "docs", "search", "other")
            },
            "top_tools": top_tools,
        },
        "token_usage": {"by_model": by_model},
    }


def _block(source, month=None):
    b = build_scoring_inputs(_worst_case_stats(source, monthly=bool(month)))
    if month:
        b["month"] = month
    return b


def _monthly(source):
    return [_block(source, month=f"2025-{m:02d}") for m in range(1, _DEFAULT_WINDOW_MONTHS + 1)]


def _noticed_stats_monthly():
    """`noticed_stats_monthly` at its real worst case: MONTHLY_SELF_HEAL_MONTHS entries,
    every per-month list at its cap.

    This block used to be `[]` in the fixture, which was already an under-measurement and
    became a load-bearing one when the scoring window narrowed to one month: the per-source
    `monthly` blocks now carry ONE entry each (they follow _DEFAULT_WINDOW_MONTHS), so if
    this stayed empty the "worst case" would simply have shrunk sixfold and the growth
    ratchet below would have stopped ratcheting anything. This block is now the widest
    multi-month structure gnomon ships -- it is deliberately shaped over the self-heal
    window, not the scoring window (see gnomon/cli/local.py MONTHLY_SELF_HEAL_MONTHS) -- so
    it is what the worst case has to be built around.

    Caps come from _build_monthly_noticed_stats: top_tools / top_skills / top_mcp_servers
    are `most_common(100)` on the MONTH's own counter, so a single month can reach each cap
    on its own (same per-block argument _MONTHLY_DIV records for top_tools).
    """
    entries = []
    for month in range(1, MONTHLY_SELF_HEAL_MONTHS + 1):
        stats = _build_noticed_stats({
            "volume": {"total_sessions": 8000, "total_prompts": 500000,
                       "tool_calls_total": 2000000, "assistant_turns": 900000,
                       "thinking_blocks": 400000, "avg_prompt_length_chars": 1234.5,
                       "median_prompt_length_chars": 987.5},
            "velocity": {"git_churn_total": 900000, "tool_churn_edit_write": 800000,
                         "shell_authored_lines_est": 700000, "git_repos_seen": 40,
                         "git_repos_with_commits": 40, "active_hours": 720.0},
            "behavior": {"iteration_depth_mean": 12.34, "iteration_depth_median": 9.5,
                         "iteration_depth_p90": 40, "iteration_depth_max": 900,
                         "files_hammered_over_15x": 500, "tool_errors": 90000,
                         "error_rate_per_100_tools": 4.5, "error_recovery_ratio": 0.987,
                         "polite_prompts": 5000, "questions_asked": 60000,
                         "delegate_actions": 40000, "background_tasks": 3000,
                         "scheduled_actions": 2000, "fanout_median": 9,
                         "longest_run_minutes": 1440.0},
            "stack": {"models": [(_name("model", i), 10 ** 6) for i in range(8)]},
            "rhythm": {"hour_histogram_local": {str(h): 90000 for h in range(24)},
                       "weekday_histogram": {d: 700000 for d in
                                             ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
                       "peak_hours_local": list(range(24)),
                       "preferred_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
            "tools": {"top_tools": [(_name("tool", i), 10 ** 6) for i in range(100)]},
            "skills": {"top_skills": [(_name("skill", i), 10 ** 5) for i in range(100)]},
            "mcp_servers": {"top_mcp_servers": [(_name("mcp", i), 10 ** 5) for i in range(100)]},
        })
        entries.append({
            "month": f"2025-{month:02d}",
            "range_start": f"2025-{month:02d}-01",
            "range_end": f"2025-{month:02d}-28",
            "stats": stats,
            "token_usage": {"total_input": 10 ** 7, "total_output": 10 ** 7,
                            "total_cache_read": 10 ** 6, "total_cache_creation": 10 ** 6,
                            "by_model": [{"model_id": _name("model", i),
                                          "label": _name("model", i),
                                          "input": 10 ** 6, "output": 10 ** 6,
                                          "cache_read": 10 ** 5, "cache_creation": 10 ** 5}
                                         for i in range(8)]},
        })
    return entries


def _corpus_block(sources, month=None):
    b = build_scoring_inputs(_worst_case_stats(sources[0], monthly=bool(month)))
    b["corpus"] = _corpus_sources_hook(sources)
    if month:
        b["month"] = month
    return b


def worst_case_summary(include_bucket_by_source=True):
    """Build a synthetic worst-case summary.json-shaped dict.

    No `scoring_inputs_corpus` block is built or shipped here (scope
    relaxation: approximate multi-source recompute is acceptable, so the
    merged-corpus block that bought only exactness was dropped entirely for
    every source count -- see gnomon/scoring/replay.py's module docstring).
    `bucket_scoring_inputs.corpus` (the recent_30d merged-bucket block) is
    still built via _corpus_block. v11 stopped EMITTING that block -- the recency
    blend that produced it is gone -- so this fixture now models the heaviest
    payload shape mirdash can still be asked to ingest (a pre-v11 upload re-sent
    or replayed) rather than the shape a current run produces. Keeping it makes the
    budget assertions strictly conservative; dropping it would quietly relax a cap
    that pre-v11 payloads still have to fit under.

    include_bucket_by_source: the trim knob -- False omits the per-source
    recent_30d bucket blocks (bucket_scoring_inputs.by_source), matching what
    gnomon shipped up to v10 (that trim was unconditional, not ratio-gated, since
    it was the cheapest available payload-budget lever).
    """
    sources = list(ALL_SOURCES)
    scoring_inputs_by_source = {
        src: {"window": _block(src), "monthly": _monthly(src)}
        for src in sources
    }
    bucket_metadata = [{"id": "recent_30d", "configured_weight": 0.65,
                         "day_bounds": {"lower": 0, "upper": 30}}]
    bucket_by_source = {
        "recent_30d": {src: {"window": _block(src)} for src in sources}
    }
    bucket_corpus = {"recent_30d": {"window": _corpus_block(sources)}}
    bucket_scoring_inputs = {"metadata": bucket_metadata, "corpus": bucket_corpus}
    if include_bucket_by_source:
        # Matches production (gnomon/cli/local.py): by_source is OMITTED
        # entirely when trimmed, never shipped as an empty dict.
        bucket_scoring_inputs["by_source"] = bucket_by_source
    omitted = []
    if not include_bucket_by_source:
        omitted.append({"feature": "bucket_scoring_inputs.by_source",
                         "reason": "trimmed_unconditionally"})
    payload_features = {
        "version": 1,
        "supported": ["bucket_scoring_inputs", "upload_size_guard"],
        "emitted": ["bucket_scoring_inputs"],
        "omitted": omitted,
        "recency_blend": {"enabled": True, "history_weight": HISTORY_WEIGHT},
    }
    profiles_by_source = score_by_source(
        scoring_inputs_by_source,
        bucket_scoring_inputs_by_source=bucket_by_source,
        bucket_metadata=bucket_metadata,
    )
    source_usage = build_source_usage(scoring_inputs_by_source)
    source_usage_monthly = build_source_usage_monthly(scoring_inputs_by_source)

    # `profile` (payload["profile"]) is scored from ONE representative source's
    # window block -- no merged-corpus block exists to score it from anymore.
    # This is only a byte-size stand-in for the measurement below: a real
    # multi-source run still scores `profile` from its live merged corpus
    # stats (unaffected by this change; see gnomon/cli/local.py), never from
    # a persisted payload block.
    rep_stats = stats_from_scoring_block(_block("claude"))
    rep_stats["scoring_inputs_by_source"] = scoring_inputs_by_source
    rep_stats["agentic"] = compute_aq(rep_stats)
    profile = build_profile(rep_stats)

    claude_tools = _worst_case_stats("claude")["tools"]
    claude_stack = _worst_case_stats("claude")["stack"]

    return {
        "context": {
            "date_range": ["2025-01-01", "2025-06-30"],
            "window": {"since": "2025-01-01T00:00:00", "until": "2025-06-30T23:59:59"},
            "sources": sorted(sources),
            "total_sessions": 400000, "total_prompts": 4000000,
            "client_version": "0.9.9",
        },
        "planning_ratio_explore_to_doing": 0.5,
        "errors": {"error_recovery_ratio": 0.9, "error_rate_per_100_tools": 2.0},
        "iteration_depth": {"mean": 3.2, "median": 3.0, "p90": 9, "max": 40, "files_over_15x": 300},
        "churn": {"git_churn_total": 5000000, "tool_churn_edit_write": 5000000,
                  "active_hours": 5000.0, "actions_per_prompt": 4.0},
        "orchestration": {"fanout_median": 3.0, "max_session_fanout": 10,
                           "parallel_dispatch_turns": 200, "parallel_session_share": 0.3,
                           "delegating_sessions": 3000, "delegate_actions": 8000,
                           "orchestratable_sessions": 20000,
                           "delegated_orchestratable_sessions": 15000},
        "compounding_writes": 30000,
        "ecosystem": {
            "skills_distinct": 200, "skills_total": 400000,
            "top_skills": [{"name": n, "calls": c} for n, c in claude_stack["top_skills"]],
            "mcp_servers_distinct": 30, "mcp_knowledge_calls": 50000, "mcp_knowledge_servers": 15,
            "top_mcp_servers": [{"server": n, "calls": 999}
                                 for n in claude_tools["mcp_knowledge_server_names"]],
        },
        "progression_monthly": [
            {"month": f"2025-{m:02d}", "prompts": 500000, "tool_calls": 2000000, "sessions": 8000,
             "active_days": 30, "tool_churn_lines": 800000, "models": [["m1", 100]],
             "top_model": "m1", "tokens_input": 10 ** 7, "tokens_output": 10 ** 7,
             "tokens_cache_read": 10 ** 6, "tokens_cache_creation": 10 ** 6,
             "tokens_total": 2 * 10 ** 7 + 2 * 10 ** 6}
            for m in range(1, _DEFAULT_WINDOW_MONTHS + 1)
        ],
        "noticed_stats_monthly": _noticed_stats_monthly(),
        "profile": profile,
        "scoring_inputs_version": SCORING_INPUTS_VERSION,
        "aq_version": AQ_VERSION,
        "gstack_version": GSTACK_VERSION,
        "score_contract_id": SCORE_CONTRACT_ID,
        "comparison_policy": "same_score_contract_id_only",
        "scoring_inputs_by_source": scoring_inputs_by_source,
        "profiles_by_source": profiles_by_source,
        "source_usage": source_usage,
        "source_usage_monthly": source_usage_monthly,
        "token_usage": {
            "total_input": 10 ** 8, "total_output": 10 ** 8,
            "total_cache_read": 10 ** 7, "total_cache_creation": 10 ** 7,
            "by_model": [
                {"model_id": _name("model", i), "model": _name("model", i),
                 "count": 100, "pct": 0.1, "tokens_input": 10 ** 7, "tokens_output": 10 ** 7,
                 "tokens_cache_read": 10 ** 6, "tokens_cache_creation": 10 ** 6}
                for i in range(12)
            ],
        },
        "bucket_scoring_inputs": bucket_scoring_inputs,
        "payload_features": payload_features,
    }


class WorstCasePayloadBudget(unittest.TestCase):
    """Gates on THIS capability's own bounded contribution to the mirdash
    ingest budget -- `bucket_scoring_inputs` + `payload_features` -- not on
    the payload's total size. See the module docstring's KNOWN RISK section
    for why: in the fully-maxed synthetic worst case this module builds,
    the PRE-EXISTING `scoring_inputs_by_source` + `profiles_by_source` fields
    (which predate this capability and are unrelated to `bucket_scoring_inputs`
    /`payload_features`) already exceed the 900 KB cap on their own -- a
    scenario never observed on real data, and not something dropping
    `scoring_inputs_corpus` (this change's own item 1) can fix, since that
    block was never the majority contributor once _NAME_LEN was corrected to
    36 (review remediation, Fix 4). Re-encoding a "whole payload under cap"
    assertion here would just be the SAME "unachievable pre-existing
    condition" mistake the old 70%-escalation assertion made, aimed at a
    different field. So: this module owns and gates the two fields it
    controls, and documents (does not gate on) the rest.
    """

    def test_trimmed_fixture_omits_by_source_key_entirely(self):
        """Shape-faithfulness (review remediation, Fix 7 minor): production
        (gnomon/cli/local.py) never emits a `bucket_scoring_inputs.by_source`
        key at all when trimmed -- it is OMITTED, not an empty dict. replay()
        treats `{}` and absent identically, so this was harmless, but the
        fixture should still mirror what a real payload actually ships."""
        shipped = worst_case_summary(include_bucket_by_source=False)
        self.assertNotIn("by_source", shipped["bucket_scoring_inputs"])

    def test_recompute_grade_blocks_stay_within_bounded_absolute_size(self):
        """Hard cap: the recompute-grade blocks' own shipped (trimmed) size must
        stay a small, bounded absolute number of bytes, regardless of anything
        else in the payload."""
        shipped = worst_case_summary(include_bucket_by_source=False)
        recompute_blocks = {
            "bucket_scoring_inputs": shipped["bucket_scoring_inputs"],
            "payload_features": shipped["payload_features"],
        }
        size = len(json.dumps(recompute_blocks, default=str).encode("utf-8"))
        print(f"\n  [payload budget] recompute-grade blocks (shipped/trimmed) "
              f"size={size} bytes of {_MAX_RECOMPUTE_GRADE_BYTES} bytes bound")
        self.assertLess(
            size, _MAX_RECOMPUTE_GRADE_BYTES,
            f"bucket_scoring_inputs + payload_features grew to {size} bytes in "
            f"the synthetic worst case, over the {_MAX_RECOMPUTE_GRADE_BYTES}-byte "
            f"bound this test enforces on this capability's own contribution.")

    def test_recompute_grade_delta_stays_bounded(self):
        """Relative cap: the marginal DELTA these blocks add to an otherwise-
        unchanged payload must stay under _MAX_RECOMPUTE_GRADE_DELTA_RATIO of the
        mirdash ingest budget, so a future change to their contents cannot
        silently balloon the payload again (the failure mode the original
        under-measured _NAME_LEN=14 fixture let through unnoticed).

        Also prints the FULL synthetic worst-case payload size (with and without
        the per-source recency-blend trim) purely for visibility -- see the
        module docstring's KNOWN RISK section for why that number is not gated
        on here."""
        shipped = worst_case_summary(include_bucket_by_source=False)
        without_new_blocks = {k: v for k, v in shipped.items()
                              if k not in ("bucket_scoring_inputs", "payload_features")}
        size_with = len(json.dumps(shipped, default=str).encode("utf-8"))
        size_without = len(json.dumps(without_new_blocks, default=str).encode("utf-8"))
        delta = size_with - size_without
        delta_ratio = delta / _INGEST_MAX_BYTES
        print(f"\n  [payload budget] recompute-grade delta={delta} bytes "
              f"ratio={delta_ratio:.4f} of {_INGEST_MAX_BYTES} bytes budget")

        untrimmed = worst_case_summary(include_bucket_by_source=True)
        u_size = len(json.dumps(untrimmed, default=str).encode("utf-8"))
        print(f"  [payload budget] FULL synthetic worst-case payload (informational, "
              f"NOT gated -- see module docstring KNOWN RISK): untrimmed={u_size} bytes "
              f"({u_size / _INGEST_MAX_BYTES:.4f}), shipped/trimmed={size_with} bytes "
              f"({size_with / _INGEST_MAX_BYTES:.4f}) of {_INGEST_MAX_BYTES} bytes budget")

        self.assertLessEqual(
            size_with, _MAX_SHIPPED_WORST_CASE_BYTES,
            f"the FULL shipped/trimmed synthetic worst-case payload grew to "
            f"{size_with} bytes, over the {_MAX_SHIPPED_WORST_CASE_BYTES}-byte "
            f"growth ratchet -- this is NOT a claim it fits under the mirdash cap "
            f"(see the module docstring KNOWN RISK section), only a tripwire so "
            f"growth in the pre-existing fields does not go silently undetected.")

        self.assertLess(
            delta_ratio, _MAX_RECOMPUTE_GRADE_DELTA_RATIO,
            f"bucket_scoring_inputs + payload_features added {delta} bytes "
            f"(ratio {delta_ratio:.4f}) to the synthetic worst-case payload, over "
            f"the {_MAX_RECOMPUTE_GRADE_DELTA_RATIO:.0%} bound this test enforces "
            f"so this capability's own footprint cannot silently grow unbounded.")


class OverBudgetRaisesPayloadTooLarge(unittest.TestCase):
    def test_over_budget_raises_payload_too_large(self):
        """_upload_summary must raise PayloadTooLarge BEFORE ever calling urlopen --
        no partial/truncated payload is sent, and the failure names the byte size."""
        oversized = {"padding": "x" * (_INGEST_MAX_BYTES + 1024)}
        with patch("urllib.request.urlopen") as mock_urlopen:
            with self.assertRaises(PayloadTooLarge) as ctx:
                _upload_summary("https://mirdash.example", "tok", oversized)
            mock_urlopen.assert_not_called()
        message = str(ctx.exception)
        self.assertIn(str(_INGEST_MAX_BYTES), message)

    def test_under_budget_does_not_raise(self):
        small = {"context": {"total_sessions": 1}}
        with patch("urllib.request.urlopen") as mock_urlopen:
            response = mock_urlopen.return_value.__enter__.return_value
            response.read.return_value = json.dumps({"reportUrl": "/r/1"}).encode("utf-8")
            result = _upload_summary("https://mirdash.example", "tok", small)
        self.assertEqual(result, "/r/1")
        mock_urlopen.assert_called_once()

    def test_tagged_archive_only_response_preserves_outcome_for_callers(self):
        small = {"context": {"total_sessions": 1}}
        payload = {"outcome": "archived_only", "reportUrl": "/metrics"}
        with patch("urllib.request.urlopen") as mock_urlopen:
            response = mock_urlopen.return_value.__enter__.return_value
            response.read.return_value = json.dumps(payload).encode("utf-8")

            result = _upload_summary("https://mirdash.example", "tok", small)

        self.assertEqual(result, payload)


if __name__ == "__main__":
    unittest.main()
