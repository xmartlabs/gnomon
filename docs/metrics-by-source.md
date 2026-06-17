# Metrics by source

This table is the source of truth for which parser captures which metric, and why.
Update it when a workstream task changes parser behaviour (see plan workstreams A–D).

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Working in current code |
| ❌ | Produces 0 / broken today |
| ❌→✅ | Broken today; fixed in this plan (task noted) |
| ⚠️ | Partial — works but with caveats |
| ⛔ | Irrecoverable by design |
| ➖ | Source-agnostic (does not depend on the parser) |

---

## Metric × source table

| Metric | Claude | Codex | Cursor | Gemini | Antigravity |
|---|---|---|---|---|---|
| total_sessions / total_prompts / tool_calls | ✅ | ✅ | ✅ | ✅ | ⛔ metadata-only count |
| git_churn (reads local disk) | ➖ ✅ | ➖ ✅ | ➖ ✅ | ❌→✅ (A3: cwd was None) | ⛔ |
| tool_churn (tool-authored output lines) | ✅ | ❌→✅ (A7: apply_patch) | ⚠️ twin-message dedup | ❌→✅ (A1: toolCalls parser) | ⛔ |
| └ deletions | ✅ | ❌→✅ (A7) | ✅ | ⚠️ write_file only → additions only | ⛔ |
| iteration_depth (edits per file) | ✅ | ✅ after A7 | ✅ | ❌→✅ (A1) | ⛔ |
| error_rate / error_recovery | ✅ | ✅ | ✅ | ❌→✅ (A1: tool_result is_error) | ⛔ |
| thinking_blocks | ✅ | ✅ (reasoning) | ✅ | ❌→✅ (A1: thoughts[]) | ⛔ |
| fanout / delegate_actions | ✅ | ❌→✅ (A6: subagent meta) | ✅ | ⛔ no subagent support | ⛔ |
| planning_ratio | ✅ | ✅ | ✅ | ❌→✅ (A1: canon tools + thinking) | ⛔ |
| model tokens | ✅ | ❌→✅ (A8: token_count event) | ❌→✅ (A4: bubble.tokenCount) | ❌→✅ (A2: tokens field) | ⛔ |
| skills (slash-command detection) | ✅ | ✅ bash-read pattern | ✅ | ✅ bash-read pattern | ⛔ |
| mcp_calls | ✅ | ❌ no `mcp__` prefix in Codex tool names | ✅ | ❌ no `mcp__` prefix | ⛔ |
| compounding_writes | ✅ | ✅ | ✅ | ✅ | ⛔ |
| active_hours | ✅ | ✅ | ✅ | ✅ | ⛔ |
| actions_per_prompt | ✅ | ✅ | ✅ | ❌→✅ (A1 required for tool_calls) | ⛔ |

---

## Cell-by-cell notes

### git_churn — source-agnostic (➖)

`git_churn` is computed by shelling out to `git log --numstat` on repos found in
`project_activity` (a per-session CWD tracker). It does not read the transcript
format at all, so it works the same regardless of source — **once the CWD is
known**. For Gemini, the parser previously set `cwd=None` (line 805 of the old
`_gemini_events`), so no repos were discovered → 0 git churn. Fix A3 extracts
`cwd` from `args.dir_path` / `args.file_path` / shell output, unblocking
git_churn for Gemini. Antigravity is ⛔ because transcripts live server-side;
the local process never sees a working directory.

### tool_churn / deletions — Codex (❌→✅ A7)

Codex emits `custom_tool_call` events with `name="apply_patch"`. The patch text
lives in `payload.input`, not in `arguments` (which was empty). The old parser
read `arguments` → empty → 0 tool churn. Fix A7 reads `payload.input`, parses
the unified-diff-like format (`*** Begin/End Patch`, `+`/`-` lines), and
reconstructs `new_string`/`old_string` so the existing churn accumulator
(line 1822-1825) sees real additions and deletions.

### tool_churn — Gemini (❌→✅ A1)

The old `_gemini_events` searched for tools in `content["functionCall"]` but the
actual format carries them in `m.toolCalls[]`. No tools were extracted → tool
churn, error_rate, recovery, planning_ratio, iteration_depth, and
actions_per_prompt were all 0 for every Gemini session. Fix A1 rewrites the
parser to follow the real shape.

### tool_churn deletions — Gemini (⚠️)

After A1, Gemini write operations map to `write_file` → canonical `Write`, which
captures additions only (file is created/overwritten, no old-string diff).
Deletions remain 0 for Gemini — this is a format limitation, not a parser bug.

### error_rate / error_recovery — Gemini (❌→✅ A1)

Tool results in Gemini transcripts are in `result[].functionResponse.response`.
Error flag: `status == "error"` or a truthy `response.error`. The old parser
never emitted `tool_result` events for Gemini → `tool_errors` and
`recovered_errors` were always 0. Fix A1 emits the correct `tool_result` events.

### thinking_blocks — Gemini (❌→✅ A1)

Thinking lives in `m.thoughts[]` (not a block type embedded in `content`). The
old parser never read this field. Fix A1 emits `{type: thinking}` events from
`thoughts[]`.

### model tokens — Codex (❌→✅ A8)

Codex emits `event_msg` events with `payload.type = "token_count"` containing
`info.total_token_usage` (cumulative). The main loop only read `msg.usage` from
assistant turns, which Codex does not set. Fix A8 handles the `event_msg`/
`token_count` path and maps `input_tokens`, `cached_input_tokens`,
`output_tokens`, `reasoning_output_tokens` to the Claude-shaped accumulator.

### model tokens — Cursor (❌→✅ A4)

Cursor SQLite rows include `bubble.tokenCount.{inputTokens, outputTokens}`.
The parser read bubble content but not `tokenCount`. Fix A4 reads the field
(guarded: only when non-zero) and emits a synthetic usage event attributed to
model `"cursor"`.

### model tokens — Gemini (❌→✅ A2)

Gemini assistant events carry `m.tokens.{input, output, cached, thoughts}`.
Fix A2 translates these to the Claude usage shape:
`input = tokens.input`, `output = tokens.output + tokens.thoughts`,
`cache_read = tokens.cached`, `cache_creation = 0`. Requires A1 to also emit
the `model` field (the accumulator is gated on `if mdl:`).

### fanout / delegate — Codex (❌→✅ A6)

Codex does not use a tool-call format for agent delegation; instead, subagent
spawns are recorded in `session_meta.payload.source.subagent.thread_spawn`.
Fix A6 reads that counter and feeds it into `delegate_actions`/`fanout` tracking.

### fanout / delegate — Gemini (⛔)

Gemini CLI does not support multi-agent / subagent patterns. The metric will
always be 0 / null for pure-Gemini corpora; this is accurate, not a parser bug.

### mcp_calls — Codex / Gemini (❌, no fix planned yet)

The MCP-call detector looks for tool names prefixed with `mcp__`. Codex and
Gemini do not use that naming convention for their tool outputs, so MCP usage
goes undetected even when those tools use MCP internally. No fix is in scope for
this plan — flagged for a future parser pass.

### Antigravity — all metrics (⛔)

Antigravity transcripts are processed server-side by the Antigravity service;
the local `paxel` process only receives metadata (session count, user info). No
tool calls, no token usage, no CWDs, no edits are available locally. All
tool-level metrics are irrecoverable for Antigravity sessions.

---

## Pendiente de calibración: TARGET del Execution score

El score **Execution** se reconstruyó (commits B1/B2) a:

```
execution = 10 × (0.6 × out_pct + 0.4 × deleg_pct)
out_rate  = tool_churn_edit_write / max(active_hours, 0.1)
out_pct   = clamp(out_rate / TARGET)
```

`TARGET` está **provisional en 1000** lines/hr autoradas (constante en `paxel.py`,
`compute_scores` y `_score_breakdown`, con comentario in-code).

**Por qué 1000 y por qué recalibrar:** se eligió ≈ p75-p90 de la distribución real
de `out_rate` en prod (2026-06, N=8: `min 405 · p50 619 · p75 985 · p90 1055`),
para que el score discrimine en vez de saturar. Pero esa distribución se calculó
**antes** de los fixes de parser de Codex (A7/A8) y Gemini (A1), que recuperan
tool_churn antes perdido → la distribución se inclina hacia arriba. **Recalibrar
`TARGET` a p75-p90 de la distribución post-fix** una vez que todos re-corran y
re-suban (estimado ~1.200-1.500).

Cómo recalibrar: re-correr `paxel.py` sobre la data real, juntar `out_rate` por
usuario del último mes, tomar p75-p90, actualizar la constante en los tres lugares.
