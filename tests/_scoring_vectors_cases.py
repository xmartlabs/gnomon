"""Hand-built scoring-input cases for the golden parity vectors.

These are the INPUT side of tests/fixtures/scoring_vectors.json. The expected outputs
are GENERATED from the Python scoring implementation (see gen_scoring_vectors.py) and
the test re-derives them to keep the file honest. Keeping the inputs in a tiny module
(not inline in the test) lets both the generator and the test import the same source.

Three cases, chosen to exercise the contract:
  * claude_only  — full-capability source; every AQ term stays.
  * cursor_only  — no skills / toolsearch / tasktool caps; those terms DROP + renormalize.
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
        "files_hammered_over_15x": 2, "plan_sessions": 32,
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
        "top_tools": [["Bash", 100]],
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
    ]
