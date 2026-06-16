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
   directamente. Ese resumen incluye las 8 métricas medidas, `progression_monthly`
   y un bloque `profile` calculado; no incluye prompts ni quotes verbatim.
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
- **Token economy (ToolSearch)** — señal exclusiva de Claude Code; lee 0 para el resto.

## Sesgos conocidos (post-fixes de hoy)

| Sesgo reportado | Estado |
|---|---|
| "Pondera Claude" — Codex sin modelo en Model mix | **Arreglado**: modelo leído de `turn_context` (gpt-5.4 etc. ahora cuenta) |
| Codex no suma skills/tools | **Arreglado**: lecturas shell de `SKILL.md` cuentan como skill use; `update_plan`→TodoWrite; `write_stdin`→BashOutput |
| Toma toda la historia, sin progresión | **Arreglado**: bucketing mensual en stats/report/profile |
| No funciona en sandbox/self-hosted | **Arreglado**: `CLAUDE_CONFIG_DIR`/`CODEX_HOME` + flags `--<source>-dir=PATH` |
| No detecta Google Antigravity | **Parcial**: detectado + count de conversaciones y rango de fechas. Los transcripts viven server-side — no hay data local para puntuar honestamente |
| Skill fluency sigue mejor leída en Claude | Abierto: `attributionSkill` es más preciso que el heurístico de shell-reads |

## Propuesta de uso como feedback a bajo costo

### Camino manual (local)

1. Cada persona corre `python3 paxel.py --no-open --summary --last=30d` 1×/mes (5 min,
   local) — la ventana hace cada summary comparable período a período, no acumulativo.
2. Comparte `summary.json`: exactamente las 8 métricas de la tabla de arriba +
   `progression.monthly`, sin prompts ni quotes ni rúbrica — safe-to-share por
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
   tabla de arriba, `progression_monthly` y el bloque `profile`, sin prompts ni
   quotes verbatim (no hace falta el `jq`).
3. Mismo análisis en la 1:1 / retro: slope propio, no ranking entre personas.

Costo total (ambos caminos): ~5 min/persona/mes. Riesgo principal: tratar la rúbrica
como ranking — mitigado usando solo las métricas medidas.
