# Metrics by source

Quick session reference. Keep only current coverage, current caveats, upload contract.

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Working as documented |
| ❌ | Not captured |
| ⚠️ | Partial |
| ⛔ | Not available by design |
| ➖ | Source-agnostic |

## Metric × source

| Metric | Claude | Codex | Cursor | Gemini | Antigravity |
|---|---|---|---|---|---|
| total_sessions / total_prompts / tool_calls | ✅ | ✅ | ✅ | ✅ | ⛔ metadata-only |
| git_churn | ➖ ✅ | ➖ ✅ | ➖ ✅ | ✅ | ⛔ |
| tool_churn | ✅ | ✅ | ⚠️ twin-message dedup | ✅ | ⛔ |
| deletions | ✅ | ✅ | ✅ | ⚠️ write-only coverage | ⛔ |
| iteration_depth | ✅ | ✅ | ✅ | ✅ | ⛔ |
| error_rate / error_recovery | ✅ | ✅ | ✅ | ✅ | ⛔ |
| thinking_blocks | ✅ | ✅ | ✅ | ✅ | ⛔ |
| fanout / delegate_actions | ✅ | ✅ | ✅ | ⛔ | ⛔ |
| planning_ratio | ✅ | ✅ | ✅ | ✅ | ⛔ |
| model tokens | ✅ | ✅ | ✅ | ✅ | ⛔ |
| skills | ✅ | ✅ | ✅ | ✅ | ⛔ |
| mcp_calls | ✅ | ✅ | ✅ | ❌ | ⛔ |
| compounding_writes | ✅ | ✅ | ✅ | ✅ | ⛔ |
| active_hours | ✅ | ✅ | ✅ | ✅ | ⛔ |
| actions_per_prompt | ✅ | ✅ | ✅ | ✅ | ⛔ |

## Session caveats

- `git_churn` is parser-independent once source yields a real `cwd`. Antigravity never does.
- Codex now counts `apply_patch` churn per file, so churn, deletions, and iteration depth are meaningful there.
- Gemini captures tool activity, thinking, tokens, and errors, but deletions stay partial because `write_file` has no old-string diff.
- Gemini has no subagent support, so `fanout` and `delegate_actions` are unavailable by design.
- Gemini MCP usage is not captured because tool names do not use `mcp__` naming.
- Antigravity remains metadata-only. No tool-level metrics should be interpreted there.

## Uploaded summary contract

`build_summary()` uploads:

- `context.total_prompts`
- `context.client_version`
- `churn.active_hours`
- `churn.actions_per_prompt`
- `noticed_stats_monthly`
- `scoring_inputs_version`
- `scoring_inputs_by_source`
- `profiles_by_source`
- `source_usage`
- `source_usage_monthly`

Mirdash reads `actions_per_prompt` from `churn`, with legacy fallback to `context.actions_per_prompt`.

### Three time scales in the payload

- `scoring_inputs_by_source[*].window` — **window** (up to 6-month) raw scoring input per source.
- `noticed_stats_monthly` — **per calendar month** evidence, one entry per month with its own `git_churn`, tokens, errors, etc.
- `scoring_inputs_by_source[*].monthly` — **per source per calendar month** raw scoring inputs.
- `profiles_by_source` / `profile` / AQ — **window** only.
- `source_usage` — **window** usage share by source.
- `source_usage_monthly` — **per calendar month** usage share by source.

Per-month session counts can sum above the window's unique session count when a session crosses a month boundary (accepted).

## Execution target

Current formula:

```text
execution = 10 × (0.6 × out_pct + 0.4 × deleg_pct)
out_rate  = tool_churn_edit_write / max(active_hours, 0.1)
out_pct   = clamp(out_rate / TARGET)
```

Current `TARGET = 1000` tool-authored lines/hr. Treat as provisional calibration point.
