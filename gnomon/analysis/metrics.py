import statistics

from gnomon.config import _pretty_model, pctile


def _error_rate_per_100(tool_errors, tool_use_total, no_tool_activity):
    """tool_errors / tool_use_total * 100, with the null-honesty guard."""
    if no_tool_activity:
        return None
    return (tool_errors / tool_use_total * 100) if tool_use_total else 0


def _error_recovery_ratio(recovered_errors, tool_errors, no_tool_activity):
    """recovered_errors / tool_errors, with the null-honesty guard."""
    if no_tool_activity:
        return None
    return (recovered_errors / tool_errors) if tool_errors else 0


def _iteration_depth_stats(depths, no_tool_activity):
    """mean / median / p90 / max / files_over_15x over per-file edit-run counts.
    `depths` need not be pre-sorted. Returns a dict with None values when the
    corpus had no tool activity at all (null honesty)."""
    if no_tool_activity:
        return {"mean": None, "median": None, "p90": None, "max": None, "heavy_files": None}
    d = sorted(depths)
    return {
        "mean": statistics.mean(d) if d else 0,
        "median": statistics.median(d) if d else 0,
        "p90": pctile(d, 90),
        "max": max(d) if d else 0,
        "heavy_files": sum(1 for x in d if x > 15),
    }


def _fanout_median(fanout_counts, no_tool_activity, all_sources_no_agent):
    """Median team-size among agent-dispatching sessions, with null-honesty guards.
    `fanout_counts` is the per-session agent-dispatch count for sessions that
    dispatched at least one agent (already filtered to n > 0)."""
    if no_tool_activity or (all_sources_no_agent and not fanout_counts):
        return None
    return statistics.median(fanout_counts) if fanout_counts else 0


def _peak_hours(hour_hist):
    """Top-3 local hours by event count (Counter.most_common(3) order)."""
    return [h for h, _ in hour_hist.most_common(3)]


def _preferred_days(weekday_hist, dow):
    """Top-3 weekday names by event count (Counter.most_common(3) order)."""
    return [dow[d] for d, _ in weekday_hist.most_common(3)]


def _active_hours_and_longest_run(session_ts, gap_cap_s, burst_gap_s):
    """Active hours (sum of inter-event gaps, each capped) and longest contiguous
    burst (minutes) over a {sessionId: [epoch_seconds]} mapping. Mirrors the
    window derivation exactly so per-month subsets reuse identical rules."""
    durations_min = []
    longest_burst_s = 0.0
    for ts_list in session_ts.values():
        ts_list = sorted(ts_list)
        active_s = 0.0
        for a, bnext in zip(ts_list, ts_list[1:]):
            active_s += min(bnext - a, gap_cap_s)
        durations_min.append(active_s / 60.0)
        bstart = bprev = None
        for t in ts_list:
            if bprev is None:
                bstart = bprev = t
            elif t - bprev > burst_gap_s:
                longest_burst_s = max(longest_burst_s, bprev - bstart)
                bstart = bprev = t
            else:
                bprev = t
        if bstart is not None:
            longest_burst_s = max(longest_burst_s, bprev - bstart)
    return sum(durations_min) / 60.0, longest_burst_s / 60.0


def _token_usage_block(tokens_by_model, zero_tok=None):
    """Shape a {raw_model_id: {input,output,cache_read,cache_creation}} mapping
    into the stats['token_usage'] payload (totals + by_model, sorted desc).
    Single shaper so window + per-month token blocks never drift."""
    all_input = sum(v["input"] for v in tokens_by_model.values())
    all_output = sum(v["output"] for v in tokens_by_model.values())
    all_cr = sum(v["cache_read"] for v in tokens_by_model.values())
    all_cc = sum(v["cache_creation"] for v in tokens_by_model.values())
    by_model = sorted(
        tokens_by_model.items(),
        key=lambda kv: kv[1]["input"] + kv[1]["output"] + kv[1]["cache_read"] + kv[1]["cache_creation"],
        reverse=True,
    )
    return {
        "total_input": all_input,
        "total_output": all_output,
        "total_cache_read": all_cr,
        "total_cache_creation": all_cc,
        "by_model": [
            {
                "model_id": m,
                "model": _pretty_model(m),
                "input": tok["input"],
                "output": tok["output"],
                "cache_read": tok["cache_read"],
                "cache_creation": tok["cache_creation"],
            }
            for m, tok in by_model
        ],
    }


def _usage_int(usage, k):
    """Return usage[k] as int; handles str/float coercion; missing/None/bad -> 0."""
    v = usage.get(k)
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# Skills whose terminal name ends in "-review" but are PLANNING ceremonies, not
# verification -- they mark a planning session (plan_sessions) for the Planning pillar.
# Counting them as review would inflate Verification and fire the review-reflex edge for planners.
_PLANNING_REVIEW_TAILS = frozenset((
    "ceo-review", "eng-review", "design-review",
    "plan-eng-review", "plan-ceo-review", "plan-design-review",
))


def _is_review_skill_name(name):
    """True for actual review/verification skills, false for planning-review ceremonies.

    We want `code-review`, `requesting-code-review`, `verify`, `cerberus`, a bare
    terminal `review`, and any other `*-review` verification skill (e.g.
    `caveman-review`, `security-review`, `hand-review`) -- but NOT planning ceremonies
    like `plan-eng-review` or `ceo-review`, which are planning rather than verification."""
    s = str(name or "").lower()
    if any(k in s for k in ("code-review", "requesting-code-review", "cerberus", "verify")):
        return True
    tail = s.split(":")[-1].split("/")[-1]
    if tail in _PLANNING_REVIEW_TAILS or tail.startswith("plan"):
        return False
    return tail == "review" or tail.endswith("-review")


def _review_skill_uses(skills):
    """Count only true review/verification skill invocations from a skills list."""
    return sum(n for k, n in skills if _is_review_skill_name(k))
