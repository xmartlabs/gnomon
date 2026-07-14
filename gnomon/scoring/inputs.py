import math
from collections import Counter

from gnomon.taxonomy import classify_tool
from gnomon.analysis.metrics import (
    _error_rate_per_100, _error_recovery_ratio, _iteration_depth_stats,
    _fanout_median, _active_hours_and_longest_run,
)


from gnomon.scoring.versioning import SCORING_INPUTS_VERSION
from gnomon.scoring.versioning import AQ_VERSION, GSTACK_VERSION, SCORE_CONTRACT_ID


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
    return {
        "scoring_inputs_version": SCORING_INPUTS_VERSION,
        "aq_version": AQ_VERSION,
        "gstack_version": GSTACK_VERSION,
        "score_contract_id": SCORE_CONTRACT_ID,
        "source": source,
        "volume": {
            "total_sessions": v.get("total_sessions", 0),
            "total_prompts": v.get("total_prompts", 0),
            "tool_calls_total": v.get("tool_calls_total", 0),
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
            "planned_eligible_sessions": b.get("planned_eligible_sessions", 0),
            "evidence_eligible_sessions": b.get("evidence_eligible_sessions", 0),
            "ordered_facts_state": b.get("ordered_facts_state", "unmeasured"),
            "linked_model_pairs": [{
                key: pair.get(key) for key in (
                    "provider", "lead_model", "child_model", "completed",
                    "lifecycle_known", "substantive_calls", "writes")
                if key in pair
            } for pair in (b.get("linked_model_pairs", []) or [])],
            "linked_model_routing_state": b.get("linked_model_routing_state", "unsupported"),
            "delegate_actions": b.get("delegate_actions", 0),
            "background_tasks": b.get("background_tasks", 0),
            "iteration_depth_mean": b.get("iteration_depth_mean"),
            "iteration_depth_p90": b.get("iteration_depth_p90"),
            "iteration_depth_max": b.get("iteration_depth_max"),
            "files_hammered_over_15x": b.get("files_hammered_over_15x", 0),
            "no_tool_activity": b.get("no_tool_activity", False),
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


def build_monthly_scoring_stats(
    months, sources_present, month_prompts, month_tools_count, month_churn,
    month_models, month_sessions, month_assistant_turns, month_thinking_blocks,
    month_bash_authored_lines, month_tool_errors, month_recovered_errors,
    month_edits_per_file, month_questions, month_delegate, month_background,
    month_scheduled, month_fanouts, month_tool_counter, month_session_ts,
    month_skill_counter, month_subagent_counter, month_mcp_server_counter,
    month_cli_counter, month_compounding, month_shell_test_runs, month_api_errors,
    planning_ratio_window, cwds, gap_cap_s, burst_gap_s,
    no_tool_activity, all_sources_no_agent, month_plan_sessions=None,
    month_planning_skill_sessions=None,
    month_session_subagent_types=None,
    month_mcp_subcategory_counter=None, month_mcp_subcategory_servers=None,
    month_grounded_sessions=None, month_write_sessions=None,
    month_session_ordered_tools=None,
):
    out = []
    for mk in months:
        m_tool_total = month_tools_count.get(mk, 0)
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
        actions_per_prompt = (m_tool_total / m_prompts) if m_prompts else 0

        cats = Counter()
        for name, c in tcounter.items():
            cats[classify_tool(name)] += c
        explore = cats.get("explore", 0) + month_thinking_blocks.get(mk, 0)
        doing = cats.get("produce", 0) + cats.get("execute", 0) + cats.get("delegate", 0)
        planning_ratio = (explore / doing) if doing else 0
        # C4: cross-session consume-once credit, scoped to this month's sessions
        # (a plan artifact only credits an execution in the SAME calendar month
        # bucket — matching the existing monthly-progression scoping).
        from gnomon.cli.accumulator import aggregate_ordered
        _month_agg = aggregate_ordered(
            (month_session_ordered_tools or {}).get(mk, {}).values())
        eligible = _month_agg["eligible"]

        stats_full = {
            "corpus": {"sources": {s: {} for s in sources_present}},
            "volume": {
                "total_sessions": len(month_sessions.get(mk, ())),
                "total_prompts": m_prompts,
                "tool_calls_total": m_tool_total,
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
                "shell_test_runs": month_shell_test_runs.get(mk, 0),
                "plan_sessions": len((month_plan_sessions or {}).get(mk, set()) & month_sessions.get(mk, set())),
                "planning_skill_sessions": len(
                    (month_planning_skill_sessions or {}).get(mk, set())
                    & month_sessions.get(mk, set())),
                "eligible_change_sessions": eligible,
                "planned_eligible_sessions": _month_agg["planned"],
                "evidence_eligible_sessions": _month_agg["evidence"],
                "ordered_facts_state": "measured" if m_tool_total else "unmeasured",
                "delegate_actions": delegate_m,
                "background_tasks": background_m,
                "scheduled_actions": scheduled_m,
                "iteration_depth_mean": round(ids["mean"], 2) if ids["mean"] is not None else None,
                "iteration_depth_p90": ids["p90"],
                "iteration_depth_max": ids["max"],
                "files_hammered_over_15x": ids["heavy_files"],
                "no_tool_activity": m_no_tool,
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
