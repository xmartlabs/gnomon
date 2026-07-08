"""Hand-built scoring-input cases for the golden parity vectors.

These are the INPUT side of tests/fixtures/scoring_vectors.json. The expected outputs
are GENERATED from the Python scoring implementation (see gen_scoring_vectors.py) and
the test re-derives them to keep the file honest. Keeping the inputs in a tiny module
(not inline in the test) lets both the generator and the test import the same source.

Three cases, chosen to exercise the contract:
  * claude_only  — full-capability source; every AQ term stays. Grounded-session coverage
                   (18/40 = 0.45) is ABOVE Context Intelligence's TARGET (0.40) -> the axis
                   is present and near-full credit.
  * cursor_only  — no skills / toolsearch / tasktool caps; those terms DROP + renormalize.
                   Grounded-session coverage (0/10 = 0.0) is a REAL measured zero (the block
                   HAS the field and HAS tool activity) -> Context Intelligence is present and
                   scored 0 (monotonic, no floor), dragging Craft down rather than dropping.
  * mixed        — claude + cursor; proves the aggregate is the tool-volume WEIGHTED MEAN
                   of the per-source scores, NOT the pooled-union number.
"""

CLAUDE_BLOCK = {
    "source": "claude",
    "volume": {"total_sessions": 40, "total_prompts": 300,
               "tool_calls_total": 4000, "thinking_blocks": 600},
    "velocity": {"active_hours": 80.0, "tool_churn_edit_write": 50000,
                 "shell_authored_lines_est": 2000},
    "behavior": {
        "planning_ratio_explore_to_doing": 0.7, "actions_per_prompt": 13.0,
        "questions_asked": 5, "error_recovery_ratio": 0.8,
        "error_rate_per_100_tools": 3.0, "api_errors_retries": 4, "fanout_median": 3,
        "shell_test_runs": 120, "delegate_actions": 200, "background_tasks": 30,
        "iteration_depth_mean": 2.5, "iteration_depth_p90": 4, "iteration_depth_max": 20,
        "files_hammered_over_15x": 2, "plan_sessions": 16,
    },
    "stack": {
        "skills_distinct": 25, "skills_total": 900, "compounding_writes": 20,
        "subagent_types_distinct": 6,
        "subagent_types": [["general-purpose", 120], ["code-reviewer", 40]],
        "top_skills": [["writing-plans", 60], ["code-review", 80],
                       ["systematic-debugging", 30]],
        "skills_all": [["writing-plans", 60], ["code-review", 80],
                       ["systematic-debugging", 30]],
        "models": [["claude-opus-4-8", 3000], ["claude-sonnet-4-5", 1000]],
    },
    "tools": {
        "agent_calls": 200, "mcp_servers_distinct": 10, "clis_distinct": 25,
        "toolsearch_calls": 150, "task_tool_calls": 300, "cli_calls": 1500,
        "mcp_calls": 400, "tool_diversity": 30, "tool_entropy_normalized": 0.8,
        "mcp_knowledge_calls": 80, "mcp_knowledge_servers": 2,
        # 18/40 sessions = 0.45 coverage -> ABOVE Context Intelligence's TARGET (0.40).
        "mcp_grounded_sessions": 18,
        "mcp_grounded_session_names": [f"claude-s{i}" for i in range(18)],
        "mcp_subcategory_breakdown": {"knowledge": {"calls": 80, "servers": 2}, "browser": {"calls": 50, "servers": 1}},
        "top_tools": [["Bash", 1500], ["Edit", 1000]],
    },
}

CURSOR_BLOCK = {
    "source": "cursor",
    "volume": {"total_sessions": 10, "total_prompts": 80,
               "tool_calls_total": 500, "thinking_blocks": 0},
    "velocity": {"active_hours": 15.0, "tool_churn_edit_write": 3000,
                 "shell_authored_lines_est": 100},
    "behavior": {
        "planning_ratio_explore_to_doing": 0.3, "actions_per_prompt": 6.0,
        "questions_asked": 1, "error_recovery_ratio": 0.5,
        "error_rate_per_100_tools": 5.0, "api_errors_retries": 2, "fanout_median": 1,
        "shell_test_runs": 5, "delegate_actions": 2, "background_tasks": 0,
        "iteration_depth_mean": 6.0, "iteration_depth_p90": 12, "iteration_depth_max": 40,
        "files_hammered_over_15x": 5, "plan_sessions": 2,
    },
    "stack": {
        "skills_distinct": 0, "skills_total": 0, "compounding_writes": 1,
        "subagent_types_distinct": 0, "subagent_types": [],
        "top_skills": [], "skills_all": [], "models": [["default", 500]],
    },
    "tools": {
        "agent_calls": 0, "mcp_servers_distinct": 2, "clis_distinct": 8,
        "toolsearch_calls": 0, "task_tool_calls": 0, "cli_calls": 100,
        "mcp_calls": 50, "tool_diversity": 12, "tool_entropy_normalized": 0.6,
        "mcp_knowledge_calls": 0, "mcp_knowledge_servers": 0,
        # 0/10 sessions = 0.0 coverage, a REAL measured zero (field present + tool activity)
        # -> axis present and scored 0 (monotonic, no floor), NOT dropped.
        "mcp_grounded_sessions": 0,
        "mcp_grounded_session_names": [],
        "mcp_subcategory_breakdown": {},
        "top_tools": [["Bash", 100]],
    },
}


# Context Intelligence low-coverage case: a claude-shaped block with a small but non-zero
# grounded-session coverage. With no floor, the axis is present and scored monotonically
# near (but not at) zero — a light grounder scores a little, a real zero (CURSOR_BLOCK)
# scores exactly zero, and neither is dropped. No boundary discontinuity remains.
CLAUDE_BOUNDARY_BLOCK = dict(CLAUDE_BLOCK, source="claude-boundary")
CLAUDE_BOUNDARY_BLOCK["volume"] = dict(CLAUDE_BLOCK["volume"])
CLAUDE_BOUNDARY_BLOCK["tools"] = dict(CLAUDE_BLOCK["tools"])
# 3/40 = 0.075 coverage -> low, scored monotonically (well below TARGET 0.40).
CLAUDE_BOUNDARY_BLOCK["tools"]["mcp_grounded_sessions"] = 3
CLAUDE_BOUNDARY_BLOCK["tools"]["mcp_grounded_session_names"] = ["b-s0", "b-s1", "b-s2"]

# no_tool_activity capability-drop case: a source with sessions but zero tool calls.
# Context Intelligence (and every other tool-derived axis) must be dropped, not scored 0.
NO_TOOL_ACTIVITY_BLOCK = {
    "source": "no-tool-activity",
    "volume": {"total_sessions": 5, "total_prompts": 20,
               "tool_calls_total": 0, "thinking_blocks": 0},
    "velocity": {"active_hours": 2.0, "tool_churn_edit_write": 0,
                 "shell_authored_lines_est": 0},
    "behavior": {
        "planning_ratio_explore_to_doing": 0, "actions_per_prompt": 0,
        "questions_asked": 0, "error_recovery_ratio": None,
        "error_rate_per_100_tools": None, "api_errors_retries": 0, "fanout_median": None,
        "shell_test_runs": 0, "delegate_actions": 0, "background_tasks": 0,
        "iteration_depth_mean": None, "iteration_depth_p90": None, "iteration_depth_max": None,
        "files_hammered_over_15x": 0, "plan_sessions": 0,
        "no_tool_activity": True,
    },
    "stack": {
        "skills_distinct": 0, "skills_total": 0, "compounding_writes": 0,
        "subagent_types_distinct": 0, "subagent_types": [],
        "top_skills": [], "skills_all": [], "models": [["default", 20]],
    },
    "tools": {
        "agent_calls": 0, "mcp_servers_distinct": 0, "clis_distinct": 0,
        "toolsearch_calls": 0, "task_tool_calls": 0, "cli_calls": 0,
        "mcp_calls": 0, "tool_diversity": 0, "tool_entropy_normalized": 0,
        "mcp_knowledge_calls": 0, "mcp_knowledge_servers": 0,
        "mcp_grounded_sessions": 0, "mcp_grounded_session_names": [],
        "mcp_subcategory_breakdown": {},
        "top_tools": [],
    },
}


def cases():
    """Return the list of (name, scoring_inputs_by_source) input cases."""
    return [
        ("claude_only", {"claude": {"window": CLAUDE_BLOCK, "monthly": []}}),
        ("cursor_only", {"cursor": {"window": CURSOR_BLOCK, "monthly": []}}),
        ("mixed_claude_cursor", {
            "claude": {"window": CLAUDE_BLOCK, "monthly": []},
            "cursor": {"window": CURSOR_BLOCK, "monthly": []},
        }),
        ("claude_boundary_above_floor", {
            "claude-boundary": {"window": CLAUDE_BOUNDARY_BLOCK, "monthly": []},
        }),
        ("no_tool_activity", {
            "no-tool-activity": {"window": NO_TOOL_ACTIVITY_BLOCK, "monthly": []},
        }),
    ]
