# paxel-XL — Agentic Quotient + Codex fix

_Design spec · 2026-06-09 · fork local de `paxel-local` (`paxel.py`)_

## Objetivo

Forkear `paxel.py` a una copia local en `claude-workshop/` y agregarle dos cosas:

1. **AQ (Agentic Quotient)** — métrica nativa 0–100 de qué tan bien se usa el stack agéntico (multi-agentes, skills, MCP+CLI, orquestación), renderizada como **sección propia** en los 3 outputs.
2. **Fix del parser Codex** — los `user` messages inyectados (`<environment_context>`, etc.) se cuentan hoy como prompts humanos, inflando sesiones/prompts y hundiendo scores en runs multi-source.

Fuera de alcance: branding propio, archetypes nuevos, publicar a GitHub, sync con upstream.

## Contexto del código

- `paxel.py`, ~2.257 líneas, stdlib pura, single-file.
- Agregación de stats en `main()`; cuenta tools, `mcp_calls`, `top_skills`, `subagent_types`.
- `compute_scores(stats)` (~1510) → 3 ejes gstack. `pick_archetype`, `signature_moves`, `growth_edges`.
- `write_profile_html` (~1888), `write_report`, `stats.json` dump.
- Codex: `_codex_events(fp)` (~391). Bug en ~428: `if role == "user" and text: yield user event` — no filtra wrappers inyectados.

## Diseño

### 1. Data collection (en el loop de agregación de `main()`)

Sin re-parse — se calcula donde ya se recorren los tool_use. Agregar a `stats`:

- `stats["tools"]["mcp_servers"]`: `[(server, count), …]` — de `mcp__<server>__…` (split `__`, índice 1).
- `stats["tools"]["clis"]`: `[(cli, count), …]` — cuando `tool == "Bash"`, partir `command` por `&& || | ; then do`, tomar el head de cada parte (saltando `VAR=val`), quedarse si está en `KNOWN_CLIS`.
- `stats["tools"]["toolsearch_calls"]`: int.
- `stats["stack"]["skills_distinct"]`: int — largo del set completo de skills que paxel ya detecta (no solo el top-15 mostrado). **Usar la detección de skills existente de paxel** (`_skill_uses`), no un conteo nuevo, para consistencia con `top_skills`.

`KNOWN_CLIS` (set constante, top del módulo):
`git gh npm npx yarn pnpm bun python python3 pip pip3 node deno cargo go rg grep sed awk find curl wget jq docker kubectl make xcodebuild pod expo eas supabase vercel psql sqlite3 open cp mv rm mkdir ls cat chmod ssh brew tsc eslint prettier vitest jest pytest ruby swift ffmpeg`

### 2. `compute_aq(stats)` → dict

Nueva función, estilo `compute_scores`. Helper: `sat(x, t) = min(1.0, x / t)` (saturación lineal).

**Eje 1 — Multi-agent orchestration (peso 33)**
Intra-pesos vol .30 / div .25 / harness .20 / async .25
- `vol = sat(agent_runs, 400)`
- `div = sat(distinct_subagent_types, 8)`
- `harness = 1.0 si hay algún subagent type que matchee /harness|trisel/ , si no 0.6`
- `async = sat(background + scheduled, 200)`
- `axis01 = .30*vol + .25*div + .20*harness + .25*async`

**Eje 2 — Skill fluency (peso 22)**
Intra .40 / .30 / .30
- `distinct = sat(skills_distinct, 40)`
- `volume = sat(total_skill_signal, 1500)` — `total_skill_signal` = suma de los counts de uso de skills que ya produce `_skill_uses`
- `meta = 1.0 si hay alguna de {subagent-driven-development, brainstorming, writing-plans, cerberus, systematic-debugging}, si no 0.6`

**Eje 3 — Tool command MCP+CLI (peso 28)**
Intra .40 / .40 / .20
- `mcp = sat(len(mcp_servers), 15)`
- `cli = sat(len(clis), 40)`
- `ts = sat(toolsearch_calls, 300)`

**Eje 4 — Orchestration discipline (peso 17)**
Intra .60 / .40
- `tasks = sat(TaskCreate + TaskUpdate, 1500)`
- `plan = 1.0 si writing-plans/plan skill presente, si no 0.6`

**Salida:**
```
{
  "aq_0_100": round(sum(axis_i * weight_i)),
  "tier": "Operator|Power User|Orchestrator|Systems Builder",
  "axes": [{"name","weight","score","signals":{…}}, …],
  "mcp_vs_cli": {"cli_calls","cli_distinct","mcp_calls","mcp_distinct","ratio"},
  "tool_diversity": {"distinct","entropy"}
}
```
Tiers: Operator <40 · Power User 40–60 · Orchestrator 60–80 · Systems Builder 80–100.

**Resultado esperado con la data real (claude-only):** ejes ≈ 33 / 22 / 26 / 15 → **AQ ≈ 95, Systems Builder**. (Supera la estimación a mano previa de 90 del one-pager por intra-pesos distintos; el one-pager HTML se reconcilia al número de la tool al implementar.) `mcp_vs_cli` ≈ 9.194 CLI / 41 vs 1.984 MCP / 12, ratio 4.6:1.

`mcp_vs_cli` y `tool_diversity` son **descriptivos, no calificados** (como Steering) — no entran al score, se muestran como contexto.

### 3. Fix Codex (`_codex_events`, ~428)

Cuando `role == "user"` y hay `text`, descartar wrappers inyectados antes de emitir el evento:
- texto que arranca con `<environment_context` o `<user_instructions`
- texto cuyo contenido (sin tags) es solo metadata de entorno (`cwd`, `shell`, `<cwd>`, `<shell>`)

Helper `_codex_is_injected(text) -> bool`. Si es inyectado → no emitir (o emitir como tipo no-prompt). Mensajes humanos reales pasan intactos.

### 4. Render (3 outputs)

- **`profile.html`** (`write_profile_html`): sección AQ nueva después del scorecard — número grande + badge de tier + 4 barras de progreso + split bar MCP-vs-CLI + nota tool diversity. CSS/markup reusado de `claude-workshop/paxel-onepager.html`.
- **`report.md`** (`write_report`): bloque `## Agentic Quotient (AQ)` con tabla de ejes + split + tool diversity.
- **`stats.json`**: `stats["agentic"] = compute_aq(stats)`.

## Verificación (por paso)

1. **Data collection:** re-run `python3 paxel.py claude --no-open`; `stats.json` tiene `tools.mcp_servers` (12), `tools.clis` (41), `tools.toolsearch_calls` (308), `stack.skills_distinct` (39).
2. **compute_aq:** `stats["agentic"]["aq_0_100"]` presente y en [0,100]; tier coherente; 4 ejes suman al total; `mcp_vs_cli.ratio` ≈ 4.6.
3. **Render:** `report.md` tiene bloque AQ; `profile.html` renderiza la sección (grep del número + barras); abrir y ver.
4. **Fix Codex:** re-run all-sources `python3 paxel.py --no-open`; el prompt más repetido **NO** es `environment_context`; `total_prompts` cae a un valor sano; archetype/scores con codex se acercan al claude-only.
5. **No-regresión:** claude-only mantiene Execution 10.0 / Planning 10.0 / Engineering 8.8 y sessions=221, prompts=1.655.

## Notas

- `claude-workshop/` no es repo git → el spec no se commitea salvo `git init`. Decisión pendiente del usuario.
- Atribución: la copia conserva el header/LICENSE original de paxel (autor Max Schilling).
