# Evaluación de métricas gnomon — ¿qué sirve para definir perfil de ingeniería?

> Contexto: task "Evaluar gnomon metrics" (relacionada a *3. Adaptación del perfil
> profesional*). Pregunta: de todo lo que reporta gnomon, ¿qué métricas dan mejor
> señal del perfil que buscamos definir, y sirve como feedback a bajo costo?

## TL;DR

Sí sirve como feedback a bajo costo, con tres condiciones:

1. **Usar las métricas medidas, no los scores.** Los números (counts, ratios) son
   deterministas y comparables; el archetype/AQ/tier es una rúbrica opinada — útil
   como conversación, no como evaluación.
2. **Mirar la progresión mensual, no los totales.** Con cuentas de USD 20 el límite
   mensual capea el volumen — el slope mes a mes es la señal honesta (ya implementado:
   `stats.json["progression"]["monthly"]`).
3. **El loop de feedback automatizado es opt-in vía `uvx xl-ai-insights`.** Corre
   el análisis local, sube `summary.json` a mirdash y abre el reporte
   directamente. Ese resumen incluye las 8 métricas medidas, `progression_monthly`,
   un bloque `profile` calculado y `noticed_stats` share-safe; no incluye prompts
   ni quotes verbatim.
   `python3 paxel.py` sigue siendo 100% local, cero red. Para el camino sin red:
   `python3 paxel.py --summary` y compartir `summary.json` manualmente (ver
   "Propuesta de uso" abajo).

## Métricas con mejor señal para perfil (en orden)

| Métrica | Qué revela | Por qué es robusta |
|---|---|---|
| `behavior.planning_ratio_explore_to_doing` | ¿Explora/planifica antes de producir, o dispara edits a ciegas? | Ratio interno, no depende del volumen ni del plan |
| `behavior.error_recovery_ratio` + `error_rate_per_100_tools` | Resiliencia: ¿se traba o recupera? | Normalizada por tool calls — comparable entre niveles de uso |
| `behavior.iteration_depth_*` | Grind: edits por archivo antes de commit. Mean bajo + p90 alto = sabe cuándo insistir | Distribución, no total |
| `velocity.git_churn_total` vs `tool_churn` | Lo que **realmente llegó a git** vs lo que el agente tocó. El ratio delata trabajo descartado | Gold standard: lee git, no transcripts |
| `behavior.fanout_median` + `delegate_actions` | ¿Orquesta agentes en paralelo o trabaja en serie? Madurez agentic real | Mediana — robusta a outliers |
| `stack.compounding_writes` | ¿Invierte en CLAUDE.md/AGENTS.md/memoria/ADRs? Señal de ingeniería que capitaliza | Count directo |
| `stack.skills_*` + `tools.mcp_servers_distinct` | Amplitud del ecosistema que domina | Ahora cross-CLI (ver fixes abajo) |
| `progression.monthly` | Evolución: adopción creciente, meseta, o abandono | Inmune al cap mensual del plan |

## Métricas que NO usar para comparar personas

- **AQ / tier / archetype** — rúbrica con pesos arbitrarios (30/35/20/15). Buena para
  auto-reflexión, mala para ranking.
- **Totales de volumen** (prompts, tool calls, horas) — miden cuánto usás el plan que
  pagás, no qué tan bien trabajás. Sesgo directo contra cuentas de USD 20.
- **Model mix** — mejoró (ahora ve GPT vía Codex), pero sigue premiando diversidad de
  modelos, que es función del presupuesto/acceso, no de skill.
- **Token economy** — desde v17 se puntúa solo por CLI-share. El término ToolSearch se
  eliminó del scoring (era ~94% carga determinista de herramientas `select:` forzada por
  el harness de deferred-tools, no una virtud del desarrollador, y su remanente deliberado
  es demasiado escaso para calibrarlo como tasa). El conteo crudo `toolsearch_calls` se
  sigue publicando como diagnóstico en el eje Tool command, pero ya no puntúa. Esto elimina
  el sesgo conocido en el que, con Claude presente, el término quedaba vivo para todo el
  corpus e incluía llamadas de fuentes que nunca podrían registrarlo.

## Sesgos conocidos (post-fixes de hoy)

| Sesgo reportado | Estado |
|---|---|
| "Pondera Claude" — Codex sin modelo en Model mix | **Arreglado**: modelo leído de `turn_context` (gpt-5.4 etc. ahora cuenta) |
| Codex no suma skills/tools | **Arreglado**: lecturas shell de `SKILL.md` cuentan como skill use; `update_plan`→TodoWrite; `write_stdin`→BashOutput |
| Toma toda la historia, sin progresión | **Arreglado**: bucketing mensual en stats/report/profile |
| No funciona en sandbox/self-hosted | **Arreglado**: `CLAUDE_CONFIG_DIR`/`CODEX_HOME` + flags `--<source>-dir=PATH` |
| No detecta Google Antigravity | **Arreglado**: el **CLI** se puntúa offline (prompts/tools/tokens/modelo, decoder protobuf stdlib). El **IDE** está encriptado → se lee llamando la API local del language server (sin dependencia externa) cuando hay uso en la ventana; aporta prompts/tools/thinking/timestamps reales/errores, pero el server enmascara modelo y tokens |
| Skill fluency sigue mejor leída en Claude | Abierto: `attributionSkill` es más preciso que el heurístico de shell-reads |

## Propuesta de uso como feedback a bajo costo

### Camino manual (local)

1. Cada persona corre `python3 paxel.py --no-open --summary --last=30d` 1×/mes (5 min,
   local) — la ventana hace cada summary comparable período a período, no acumulativo.
2. Comparte `summary.json`: exactamente las 8 métricas de la tabla de arriba +
   `progression.monthly` + `noticed_stats`, sin prompts ni quotes ni rúbrica — safe-to-share por
   construcción (no hace falta el `jq`).
3. En la 1:1 / retro se mira **el slope propio**, no la comparación entre personas:
   ¿sube planning_ratio? ¿baja error_rate? ¿aparecen compounding_writes?
4. El profile.html queda como artefacto personal/motivacional, no como evaluación.

### Camino automatizado (opt-in vía mirdash)

1. Cada persona corre `uvx --from git+https://github.com/xmartlabs/gnomon xl-ai-insights`
   1×/mes (~5 min). Una vez publicado en PyPI: `uvx xl-ai-insights`.
2. El comando corre `paxel.py` localmente, abre el navegador para un login rápido,
   sube `summary.json` a mirdash, y abre el reporte automáticamente.
3. En la 1:1 / retro se mira **el slope propio** en mirdash, no la comparación
   entre personas: ¿sube `planning_ratio`? ¿baja `error_rate`? ¿aparecen
   `compounding_writes`?
4. El `profile.html` local queda como artefacto personal/motivacional, no como
   evaluación.

### Camino alternativo (máxima privacidad, sin red)

1. Corre `python3 paxel.py --summary` (todo on-device, cero red).
2. Comparte `summary.json` manualmente: incluye exactamente las 8 métricas de la
   tabla de arriba, `progression_monthly`, `profile` y `noticed_stats`, sin prompts ni
   quotes verbatim (no hace falta el `jq`).
3. Mismo análisis en la 1:1 / retro: slope propio, no ranking entre personas.

Costo total (ambos caminos): ~5 min/persona/mes. Riesgo principal: tratar la rúbrica
como ranking — mitigado usando solo las métricas medidas.

## Rate denominators

AQ's rate terms (test runs, review skills, task planning, skills,
compounding writes) are `count / volume.tool_calls_total`, per TOOL CALL, not per
session. One session is not one unit of work across tools: on a measured corpus, Claude
sessions averaged ~68 tool calls and ~37 active minutes while one-shot `codex exec`
sessions averaged ~18 calls and ~2.7 minutes. A per-session denominator made the short
ones act as pure denominator — Verification read 34.4/35 on the Claude slice alone and
22.9/35 merged, for identical behavior.

The targets were recalibrated into per-tool-call units (see the constants at the top of
`gnomon/scoring/aq.py`, each with its p40/p50 band and sample size). There is no
per-source weighting: pooling numerator and denominator over the same unit already makes
the corpus rate the tool-call-share-weighted mean of the per-source rates, so it can
never land outside the range its sources span. Absolute volume still does not raise AQ,
because both sides of the ratio grow together.

A payload that omits `volume.tool_calls_total` scores those terms N/A — dropped and
renormalized — rather than 0, so a legacy or foreign block does not publish a phantom
collapse across six terms.

**Known limitation.** The denominator is every tool call in the corpus, including calls
from a source that could never emit the signal being scored, because `available_caps` is
a union: one capable source keeps a term live for all of it. Adding an OpenCode corpus
beside Claude therefore dilutes any capability-gated rate term (e.g. the Skill fluency and
Discipline skill/task-tool terms) with zero behavior change. This predates the per-tool-call
change and is unchanged by it. ToolSearch used to be the sharpest example of this bias
(Token economy 1.00 -> 0.63); v17 removed its rate term from scoring, so it no longer
contributes to the limitation.

## Disponibilidad de Planning practice

Planning practice publishes counted planning sessions (`P`), eligible
top-level sessions (`E`), unmeasured sessions (`U`), state, share, and coverage
for corpus, source, month, and rolling-window slices. It preserves
`0 <= P <= E`, computes `share = P/E`, and computes
`coverage = E/(E+U)`. State is `measured` for `E>0,U=0`, `partial` for
`E>0,U>0`, and `unmeasured` when no confirmed denominator exists. The term's
effective Planning weight is `0.25 * coverage`; unavailable evidence has zero
weight and the remaining Planning terms are renormalized.

`P` counts a session when it contains plan mode (`EnterPlanMode` /
`ExitPlanMode`) **or** a recognized planning Skill or subagent — either signal is
sufficient, and a session with both still counts once. The todo family
(`TodoWrite` / `TaskCreate`) is deliberately excluded: it is the agent's own
execution bookkeeping, it already earns Ordered planning readiness through the
`PLAN_MIN_STEPS` distinct-step gate, and it appears in a large majority of
sessions, so admitting it would saturate the term without any behavior change.
The wire field names still carry the historical `planning_skill_*` prefix; they
are the dashboard contract and are intentionally not renamed.
