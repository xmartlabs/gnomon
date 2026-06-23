import math
import statistics
from collections import Counter
from datetime import datetime, timedelta

from gnomon.config import _pretty_model, _client_version
from gnomon.taxonomy import classify_tool
from gnomon.analysis.churn import git_churn
from gnomon.analysis.metrics import (
    _error_rate_per_100, _error_recovery_ratio, _iteration_depth_stats,
    _fanout_median, _peak_hours, _preferred_days, _active_hours_and_longest_run,
    _token_usage_block,
)
from gnomon.scoring.gstack import score_breakdown
from gnomon.scoring.archetype import pick_archetype
from gnomon.scoring.insights import steering_reading, growth_edges_structured, signature_moves_structured
from gnomon.scoring.aggregate import score_by_source


def _model_usage_from_models(models, tok_by_model=None):
    """Shape a [(model_id, count), ...] list into the model_usage payload (top 12, with a
    GLOBAL pct so a >12-model tail honestly sums to <1). `tok_by_model` maps model_id ->
    {input,output,cache_read,cache_creation}; absent (e.g. per-source, where token usage is
    only tracked corpus-wide) → token fields default to 0. Single builder so the whole-corpus
    and per-source model mixes never drift."""
    tok_by_model = tok_by_model or {}
    total = sum(n for _, n in models)
    if total <= 0:
        return []
    return [
        {
            "model_id": m,
            "model": _pretty_model(m),
            "count": int(n),
            "pct": round(n / total, 3),
            "tokens_input":          (tok_by_model.get(m) or {}).get("input", 0),
            "tokens_output":         (tok_by_model.get(m) or {}).get("output", 0),
            "tokens_cache_read":     (tok_by_model.get(m) or {}).get("cache_read", 0),
            "tokens_cache_creation": (tok_by_model.get(m) or {}).get("cache_creation", 0),
        }
        for m, n in models[:12]  # most_common() already desc
    ]


def _build_profile(stats):
    """Assemble the `profile` sub-dict for build_summary: level, per-axis scores with
    explainable drill-down, archetype, and steering style. All values are computed or
    count-based — no prompts, no verbatim quotes, no skill/project names beyond what
    compute_aq already exposes. Defensive: if stats lacks the grading keys (e.g. a
    zero-activity corpus) it still returns a well-formed dict."""
    aq = stats.get("agentic", {})
    sb = score_breakdown(stats)
    arch_scores = {
        "Execution": sb["execution"]["value"],
        "Planning": sb["planning"]["value"],
        "Engineering": sb["engineering"]["value"],
    }
    arch_title, arch_quote = pick_archetype(stats, arch_scores)
    all_models = (stats.get("stack") or {}).get("models") or []
    _tok_by_model = {e["model_id"]: e for e in (stats.get("token_usage") or {}).get("by_model") or []}
    model_usage = _model_usage_from_models(all_models, _tok_by_model)
    return {
        "aq": aq,
        "archetype": {"title": arch_title, "quote": arch_quote},
        "scores": sb,
        "steering": steering_reading(stats),
        "growth_edges": growth_edges_structured(stats, arch_scores),
        "signature_moves": signature_moves_structured(stats),
        "model_usage": model_usage,
    }


def _build_monthly_noticed_stats(
    months, month_prompts, month_tools_count, month_churn, month_models,
    month_model_tokens, month_sessions, month_dates, month_assistant_turns,
    month_thinking_blocks, month_prompt_lengths, month_bash_write_calls,
    month_bash_authored_lines, month_tool_errors, month_recovered_errors,
    month_edits_per_file, month_polite, month_questions, month_delegate,
    month_background, month_scheduled, month_fanouts, month_hour_hist,
    month_weekday_hist, month_tool_counter, month_session_ts,
    no_tool_activity, all_sources_no_agent, cwds, gap_cap_s, burst_gap_s, dow,
):
    """Build stats['monthly_noticed_stats'] — one entry per calendar month present
    in the window, chronological. Each entry's `stats` is shaped by the SAME
    `_build_noticed_stats` used for the window block (single shaper → no drift),
    and every derived value reuses the shared anti-drift helpers.

    git_churn is called ONCE per month with that month's [start, next_month_start)
    range — never the window total.
    """
    out = []
    for mk in months:
        year, mon = int(mk[:4]), int(mk[5:7])
        month_start = datetime(year, mon, 1).date()
        next_month_start = (datetime(year + 1, 1, 1) if mon == 12
                            else datetime(year, mon + 1, 1)).date()
        # per-month git churn over the SAME repos as the window call, restricted
        # to this month's range (one call per month).
        gc_m = git_churn(cwds, month_start.isoformat(), next_month_start.isoformat())

        lengths = month_prompt_lengths.get(mk, [])
        avg_len = statistics.mean(lengths) if lengths else 0
        med_len = statistics.median(lengths) if lengths else 0

        active_hours_m, longest_run_m = _active_hours_and_longest_run(
            month_session_ts.get(mk, {}), gap_cap_s, burst_gap_s)

        m_tool_total = month_tools_count.get(mk, 0)
        # Per-month null-honesty: a month with zero tool calls is not measurable
        # even if the surrounding window has tool activity.
        m_no_tool = (m_tool_total == 0)
        ids = _iteration_depth_stats(month_edits_per_file.get(mk, []), m_no_tool)
        err_rate = _error_rate_per_100(
            month_tool_errors.get(mk, 0), m_tool_total, m_no_tool)
        recov = _error_recovery_ratio(
            month_recovered_errors.get(mk, 0), month_tool_errors.get(mk, 0), m_no_tool)
        fanouts = [n for n in month_fanouts.get(mk, {}).values() if n > 0]
        # NOTE: all_sources_no_agent is still window-level (per-month source tracking
        # not available); m_no_tool already forces None for tool-less months, covering
        # the primary case.  Residual: an all-agent-incapable month inside an
        # agent-capable window still returns 0 (not None) for fanout_median.
        fan_med = _fanout_median(fanouts, m_no_tool, all_sources_no_agent)

        partial = {
            "volume": {
                "total_sessions": len(month_sessions.get(mk, ())),
                "total_prompts": month_prompts.get(mk, 0),
                "tool_calls_total": m_tool_total,
                "assistant_turns": month_assistant_turns.get(mk, 0),
                "thinking_blocks": month_thinking_blocks.get(mk, 0),
                "avg_prompt_length_chars": round(avg_len, 1),
                "median_prompt_length_chars": round(med_len, 1),
            },
            "velocity": {
                "git_churn_total": gc_m["churn"],
                "tool_churn_edit_write": month_churn.get(mk, 0),
                "shell_authored_lines_est": month_bash_authored_lines.get(mk, 0),
                "git_repos_seen": gc_m["repos_seen"],
                "git_repos_with_commits": gc_m["repos_with_commits"],
                "active_hours": round(active_hours_m, 1),
            },
            "behavior": {
                "iteration_depth_mean": round(ids["mean"], 2) if ids["mean"] is not None else None,
                "iteration_depth_median": round(ids["median"], 2) if ids["median"] is not None else None,
                "iteration_depth_p90": ids["p90"],
                "iteration_depth_max": ids["max"],
                "files_hammered_over_15x": ids["heavy_files"],
                "tool_errors": month_tool_errors.get(mk, 0),
                "error_rate_per_100_tools": round(err_rate, 1) if err_rate is not None else None,
                "error_recovery_ratio": round(recov, 3) if recov is not None else None,
                "polite_prompts": month_polite.get(mk, 0),
                "questions_asked": month_questions.get(mk, 0),
                "delegate_actions": month_delegate.get(mk, 0),
                "background_tasks": month_background.get(mk, 0),
                "scheduled_actions": month_scheduled.get(mk, 0),
                "fanout_median": fan_med,
                "longest_run_minutes": round(longest_run_m, 1),
            },
            "stack": {
                "models": month_models.get(mk, Counter()).most_common(),
            },
            "rhythm": {
                "hour_histogram_local": {str(h): month_hour_hist.get(mk, {}).get(h, 0) for h in range(24)},
                "weekday_histogram": {dow[d]: month_weekday_hist.get(mk, {}).get(d, 0) for d in range(7)},
                "peak_hours_local": _peak_hours(month_hour_hist.get(mk, Counter())),
                "preferred_days": _preferred_days(month_weekday_hist.get(mk, Counter()), dow),
            },
            "tools": {
                "top_tools": month_tool_counter.get(mk, Counter()).most_common(20),
            },
        }
        out.append({
            "month": mk,
            "range_start": month_start.isoformat(),
            "range_end": (next_month_start - timedelta(days=1)).isoformat(),
            "stats": _build_noticed_stats(partial),
            "token_usage": _token_usage_block(dict(month_model_tokens.get(mk, {}))),
        })
    return out


def _build_noticed_stats(stats):
    """Share-safe evidence slice for the local "What we noticed" cards.

    Count-only / derived values, no prompts, quotes, paths, project names, or raw
    transcript text. Mirdash can store this inside summaryRaw and decide later
    whether to render cards or inspect the evidence.
    """
    v = stats.get("volume") or {}
    b = stats.get("behavior") or {}
    vel = stats.get("velocity") or {}
    st = stats.get("stack") or {}
    t = stats.get("tools") or {}
    r = stats.get("rhythm") or {}

    models = st.get("models") or []
    model_total = sum(n for _, n in models) or 0
    top_models = [
        {
            "model_id": model_id,
            "label": _pretty_model(model_id),
            "turns": int(turns),
            "pct": round(turns / model_total, 3) if model_total else 0,
        }
        for model_id, turns in models
    ]

    weekday_raw = r.get("weekday_histogram") or {}
    weekday_histogram = {
        day: int(weekday_raw.get(day, 0))
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    }

    return {
        "volume": {
            "total_sessions": v.get("total_sessions", 0),
            "total_prompts": v.get("total_prompts", 0),
            "tool_calls_total": v.get("tool_calls_total", 0),
            "assistant_turns": v.get("assistant_turns", 0),
            "thinking_blocks": v.get("thinking_blocks", 0),
        },
        "shipping": {
            "git_churn_total": vel.get("git_churn_total", 0),
            "tool_churn_edit_write": vel.get("tool_churn_edit_write", 0),
            "shell_authored_lines_est": vel.get("shell_authored_lines_est", 0),
            "git_repos_seen": vel.get("git_repos_seen", 0),
            "git_repos_with_commits": vel.get("git_repos_with_commits", 0),
            "active_hours": vel.get("active_hours", 0),
        },
        "iteration": {
            "depth_mean": b.get("iteration_depth_mean"),
            "depth_median": b.get("iteration_depth_median"),
            "depth_p90": b.get("iteration_depth_p90"),
            "depth_max": b.get("iteration_depth_max"),
            "files_over_15x": b.get("files_hammered_over_15x", 0),
        },
        "errors": {
            "tool_errors": b.get("tool_errors", 0),
            "error_rate_per_100_tools": b.get("error_rate_per_100_tools"),
            "error_recovery_ratio": b.get("error_recovery_ratio"),
        },
        "models": {
            "top_models": top_models,
        },
        "rhythm": {
            "peak_hours_local": list(r.get("peak_hours_local") or []),
            "weekday_histogram": weekday_histogram,
            "preferred_days": list(r.get("preferred_days") or []),
        },
        "prompts": {
            "avg_length_chars": v.get("avg_prompt_length_chars", 0),
            "median_length_chars": v.get("median_prompt_length_chars", 0),
            "polite_prompts": b.get("polite_prompts", 0),
            "questions_asked": b.get("questions_asked", 0),
        },
        "agents": {
            "delegate_actions": b.get("delegate_actions", 0),
            "background_tasks": b.get("background_tasks", 0),
            "scheduled_actions": b.get("scheduled_actions", 0),
            "fanout_median": b.get("fanout_median"),
        },
        "sessions": {
            "longest_run_minutes": b.get("longest_run_minutes", 0),
        },
        "tools": {
            "top_tools": [
                {"name": str(name), "calls": int(calls)}
                for name, calls in (t.get("top_tools") or [])
            ],
        },
    }


SCORING_INPUTS_VERSION = 1


def _pairs(seq):
    """Normalize a (name, count) iterable into a list of JSON-safe [name, count] lists."""
    return [[str(k), int(n)] for k, n in (seq or [])]


def _build_scoring_inputs(stats):
    """The EXACT raw-input field set the scoring functions consume, shaped into a flat,
    re-scorable block. Single shaper — used for a source's window AND each of its months
    (no drift). The emitted block is itself a valid `stats`-shaped slice (it carries the
    corpus.sources tag and the volume/velocity/behavior/stack/tools sub-dicts compute_aq /
    compute_scores read), so feeding it straight back into the scoring fns reproduces the
    score. The `source` tag drives that slice's capability set (SOURCE_CAPS).

    Fields are grouped exactly as the audit lists them:
      volume   — total_sessions, total_prompts, tool_calls_total, thinking_blocks
      velocity — active_hours, tool_churn_edit_write, shell_authored_lines_est
      behavior — planning_ratio, actions_per_prompt, questions_asked, error_recovery_ratio,
                 error_rate_per_100_tools, api_errors_retries, fanout_median, shell_test_runs,
                 delegate_actions, background_tasks, iteration_depth_{mean,p90,max},
                 files_hammered_over_15x
      stack    — skills_distinct/total, compounding_writes, subagent_types_distinct,
                 subagent_types[], top_skills/skills_all[] (RAW names), models[]
      tools    — agent_calls, mcp_servers_distinct, clis_distinct, toolsearch_calls,
                 task_tool_calls, cli_calls, mcp_calls, tool_diversity,
                 tool_entropy_normalized, top_tools[]
    """
    v = stats.get("volume") or {}
    vel = stats.get("velocity") or {}
    b = stats.get("behavior") or {}
    st = stats.get("stack") or {}
    t = stats.get("tools") or {}
    srcs = sorted((stats.get("corpus", {}).get("sources") or {}).keys())
    source = srcs[0] if len(srcs) == 1 else (",".join(srcs) if srcs else None)
    return {
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
            "shell_test_runs": b.get("shell_test_runs", 0),
            "delegate_actions": b.get("delegate_actions", 0),
            "background_tasks": b.get("background_tasks", 0),
            "iteration_depth_mean": b.get("iteration_depth_mean"),
            "iteration_depth_p90": b.get("iteration_depth_p90"),
            "iteration_depth_max": b.get("iteration_depth_max"),
            "files_hammered_over_15x": b.get("files_hammered_over_15x", 0),
        },
        "stack": {
            "skills_distinct": st.get("skills_distinct", 0),
            "skills_total": st.get("skills_total", 0),
            "compounding_writes": st.get("compounding_writes", 0),
            "subagent_types_distinct": st.get("subagent_types_distinct", 0),
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
            "top_tools": _pairs(t.get("top_tools")),
        },
        # Per-source token usage (by_model). NOT a scoring input — carried so the
        # per-source model_usage keeps real token counts (and a future recompute has the
        # per-source token split). Shape = stats['token_usage'] (_token_usage_block).
        "token_usage": stats.get("token_usage") or {"by_model": []},
    }


def _build_monthly_scoring_stats(
    months, sources_present, month_prompts, month_tools_count, month_churn,
    month_models, month_sessions, month_assistant_turns, month_thinking_blocks,
    month_bash_authored_lines, month_tool_errors, month_recovered_errors,
    month_edits_per_file, month_questions, month_delegate, month_background,
    month_scheduled, month_fanouts, month_tool_counter, month_session_ts,
    month_skill_counter, month_subagent_counter, month_mcp_server_counter,
    month_cli_counter, month_compounding, month_shell_test_runs, month_api_errors,
    planning_ratio_window, cwds, gap_cap_s, burst_gap_s,
    no_tool_activity, all_sources_no_agent,
):
    """Build per-month FULL stats slices (corpus/volume/velocity/behavior/stack/tools),
    one per month present, so _build_scoring_inputs can run over each month identically
    to the window. Mirrors _build_monthly_noticed_stats' per-month derivation rules and
    reuses the same anti-drift helpers; adds the stack/tool fields scoring needs that
    noticed_stats omits. Returns [{"month": "YYYY-MM", "stats_full": {...}}, ...].
    """
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

        # tool diversity / entropy from this month's tool distribution (same formula as window)
        diversity = len(tcounter)
        tot = sum(tcounter.values()) or 1
        entropy = -sum((c / tot) * math.log2(c / tot) for c in tcounter.values())
        norm_entropy = entropy / math.log2(diversity) if diversity > 1 else 0
        mcp_calls = sum(mcp_c.values())
        actions_per_prompt = (m_tool_total / m_prompts) if m_prompts else 0

        # explore/doing for planning_ratio: derive from this month's tool categories
        cats = Counter()
        for name, c in tcounter.items():
            cats[classify_tool(name)] += c
        explore = cats.get("explore", 0) + month_thinking_blocks.get(mk, 0)
        doing = cats.get("produce", 0) + cats.get("execute", 0) + cats.get("delegate", 0)
        planning_ratio = (explore / doing) if doing else 0

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
                "delegate_actions": delegate_m,
                "background_tasks": background_m,
                "scheduled_actions": scheduled_m,
                "iteration_depth_mean": round(ids["mean"], 2) if ids["mean"] is not None else None,
                "iteration_depth_p90": ids["p90"],
                "iteration_depth_max": ids["max"],
                "files_hammered_over_15x": ids["heavy_files"],
            },
            "stack": {
                "models": month_models.get(mk, Counter()).most_common(),
                "top_skills": skill_c.most_common(15),
                "skills_all": skill_c.most_common(200),  # see local.py: high cap so AQ needles aren't dropped
                "skills_distinct": len(skill_c),
                "skills_total": sum(skill_c.values()),
                "subagent_types_distinct": len(sub_c),
                "subagent_types": sub_c.most_common(10),
                "compounding_writes": month_compounding.get(mk, 0),
            },
            "tools": {
                "tool_diversity": diversity,
                "tool_entropy_normalized": round(norm_entropy, 3),
                "mcp_calls": mcp_calls,
                "top_tools": tcounter.most_common(20),
                "mcp_servers_distinct": len(mcp_c),
                "clis_distinct": len(cli_c),
                "cli_calls": sum(cli_c.values()),
                "toolsearch_calls": tcounter.get("ToolSearch", 0),
                "task_tool_calls": tcounter.get("TaskCreate", 0) + tcounter.get("TaskUpdate", 0),
                "agent_calls": tcounter.get("Agent", 0),
            },
        }
        out.append({"month": mk, "stats_full": stats_full})
    return out


_SOURCE_USAGE_METRICS = ("sessions", "prompts", "tool_calls", "active_hours")


def _usage_raw_from_block(block):
    """Pull the four usage counts out of a scoring-input block's volume/velocity."""
    vol = (block or {}).get("volume") or {}
    vel = (block or {}).get("velocity") or {}
    return {
        "sessions": vol.get("total_sessions", 0) or 0,
        "prompts": vol.get("total_prompts", 0) or 0,
        "tool_calls": vol.get("tool_calls_total", 0) or 0,
        "active_hours": vel.get("active_hours", 0) or 0,
    }


def _source_usage_share(raw_by_source):
    """raw_by_source = {src: {sessions,prompts,tool_calls,active_hours}} → share block.
    Each metric's pct is a GLOBAL share (count / sum-across-sources) so the bars sum to ~1.
    `prompts` is the primary, comparable metric (a prompt = one human message, ~the same unit
    across tools); the others ride along for an optional UI toggle. sessions is NOT primary —
    tools fragment sessions very differently (a Cursor corpus shows dozens of tiny sessions
    vs a Claude one)."""
    totals = {m: sum(r.get(m, 0) or 0 for r in raw_by_source.values()) for m in _SOURCE_USAGE_METRICS}
    by_source = {}
    for src, r in raw_by_source.items():
        entry = {m: (r.get(m, 0) or 0) for m in _SOURCE_USAGE_METRICS}
        for m in _SOURCE_USAGE_METRICS:
            entry[f"{m}_pct"] = round(entry[m] / totals[m], 3) if totals[m] else 0
        by_source[src] = entry
    return {"by_source": by_source, "totals": totals, "primary_metric": "prompts"}


def _build_source_usage(scoring_inputs_by_source):
    """Window-level per-tool usage share (whole upload window)."""
    raw = {src: _usage_raw_from_block(b.get("window"))
           for src, b in (scoring_inputs_by_source or {}).items()}
    return _source_usage_share(raw)


def _build_source_usage_monthly(scoring_inputs_by_source):
    """Per-CALENDAR-MONTH per-tool usage share, so the dashboard's monthly view shows the
    share for THAT month (not the whole-window share). One entry per month present across
    sources, chronological; same shape as _build_source_usage + a `month` key. Mirrors how
    noticed_stats_monthly is per-month."""
    months = {}  # "YYYY-MM" -> {src: usage_raw}
    for src, b in (scoring_inputs_by_source or {}).items():
        for entry in (b.get("monthly") or []):
            mk = entry.get("month")
            if not mk:
                continue
            months.setdefault(mk, {})[src] = _usage_raw_from_block(entry)
    out = []
    for mk in sorted(months):
        block = _source_usage_share(months[mk])
        block["month"] = mk
        out.append(block)
    return out


def _profiles_by_source(scoring_inputs_by_source):
    """Precompute per-source + aggregate profiles (so mirdash just displays them — no
    recompute). Each per-source profile's model_usage is populated from that source's own
    stack.models (score_by_source leaves it empty); tokens are 0 there (token usage is only
    tracked corpus-wide). The aggregate keeps model_usage empty (it's a score blend)."""
    sbs = score_by_source(scoring_inputs_by_source or {})
    for src, profile in (sbs.get("by_source") or {}).items():
        window = (scoring_inputs_by_source.get(src) or {}).get("window") or {}
        models = (window.get("stack") or {}).get("models") or []
        tok_by_model = {e["model_id"]: e
                        for e in ((window.get("token_usage") or {}).get("by_model") or [])}
        profile["model_usage"] = _model_usage_from_models(models, tok_by_model)
    return sbs


def build_summary(stats):
    """The shareable subset for the low-cost feedback loop (docs/metrics-evaluation.md):
    the 8 high-signal MEASURED metrics + monthly progression + rubric profile block.
    The profile sub-dict carries scores/level/archetype/steering; all values are computed
    or count-based — no prompts, no verbatim quotes, no raw skill/project names.
    Safe to share as-is."""
    v, b, vel, st, t, c = (stats["volume"], stats["behavior"], stats["velocity"],
                           stats["stack"], stats["tools"], stats["corpus"])
    return {
        "context": {
            "date_range": c.get("date_range"),
            "window": c.get("window"),
            "sources": sorted((c.get("sources") or {}).keys()),
            "total_sessions": v["total_sessions"],
            "total_prompts": v["total_prompts"],
            "client_version": _client_version(),
        },
        "planning_ratio_explore_to_doing": b["planning_ratio_explore_to_doing"],
        "errors": {
            "error_recovery_ratio": b["error_recovery_ratio"],
            "error_rate_per_100_tools": b["error_rate_per_100_tools"],
        },
        "iteration_depth": {
            "mean": b["iteration_depth_mean"], "median": b["iteration_depth_median"],
            "p90": b["iteration_depth_p90"], "max": b["iteration_depth_max"],
            "files_over_15x": b["files_hammered_over_15x"],
        },
        "churn": {
            "git_churn_total": vel["git_churn_total"],
            "tool_churn_edit_write": vel["tool_churn_edit_write"],
            "active_hours": vel["active_hours"],
            "actions_per_prompt": b["actions_per_prompt"],
        },
        "orchestration": {
            "fanout_median": b["fanout_median"],
            "delegate_actions": b["delegate_actions"],
        },
        "compounding_writes": st["compounding_writes"],
        "ecosystem": {
            "skills_distinct": st["skills_distinct"], "skills_total": st["skills_total"],
            "mcp_servers_distinct": t["mcp_servers_distinct"],
        },
        "progression_monthly": (stats.get("progression") or {}).get("monthly", []),
        # Per-calendar-month evidence slice. KEEP: mirdash's ingest route unpacks this into
        # the buildMetricMonthlyStats table (its monthly/team views depend on it). The
        # window-level noticed_stats block stays dropped (nothing consumes it).
        "noticed_stats_monthly": stats.get("monthly_noticed_stats", []),
        "profile": _build_profile(stats),
        # Raw scoring inputs per source × (window + month) — the cross-language parity
        # contract (mirdash re-scores from these). Superset of the window-level
        # noticed_stats block, which is dropped (the per-source window slice for the
        # lone source equals the old whole-corpus noticed_stats here).
        "scoring_inputs_version": stats.get("scoring_inputs_version", SCORING_INPUTS_VERSION),
        "scoring_inputs_by_source": stats.get("scoring_inputs_by_source", {}),
        # Precomputed per-agent + aggregate profiles (mirdash displays these directly; the
        # pooled `profile` above stays the headline "Combined"). Raw inputs above let a
        # future phase recompute these server-side, but for now gnomon ships them.
        "profiles_by_source": _profiles_by_source(stats.get("scoring_inputs_by_source") or {}),
        # Per-tool usage share (primary metric: prompts) for the "which tool did you use
        # most" chart. Window-level + per-calendar-month (so the monthly view shows the
        # month's share, not the whole-window share).
        "source_usage": _build_source_usage(stats.get("scoring_inputs_by_source") or {}),
        "source_usage_monthly": _build_source_usage_monthly(stats.get("scoring_inputs_by_source") or {}),
        "token_usage": stats.get("token_usage") or {
            "total_input": 0, "total_output": 0,
            "total_cache_read": 0, "total_cache_creation": 0,
            "by_model": [],
        },
    }
