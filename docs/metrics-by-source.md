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

- **Rate terms are scored per tool call, not per session.** Test runs, review skills,
  ToolSearch, task planning, skills and compounding writes are `count / tool_calls_total`
  over the whole corpus — a Codex one-shot (~18 calls, ~2.7 min) is not one Claude session
  (~68 calls, ~37 min), and a per-session denominator let the short ones act as pure
  denominator. There is no per-source weighting: pooling both sides over the same unit
  already makes the corpus rate the tool-call-share-weighted mean of its sources' rates.
  A payload that omits `volume.tool_calls_total` scores those terms N/A (dropped and
  renormalized) rather than zero, so a legacy block does not publish a phantom collapse.
- **Capability dilution is a known limitation, not something rates correct.** The
  denominator is every tool call in the corpus, including calls from a source that could
  never emit the signal being scored — `available_caps` is a UNION, so one capable source
  keeps a term live for the whole corpus. Adding an OpenCode corpus alongside Claude lowers
  ToolSearch-based axes with no behavior change (measured: Token economy 1.00 -> 0.63).
  This predates the per-tool-call change and is unchanged by it; excluding an incapable
  source's calls from cap-gated denominators is tracked separately.
- **Planning practice** has authoritative root/child identity for Claude, Codex,
  Cursor, and OpenCode. Other active sources contribute unmeasured sessions (`U`) to
  coverage instead of forcing the measured `P/E` share to zero or unavailable.
- **Planning practice** counts plan mode as well as planning Skills, so the signal is
  reachable per source: Claude Code emits `ExitPlanMode`, Cursor's `create_plan` and
  `switch_mode(plan)` normalize to `EnterPlanMode`, and Codex has no plan mode but does
  reach the term through shell `SKILL.md` reads. Cursor cannot emit a first-class `Skill`
  at all, so plan mode is its only path in.
- Authoritative root/child identity does **not** imply the planning signal is reachable.
  OpenCode has the identity (so its eligible denominator accrues) but emits no plan-mode
  tool and no skill signal, so its numerator can never fire. It therefore lacks the
  `planning_signal` capability and both the **Planning practice** term and AQ
  **Discipline**'s planning term are dropped and renormalized for OpenCode-only corpora,
  rather than scored 0 on telemetry the source cannot produce. A source that *can* emit the
  signal and simply never planned still scores 0 — the cap keys off capability, not off the
  share being zero.
- `git_churn` is parser-independent once source yields a real `cwd`. Antigravity CLI yields a real
  `cwd` (from `trajectory_metadata_blob`); the IDE derives it best-effort from edit/command paths.
- Codex now counts `apply_patch` churn per file, so churn, deletions, and iteration depth are meaningful there.
- Gemini captures tool activity, thinking, tokens, and errors, but deletions stay partial because `write_file` has no old-string diff.
- Gnomon does not extract delegation signals from Gemini, Pi, or OpenCode, so the
  **Orchestration** AQ axis is dropped (caps lack `delegate`), not scored 0. OpenCode itself
  supports child sessions; their parent identity is still used to scope Planning practice.
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

Current runtime contract: **scoring inputs version 7**, **AQ version 7**, and **GStack version 7** (`score_contract_id = 7:7:7`). Previous-contract scores
must not be shown as improvement or regression against v6. AQ is blended as
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
  These feed the per-source profiles and model-routing eligibility; the corpus AQ's rate
  terms do NOT read them, since the per-tool-call denominator is the merged
  `volume.tool_calls_total`.
- `noticed_stats_monthly` — **per calendar month** evidence, one entry per month with its own `git_churn`, tokens, errors, etc.
- `scoring_inputs_by_source[*].monthly` — **per source per calendar month** raw scoring inputs.
- `profiles_by_source` / `profile` / AQ — **65/35 blended AQ** (65% recent
  30-day rolling + 35% full window); gstack/archetype/steering remain scoped
  to the requested full-window inputs.
- **One canonical combined AQ**: `profile.aq`, scored from the merged corpus.
  `profiles_by_source.by_source[*].aq` are per-source readings. The aggregate's
  weighted mean of per-source scores is published as
  `profiles_by_source.aggregate.aq_diagnostic` (with `canonical_aq: "profile.aq"`)
  and must not be displayed as a combined score: distinct counts are unions, so
  blending per-source scores under-counts breadth of tooling (7 MCP servers across
  three tools really is 7). Two combined numbers used to ship in the same payload.
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
