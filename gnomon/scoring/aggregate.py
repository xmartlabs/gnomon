"""Per-source and aggregate scoring on top of the per-source raw scoring inputs.

The whole-corpus `profile` (gnomon/output/summary.py::_build_profile) pools every
source into one stats dict and scores it once, with capabilities = UNION of sources.
That dilutes a high-signal source (e.g. Claude) when a low-capability source (e.g.
Cursor, which can't record skills/toolsearch/tasktool) is mixed in.

This module recomputes scores PER SOURCE — each from its OWN single-source slice, so
compute_aq keys its capability set off that one source (SOURCE_CAPS) and drops +
renormalizes the terms that source can't record (no penalty, no dilution). It then
combines the per-source SCORES into an aggregate.

AGGREGATE RULE (documented contract — mirdash mirrors this in TS):
    Do NOT pool the raw inputs (pooling re-introduces the union-capability dilution and
    lets a noisy source drown a precise one). Instead combine the per-source SCORES with
    a tool-volume weight:

        aggregate_score = Σ_s (w_s · score_s) / Σ_s w_s,   w_s = tool_calls_total(s)

    Applied independently to: the AQ total (aq_0_100), each of the 4 AQ pillars
    (Breadth/Craft/Efficiency/Savvy), and each of the 3 gstack axes (Execution/Planning/
    Engineering). A source with zero tool calls contributes zero weight. When every source
    has zero weight the aggregate falls back to a simple unweighted mean so a degenerate
    corpus still yields a well-formed (zero-ish) profile rather than a divide-by-zero.

    The aggregate's non-numeric fields (tier, archetype, steering, growth_edges,
    signature_moves) are derived from the WEIGHTED-MEAN numbers via the same vocabulary /
    selection logic the single-source path uses, so they stay internally consistent with
    the combined score (e.g. tier is the band the aggregate aq_0_100 lands in).
"""

from gnomon.scoring.aq import compute_aq
from gnomon.scoring.gstack import score_breakdown, _axis_verdict
from gnomon.scoring.archetype import pick_archetype
from gnomon.scoring.insights import (
    steering_reading, growth_edges_structured, signature_moves_structured,
)
from gnomon.scoring.profiles import build_profile, stats_from_scoring_block


def _aq_tier_for(total):
    """The single AQ→tier vocabulary, kept identical to compute_aq's banding."""
    return ("Elite" if total >= 88 else "Advanced" if total >= 75 else "Proficient" if total >= 60
            else "Adequate" if total >= 45 else "Apprentice" if total >= 25 else "Novice")


def _slice_to_stats(block):
    """A scoring-input block is already stats-shaped (corpus.sources + volume/velocity/
    behavior/stack/tools). The scoring fns also read a few optional keys via .get(); this
    fills the ones that matter so single-source scoring matches the whole-corpus path."""
    return stats_from_scoring_block(block)


def _profile_from_block(block):
    """Run the existing scoring fns over a single source's scoring-input slice and return
    a profile dict in the SAME shape build_summary's `profile` produces."""
    stats = _slice_to_stats(block)
    stats["agentic"] = compute_aq(stats)
    return build_profile(stats, model_usage=[])


def _weighted_mean(pairs):
    """Σ(w·v)/Σw over (weight, value) pairs; unweighted mean when all weights are 0."""
    tot_w = sum(w for w, _ in pairs)
    if tot_w:
        return sum(w * v for w, v in pairs) / tot_w
    vals = [v for _, v in pairs]
    return (sum(vals) / len(vals)) if vals else 0.0


def _aggregate_profile(per_source):
    """Combine per-source profiles into the aggregate profile (weighted by tool volume).
    See module docstring for the rule. Pillars/axes are matched by name across sources so
    a source that dropped an N/A pillar simply contributes nothing to that pillar's mean.
    """
    items = list(per_source.items())  # [(source, {weight, profile}), ...]

    def W(entry):
        return entry["weight"]

    # ---- AQ total + tier ----
    aq_total = round(_weighted_mean([(W(e), e["profile"]["aq"]["aq_0_100"]) for _, e in items]))
    # ---- AQ pillars (by name) ----
    pillar_names, pillar_meta = [], {}
    for _, e in items:
        for p in e["profile"]["aq"].get("pillars", []):
            if p["name"] not in pillar_meta:
                pillar_names.append(p["name"])
                pillar_meta[p["name"]] = p.get("weight", 0)
    agg_pillars = []
    for name in pillar_names:
        pairs = [(W(e), p["score"]) for _, e in items
                 for p in e["profile"]["aq"].get("pillars", []) if p["name"] == name]
        agg_pillars.append({"name": name, "weight": pillar_meta[name],
                            "score": round(_weighted_mean(pairs), 1)})
    agg_aq = {
        "aq_0_100": aq_total,
        "tier": _aq_tier_for(aq_total),
        "pillars": agg_pillars,
    }

    # ---- gstack axes (Execution/Planning/Engineering) ----
    def axis_mean(axis):
        return round(_weighted_mean(
            [(W(e), e["profile"]["scores"][axis]["value"]) for _, e in items]), 1)
    agg_scores = {ax: {"value": axis_mean(ax)}
                  for ax in ("execution", "planning", "engineering")}

    # ---- non-numeric fields derived from the AGGREGATE numbers (internally consistent) ----
    arch_scores = {"Execution": agg_scores["execution"]["value"],
                   "Planning": agg_scores["planning"]["value"],
                   "Engineering": agg_scores["engineering"]["value"]}
    # Build a minimal stats dict carrying the aggregate AQ so insight pickers that read
    # stats["agentic"].pillars stay consistent with the combined score. The archetype /
    # steering / growth / signature pickers read behavior+volume — use the tool-volume
    # weighted means of those so the narrative matches the combined numbers.
    synth = _synth_stats_for_aggregate(items, agg_aq)
    arch_title, arch_quote = pick_archetype(synth, arch_scores)
    return {
        "aq": agg_aq,
        "archetype": {"title": arch_title, "quote": arch_quote},
        "scores": _expand_axes(agg_scores, synth),
        "steering": steering_reading(synth),
        "growth_edges": growth_edges_structured(synth, arch_scores),
        "signature_moves": signature_moves_structured(synth),
        "model_usage": [],
        "combination": {
            "rule": "weighted_mean_of_per_source_scores",
            "weight": "tool_calls_total",
            "weights": {src: e["weight"] for src, e in items},
        },
    }


def _expand_axes(agg_scores, synth):
    """The aggregate axis VALUE is the weighted mean of the per-source axis values (the
    documented rule), NOT the synth-pooled breakdown. We keep the full score_breakdown
    shape (subs are the tool-volume synth blend — a descriptive breakdown), but every
    axis-level field that quotes the score is recomputed from the weighted-mean value so
    the axis VALUE, verdict, and narrative agree (no `value=8.3` next to a `7.7/10`
    narrative). The per-sub percentages remain the synth blend (supporting detail)."""
    sb = score_breakdown(synth)
    for ax in ("execution", "planning", "engineering"):
        v = agg_scores[ax]["value"]
        av = _axis_verdict(v)
        sb[ax]["value"] = v
        sb[ax]["score_out_of_10"] = f"{v} / 10"
        sb[ax]["axis_verdict"] = av
        subs = sb[ax].get("subs") or []
        if subs:
            best = max(subs, key=lambda s: s.get("pct", 0))
            drag = next((s for s in subs if s.get("is_drag")), subs[-1])
            sb[ax]["axis_narrative"] = (
                f"{ax.capitalize()} scores {v}/10 ({av}). "
                f"Strongest: {best['label']} ({best['score_pct']}%); "
                f"weakest: {drag['label']} ({drag['score_pct']}%).")
    return sb


def _synth_stats_for_aggregate(items, agg_aq):
    """Tool-volume-weighted blend of the per-source behavior/volume/velocity/stack/tools
    fields, so the narrative pickers (archetype/steering/growth/signature) read numbers
    consistent with the combined score. AQ is the already-combined aggregate AQ."""
    def wmean(path_get):
        pairs = []
        for _, e in items:
            w = e["weight"]
            v = path_get(e["block"])
            if v is not None:
                pairs.append((w, v))
        return _weighted_mean(pairs) if pairs else 0

    def wsum(path_get):
        return sum(int(path_get(e["block"]) or 0) for _, e in items)

    b = lambda blk: blk.get("behavior") or {}
    v = lambda blk: blk.get("volume") or {}
    vel = lambda blk: blk.get("velocity") or {}
    st = lambda blk: blk.get("stack") or {}
    t = lambda blk: blk.get("tools") or {}

    merged_skills = {}
    merged_models = {}
    for _, e in items:
        # skills_all (cap 200), NOT top_skills (cap 15): the narrative pickers
        # (archetype/steering/growth/signature) match needle skills by substring, so a
        # 15-item view could silently drop a needle ranked past 15. Same reason local.py
        # caps skills_all high.
        for k, n in (st(e["block"]).get("skills_all") or []):
            merged_skills[k] = merged_skills.get(k, 0) + n
        for k, n in (st(e["block"]).get("models") or []):
            merged_models[k] = merged_models.get(k, 0) + n

    synth = {
        "corpus": {"sources": {src: {} for src, _ in items}},
        "agentic": agg_aq,
        "volume": {
            "total_sessions": wsum(lambda blk: v(blk).get("total_sessions")),
            "total_prompts": wsum(lambda blk: v(blk).get("total_prompts")),
            "tool_calls_total": wsum(lambda blk: v(blk).get("tool_calls_total")),
            "thinking_blocks": wsum(lambda blk: v(blk).get("thinking_blocks")),
        },
        "velocity": {
            "tool_churn_edit_write": wsum(lambda blk: vel(blk).get("tool_churn_edit_write")),
            "shell_authored_lines_est": wsum(lambda blk: vel(blk).get("shell_authored_lines_est")),
            "active_hours": round(sum(vel(e["block"]).get("active_hours") or 0 for _, e in items), 1),
        },
        "behavior": {
            "planning_ratio_explore_to_doing": round(wmean(lambda blk: b(blk).get("planning_ratio_explore_to_doing")), 2),
            "actions_per_prompt": round(wmean(lambda blk: b(blk).get("actions_per_prompt")), 1),
            "questions_asked": wsum(lambda blk: b(blk).get("questions_asked")),
            "delegate_actions": wsum(lambda blk: b(blk).get("delegate_actions")),
            "background_tasks": wsum(lambda blk: b(blk).get("background_tasks")),
            "shell_test_runs": wsum(lambda blk: b(blk).get("shell_test_runs")),
            "plan_sessions": wsum(lambda blk: b(blk).get("plan_sessions")),
            "fanout_median": wmean(lambda blk: b(blk).get("fanout_median")),
            "iteration_depth_mean": wmean(lambda blk: b(blk).get("iteration_depth_mean")),
            "iteration_depth_p90": wmean(lambda blk: b(blk).get("iteration_depth_p90")),
            "iteration_depth_max": max((b(e["block"]).get("iteration_depth_max") or 0) for _, e in items) if items else 0,
            "files_hammered_over_15x": wsum(lambda blk: b(blk).get("files_hammered_over_15x")),
            "error_rate_per_100_tools": wmean(lambda blk: b(blk).get("error_rate_per_100_tools")),
            "error_recovery_ratio": wmean(lambda blk: b(blk).get("error_recovery_ratio")),
            "api_errors_retries": wsum(lambda blk: b(blk).get("api_errors_retries")),
        },
        "stack": {
            "top_skills": sorted(merged_skills.items(), key=lambda kv: -kv[1]),
            "skills_all": sorted(merged_skills.items(), key=lambda kv: -kv[1]),
            "models": sorted(merged_models.items(), key=lambda kv: -kv[1]),
            "compounding_writes": wsum(lambda blk: st(blk).get("compounding_writes")),
            "skills_distinct": wsum(lambda blk: st(blk).get("skills_distinct")),
            "skills_total": wsum(lambda blk: st(blk).get("skills_total")),
            "subagent_types_distinct": max((st(e["block"]).get("subagent_types_distinct") or 0) for _, e in items) if items else 0,
            "subagent_types": [],
        },
        "tools": {
            "top_tools": [],
            "mcp_servers_distinct": max((t(e["block"]).get("mcp_servers_distinct") or 0) for _, e in items) if items else 0,
            "clis_distinct": max((t(e["block"]).get("clis_distinct") or 0) for _, e in items) if items else 0,
            "cli_calls": wsum(lambda blk: t(blk).get("cli_calls")),
            "mcp_calls": wsum(lambda blk: t(blk).get("mcp_calls")),
            "toolsearch_calls": wsum(lambda blk: t(blk).get("toolsearch_calls")),
            "tool_diversity": max((t(e["block"]).get("tool_diversity") or 0) for _, e in items) if items else 0,
            "tool_entropy_normalized": wmean(lambda blk: t(blk).get("tool_entropy_normalized")),
        },
    }
    return synth


def score_by_source(scoring_inputs_by_source):
    """Given build_summary's scoring_inputs_by_source, return:
        {"by_source": {<source>: <profile>}, "aggregate": <profile>}

    Each per-source profile is computed from that source's WINDOW slice using that
    source's own caps (single-source → no union dilution). The aggregate combines the
    per-source SCORES per the module's documented weighted-mean rule.
    """
    by_source = {}
    per_source_meta = {}
    for src, blocks in scoring_inputs_by_source.items():
        window = blocks.get("window") or {}
        profile = _profile_from_block(window)
        by_source[src] = profile
        per_source_meta[src] = {
            "profile": profile,
            "block": window,
            "weight": (window.get("volume") or {}).get("tool_calls_total", 0),
        }
    aggregate = _aggregate_profile(per_source_meta) if per_source_meta else None
    return {"by_source": by_source, "aggregate": aggregate}
