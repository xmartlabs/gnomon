import json

from gnomon.scoring.aq import CONTEXT_INTELLIGENCE_TARGET, PLANNING_TARGET


REPO_URL = "https://github.com/Photobombastic/paxel-local"

# Plain-language explanation shown under each score bar — what the axis measures, in
# human terms, no jargon. (The gstack grounding lives in the disclaimer + README, not here.)
SCORE_NOTES = {
    "Execution": "How much you produce, and how efficiently — your tool output rate (Edit/Write "
                 "lines per active hour) and how hard you delegate to agents.",
    "Planning": "How much you think before you build — exploring before writing, reasoning "
                "depth, and laying out a plan first. (Prompt length was dropped — terse expert "
                "prompts shouldn't score below verbose ones.)",
    "Engineering": "How clean your work is — getting files right early, not re-editing the same "
                   "one over and over, low error rate, and checking your work.",
}

# One-line versions of the axis notes for the shareable poster image — the full SCORE_NOTES
# don't fit on a single line under a bar on the card.
SCORE_NOTES_SHORT = {
    "Execution": "Shipped output, at AI leverage",
    "Planning": "Think before you build",
    "Engineering": "Craft, with little rework",
}

# Hover tooltips for the AQ pillars and axes — what each one measures, in plain language,
# grounded in the actual compute_aq formulas (keep in sync if an axis changes). Every
# pillar/axis name emitted by compute_aq must have an entry (tested).
AQ_PILLAR_NOTES = {
    "Breadth": "How much machinery you operate — agents coordinated, skills in rotation, "
               "tools wired in, structured tracking.",
    "Craft": "How well you operate it — verified work, grounded edits, and learnings that persist.",
    "Efficiency": "Leverage per intervention — how far each prompt goes, and how well errors get absorbed.",
    "Savvy": "Smart choices — routing models to tasks and spending tokens lean.",
}
AQ_AXIS_NOTES = {
    "Orchestration": "Coordination over volume: distinct subagent types, median fan-out per "
                     "orchestrating session, and harness use — raw agent runs only count as a small floor.",
    "Skill fluency": "Range and volume of skills you invoke, plus whether process skills "
                     "(planning, debugging, brainstorming) are in the rotation.",
    "Tool command (MCP + CLI)": "External reach: distinct MCP servers, distinct CLIs, and "
                                "loading tool schemas on demand (ToolSearch).",
    "Discipline": "Structured work: task-tool usage plus planning skills in evidence.",
    "Verification": "Whether work gets checked: shell test runs and review-type skill invocations.",
    "Grounding": "Reading before writing — how much the agent explores relative to how much it edits.",
    "Context Intelligence": "Consulting external context before you write. We count the share of "
                            "eligible change sessions where a knowledge-MCP call or an explore-class "
                            "project/data/design MCP call (Jira, Notion, Figma, etc.) happens before "
                            "the first Edit/Write/MultiEdit/NotebookEdit. Eligible changes require a "
                            "write plus two distinct files or ten substantive tool calls. "
                            f"Score = min(1, coverage / {CONTEXT_INTELLIGENCE_TARGET:.2f}).",
    "Compounding": "Whether learnings persist: writes to memory/docs/skills, plus retro and planning habits.",
    "Steering leverage": "Agent actions per prompt, scored as a sweet spot (5–20): enough leash "
                         "to run, not so loose it drifts.",
    "Recovery": "Share of tool errors recovered from, minus API-retry noise.",
    "Model mix": "Using more than one model, with real work routed off your default — "
                 "match the model to the task.",
    "Token economy": "Token-lean habits: on-demand schema loading (ToolSearch) and a CLI-first "
                     "share of tool traffic.",
}


def _clamp(x):
    return max(0.0, min(1.0, x))


def _caps_of(stats):
    from gnomon.config import available_caps
    return available_caps((stats.get("corpus") or {}).get("sources", {}) or {})


def _apply_sub_caps(subs, caps):
    """Drop score_breakdown subs whose `_cap` no present source can emit, renormalize the kept
    subs' display weights to sum 1.0 (mirrors _axis_value so the breakdown matches the score),
    and strip the internal `_cap` key. Subs without a `_cap` are always kept."""
    kept = []
    for s in subs:
        cap = s.pop("_cap", None)
        if cap is None or cap in caps:
            kept.append(s)
    tot = sum(s["weight"] for s in kept) or 1.0
    for s in kept:
        s["weight"] = round(s["weight"] / tot, 4)
    return kept


def _axis_value(terms, caps):
    """terms: [(weight, pct, required_cap_or_None)]. Drop terms whose cap no present source can
    emit and renormalize the remaining weights to sum 1.0 (so a source isn't scored 0 on a signal
    its backend can't record), then return the 0..10 axis score. With full caps (default / pooled
    corpus) nothing drops and this equals the plain weighted sum."""
    live = [(w, v) for (w, v, cap) in terms
            if v is not None and (cap is None or cap in caps)]
    tot = sum(w for w, _ in live) or 1.0
    return round(10 * sum(w * v for w, v in live) / tot, 1)


def _d10(x):
    """First 10 chars of an ISO date, or '—' when missing (empty/timestampless corpus)."""
    return (x or "")[:10] or "—"


_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _mon_yr(iso):
    """'2025-06-08' -> 'Jun 2025' (human-readable timeframe for the share poster)."""
    iso = iso or ""
    if len(iso) >= 7 and iso[4] == "-":
        try:
            return f"{_MONTHS[int(iso[5:7])]} {iso[0:4]}"
        except (ValueError, IndexError):
            pass
    return (iso[:10] or "—")


def _js(obj):
    """json.dumps for embedding INSIDE a <script> tag. Python's json.dumps does not escape
    '<', '>', '&', so a prompt containing '</script>' (a real web-dev question) would close
    the script element early and break the whole page. Escape them to \\uXXXX (still valid
    JSON/JS), plus the U+2028/U+2029 line separators that break JS string literals."""
    return (json.dumps(obj)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace(" ", "\\u2028").replace(" ", "\\u2029"))


def _skill_uses(stats, needle):
    return sum(n for k, n in stats["stack"].get("top_skills", []) if needle in k.lower())


def _skill_uses_any(stats, needles):
    # Read skills_all (up to 200), not top_skills (15): a planning/quality skill
    # ranked below the 15th most-used skill would otherwise be invisible to the
    # metric and score 0 for someone who genuinely used it.
    skills = stats["stack"].get("skills_all") or stats["stack"].get("top_skills", [])
    return sum(n for k, n in skills
               if any(nd in str(k).lower() for nd in needles))


def _evidence(stats):
    """How much activity we actually have to judge habits on, 0..1. ~1.0 for any real
    corpus, near 0 for a thin one. Used to stop 'absence of a signal' from reading as
    'did it perfectly' in the inverse score terms — a barely-used corpus shouldn't grade
    as a flawless builder. (See _ev and the LOW_DATA flag in write_profile_html.)
    Saturates at ~2000 tool calls (≈15 real sessions) so the gating actually has a
    gradient across thin→mid corpora, not just sub-30-minute ones."""
    return _clamp(stats["volume"]["tool_calls_total"] / 2000)


def _ev(credit, ev):
    """Pull an ABSENCE-reward score term toward a neutral 0.5 when evidence (ev) is low,
    so 'no data' lands at the midpoint (admitted uncertainty) instead of a flattering 1.0.
    At ev=1.0 (any real corpus) this returns `credit` unchanged — a true no-op for real
    users; it only ever bites thin corpora. Apply ONLY to inverse terms (those that score
    high when a 'bad' metric is low/zero); presence terms already score 0 for 'didn't do it'."""
    return 0.5 * (1 - ev) + ev * credit


def _verdict(pct):
    """Map 0..1 pct to human-readable verdict."""
    if pct >= 0.9: return "excellent"
    if pct >= 0.7: return "good"
    if pct >= 0.5: return "adequate"
    if pct >= 0.3: return "weak"
    return "poor"

def _axis_verdict(value):
    """Map 0..10 axis score to verdict."""
    if value >= 8.0: return "excellent"
    if value >= 6.5: return "good"
    if value >= 5.0: return "adequate"
    if value >= 3.0: return "weak"
    return "poor"

def _fmt_val(value, unit):
    """Format a measured value with its unit for display."""
    if abs(value) >= 100:
        return f"{value:,.0f} {unit}"
    return f"{value:.2g} {unit}"

def _fmt_target(target, unit, direction):
    """Format target with direction prefix for lower-is-better metrics."""
    pfx = "≤ " if direction == "lower" else ""
    if abs(target) >= 100:
        return f"{pfx}{target:,.0f} {unit}"
    return f"{pfx}{target:.2g} {unit}"

def _sub_narrative(label, verdict, display_value, display_target, direction, score_pct):
    """Build one canonical sentence explaining a sub-metric."""
    if direction == "higher":
        if score_pct >= 90:
            rel = "well above target"
        elif score_pct >= 50:
            rel = "approaching target"
        else:
            rel = "below target"
    else:
        if score_pct >= 90:
            rel = "well within target"
        elif score_pct >= 50:
            rel = "near target threshold"
        else:
            rel = "above target threshold"
    return (f"{label} is {verdict} ({display_value}, target {display_target}"
            f" — {rel}, scoring {score_pct}%).")

def _enrich_sub(sub):
    """Add narrative fields to a score_breakdown sub dict, in-place."""
    p = sub["pct"]
    sub["verdict"] = _verdict(p)
    sub["score_pct"] = round(p * 100)
    sub["display_value"] = _fmt_val(sub["your_value"], sub["unit"])
    sub["display_target"] = _fmt_target(sub["target"], sub["unit"], sub["direction"])
    sub["narrative"] = _sub_narrative(
        sub["label"], sub["verdict"], sub["display_value"],
        sub["display_target"], sub["direction"], sub["score_pct"])
    return sub


def compute_scores(stats):
    # THREE graded axes (Execution/Planning/Engineering), grounded in gstack (module note
    # above) and then hardened by a gstack self-audit. Steering is NOT scored here — it's
    # described in steering_reading (it was inverted; see that function). Design rules:
    #   1. Each metric is owned by EXACTLY ONE place — no metric drives two graded axes, so
    #      the axes are genuinely independent (no hidden correlation).
    #   2. actions_per_prompt and questions_asked live ONLY in steering_reading (hands-on
    #      cadence — described, not scored); neither graded axis rewards them.
    #   3. iteration_depth_p90 lives ONLY in Engineering.
    #   4. Skill-detection terms are kept but de-weighted (a builder who plans in Notion
    #      and reviews on GitHub shouldn't score 0) — behavior carries the axes.
    # Weights sum to 1.0 per axis; every term is clamped 0..1 against a justified target;
    # `_ev` pulls the INVERSE terms toward neutral on a thin corpus.
    v, b, vel = stats["volume"], stats["behavior"], stats["velocity"]
    if v["total_sessions"] == 0 or v["tool_calls_total"] == 0:
        # No real activity → don't manufacture a flattering "Quality Guardian 9.0"
        return {"Execution": 0.0, "Planning": 0.0, "Engineering": 0.0}
    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)
    hours = max(vel["active_hours"], 0.1)
    ev = _evidence(stats)   # 0..1 confidence; gates the inverse terms so a thin corpus
                            # can't read as flawless (no-op at ev=1.0 for any real user).
    caps = _caps_of(stats)  # capability-aware: drop signals a source can't emit (vs scoring 0)

    # EXECUTION — shipped output at AI leverage. Two signals, no overlap with other axes:
    #   (a) TOOL OUTPUT RATE: tool_churn_edit_write (tool-authored lines) per active
    #       hour — source-agnostic and harder to game than git churn.
    #   (b) DELEGATION/parallelism.
    #   Removed: committed-code rate (git_churn/hours/400) — saturated at pct=1.0 due to
    #   inflated git_churn (generated/lockfile/merge commits); and ship fidelity
    #   (git_churn/tool_churn) — numerator inflated + denominator under-counted →
    #   metric was not truthful.
    _EXECUTION_OUTPUT_TARGET = 1000  # tool-authored lines per active hour
    out_rate   = vel["tool_churn_edit_write"] / hours
    out_pct    = _clamp(out_rate / _EXECUTION_OUTPUT_TARGET)
    deleg_pct  = _clamp((b["delegate_actions"] + b["background_tasks"]) / max(prompts * 0.3, 1))
    # delegation needs a source that CAN delegate; output rate is source-agnostic (no cap).
    execution = _axis_value([(0.60, out_pct, None), (0.40, deleg_pct, "delegate")], caps)

    # PLANNING — think before you build. Behavior-led.
    # DROPPED the avg_prompt_length term (was 0.25): it is experience-INVERTING — expertise
    # produces TERSER, more precise prompts, so the term paid for verbosity. It's the main reason a
    # 4-month vibe-coder maxed Planning over a 30-year engineer (an expert-elicitation validity
    # review caught this). Weight redistributed to the construct-relevant terms.
    # Plan ceremony = fraction of sessions with a planning signal (plan-mode/todo tool OR
    # a planning Skill), NOT a raw plan-tool count. Counting distinct sessions stops
    # TodoWrite (fires many times/session) from saturating the term; target 0.4 = plan in
    # ~40% of sessions. See accumulator.plan_sessions.
    plan_ceremony = _clamp((b.get("planning_skill_sessions", b.get("plan_sessions", 0)) / sess) / 0.4)
    eligible = b.get("eligible_change_sessions", 0) or 0
    ordered_plan = (None if b.get("ordered_facts_state") != "measured" or not eligible
                    else _clamp((b.get("planned_eligible_sessions", 0) / eligible)
                                / PLANNING_TARGET))
    # reasoning depth needs a source that emits thinking blocks (Antigravity CLI doesn't);
    # explore-ratio is behavioral/source-agnostic; plan ceremony is per-session.
    planning = _axis_value([
        (0.30, _clamp(b["planning_ratio_explore_to_doing"] / 0.65), None),
        (0.30, _clamp((v["thinking_blocks"] / sess) / 12.0), "thinking"),
        (0.25, plan_ceremony, "skills"),
        (0.15, ordered_plan, None),
    ], caps)

    # STEERING IS NOT SCORED — it's DESCRIBED (see steering_reading). Hands-on cadence
    # (actions/prompt + how often the agent checks in) is real and measurable, but it has no
    # good/bad end: a deliberate hands-off operator who delegates and gets clean autonomous output
    # back is steering by a mechanism we CANNOT read from transcripts (it needs delegation→
    # survived-to-commit attribution). Grading it INVERTED the axis — `(15 - actions_per_prompt)`
    # meant a more autonomous engineer scored LOWER (the Chris Sells case). You don't fix a
    # backwards gauge with a disclaimer underneath it; you stop grading it and state the fact.
    # (An earlier "autonomous command" term that tried to credit delegation×low-error was also
    # reverted — it collapsed to error-rate-in-a-costume; see git history.)

    # ENGINEERING — craft / low rework. The old churn_back term (deletion ratio) was CUT:
    # it scored a clean refactor as "thrash" and gave a perfect score to anyone who never
    # committed. Replaced by iteration_depth_mean ("did you get the file right early"), the
    # honest rework signal. p90 + file-hammering stay here (their only home). Ceremony de-weighted.
    # "code-review" (not bare "review") so this doesn't greedily match Planning's
    # plan-eng-review / plan-design-review / ceo-review ceremonies (which mark plan_sessions).
    eng_skills = _skill_uses_any(stats, ("code-review", "test", "tdd", "qa", "investigate",
                                         "retro", "learn", "cso", "karpathy", "debug")) \
        + b.get("shell_test_runs", 0)   # CLI tests (pytest/go test/…) count as quality work too
    engineering = 10 * (
        0.30 * _ev(1 - _clamp(((b.get("iteration_depth_mean") or 0) - 2) / 8), ev)  # low rework: got files right early
        + 0.25 * _ev(1 - _clamp(((b.get("iteration_depth_p90") or 0) - 3) / 9), ev)  # clean iteration: low typical depth
        + 0.20 * _ev(1 - _clamp(((b.get("files_hammered_over_15x") or 0) / sess) / 0.25), ev)  # focused: few hammered files
        + 0.15 * _clamp((eng_skills / sess) / 3.0)                       # quality ceremonies: review/qa/investigate
        + 0.10 * _ev(1 - _clamp((b.get("error_rate_per_100_tools") or 0) / 10), ev))  # low error rate: root-cause discipline

    return {"Execution": round(execution, 1), "Planning": round(planning, 1),
            "Engineering": round(engineering, 1)}


def score_breakdown(stats):
    """Per-axis sub-component breakdown for the dashboard UI. Returns the same three
    axes as compute_scores with per-sub pct/value/target fields so the UI can show WHY
    a score is high or low.  The formula constants are intentionally kept in sync with
    compute_scores via the equality assertion in tests; any drift will fail the test.
    NOTE: keep constants aligned with compute_scores (above) — any formula change must
    be made in BOTH places; the test_value_equals_compute_scores test enforces this."""
    v, b, vel = stats.get("volume", {}), stats.get("behavior", {}), stats.get("velocity", {})
    # Guard: no real activity → well-formed zeros (mirrors compute_scores early-return)
    if v.get("total_sessions", 0) == 0 or v.get("tool_calls_total", 0) == 0:
        def _zero_sub(label, target, unit, weight, direction):
            return {"label": label, "your_value": 0.0, "target": target, "unit": unit,
                    "weight": weight, "pct": 0.5, "direction": direction, "is_drag": False,
                    "verdict": "adequate", "score_pct": 50,
                    "display_value": _fmt_val(0.0, unit),
                    "display_target": _fmt_target(target, unit, direction),
                    "narrative": f"No activity recorded for {label}."}
        def _zero_axis(gloss, subs_spec):
            subs = [_zero_sub(*sp) for sp in subs_spec]
            subs[0]["is_drag"] = True   # deterministic sentinel for the no-activity case;
                                        # NOT a meaningful weakest-sub signal (all values are 0)
            return {"value": 0.0, "gloss": gloss, "drag_note": "No activity recorded.", "subs": subs,
                    "axis_verdict": "poor", "score_out_of_10": "0.0 / 10",
                    "drag_narrative": "No activity recorded.",
                    "axis_narrative": "No activity recorded."}
        return {
            "execution": _zero_axis("How much you ship, at AI leverage", [
                ("Tool output rate",          1000, "tool-authored lines/hr", 0.60, "higher"),
                ("Delegation & parallelism",  0.30, "agent-runs/prompt",  0.40, "higher"),
            ]),
            "planning": _zero_axis("Think before you build", [
                ("Explore-before-build", 0.65, "explore/doing ratio", 0.30, "higher"),
                ("Reasoning depth",     12.0, "thinking blocks/session", 0.30, "higher"),
                ("Planning skill practice", 0.4, "planning sessions/session", 0.25, "higher"),
                ("Ordered planning readiness", PLANNING_TARGET,
                 "eligible-session coverage", 0.15, "higher"),
            ]),
            "engineering": _zero_axis("Craft and low rework", [
                ("Low rework",       2.0, "mean file-edit depth", 0.30, "lower"),
                ("Clean iteration",  3.0, "p90 file-edit depth",  0.25, "lower"),
                ("Focus",           0.25, "hammered-files/session", 0.20, "lower"),
                ("Quality ceremony", 3.0, "quality-skills/session", 0.15, "higher"),
                ("Low errors",      10.0, "errors/100 tools", 0.10, "lower"),
            ]),
        }

    sess = max(v["total_sessions"], 1)
    prompts = max(v["total_prompts"], 1)
    hours = max(vel.get("active_hours", 0.1), 0.1)
    ev = _evidence(stats)
    caps = _caps_of(stats)

    # --- EXECUTION ---
    _EXECUTION_OUTPUT_TARGET = 1000  # tool-authored lines per active hour
    out_rate       = vel.get("tool_churn_edit_write", 0) / hours
    out_pct        = _clamp(out_rate / _EXECUTION_OUTPUT_TARGET)
    deleg_raw      = (b.get("delegate_actions", 0) + b.get("background_tasks", 0)) / max(prompts * 0.3, 1)
    deleg_pct      = _clamp(deleg_raw)
    execution_val  = _axis_value([(0.60, out_pct, None), (0.40, deleg_pct, "delegate")], caps)
    exec_subs = [
        {"label": "Tool output rate", "your_value": out_rate,
         "target": _EXECUTION_OUTPUT_TARGET, "unit": "tool-authored lines/hr", "weight": 0.60,
         "pct": out_pct, "direction": "higher", "is_drag": False, "_cap": None},
        # your_value is the raw measured agent-runs/prompt (denominator: actual prompts).
        # pct matches compute_scores' clamp (denominator: prompts*0.3) and equals
        # your_value/target in the normal regime (prompts ≥ 4).  For tiny corpora
        # (prompts < 4) the score's floor (max(prompts*0.3, 1)) causes pct to diverge
        # from your_value/target — DO NOT change pct to derive from your_value, as that
        # would break the value==compute_scores invariant for small-corpus inputs.
        # The UI must fill bars from pct, not recompute from your_value/target.
        {"label": "Delegation & parallelism",
         "your_value": (b.get("delegate_actions", 0) + b.get("background_tasks", 0)) / max(prompts, 1),
         "target": 0.30, "unit": "agent-runs/prompt", "weight": 0.40, "pct": deleg_pct,
         "direction": "higher", "is_drag": False, "_cap": "delegate"},
    ]
    exec_subs = [_enrich_sub(s) for s in _apply_sub_caps(exec_subs, caps)]

    # --- PLANNING ---
    explore_pct       = _clamp(b.get("planning_ratio_explore_to_doing", 0) / 0.65)
    thinking_raw      = v.get("thinking_blocks", 0) / sess
    thinking_pct      = _clamp(thinking_raw / 12.0)
    # Plan ceremony = fraction of sessions with a planning signal (see compute_scores);
    # per-session, so TodoWrite volume can't saturate it. Target 0.4.
    plan_sess_raw     = b.get("planning_skill_sessions", b.get("plan_sessions", 0)) / sess
    plan_ceremony_pct = _clamp(plan_sess_raw / 0.4)
    eligible = b.get("eligible_change_sessions", 0) or 0
    ordered_raw = b.get("planned_eligible_sessions", 0) / eligible if eligible else 0
    ordered_pct = (None if b.get("ordered_facts_state") != "measured" or not eligible
                   else _clamp(ordered_raw / PLANNING_TARGET))
    planning_val      = _axis_value([(0.30, explore_pct, None), (0.30, thinking_pct, "thinking"),
                                     (0.25, plan_ceremony_pct, "skills"),
                                     (0.15, ordered_pct, None)], caps)
    plan_subs = [
        {"label": "Explore-before-build",
         "your_value": b.get("planning_ratio_explore_to_doing", 0),
         "target": 0.65, "unit": "explore/doing ratio", "weight": 0.30, "pct": explore_pct,
         "direction": "higher", "is_drag": False, "_cap": None},
        {"label": "Reasoning depth", "your_value": thinking_raw,
         "target": 12.0, "unit": "thinking blocks/session", "weight": 0.30, "pct": thinking_pct,
         "direction": "higher", "is_drag": False, "_cap": "thinking"},
        {"label": "Planning skill practice", "your_value": plan_sess_raw,
         "target": 0.4, "unit": "planning sessions/session", "weight": 0.25, "pct": plan_ceremony_pct,
         "direction": "higher", "is_drag": False, "_cap": "skills"},
    ]
    if ordered_pct is not None:
        plan_subs.append({"label": "Ordered planning readiness", "your_value": ordered_raw,
                          "target": PLANNING_TARGET, "unit": "eligible-session coverage", "weight": 0.15,
                          "pct": ordered_pct, "direction": "higher", "is_drag": False, "_cap": None})
    plan_subs = [_enrich_sub(s) for s in _apply_sub_caps(plan_subs, caps)]

    # --- ENGINEERING ---
    eng_skills = _skill_uses_any(stats, ("code-review", "test", "tdd", "qa", "investigate",
                                         "retro", "learn", "cso", "karpathy", "debug")) \
        + b.get("shell_test_runs", 0)
    rework_pct   = _ev(1 - _clamp(((b.get("iteration_depth_mean") or 0) - 2) / 8), ev)
    iter_pct     = _ev(1 - _clamp(((b.get("iteration_depth_p90") or 0) - 3) / 9), ev)
    focus_pct    = _ev(1 - _clamp(((b.get("files_hammered_over_15x") or 0) / sess) / 0.25), ev)
    qual_raw     = eng_skills / sess
    qual_pct     = _clamp(qual_raw / 3.0)
    err_pct      = _ev(1 - _clamp((b.get("error_rate_per_100_tools") or 0) / 10), ev)
    engineering_val = round(10 * (0.30 * rework_pct + 0.25 * iter_pct + 0.20 * focus_pct
                                  + 0.15 * qual_pct + 0.10 * err_pct), 1)
    eng_subs = [
        {"label": "Low rework", "your_value": b.get("iteration_depth_mean") or 0,
         "target": 2.0, "unit": "mean file-edit depth", "weight": 0.30, "pct": rework_pct,
         "direction": "lower", "is_drag": False},
        {"label": "Clean iteration", "your_value": b.get("iteration_depth_p90") or 0,
         "target": 3.0, "unit": "p90 file-edit depth", "weight": 0.25, "pct": iter_pct,
         "direction": "lower", "is_drag": False},
        {"label": "Focus", "your_value": (b.get("files_hammered_over_15x") or 0) / sess,
         "target": 0.25, "unit": "hammered-files/session", "weight": 0.20, "pct": focus_pct,
         "direction": "lower", "is_drag": False},
        {"label": "Quality ceremony", "your_value": qual_raw,
         "target": 3.0, "unit": "quality-skills/session", "weight": 0.15, "pct": qual_pct,
         "direction": "higher", "is_drag": False},
        {"label": "Low errors", "your_value": b.get("error_rate_per_100_tools") or 0,
         "target": 10.0, "unit": "errors/100 tools", "weight": 0.10, "pct": err_pct,
         "direction": "lower", "is_drag": False},
    ]
    eng_subs = [_enrich_sub(s) for s in eng_subs]

    def _mark_drag(axis_name, subs, gloss):
        """Flag the sub with the smallest weight*pct contribution; build a drag_note."""
        drag_idx = min(range(len(subs)), key=lambda i: subs[i]["weight"] * subs[i]["pct"])
        for i, s in enumerate(subs):
            s["is_drag"] = (i == drag_idx)
        d = subs[drag_idx]
        if d["direction"] == "higher":
            note = (f"{d['label']} is dragging this down — "
                    f"{d['your_value']:.2g} {d['unit']}, target ~{d['target']:.2g}.")
        else:
            note = (f"{d['label']} is dragging this down — "
                    f"{d['your_value']:.2g} {d['unit']} (target ≤{d['target']:.2g}).")
        _axis_values = {
            "execution": execution_val,
            "planning": planning_val,
            "engineering": engineering_val,
        }
        drag_sub = subs[drag_idx]
        best_sub = max(subs, key=lambda s: s["pct"])
        av = _axis_verdict(_axis_values[axis_name])
        dir_hint = "higher is better" if drag_sub["direction"] == "higher" else "lower is better"
        drag_narr = (
            f"{drag_sub['label']} is the weakest contributor, scoring {drag_sub['score_pct']}%. "
            f"Your value: {drag_sub['display_value']} (target: {drag_sub['display_target']}, {dir_hint}).")
        axis_name_display = axis_name.capitalize()
        axis_narr = (
            f"{axis_name_display} scores {_axis_values[axis_name]}/10 ({av}). "
            f"Strongest: {best_sub['label']} ({best_sub['score_pct']}%); "
            f"weakest: {drag_sub['label']} ({drag_sub['score_pct']}%).")
        return {"value": _axis_values[axis_name],
                "gloss": gloss, "drag_note": note, "subs": subs,
                "axis_verdict": av,
                "score_out_of_10": f"{_axis_values[axis_name]} / 10",
                "drag_narrative": drag_narr,
                "axis_narrative": axis_narr}

    return {
        "execution": _mark_drag("execution", exec_subs, "How much you ship, at AI leverage"),
        "planning":  _mark_drag("planning",  plan_subs, "Think before you build"),
        "engineering": _mark_drag("engineering", eng_subs, "Craft and low rework"),
    }
