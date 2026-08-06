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

- Rate terms are `count / volume.tool_calls_total` over the corpus. Missing or
  insufficient evidence drops the term and renormalizes its weight.
- Capability-specific terms drop when a source cannot emit their signal; a
  measurable absent signal scores zero.
- Planning coverage preserves measured and unmeasured session counts by source.
  A source without a planning signal does not force a measured corpus to zero.
- Git churn needs a real working directory. Antigravity IDE working directories
  are best-effort; its model IDs and token counts are unavailable by design.
- Gemini deletion coverage is write-only, and Gemini MCP names do not identify
  MCP usage. Cursor skill detection uses SKILL.md reads or injected attached skills.
- Delegation coverage is source-specific. Sources without a delegation signal
  drop the Orchestration axis rather than scoring zero.

## Uploaded summary contract

Current runtime contract: **scoring inputs version 16**, **AQ version 16**, and
**GStack version 16** (`score_contract_id = 16:16:16`). Compare scores only when
contract IDs match.

`Workflow` dispatch fan-out is sourced from the real dispatched-agent transcripts
under `.../subagents/workflows/wf_*/agent-*.jsonl`, one credit per distinct
dispatched agent, rather than from the `Workflow` tool_use call count (one call
can fan out to many agents). `Agent`/`Task` calls are unchanged: one call is
still one dispatched agent.

Compounding credits MCP knowledge-write persistence calls (mem0
`add_memory`/`update_memory`, engram `mem_save`/`mem_update`) in addition to
filesystem memory/ADR writes, deduped per distinct persisted target within a
session so target-less or repeat-target spam cannot saturate the axis. Reads,
deletions, and fetch-only knowledge servers (context7-class) still credit zero.

### Windows and evidence

- The scoring window is a trailing `--window=N` calendar-month window (default 1).
  It is published as `context.window_months` from the span actually processed.
- `noticed_stats_monthly` is separate six-month evidence used to correct the
  per-calendar-month series. It is not the AQ scoring window.
- Rate terms use `volume.tool_calls_total` as a corpus-wide denominator. A missing
  or insufficient denominator drops the term and renormalizes its weight rather
  than scoring a synthetic zero.
- `partial_terms` appears when an axis scores fewer than all configured terms. It
  reports `{scored, total, weight_scored}`; absence means no term was dropped.

### Actions per prompt and steering

`behavior.actions_per_prompt` is top-level tool calls per human instruction:

```
(volume.tool_calls_total - volume.sidechain_tool_calls) /
volume.total_instructions
```

`volume.total_instructions` includes typed prompts and bare slash commands.
`volume.tool_calls_total` remains sidechain-inclusive for rate terms and
cross-source aggregation. `volume.sidechain_tool_calls` makes delegated volume
observable and is not itself scored.

`agentic.steering_leverage.actions_per_prompt` is published even when steering is
not graded. Its `state` is one of:

| State | Meaning |
|---|---|
| `withheld_unvalidated_band` | The steering band is not validated; the term is withheld. |
| `unmeasured_sidechain_labels` | Delegation was observed but sidechain calls cannot be labelled; the term is dropped. |
| `scored` | The term is measurable and the validated band is active. |

Dropped Steering weight is renormalized within Efficiency. The unmeasured-label
case is driven by observed delegation, not capability alone.

### Source coverage

The table above is the source-level coverage contract. Capability-specific AQ terms
drop and renormalize when a source cannot emit the required signal; they score zero
only when the signal is measurable and absent. `sidechain_label_state` is
corpus-wide: every contributing source must provide a trustworthy numerator for a
combined steering reading.

### Replay

`gnomon.scoring.replay.replay(payload)` recomputes from persisted scoring inputs;
it does not read local transcripts. It refuses payloads with incompatible counter
definitions, an `actions_per_prompt` basis before `TOP_LEVEL_ACTIONS_INPUTS_VERSION`, or a scoring window other
than the calibrated one-month window. Formula-version differences alone are
replayable.

Replay returns `aq_exactness`: single-source payloads are `exact`; multi-source
payloads report an approximate weighted-mean status. `profiles_by_source_status`
independently reports whether per-source profiles are exact or unavailable because
required historical bucket data was trimmed. Consumers must branch on these fields.

### Payload limit

Uploads are serialized and checked before POST against the 900 KiB ingest limit
(`900 * 1024` bytes). Oversized payloads raise `PayloadTooLarge`; they are never
silently truncated or uploaded partially.

### Payload time scales

| Field | Scope |
|---|---|
| `scoring_inputs_by_source[*].window`, `profile`, `profiles_by_source`, `source_usage` | Requested scoring window |
| `noticed_stats_monthly`, `scoring_inputs_by_source[*].monthly`, `source_usage_monthly` | Per calendar month evidence |

`profile.aq` is the canonical combined AQ. Per-source scores and their aggregate
diagnostic are not a replacement combined score.

## Execution target

Current formula:

```text
execution = 10 × (0.6 × out_pct + 0.4 × deleg_pct)
out_rate  = tool_churn_edit_write / max(active_hours, 0.1)
out_pct   = clamp(out_rate / TARGET)
```

Current `TARGET = 1000` tool-authored lines/hr. Treat as provisional calibration point.
