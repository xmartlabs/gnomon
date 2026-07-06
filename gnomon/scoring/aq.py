import re

from gnomon.analysis.metrics import _review_skill_uses
from gnomon.config import available_caps


def compute_aq(stats):
    """Agentic Quotient v2 — 'how well you OPERATE AGENTS' (distinct from the gstack
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

    def wsum(*terms):
        """Weighted mean of (coef, value, required_cap) terms, dropping terms whose cap is
        unavailable and renormalizing the remaining coefficients to sum 1. Returns None when
        NO term is measurable (the whole axis is unsupported -> build_pillar drops it)."""
        live = [(c, v) for c, v, cap in terms if cap is None or cap in caps]
        tot = sum(c for c, _ in live)
        return sum(c * v for c, v in live) / tot if tot else None

    skills = st.get("skills_all") or st.get("top_skills", [])

    def skill_uses(needles):
        return sum(n for k, n in skills if any(nd in str(k).lower() for nd in needles))

    def has_skill(needles):
        return any(any(nd in str(k).lower() for nd in needles) for k, _ in skills)

    # ---- Pillar 1: Breadth (unchanged axes) ----
    agent_runs = t.get("agent_calls", 0)
    fanout = b.get("fanout_median") or 0  # None (unmeasured) treated as 0 for AQ
    o_harn = 1.0 if (any(re.search(r"harness|trisel", str(k), re.I)
                         for k, _ in st.get("subagent_types", [])) or has_skill(["trisel"])) else 0.6
    # Coordination over volume: fan-out (agents coordinated per orchestrating session)
    # is the orchestration tell — a serial grinder firing N agents one-per-session reads
    # fanout=1, a real orchestrator reads its team size. agent_runs stays only as a small
    # volume floor; the old (background + scheduled) COUNT term was cut (it double-counted
    # volume and rewarded firing-and-forgetting, not coordinating).
    orchestration = (.30 * sat(st.get("subagent_types_distinct", 0), 8) + .30 * sat(fanout, 5)
                     + .20 * o_harn + .20 * sat(agent_runs, 400))
    skill_fluency = (.40 * sat(st.get("skills_distinct", 0), 40) + .30 * sat(st.get("skills_total", 0), 1500)
                     + .30 * (1.0 if has_skill(["subagent-driven", "brainstorm", "writing-plans",
                                                "cerberus", "systematic-debugging"]) else 0.6))
    # toolsearch term drops out (renormalized) when no present source can record it
    tool_command = wsum((.40, sat(t.get("mcp_servers_distinct", 0), 15), None),
                        (.40, sat(t.get("clis_distinct", 0), 40), None),
                        (.20, sat(t.get("toolsearch_calls", 0), 300), "toolsearch"))
    # plan-skill term needs the Skill capability; falls back to task-tool usage alone
    discipline = wsum((.60, sat(t.get("task_tool_calls", 0), 1500), "tasktool"),
                      (.40, (1.0 if (has_skill(["writing-plans", "autoplan", "plan"])
                                     or b.get("plan_sessions", 0) > 0) else 0.6), "skills"))
    breadth_axes = [
        # Orchestration needs subagent delegation; a source that can't fan out by design
        # (Gemini/Pi/opencode) drops this axis (renormalized) instead of scoring ~0.
        ("Orchestration", 33, orchestration, {"agent_runs": agent_runs,
         "subagent_types": st.get("subagent_types_distinct", 0), "fanout_median": fanout},
         "delegate"),
        ("Skill fluency", 22, skill_fluency, {"skills_distinct": st.get("skills_distinct", 0),
         "skills_total": st.get("skills_total", 0)}, "skills"),
        ("Tool command (MCP + CLI)", 28, tool_command, {"mcp_servers": t.get("mcp_servers_distinct", 0),
         "clis": t.get("clis_distinct", 0), "toolsearch": t.get("toolsearch_calls", 0)}),
        ("Discipline", 17, discipline, {"task_tool_calls": t.get("task_tool_calls", 0)}),
    ]

    # ---- Pillar 2: Craft ----
    review_n = _review_skill_uses(skills)
    # review-skill term needs Skill capability; falls back to shell test runs alone
    verification = wsum((.5, sat(b.get("shell_test_runs", 0), 150), None),
                        (.5, sat(review_n, 100), "skills"))
    grounding = sat(b.get("planning_ratio_explore_to_doing", 0), 1.0)
    compounding = wsum((.6, sat(st.get("compounding_writes", 0), 30), None),
                       (.4, (1.0 if has_skill(["retro", "writing-plans", "brainstorm"]) else 0.6), "skills"))
    craft_axes = [
        ("Verification", 40, verification, {"test_runs": b.get("shell_test_runs", 0), "review_skills": review_n}),
        ("Grounding", 30, grounding, {"planning_ratio": b.get("planning_ratio_explore_to_doing", 0)}),
        ("Compounding", 30, compounding, {"compounding_writes": st.get("compounding_writes", 0)}),
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
    models = st.get("models", [])
    total_turns = sum(n for _, n in models)
    top_turns = max((n for _, n in models), default=0)
    offload_share = (1 - top_turns / total_turns) if total_turns else 0
    model_mix = .5 * sat(len(models), 3) + .5 * sat(offload_share, 0.30)
    cli_calls, mcp_calls = t.get("cli_calls", 0), t.get("mcp_calls", 0)
    cli_share = cli_calls / (cli_calls + mcp_calls) if (cli_calls + mcp_calls) else 0
    # toolsearch term drops out (renormalized) when unsupported, leaving CLI-share
    token_economy = wsum((.5, sat(t.get("toolsearch_calls", 0), 300), "toolsearch"),
                         (.5, sat(cli_share, 0.70), None))
    savvy_axes = [
        # Model mix needs a real per-turn model id; a source that masks it (Antigravity IDE)
        # drops this axis (renormalized) instead of scoring 0.
        ("Model mix", 50, model_mix, {"distinct_models": len(models), "offload_share": round(offload_share, 2)},
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
            return len(a) < 5 or a[4] is None or a[4] in caps   # required cap available
        live = [a for a in axes if _live(a)]
        wlive = sum(a[1] for a in live) or 1
        scale = 100.0 / wlive
        out = [{"name": a[0], "weight": round(a[1] * scale), "score": round(a[1] * scale * a[2], 1),
                "signals": a[3]} for a in live]
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
        "mcp_vs_cli": {"cli_calls": cli_calls, "cli_distinct": t.get("clis_distinct", 0),
                       "mcp_calls": mcp_calls, "mcp_distinct": t.get("mcp_servers_distinct", 0),
                       "ratio": round(cli_calls / mcp_calls, 1) if mcp_calls else None},
        "tool_diversity": {"distinct": t.get("tool_diversity", 0), "entropy": t.get("tool_entropy_normalized", 0)},
    }
