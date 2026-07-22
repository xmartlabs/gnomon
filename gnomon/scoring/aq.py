from gnomon.analysis.metrics import _review_skill_uses, _task_skill_uses
from gnomon.config import available_caps
from gnomon.scoring.versioning import SCORE_CONTRACT_ID

PLANNING_TARGET = 0.50
CONTEXT_INTELLIGENCE_TARGET = 0.60

# ---- Ordered-planning redesign (C1-C7) calibration placeholders ------------
# All five constants below are PROVISIONAL calibration placeholders (proposal C5):
# picked from qualitative guidance (Anthropic plan-mode guidance, Fowler's Design
# Stamina Hypothesis), NOT yet fit against a real corpus. Recalibrate all of them
# together once eligible/planned counts are available from production data —
# do not tune one in isolation, they interact (a lower CHURN_MIN admits more
# sessions as eligible, which shifts the denominator PLANNING_TARGET is judged
# against).
CHURN_MIN = 80              # net changed lines (C2): single-file eligibility via churn
WINDOW = 72 * 3600           # seconds (C4): cross-session plan-credit lookback window
PLAN_MIN_LINES = 8          # net lines (C6): minimum substantive plan-file size
PLAN_MIN_STEPS = 3          # distinct todo/task steps (C6): raised from 2 (anti-theater)
MIN_ELIGIBLE_SESSIONS = 5   # sessions (C7): below this, drop+renormalize (noise floor)

# ---- Orchestration v2 — frequency + quality compound -------------------------
ORCHESTRATABLE_CODE_FILES = 3    # code files written (stricter than eligible's 2)
ORCHESTRATABLE_SUBSTANTIVE = 20  # substantive tool calls (stricter than eligible's 10)
# PROVISIONAL: the current three-user sample is insufficient for recalibration.
ORCHESTRATION_FREQUENCY_TARGET = 0.78  # 78% of orchestratable sessions should delegate
ORCHESTRATION_FULL_CONFIDENCE_SESSIONS = 5

_MODEL_TIERS = {
    "anthropic": (("opus", 3), ("sonnet", 2), ("haiku", 1)),
    "openai": (("pro", 4), ("mini", 2), ("nano", 1), ("gpt-", 3), ("codex", 3)),
}


def _model_tier(provider, model):
    low = str(model or "").lower()
    for needle, tier in _MODEL_TIERS.get(provider, ()):
        if needle in low:
            return tier
    return None


def score_linked_routing(pairs, state):
    if state != "measured":
        return {"state": state, "score": None,
                "successful_lower_tier_pairs": 0, "eligible_completed_substantive_pairs": 0,
                "excluded_reasons": {}}
    successful = eligible = 0
    excluded = {}
    for pair in pairs or []:
        if not pair.get("completed"):
            excluded["incomplete"] = excluded.get("incomplete", 0) + 1
            continue
        lead = _model_tier(pair.get("provider"), pair.get("lead_model"))
        child = _model_tier(pair.get("provider"), pair.get("child_model"))
        if lead is None or child is None:
            excluded["unknown_model"] = excluded.get("unknown_model", 0) + 1
            continue
        if not (pair.get("writes", 0) or pair.get("substantive_calls", 0) >= 5):
            excluded["not_substantive"] = excluded.get("not_substantive", 0) + 1
            continue
        eligible += 1
        successful += child < lead
    if excluded and not eligible:
        state = "unmeasured"
    rate = successful / eligible if eligible else 0.0
    return {"state": state, "score": min(1.0, rate / 0.40) if state == "measured" else None,
            "successful_lower_tier_pairs": successful,
            "eligible_completed_substantive_pairs": eligible, "excluded_reasons": excluded}


def _models_for_scoring(stats, fallback):
    """Pool model rows only from sources where model choice is scoreable."""
    by_source = stats.get("scoring_inputs_by_source")
    if not by_source:
        return fallback
    counts = {}
    for source, blocks in by_source.items():
        if "model" not in available_caps([source]):
            continue
        window = (blocks or {}).get("window") or {}
        for model, turns in ((window.get("stack") or {}).get("models") or []):
            counts[model] = counts.get(model, 0) + turns
    return list(counts.items())


def compute_aq(stats):
    """Agentic Quotient v4 — 'how well you OPERATE AGENTS' (distinct from the gstack
    scorecard, which grades how you BUILD). Four pillars: Breadth (how much machinery),
    Craft (how well), Efficiency (leverage per intervention), Savvy (smart choices).
    MCP-vs-CLI and tool diversity stay descriptive (not graded).

    Capability-aware: a signal a source CANNOT record (skills/toolsearch on Cursor, etc.)
    is dropped and its weight renormalized away — not scored 0 — so non-Claude tools aren't
    penalized for what their backend never persists. With a full-capability corpus (Claude)
    every term stays and this is a no-op."""
    t, st, b = stats.get("tools", {}), stats.get("stack", {}), stats.get("behavior", {})
    caps = available_caps((stats.get("corpus", {}).get("sources") or {}).keys())
    has_skills = "skills" in caps
    has_toolsearch = "toolsearch" in caps

    def sat(x, target):
        return min(1.0, x / target) if target else 0.0

    # Per-session rate score. An absolute cumulative count over the window penalizes low-session
    # users by their exact session deficit (a volume artifact — verified: same per-session
    # behavior scores 2.4x lower for a user with 2.4x fewer sessions). Score count/session
    # against a PER-SESSION target instead. Targets calibrated from prod non-zero-user p40-50
    # (2026-07, n~6-10) — PROVISIONAL; recalibrate as adoption grows (see --tools diagnostic).
    sessions = max((stats.get("volume", {}) or {}).get("total_sessions", 0), 1)

    def rate(x, per_session_target):
        return sat(x / sessions, per_session_target)

    def wsum(*terms):
        """Weighted mean of (coef, value, required_cap) terms, dropping terms whose cap is
        unavailable and renormalizing the remaining coefficients to sum 1. Returns None when
        NO term is measurable (the whole axis is unsupported -> build_pillar drops it)."""
        live = [(c, v) for c, v, cap in terms
                if v is not None and (cap is None or cap in caps)]
        tot = sum(c for c, _ in live)
        return sum(c * v for c, v in live) / tot if tot else None

    skills = st.get("skills_all") or st.get("top_skills", [])

    def skill_uses(needles):
        return sum(n for k, n in skills if any(nd in str(k).lower() for nd in needles))

    def has_skill(needles):
        return any(any(nd in str(k).lower() for nd in needles) for k, _ in skills)

    # ---- Pillar 1: Breadth (unchanged axes) ----
    fanout = b.get("fanout_median") or 0  # None (unmeasured) treated as 0 for AQ
    # Harness use = a SINGLE session coordinating a team of >=3 distinct subagent roles
    # (behavioral), not a subagent/skill NAMED "harness"/"trisel" (opaque), and not window-wide
    # role variety (subagent_types_distinct would credit 3 roles fired one-per-session, which
    # never coordinated a team). max_session_subagent_types is the per-session distinct-role
    # peak — name-/content-agnostic, so it works in the cross-source aggregate.
    o_harn = 1.0 if st.get("max_session_subagent_types", 0) >= 3 else 0.6
    # Orchestration v2: observed frequency (share of orchestratable sessions that
    # delegated), normalized target score, and coordination quality (subagent
    # diversity, fan-out, harness use). Frequency earns its full 30% weight
    # progressively over the first five eligible sessions.
    # fanout target 5: span-of-control theory (Graicunas/Urwick) lands at 5-7.
    o_quality = (0.40 * sat(st.get("subagent_types_distinct", 0), 8)
               + 0.40 * sat(fanout, 5)
               + 0.20 * o_harn)
    _o_orchestratable = b.get("orchestratable_sessions") or 0
    _o_delegated = b.get("delegated_orchestratable_sessions") or 0
    o_frequency = (_o_delegated / _o_orchestratable) if _o_orchestratable else None
    o_frequency_score = (sat(o_frequency, ORCHESTRATION_FREQUENCY_TARGET)
                         if o_frequency is not None else None)
    o_frequency_confidence = min(
        _o_orchestratable / ORCHESTRATION_FULL_CONFIDENCE_SESSIONS, 1.0)
    o_frequency_weight = 0.30 * o_frequency_confidence
    orchestration = ((1.0 - o_frequency_weight) * o_quality
                     + o_frequency_weight * o_frequency_score
                     if o_frequency_score is not None else o_quality)
    # skills_total -> per-session rate; skills_distinct stays (diversity, correctly absolute)
    skill_fluency = (.40 * sat(st.get("skills_distinct", 0), 40) + .30 * rate(st.get("skills_total", 0), 10)
                     + .30 * (1.0 if has_skill(["subagent-driven", "brainstorm", "writing-plans",
                                                "cerberus", "systematic-debugging"]) else 0.6))
    # mcp_servers/clis are distinct-counts (kept absolute); toolsearch -> per-session rate.
    # toolsearch term drops out (renormalized) when no present source can record it
    tool_command = wsum((.40, sat(t.get("mcp_servers_distinct", 0), 15), None),
                        (.40, sat(t.get("clis_distinct", 0), 40), None),
                        (.20, rate(t.get("toolsearch_calls", 0), 0.30), "toolsearch"))
    # task-tool -> per-session rate; TaskCreate/Update + SDD sdd-tasks skill invocations
    # both count as structured task planning. plan-skill term needs the Skill capability.
    task_calls = t.get("task_tool_calls", 0) + _task_skill_uses(skills)
    ordered_state = b.get("ordered_facts_state")
    eligible = b.get("eligible_change_sessions", 0) or 0
    # C7 — significance floor: below MIN_ELIGIBLE_SESSIONS the ratio is noise
    # (e.g. 40% over 2 sessions), so drop the term (None -> renormalized)
    # rather than score it. Placeholder constant, see aq.py's MIN_ELIGIBLE_SESSIONS.
    ordered_planning = (None if ordered_state != "measured"
                        or eligible < MIN_ELIGIBLE_SESSIONS
                        else sat(b.get("planned_eligible_sessions", 0) / eligible,
                                 PLANNING_TARGET))
    planning_skill = 1.0 if has_skill(["writing-plans", "autoplan", "plan"]) else 0.6
    discipline = wsum((.40, rate(task_calls, 1.0), "tasktool"),
                      (.40, planning_skill, "skills"),
                      (.20, ordered_planning, None))
    breadth_axes = [
        # Orchestration needs subagent delegation; a source that can't fan out by design
        # (Gemini/Pi/opencode) drops this axis (renormalized) instead of scoring ~0.
        ("Orchestration", 33, orchestration, {"subagent_types": st.get("subagent_types_distinct", 0),
         "fanout_median": fanout, "o_harn": o_harn,
         "frequency": round(o_frequency, 3) if o_frequency is not None else None,
         "frequency_score": (round(o_frequency_score, 3)
                             if o_frequency_score is not None else None),
         "frequency_confidence": round(o_frequency_confidence, 3),
         "frequency_weight": round(o_frequency_weight, 3),
         "coordination_quality": round(o_quality, 3),
         "orchestratable_sessions": _o_orchestratable,
         "delegated_orchestratable_sessions": _o_delegated},
         "delegate"),
        ("Skill fluency", 22, skill_fluency, {"skills_distinct": st.get("skills_distinct", 0),
         "skills_total": st.get("skills_total", 0)}, "skills"),
        ("Tool command (MCP + CLI)", 28, tool_command, {"mcp_servers": t.get("mcp_servers_distinct", 0),
         "clis": t.get("clis_distinct", 0), "toolsearch": t.get("toolsearch_calls", 0)}),
        ("Discipline", 17, discipline, {"task_tool_calls": task_calls}),
    ]

    # ---- Pillar 2: Craft ----
    review_n = _review_skill_uses(skills)
    # review-skill term needs observable skill data (first-class Skill tool OR SKILL.md reads /
    # injected skills on Cursor). Skill fluency / Discipline still require `skills` only.
    # test runs + review skills -> per-session rates (matches gstack's per-session test handling)
    verification = wsum((.5, rate(b.get("shell_test_runs", 0), 1.5), None),
                        (.5, rate(review_n, 1.5), "skill_reads"))
    grounding = sat(b.get("planning_ratio_explore_to_doing", 0), 1.0)
    # Context Intelligence: PURE per-session grounding COVERAGE, not knowledge-MCP call/
    # server volume (the old `<50 calls` gate was gameable by auto-fired knowledge-MCP
    # calls with zero relationship to authored output). A session is "grounded" when a
    # knowledge-MCP call (accumulator.py's per-session state machine) precedes a later
    # Edit/Write/MultiEdit/NotebookEdit in that SAME session. coverage = grounded/total.
    # MONOTONIC per-session coverage score — NO floor. More grounding never lowers the
    # axis, and a real measured zero (has tool activity, 0 grounded sessions) is scored 0,
    # NOT dropped. TARGET is PROVISIONAL (recalibrate from prod p40-50). The axis is N/A
    # ONLY when the source genuinely can't measure grounding: no_tool_activity (can't
    # reconstruct ordered per-session tool sequences) OR the grounding field is absent
    # (legacy/external block predating the accumulator, which always sets the field —
    # a missing field means backward-compat, so stay N/A instead of scoring a phantom 0).
    _v5_ordered = "ordered_facts_state" in b
    grounded = (b.get("evidence_eligible_sessions") if _v5_ordered
                else t.get("mcp_grounded_sessions"))
    ci_denom = (b.get("eligible_change_sessions") if _v5_ordered
                else t.get("mcp_write_sessions", sessions))
    coverage = (grounded / ci_denom) if grounded is not None and ci_denom else None
    context_intel = (None if ((_v5_ordered and ordered_state != "measured")
                              or b.get("no_tool_activity") or grounded is None or not ci_denom)
                     else sat(coverage, CONTEXT_INTELLIGENCE_TARGET))
    # compounding writes -> per-session rate (rewards the habit, not raw volume)
    compounding = wsum((.6, rate(st.get("compounding_writes", 0), 0.25), None),
                       (.4, (1.0 if has_skill(["retro", "writing-plans", "brainstorm"]) else 0.6), "skill_reads"))
    _review_skills_applicable = "skill_reads" in caps
    verification_signals = {"test_runs": b.get("shell_test_runs", 0)}
    if _review_skills_applicable:
        verification_signals["review_skills"] = review_n
    else:
        verification_signals["review_skills_applicable"] = False
    craft_axes = [
        ("Verification", 35, verification, verification_signals),
        ("Grounding", 25, grounding, {"planning_ratio": b.get("planning_ratio_explore_to_doing", 0)}),
        ("Context Intelligence", 20, context_intel,
         {"grounded_sessions": grounded, "write_sessions": ci_denom,
          "total_sessions": sessions,
          "coverage": round(coverage, 3) if coverage is not None else None,
          "target_coverage": CONTEXT_INTELLIGENCE_TARGET,
          "grounded_session_rule": "knowledge-MCP call OR explore-class project/data/design MCP call before a later Edit/Write/MultiEdit/NotebookEdit in the same session",
          "score_formula": (f"coverage = evidence_eligible_sessions / eligible_change_sessions; score = min(1, coverage / {CONTEXT_INTELLIGENCE_TARGET:.2f})"
                            if _v5_ordered else
                            f"coverage = grounded_sessions / write_sessions; score = min(1, coverage / {CONTEXT_INTELLIGENCE_TARGET:.2f})")}),
        ("Compounding", 20, compounding, {"compounding_writes": st.get("compounding_writes", 0)}),
    ]

    # ---- Pillar 3: Efficiency ----
    app = b.get("actions_per_prompt", 0)
    if app <= 0:
        lever = 0.0
    elif app < 5:
        lever = app / 5
    elif app <= 20:
        lever = 1.0
    else:
        lever = max(0.0, 1 - (app - 20) / 40)
    # API-error hygiene is scored as a RATE (per 100 tool calls), not an absolute count:
    # an absolute threshold penalizes volume and is window-size dependent. Target 2/100 =
    # full penalty (healthy env < 0.5/100; retry-storm / broken setup > 2/100).
    tool_calls = stats.get("volume", {}).get("tool_calls_total", 0)
    api_per_100 = 100 * b.get("api_errors_retries", 0) / tool_calls if tool_calls else 0
    recovery = .85 * sat(b.get("error_recovery_ratio") or 0, 1.0) + .15 * (1 - sat(api_per_100, 2.0))
    eff_axes = [
        ("Steering leverage", 50, lever, {"actions_per_prompt": app}),
        ("Recovery", 50, recovery, {"recovery_ratio": b.get("error_recovery_ratio") or 0,
         "api_retries": b.get("api_errors_retries", 0), "api_per_100_tools": round(api_per_100, 3)}),
    ]

    # ---- Pillar 4: Savvy ----
    # Provider-agnostic: works across Claude / OpenAI-Codex / Gemini / etc. "Model mix"
    # rewards using more than one model and routing work off your single default model
    # (match model to task) — no hard-coded model names or tiers.
    models = _models_for_scoring(stats, st.get("models", []))
    total_turns = sum(n for _, n in models)
    top_turns = max((n for _, n in models), default=0)
    offload_share = (1 - top_turns / total_turns) if total_turns else 0
    routing = score_linked_routing(b.get("linked_model_pairs", []), b.get("linked_model_routing_state", "unsupported"))
    model_mix = (.35 * sat(len(models), 3) + .35 * sat(offload_share, 0.30)
                 + .30 * routing["score"] if routing["score"] is not None
                 else .5 * sat(len(models), 3) + .5 * sat(offload_share, 0.30))
    cli_calls, mcp_calls = t.get("cli_calls", 0), t.get("mcp_calls", 0)
    cli_share = cli_calls / (cli_calls + mcp_calls) if (cli_calls + mcp_calls) else 0
    # toolsearch term drops out (renormalized) when unsupported, leaving CLI-share
    token_economy = wsum((.5, rate(t.get("toolsearch_calls", 0), 0.30), "toolsearch"),
                         (.5, sat(cli_share, 0.70), None))
    savvy_axes = [
        # Model mix needs a real per-turn model id; a source that masks it (Antigravity IDE)
        # drops this axis (renormalized) instead of scoring 0.
        ("Model mix", 50, model_mix, {"distinct_models": len(models), "offload_share": round(offload_share, 2),
         "routing": routing},
         "model"),
        ("Token economy", 50, token_economy, {"toolsearch": t.get("toolsearch_calls", 0), "cli_share": round(cli_share, 2)}),
    ]

    def build_pillar(name, weight, axes):
        # An axis may carry a 5th element: a required capability. If no present source can
        # record it, drop the axis and renormalize the remaining axis weights back to 100 so
        # the pillar isn't dragged down by an unmeasurable signal. Full-capability corpora
        # (Claude) keep every axis -> scale == 1.0 -> no-op.
        def _live(a):
            if a[2] is None:                               # wsum found no measurable term
                return False
            if len(a) < 5 or a[4] is None:
                return True
            # Skill fluency is observable via first-class Skill tool or read/inject paths.
            if a[0] == "Skill fluency" and a[4] == "skills":
                return "skills" in caps or "skill_reads" in caps
            return a[4] in caps
        live = [a for a in axes if _live(a)]
        wlive = sum(a[1] for a in live) or 1
        scale = 100.0 / wlive
        effective_weights = [round(a[1] * scale) for a in live]
        if effective_weights:
            effective_weights[-1] += 100 - sum(effective_weights)
        out = [{"name": a[0], "base_weight": a[1], "weight": effective_weight,
                # Binary64 guarantees 15 portable significant decimal digits. Canonicalize
                # only the exported diagnostic; keep scoring on the unrounded value below.
                "normalized_score": float(format(a[2], ".15g")),
                "score": round(effective_weight * a[2], 1),
                "signals": a[3]}
               for a, effective_weight in zip(live, effective_weights)]
        pillar = {"name": name, "weight": weight, "score": round(sum(x["score"] for x in out), 1), "axes": out}
        dropped = [a[0] for a in axes if a not in live]
        if dropped:
            pillar["not_applicable"] = dropped
        return pillar

    pillars = [build_pillar("Breadth", 30, breadth_axes), build_pillar("Craft", 35, craft_axes),
               build_pillar("Efficiency", 20, eff_axes), build_pillar("Savvy", 15, savvy_axes)]
    total = round(sum(p["weight"] / 100 * p["score"] for p in pillars))
    # ONE honest level vocabulary, driven by AQ (the score that actually separates level).
    # No flattery at the floor: a low score reads low. Also drives the profile archetype.
    tier = ("Elite" if total >= 88 else "Advanced" if total >= 75 else "Proficient" if total >= 60
            else "Adequate" if total >= 45 else "Apprentice" if total >= 25 else "Novice")
    return {
        "aq_0_100": total, "tier": tier, "pillars": pillars,
        "score_contract_id": SCORE_CONTRACT_ID,
        "mcp_vs_cli": {"cli_calls": cli_calls, "cli_distinct": t.get("clis_distinct", 0),
                       "mcp_calls": mcp_calls, "mcp_distinct": t.get("mcp_servers_distinct", 0),
                       "ratio": round(cli_calls / mcp_calls, 1) if mcp_calls else None},
        "tool_diversity": {"distinct": t.get("tool_diversity", 0), "entropy": t.get("tool_entropy_normalized", 0)},
    }
