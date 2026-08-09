import math
from collections import Counter

from gnomon.taxonomy import classify_tool
from gnomon.analysis.metrics import (
    _error_rate_per_100, _error_recovery_ratio, _iteration_depth_stats,
    _fanout_median, _active_hours_and_longest_run,
)


from gnomon.scoring.versioning import SCORING_INPUTS_VERSION
from gnomon.scoring.versioning import AQ_VERSION, GSTACK_VERSION, SCORE_CONTRACT_ID


def _adjusted_doing(raw_doing, planning_dispatch_calls):
    """The `doing` denominator of planning_ratio_explore_to_doing, with planning dispatches
    removed — but never emptied.

    Planning dispatches classify `execute`/`delegate`, so leaving them in makes thinking
    first lower the very term that rewards it. Taking them out can, for a corpus whose only
    execute/delegate activity IS planning, drive the denominator to 0 and publish a ratio of
    0 — the worst value for a term that rewards exploring, handed to someone who did nothing
    but explore and plan. Inverting a score is worse than not adjusting it, so we fall back
    to the raw denominator: a corpus with no build has nothing to compare its exploring
    against. Shared by the corpus, per-source and monthly paths so all three agree.
    """
    adjusted = raw_doing - planning_dispatch_calls
    return adjusted if adjusted > 0 else raw_doing


def _pairs(seq):
    return [[str(k), int(n)] for k, n in (seq or [])]


def build_scoring_inputs(stats):
    v = stats.get("volume") or {}
    vel = stats.get("velocity") or {}
    b = stats.get("behavior") or {}
    st = stats.get("stack") or {}
    t = stats.get("tools") or {}
    srcs = sorted((stats.get("corpus", {}).get("sources") or {}).keys())
    source = srcs[0] if len(srcs) == 1 else (",".join(srcs) if srcs else None)
    result = {
        "scoring_inputs_version": SCORING_INPUTS_VERSION,
        "aq_version": AQ_VERSION,
        "gstack_version": GSTACK_VERSION,
        "score_contract_id": SCORE_CONTRACT_ID,
        "source": source,
        "volume": {
            "total_sessions": v.get("total_sessions", 0),
            "total_prompts": v.get("total_prompts", 0),
            # v12 — the DENOMINATOR `behavior.actions_per_prompt` is built on: typed-text
            # turns plus bare slash commands. Falls back to `total_prompts`, NOT to 0: a
            # pre-v12 block carries no such key and its own ratio was built by dividing by
            # `total_prompts`, so that is the denominator which reconstructs it. A 0 default
            # would make the shipped ratio unrecomputable from the block, and inventing a
            # wider number would misstate a payload that never measured one.
            "total_instructions": v.get("total_instructions",
                                        v.get("total_prompts", 0)),
            "tool_calls_total": v.get("tool_calls_total", 0),
            # v12 diagnostic sibling of tool_calls_total: how much of it was subagent work.
            # Nothing scores it. `.get(..., 0)` is load-bearing for REPLAY — a payload
            # captured before v12 carries no such key, and it must project as a plain 0
            # rather than raising or being invented.
            "sidechain_tool_calls": v.get("sidechain_tool_calls", 0),
            "thinking_blocks": v.get("thinking_blocks", 0),
        },
        "velocity": {
            "active_hours": vel.get("active_hours", 0),
            "tool_churn_edit_write": vel.get("tool_churn_edit_write", 0),
            "shell_authored_lines_est": vel.get("shell_authored_lines_est", 0),
        },
        "behavior": {
            "planning_ratio_explore_to_doing": b.get("planning_ratio_explore_to_doing", 0),
            "actions_per_prompt": b.get("actions_per_prompt", 0),
            "questions_asked": b.get("questions_asked", 0),
            "error_recovery_ratio": b.get("error_recovery_ratio"),
            "error_rate_per_100_tools": b.get("error_rate_per_100_tools"),
            "api_errors_retries": b.get("api_errors_retries", 0),
            "fanout_median": b.get("fanout_median"),
            "max_session_fanout": b.get("max_session_fanout"),
            "parallel_dispatch_turns": b.get("parallel_dispatch_turns", 0),
            "delegating_sessions": b.get("delegating_sessions", 0),
            "parallel_session_share": b.get("parallel_session_share"),
            "shell_test_runs": b.get("shell_test_runs", 0),
            "plan_sessions": b.get("plan_sessions", 0),
            "planning_skill_sessions": b.get("planning_skill_sessions", 0),
            "eligible_change_sessions": b.get("eligible_change_sessions", 0),
            # v18 — Verification coverage numerator. NO default here, deliberately: a
            # payload captured before v18 (or a legacy row missing this key for any other
            # reason) has genuinely NEVER MEASURED coverage, and that ABSENCE must stay
            # distinguishable from a real MEASURED zero. `.get(..., 0)` used to coerce
            # both to 0, which is indistinguishable from an idle-but-eligible corpus once
            # it reaches aq.py — aq.py's coverage term fabricated a 0.0 for a legacy row
            # that had `ordered_facts_state == "measured"` and `eligible_change_sessions >
            # 0` (both pre-v18 fields), corrupting the score instead of staying N/A
            # (renormalized onto review-skills). `b.get(...)` with NO default projects
            # absence as None, and aq.py's `_test_covered_measured` flag reads that None
            # to decide N/A vs a genuine measured zero -- same fail-closed rule Context
            # Intelligence applies elsewhere in this module.
            "test_covered_change_sessions": b.get("test_covered_change_sessions"),
            "planned_eligible_sessions": b.get("planned_eligible_sessions", 0),
            "evidence_eligible_sessions": b.get("evidence_eligible_sessions", 0),
            "ordered_facts_state": b.get("ordered_facts_state", "unmeasured"),
            # v12 — whether `actions_per_prompt`'s top-level numerator is trustworthy here.
            # Defaults to "measured", NOT "unmeasured", and the asymmetry with
            # `ordered_facts_state` above is deliberate: this is a claim about the ADAPTER's
            # ability to label sidechain events, so a pre-v12 payload (which carries no such
            # key) predates the claim rather than failing it. Defaulting to "unmeasured" would
            # silently drop the Steering-leverage term for every historical row on replay,
            # which is a much larger and less honest change than admitting one real gap.
            "sidechain_label_state": b.get("sidechain_label_state", "measured"),
            "linked_model_pairs": [{
                key: pair.get(key) for key in (
                    "provider", "lead_model", "child_model", "completed",
                    "lifecycle_known", "substantive_calls", "writes")
                if key in pair
            } for pair in (b.get("linked_model_pairs", []) or [])],
            "linked_model_routing_state": b.get("linked_model_routing_state", "unsupported"),
            "delegate_actions": b.get("delegate_actions", 0),
            # NOTE: planning_dispatch_actions is deliberately NOT forwarded here. This payload
            # is the wire contract with the mirdash dashboard (pinned by an exact key-set
            # test), the ratio already travels as a single number, and nothing on the other
            # side reads the subtrahend. It stays on the internal stats for the report and
            # for auditing.
            "background_tasks": b.get("background_tasks", 0),
            "iteration_depth_mean": b.get("iteration_depth_mean"),
            "iteration_depth_p90": b.get("iteration_depth_p90"),
            "iteration_depth_max": b.get("iteration_depth_max"),
            "files_hammered_over_15x": b.get("files_hammered_over_15x", 0),
            "no_tool_activity": b.get("no_tool_activity", False),
            "orchestratable_sessions": b.get("orchestratable_sessions", 0),
            "delegated_orchestratable_sessions": b.get("delegated_orchestratable_sessions", 0),
        },
        "stack": {
            "skills_distinct": st.get("skills_distinct", 0),
            "skills_total": st.get("skills_total", 0),
            "compounding_writes": st.get("compounding_writes", 0),
            "subagent_types_distinct": st.get("subagent_types_distinct", 0),
            "max_session_subagent_types": st.get("max_session_subagent_types", 0),
            "subagent_types": _pairs(st.get("subagent_types")),
            "top_skills": _pairs(st.get("top_skills")),
            "skills_all": _pairs(st.get("skills_all")),
            "models": _pairs(st.get("models")),
        },
        "tools": {
            "agent_calls": t.get("agent_calls", 0),
            "mcp_servers_distinct": t.get("mcp_servers_distinct", 0),
            "clis_distinct": t.get("clis_distinct", 0),
            "toolsearch_calls": t.get("toolsearch_calls", 0),
            "task_tool_calls": t.get("task_tool_calls", 0),
            "cli_calls": t.get("cli_calls", 0),
            "mcp_calls": t.get("mcp_calls", 0),
            "tool_diversity": t.get("tool_diversity", 0),
            "tool_entropy_normalized": t.get("tool_entropy_normalized", 0),
            "mcp_knowledge_calls": t.get("mcp_knowledge_calls", 0),
            "mcp_knowledge_servers": t.get("mcp_knowledge_servers", 0),
            # server NAMES (not just count) so the aggregate can union distinct servers
            # across sources instead of max()-ing counts (which undercounts the union)
            "mcp_knowledge_server_names": list(t.get("mcp_knowledge_server_names", []) or []),
            "mcp_grounded_sessions": t.get("mcp_grounded_sessions", 0),
            "mcp_write_sessions": t.get("mcp_write_sessions", 0),
            "mcp_subcategory_breakdown": t.get("mcp_subcategory_breakdown", {}),
            "top_tools": _pairs(t.get("top_tools")),
        },
        "token_usage": stats.get("token_usage") or {"by_model": []},
    }
    if any(field in b for field in (
            "planning_skill_eligible_sessions",
            "planning_skill_unmeasured_sessions",
            "planning_skill_session_scope_state",
            "planning_skill_session_share",
            "planning_skill_session_coverage")):
        result["behavior"].update({
            "planning_skill_eligible_sessions": b.get(
                "planning_skill_eligible_sessions"),
            "planning_skill_unmeasured_sessions": b.get(
                "planning_skill_unmeasured_sessions"),
            "planning_skill_session_scope_state": b.get(
                "planning_skill_session_scope_state"),
            "planning_skill_session_share": b.get(
                "planning_skill_session_share"),
            "planning_skill_session_coverage": b.get(
                "planning_skill_session_coverage"),
        })
    return result


def build_monthly_scoring_stats(
    months, sources_present, month_prompts, month_tools_count, month_churn,
    month_models, month_sessions, month_assistant_turns, month_thinking_blocks,
    month_bash_authored_lines, month_tool_errors, month_recovered_errors,
    month_edits_per_file, month_questions, month_delegate, month_background,
    month_scheduled, month_fanouts, month_tool_counter, month_session_ts,
    month_skill_counter, month_subagent_counter, month_mcp_server_counter,
    month_cli_counter, month_compounding, month_shell_test_runs, month_api_errors,
    cwds, gap_cap_s, burst_gap_s,
    no_tool_activity, all_sources_no_agent, month_plan_sessions=None,
    month_planning_skill_sessions=None,
    month_planning_skill_eligible_sessions=None,
    month_planning_skill_unmeasured_sessions=None,
    month_session_subagent_types=None,
    month_mcp_subcategory_counter=None, month_mcp_subcategory_servers=None,
    month_grounded_sessions=None, month_write_sessions=None,
    month_session_ordered_tools=None, month_planning_dispatch_calls=None,
    month_sidechain_tools=None, month_command_only=None,
):
    out = []
    for mk in months:
        m_tool_total = month_tools_count.get(mk, 0)
        m_sidechain_tools = (month_sidechain_tools or {}).get(mk, 0)
        m_command_only = (month_command_only or {}).get(mk, 0)
        m_no_tool = (m_tool_total == 0)
        active_hours_m, _ = _active_hours_and_longest_run(
            month_session_ts.get(mk, {}), gap_cap_s, burst_gap_s)
        ids = _iteration_depth_stats(month_edits_per_file.get(mk, []), m_no_tool)
        err_rate = _error_rate_per_100(month_tool_errors.get(mk, 0), m_tool_total, m_no_tool)
        recov = _error_recovery_ratio(
            month_recovered_errors.get(mk, 0), month_tool_errors.get(mk, 0), m_no_tool)
        fanouts = [n for n in month_fanouts.get(mk, {}).values() if n > 0]
        fan_med = _fanout_median(fanouts, m_no_tool, all_sources_no_agent)

        m_prompts = month_prompts.get(mk, 0)
        tcounter = month_tool_counter.get(mk, Counter())
        skill_c = month_skill_counter.get(mk, Counter())
        sub_c = month_subagent_counter.get(mk, Counter())
        mcp_c = month_mcp_server_counter.get(mk, Counter())
        cli_c = month_cli_counter.get(mk, Counter())
        delegate_m = month_delegate.get(mk, 0)
        background_m = month_background.get(mk, 0)
        scheduled_m = month_scheduled.get(mk, 0)

        diversity = len(tcounter)
        tot = sum(tcounter.values()) or 1
        entropy = -sum((c / tot) * math.log2(c / tot) for c in tcounter.values())
        norm_entropy = entropy / math.log2(diversity) if diversity > 1 else 0
        mcp_calls = sum(mcp_c.values())
        m_subcat_c = (month_mcp_subcategory_counter or {}).get(mk, {})
        m_subcat_s = (month_mcp_subcategory_servers or {}).get(mk, {})
        m_grounded = (month_grounded_sessions or {}).get(mk, set())
        m_grounded_counted = len(m_grounded & set(month_sessions.get(mk, set())))
        m_write_sess = (month_write_sessions or {}).get(mk, set())
        m_write_counted = len(m_write_sess & set(month_sessions.get(mk, set())))
        # v12: top-level calls per human INSTRUCTION, the same definition the corpus and
        # per-source paths use, on both sides. A month whose numerator still counted sidechain
        # -- or whose denominator still dropped bare slash commands -- would make the rolling
        # series compare two different quantities month to month.
        m_instructions = m_prompts + m_command_only
        actions_per_prompt = (
            ((m_tool_total - m_sidechain_tools) / m_instructions) if m_instructions else 0)

        cats = Counter()
        for name, c in tcounter.items():
            cats[classify_tool(name)] += c
        explore = cats.get("explore", 0) + month_thinking_blocks.get(mk, 0)
        # Planning dispatches leave the denominator, mirroring the corpus and per-source
        # paths. This path can only see tool NAMES, so whether a Skill or Agent call was a
        # planning one is not decidable here — the count has to be threaded in, or corpus
        # and monthly would publish two different definitions of the same ratio and the
        # rolling-AQ blend would mix them.
        m_dispatch = (month_planning_dispatch_calls or {}).get(mk, 0)
        doing = _adjusted_doing(
            cats.get("produce", 0) + cats.get("execute", 0) + cats.get("delegate", 0),
            m_dispatch)
        planning_ratio = (explore / doing) if doing else 0
        # C4: cross-session consume-once credit, scoped to this month's sessions
        # (a plan artifact only credits an execution in the SAME calendar month
        # bucket — matching the existing monthly-progression scoping).
        from gnomon.cli.accumulator import aggregate_ordered
        _month_agg = aggregate_ordered(
            (month_session_ordered_tools or {}).get(mk, {}).values())
        eligible = _month_agg["eligible"]
        _month_orchestratable = _month_agg["orchestratable"]

        _month_delegated_orch_sids = set()
        for (src, sid), facts in (month_session_ordered_tools or {}).get(mk, {}).items():
            from gnomon.cli.accumulator import derive_session_ordered_facts
            d = derive_session_ordered_facts(facts)
            if d["orchestratable"] and month_fanouts.get(mk, {}).get(sid, 0) > 0:
                _month_delegated_orch_sids.add(sid)
        _month_delegated_orchestratable = len(_month_delegated_orch_sids)

        _planning_denominator_set = (
            (month_planning_skill_eligible_sessions or {}).get(mk, set()))
        _planning_numerator_set = (
            (month_planning_skill_sessions or {}).get(mk, set())
            & _planning_denominator_set)
        _planning_unmeasured_set = (
            (month_planning_skill_unmeasured_sessions or {}).get(mk, set())
            - _planning_denominator_set)
        _planning_numerator = len(_planning_numerator_set)
        _planning_denominator = len(_planning_denominator_set)
        _planning_unmeasured = len(_planning_unmeasured_set)
        _planning_scope_state = (
            "measured" if _planning_denominator > 0 and _planning_unmeasured == 0
            else "partial" if _planning_denominator > 0 and _planning_unmeasured > 0
            else "unmeasured")
        assert 0 <= _planning_numerator <= _planning_denominator

        stats_full = {
            "corpus": {"sources": {s: {} for s in sources_present}},
            "volume": {
                "total_sessions": len(month_sessions.get(mk, ())),
                "total_prompts": m_prompts,
                "total_instructions": m_instructions,
                "tool_calls_total": m_tool_total,
                "sidechain_tool_calls": m_sidechain_tools,
                "assistant_turns": month_assistant_turns.get(mk, 0),
                "thinking_blocks": month_thinking_blocks.get(mk, 0),
            },
            "velocity": {
                "tool_churn_edit_write": month_churn.get(mk, 0),
                "shell_authored_lines_est": month_bash_authored_lines.get(mk, 0),
                "active_hours": round(active_hours_m, 1),
            },
            "behavior": {
                "planning_ratio_explore_to_doing": round(planning_ratio, 2),
                "actions_per_prompt": round(actions_per_prompt, 1),
                "questions_asked": month_questions.get(mk, 0),
                "error_recovery_ratio": round(recov, 3) if recov is not None else None,
                "error_rate_per_100_tools": round(err_rate, 1) if err_rate is not None else None,
                "api_errors_retries": month_api_errors.get(mk, 0),
                "fanout_median": fan_med,
                "max_session_fanout": max(fanouts, default=0),
                "parallel_dispatch_turns": None,
                "delegating_sessions": len(fanouts),
                "parallel_session_share": (
                    round(sum(1 for n in fanouts if n >= 2) / len(fanouts), 3)
                    if fanouts else 0.0),
                "shell_test_runs": month_shell_test_runs.get(mk, 0),
                "plan_sessions": len((month_plan_sessions or {}).get(mk, set()) & month_sessions.get(mk, set())),
                "planning_skill_sessions": _planning_numerator,
                "planning_skill_eligible_sessions": _planning_denominator,
                "planning_skill_unmeasured_sessions": _planning_unmeasured,
                "planning_skill_session_scope_state": _planning_scope_state,
                "planning_skill_session_share": (
                    round(_planning_numerator / _planning_denominator, 6)
                    if _planning_scope_state in {"measured", "partial"} else None),
                "planning_skill_session_coverage": (
                    round(_planning_denominator / (
                        _planning_denominator + _planning_unmeasured), 6)
                    if _planning_scope_state in {"measured", "partial"} else None),
                "eligible_change_sessions": eligible,
                "test_covered_change_sessions": _month_agg["test_covered"],
                "planned_eligible_sessions": _month_agg["planned"],
                "evidence_eligible_sessions": _month_agg["evidence"],
                "ordered_facts_state": "measured" if m_tool_total else "unmeasured",
                "delegate_actions": delegate_m,
                # No planning_dispatch_actions here, unlike the corpus and per-source slices.
                # It would be unreachable: this dict is only consumed through
                # build_scoring_inputs (which deliberately drops the field to keep the
                # mirdash wire contract stable), and the raw monthly stats are discarded
                # before stats.json is written. An unread field is worse than an asymmetry.
                "background_tasks": background_m,
                "scheduled_actions": scheduled_m,
                "iteration_depth_mean": round(ids["mean"], 2) if ids["mean"] is not None else None,
                "iteration_depth_p90": ids["p90"],
                "iteration_depth_max": ids["max"],
                "files_hammered_over_15x": ids["heavy_files"],
                "no_tool_activity": m_no_tool,
                "orchestratable_sessions": _month_orchestratable,
                "delegated_orchestratable_sessions": _month_delegated_orchestratable,
            },
            "stack": {
                "models": month_models.get(mk, Counter()).most_common(),
                "top_skills": skill_c.most_common(15),
                "skills_all": skill_c.most_common(200),
                "skills_distinct": len(skill_c),
                "skills_total": sum(skill_c.values()),
                "subagent_types_distinct": len(sub_c),
                "max_session_subagent_types": max(
                    (len(v) for v in (month_session_subagent_types or {}).get(mk, {}).values()),
                    default=0),
                "subagent_types": sub_c.most_common(10),
                "compounding_writes": month_compounding.get(mk, 0),
            },
            "tools": {
                "tool_diversity": diversity,
                "tool_entropy_normalized": round(norm_entropy, 3),
                "mcp_calls": mcp_calls,
                "top_tools": tcounter.most_common(20),
                "mcp_servers_distinct": len(mcp_c),
                "mcp_knowledge_calls": m_subcat_c.get("knowledge", 0) if isinstance(m_subcat_c, dict) else (m_subcat_c.get("knowledge", 0) if m_subcat_c else 0),
                "mcp_knowledge_servers": len(m_subcat_s.get("knowledge", set())) if m_subcat_s else 0,
                "mcp_knowledge_server_names": sorted(m_subcat_s.get("knowledge", set())) if m_subcat_s else [],
                "mcp_grounded_sessions": m_grounded_counted,
                "mcp_write_sessions": m_write_counted,
                "mcp_grounded_session_names": sorted(m_grounded),
                "mcp_subcategory_breakdown": {
                    cat: {"calls": m_subcat_c[cat], "servers": len(m_subcat_s.get(cat, set()))}
                    for cat in sorted(set(m_subcat_c))
                } if m_subcat_c else {},
                "clis_distinct": len(cli_c),
                "cli_calls": sum(cli_c.values()),
                "toolsearch_calls": tcounter.get("ToolSearch", 0),
                "task_tool_calls": tcounter.get("TaskCreate", 0) + tcounter.get("TaskUpdate", 0),
                "agent_calls": tcounter.get("Agent", 0),
            },
        }
        out.append({"month": mk, "stats_full": stats_full})
    return out
