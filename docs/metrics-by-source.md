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
| skills | ✅ | ✅ | ⛔ | ✅ | ⚠️ via SKILL.md read | ⚠️ via SKILL.md read |
| mcp_calls | ✅ | ✅ | ✅ | ❌ | ✅ (`server::tool`) | ✅ (`server::tool`) |
| compounding_writes | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| active_hours | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (real per-step ts) |
| actions_per_prompt | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Session caveats

- **Planning Skill Practice** has authoritative root/child identity for Claude, Codex,
  Cursor, and OpenCode. Other active sources contribute unmeasured sessions (`U`) to
  coverage instead of forcing the measured `P/E` share to zero or unavailable.
- `git_churn` is parser-independent once source yields a real `cwd`. Antigravity CLI yields a real
  `cwd` (from `trajectory_metadata_blob`); the IDE derives it best-effort from edit/command paths.
- Codex now counts `apply_patch` churn per file, so churn, deletions, and iteration depth are meaningful there.
- Gemini captures tool activity, thinking, tokens, and errors, but deletions stay partial because `write_file` has no old-string diff.
- Gnomon does not extract delegation signals from Gemini, Pi, or OpenCode, so the
  **Orchestration** AQ axis is dropped (caps lack `delegate`), not scored 0. OpenCode itself
  supports child sessions; their parent identity is still used to scope Planning Skill Practice.
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
- **Skills** (Cursor): counted when a skill file is read via `Read`/`Bash` (`skills/<name>/SKILL.md`),
  or listed in injected `<manually_attached_skills>` on user turns (not the full `available_skills` catalog).
- **Orchestration** (Cursor): measured from `Task`/`task_v2` dispatches in the parent Composer
  session — not UI multitask tabs. `fanout_median` is the median agents-per-delegating-session;
  AQ combines coordination quality with the raw share of orchestratable sessions that delegate.
  That raw `frequency` is normalized against the provisional `0.78` target as
  `frequency_score`; its scoring weight rises progressively from 0% to 30% across the first five
  orchestratable sessions. The target remains provisional because the current three-user sample
  is insufficient for recalibration. `max_session_fanout`, `parallel_dispatch_turns`, and
  `parallel_session_share` are descriptive metrics, not AQ inputs. `parallel_session_share` means
  the share of sessions with at least two agent invocations; it does not prove temporal concurrency.
- **Git churn** requires local repo access: if `git_repos_seen == 0` but tool churn is high,
  `summary.json` includes `churn.git_coverage_warning` (common on upload/CI without `state.vscdb` + `.git`).
- **Model mix** (AQ Savvy axis) is **not scored** for Cursor — every included model costs one
  request, so routing between Composer 2.5 and cheaper models is not a cost signal. Model ids
  are still collected for descriptive stats when `state.vscdb` (or CLI `~/.cursor/chats` sidecar)
  is available; `stack.model_signal_missing` flags runs where assistant turns exist but no model
  id was recovered.

## Uploaded summary contract

Current runtime contract: **scoring inputs version 5**, **AQ version 5**, and **GStack version 5** (`score_contract_id = 5:5:5`). Previous-contract scores
must not be shown as improvement or regression against v5. AQ is blended as
65% recent (rolling 30-day) + 35%
full-window (cumulative). The full window includes recent activity, so
improvements are reflected in both components. Empty recent windows fall back
to the unblended full-window AQ.

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
- `profiles_by_source` / `profile` / AQ — **65/35 blended AQ** (65% recent
  30-day rolling + 35% full window); gstack/archetype/steering remain scoped
  to the requested full-window inputs.
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
