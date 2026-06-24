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

Antigravity has two surfaces: **CLI** (`agy`, read offline from the SQLite+protobuf conversation
DBs) and **IDE** (encrypted `*.pb`, read by driving the running language server's local API
directly — no external dependency). Both decode to the same normalized events.

| Metric | Claude | Codex | Cursor | Gemini | Antigravity CLI | Antigravity IDE |
|---|---|---|---|---|---|---|
| total_sessions / total_prompts / tool_calls | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| git_churn | ➖ ✅ | ➖ ✅ | ➖ ✅ | ✅ | ✅ | ⚠️ best-effort cwd |
| tool_churn | ✅ | ✅ | ⚠️ twin-message dedup | ✅ | ✅ | ⚠️ create-file content only |
| deletions | ✅ | ✅ | ✅ | ⚠️ write-only coverage | ⚠️ write-only | ❌ |
| iteration_depth | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| error_rate / error_recovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (run-command exit codes) |
| thinking_blocks | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ (planner thinking) |
| fanout / delegate_actions | ✅ | ✅ | ✅ | ⛔ | ⚠️ invoke_subagent only | ❌ |
| planning_ratio | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| model tokens | ✅ | ✅ | ✅ | ✅ | ✅ | ⛔ masked by server |
| skills | ✅ | ✅ | ✅ | ✅ | ⚠️ via SKILL.md read | ⚠️ via SKILL.md read |
| mcp_calls | ✅ | ✅ | ✅ | ❌ | ✅ (`server::tool`) | ✅ (`server::tool`) |
| compounding_writes | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| active_hours | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (real per-step ts) |
| actions_per_prompt | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Session caveats

- `git_churn` is parser-independent once source yields a real `cwd`. Antigravity CLI yields a real
  `cwd` (from `trajectory_metadata_blob`); the IDE derives it best-effort from edit/command paths.
- Codex now counts `apply_patch` churn per file, so churn, deletions, and iteration depth are meaningful there.
- Gemini captures tool activity, thinking, tokens, and errors, but deletions stay partial because `write_file` has no old-string diff.
- Gemini/Pi/opencode have no subagent support, so the **Orchestration** AQ axis is dropped (caps
  lack `delegate`), not scored 0 — they aren't penalized for fan-out they can't do.
- Gemini MCP usage is not captured because tool names do not use `mcp__` naming.
- **Antigravity CLI** is fully scored offline: prompts, tool calls, tokens, and model are decoded
  from the protobuf step payloads (stdlib decoder, no deps).
- **Antigravity IDE** transcripts are encrypted; gnomon reads them by calling **every** running
  language server's local API (one per open workspace; auto-launched when the unencrypted usage
  index shows in-window history; no external dependency). It yields prompts, tool calls (with
  commands), thinking, real per-step timestamps, and run-command error codes — but the server
  **masks the model id** (`MODEL_PLACEHOLDER_*`) and does not expose token counts.
- **MCP** is detected on both surfaces: the CLI names MCP tools `server::tool` (→ `mcp__server__tool`),
  the IDE emits a dedicated `MCP_TOOL` step (`mcpTool.serverName` + `toolCall.name`). Counted as
  `mcp_calls` + distinct servers.
- **Skills** are detected when a skill file is read (`skills/<name>/SKILL.md` → `attributionSkill`),
  on both surfaces — so only file-loaded/`/slash`-invoked skills are counted, not context-injected ones.

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
