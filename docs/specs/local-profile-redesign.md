# Spec — Rediseño del perfil local (`profile.html`)

Fuente: `docs/adr/local-profile-redesign.md` (ADR 1–21). Vocabulario del glosario de ese doc.

## Problema

Quien corre `xl-ai-insights --local` recibe una página larga que no contesta rápido lo que vino a buscar: cómo trabaja con agentes y qué mejorar. El nivel (AQ) está calculado sobre todo el historial, así que casi no se mueve mes a mes y no coincide con el número que la misma persona ve en el dashboard. Los conteos, los scores y las curiosidades están mezclados en cards iguales, dos sistemas de score compiten con el mismo peso y hacen falta disclaimers para explicarlos. Además, la página lleva la marca del upstream (Roadmap, paxel-local) y un estilo que no es el del resto de gnomon. Al compartirla, el usuario promociona otro proyecto.

## Alcance

Incluye:
- Nueva estructura de `profile.html` en este orden: masthead, hero, tendencia, diagnóstico (How you work | What to work on), desglose AQ, Actividad, Retrato, footer (ADR 20).
- Lenguaje visual del design system v2: tokens, tipografía y reglas, sin cards ni gradientes.
- Período único: el mes calendario en curso, parcial y etiquetado. Es el nuevo default de `--local`.
- AQ del mes en curso como titular, con delta vs el mes anterior y tendencia de 6 meses.
- Composición de modelos del mes en Actividad.
- Póster PNG rediseñado; X y copy de caption se mantienen.
- Marca gnomon, fuentes embebidas, dark mode con toggle y estados vacíos explicados.

NO incluye:
- Cambios en `summary.json`, `stats.json` o `report.md` más allá de lo que la página necesite. El contrato de upload no cambia.
- Evolución de modelos por mes (columnas apiladas) ni guardar el total de turnos por mes.
- Sacar gstack del perfil o eliminar menciones a gstack dentro del texto de los edges.
- Traducción al español o i18n.
- Crédito al upstream dentro del perfil; queda en README y LICENSE.
- Fallback al mes anterior cuando el mes en curso tiene poco volumen.
- Cambios en el dashboard self-hosted.

## Criterios de aceptación

Salvo que se diga otra cosa, "una corrida local" es `--local` sobre los fixtures del smoke test, con la fecha actual fijada dentro del rango de los fixtures, y los criterios se observan en el `profile.html` resultante (DOM y el JSON del póster embebido).

### ADDED

**Período**
- [ ] Given una corrida local sin flags de ventana, When se genera el perfil, Then el hero muestra el mes calendario en curso con la etiqueta "in progress" y la cantidad de días transcurridos.
- [ ] Given actividad en el mes en curso y en meses anteriores, When se genera el perfil, Then los conteos de Actividad cuentan solo eventos del mes en curso.
- [ ] Given actividad en el mes en curso y en meses anteriores, When se genera el perfil, Then moves, edges, composición de modelos, curiosidades y quotes se derivan solo del mes en curso.
- [ ] Given una corrida con `--since`, `--until` o `--last`, When se genera el perfil, Then el período mostrado es el pedido por el flag y no el mes en curso.

**Hero**
- [ ] Given un AQ calculado para el mes en curso, When se genera el perfil, Then el titular muestra el tier y el AQ de ese mes.
- [ ] Given AQ del mes en curso y del mes anterior, When se genera el perfil, Then el hero muestra el delta con signo y un glifo de dirección (▲/▼), no solo color.
- [ ] Given que no hay AQ del mes anterior, When se genera el perfil, Then en lugar del delta aparece "first month" en gris.
- [ ] Given un scorecard gstack, When se genera el perfil, Then Execution, Planning y Engineering aparecen en el hero con un tamaño de figura menor que el del AQ.
- [ ] Given un AQ con pilares, When se genera el perfil, Then el hero muestra la frase del pilar más flojo que produce `pick_archetype`.
- [ ] Given una corrida local, When se genera el perfil, Then los botones Post on X, Copy caption y Download image están en el hero.

**Tendencia**
- [ ] Given actividad en 6 o más meses, When se genera el perfil, Then la tendencia muestra 6 columnas de AQ: el mes en curso y los 5 anteriores.
- [ ] Given actividad en menos de 6 meses, When se genera el perfil, Then la tendencia muestra solo los meses con actividad.
- [ ] Given una tendencia generada, When se muestra, Then la columna del mes en curso está marcada como "in progress".
- [ ] Given un corpus con más de una fuente, When se genera la tendencia, Then los valores mensuales se marcan como aproximados.
- [ ] Given un corpus de una sola fuente, When se genera la tendencia, Then los valores no llevan la marca de aproximado.
- [ ] Given un corpus de una sola fuente, When se compara el AQ titular con el de `xl-ai-insights` para el mismo mes y los mismos transcripts, Then los dos valores son iguales.

**Diagnóstico**
- [ ] Given signature moves que pasan su gate en el mes, When se genera el perfil, Then "How you work" muestra como mucho 3, cada uno con su tag de etapa.
- [ ] Given growth edges en el mes, When se genera el perfil, Then "What to work on" muestra como mucho 3, en el orden de urgencia de `growth_edges_structured`.
- [ ] Given un edge con `axis` de un eje del AQ, When se muestra, Then su tag de origen es "<Pilar> · <Eje>".
- [ ] Given un edge con `axis` de un eje del AQ, When se muestra el desglose, Then ese eje aparece marcado.
- [ ] Given un edge con `axis` nulo, When se muestra, Then su tag de origen es "gstack · <dimensión>".
- [ ] Given una corrida local, When se genera el perfil, Then "What to work on" no contiene la nota sobre /commands de gstack.

**Desglose AQ**
- [ ] Given un AQ con 4 pilares, When se genera el perfil, Then los 12 ejes se muestran con barra y valor, sin controles de plegado.
- [ ] Given un AQ con 4 pilares, When se genera el perfil, Then no aparecen los pesos de los pilares, ni como número ni como porcentaje.

**Actividad**
- [ ] Given uso de modelos en el mes, When se genera el perfil, Then "Models used" lista cada modelo con su % de turnos y la cantidad de turnos, ordenados de mayor a menor.
- [ ] Given una corrida local, When se genera Actividad, Then incluye volumen (git, Edit/Write, shell), agentes, errores con % de recovery, máximo de ediciones sobre un archivo y go-to tool.
- [ ] Given una corrida local, When se genera Actividad, Then incluye Steering, MCP vs CLI y tool diversity, rotulados como no calificados.

**Retrato**
- [ ] Given una corrida local, When se genera el Retrato, Then contiene las 6 curiosidades: best time, weekends, prompt length, teammate/tool, politeness, longest run.
- [ ] Given candidatas de quote en el mes, When se genera el Retrato, Then aparecen go-to prompt, crash-out y off-the-cuff, y las dos últimas tienen reroll si su pool tiene más de una.

**Estados vacíos**
- [ ] Given 0 signature moves en el mes, When se genera el perfil, Then "How you work" muestra una línea gris que explica que ningún move pasó su gate.
- [ ] Given 0 growth edges en el mes, When se genera el perfil, Then "What to work on" muestra una línea gris explicativa.
- [ ] Given un eje del AQ que se cae por falta de datos de la fuente, When se muestra el desglose, Then ese eje dice "not measured for this source" en gris.
- [ ] Given un tipo de quote sin candidatas en el mes, When se genera el Retrato, Then su card aparece con una línea gris que explica la ausencia.
- [ ] Given cualquier estado vacío, When se muestra, Then no usa el color negativo (`--negative`).

**Tema**
- [ ] Given un sistema en modo oscuro y nada guardado en `localStorage["gn-theme"]`, When se abre el perfil, Then se pinta con los tokens dark antes del primer paint.
- [ ] Given que el usuario usa el toggle, When reabre el perfil en el mismo browser, Then se respeta el tema elegido.
- [ ] Given `localStorage` no disponible, When se abre el perfil, Then se aplica el tema del sistema sin errores en consola.

**Share**
- [ ] Given cualquier tema de la página, When se descarga la imagen, Then el póster sale con la paleta clara.
- [ ] Given una corrida local, When se descarga la imagen, Then el póster contiene tier, AQ del mes, delta, los 4 pilares, 2–3 moves y como mucho 1 quote.
- [ ] Given que el usuario hizo reroll de la quote off-the-cuff, When descarga la imagen, Then el póster usa la quote visible en ese momento.

**Fuentes**
- [ ] Given una corrida local, When se inspecciona el perfil, Then no hay ninguna URL externa de fuentes ni de hojas de estilo.
- [ ] Given una corrida local, When se inspecciona el perfil, Then Archivo e IBM Plex Mono están declaradas vía `@font-face` con datos embebidos.
- [ ] Given una instalación vía `uvx --from git+…`, When se corre `--local`, Then el perfil se genera con las fuentes embebidas y sin error por archivos faltantes.

### MODIFIED

- [ ] [antes] Given una corrida local sin flags de ventana, When se genera el perfil, Then todo se calcula sobre el historial completo.
      [ahora] Given una corrida local sin flags de ventana, When se genera el perfil, Then todo se calcula sobre el mes calendario en curso, salvo la tendencia (6 meses).
- [ ] [antes] Given un AQ, When se genera el perfil, Then el titular es el tier del AQ del historial completo.
      [ahora] Given un AQ, When se genera el perfil, Then el titular es el tier del AQ del mes en curso.
- [ ] [antes] Given progresión mensual, When se genera el perfil, Then "Your trajectory" muestra tool calls por mes.
      [ahora] Given progresión mensual, When se genera el perfil, Then la tendencia muestra AQ por mes.
- [ ] [antes] Given un scorecard gstack, When se genera el perfil, Then tiene sección propia con barras, notas y un disclaimer.
      [ahora] Given un scorecard gstack, When se genera el perfil, Then aparece como 3 figuras en el hero, sin sección ni disclaimer.
- [ ] [antes] Given una corrida local, When se genera el perfil, Then las 12 cards de "What we noticed" van en una grilla única.
      [ahora] Given una corrida local, When se genera el perfil, Then los conteos van en Actividad y los rasgos en el Retrato.
- [ ] [antes] Given una corrida local, When se inspecciona el perfil, Then el masthead, el `<title>`, el póster, el caption y el footer dicen Roadmap o paxel y linkean a roadmap.chat o a `Photobombastic/paxel-local`.
      [ahora] Given una corrida local, When se inspecciona el perfil, Then esos lugares dicen gnomon, linkean solo a `xmartlabs/gnomon`, y no aparecen "Roadmap", "paxel" ni "Max Schilling".
- [ ] [antes] Given una corrida local, When se descarga la imagen, Then el póster usa la paleta coral y el scorecard gstack como bloque central.
      [ahora] Given una corrida local, When se descarga la imagen, Then el póster usa la paleta y las fuentes del v2, con el AQ y los pilares como bloque central.
- [ ] [antes] Given una corrida local, When se genera el perfil, Then los signature moves muestran hasta 5.
      [ahora] Given una corrida local, When se genera el perfil, Then "How you work" muestra hasta 3.
- [ ] [antes] Given un tipo de quote sin candidatas, When se genera el perfil, Then esa card no aparece.
      [ahora] Given un tipo de quote sin candidatas, When se genera el perfil, Then la card aparece con una línea gris explicativa.
- [ ] [antes] Given un AQ, When se genera el perfil, Then cada pilar muestra su peso ("/ 30 weight").
      [ahora] Given un AQ, When se genera el perfil, Then ningún pilar muestra peso.

#### Delta 2026-09-30 (ADR 22 y 23)

- [ ] [antes] Given un corpus de una sola fuente, When se compara el AQ titular con el de `xl-ai-insights` para el mismo mes y los mismos transcripts, Then los dos valores son iguales.
      [ahora] Given un corpus de una sola fuente y un mes cerrado, When se compara el AQ de ese mes en el perfil con el de `xl-ai-insights`, Then los dos valores son iguales. Para el mes en curso no se exige igualdad: el upload usa 30 días móviles (ADR 22).
- [ ] Given un AQ, When se muestra el desglose, Then cada eje muestra su valor en escala 0–100 y ningún texto revela el máximo del eje.
- [ ] Given un edge "Add a reflex" o "Stop the grind", When se muestra, Then su tag de origen es "gstack · Engineering". Given "Go deeper", Then es "gstack · Balanced".
- [ ] Given un edge con `axis` de un eje del AQ, When se muestra en el perfil, Then su consejo no contiene "is your thinnest AQ signal".
- [ ] Given un AQ con pilares, When se genera el perfil, Then la frase del hero dice "thinnest pillar" y no contiene "thinnest axis".
- [ ] Given un corpus con más de una fuente, When se genera la tendencia, Then cada valor mensual aproximado lleva el prefijo "≈" y debajo de la gráfica hay una línea que lo explica.
- [ ] Given una corrida local, When se genera el Retrato, Then la sección de rasgos se titula "Curiosities".
- [ ] Given una corrida local, When se descarga la imagen, Then el póster no contiene el scorecard gstack ni la frase del pilar.
- [ ] Given más llamadas MCP que CLI, When se muestra la lectura MCP vs CLI, Then el texto no dice "CLI-first".

#### Delta 2026-10-01 (ADR 24)

- [ ] Given una corrida local, When se genera el hero, Then el label del AQ es "AQ", sin mes.
- [ ] [antes] Given un corpus multi-fuente, When se genera la tendencia, Then los valores aproximados llevan "≈" y una nota.
      [ahora] Given cualquier corpus, When se genera la tendencia, Then se titula "AQ evolution by month", no muestra cantidad de meses ni texto lateral, y no contiene "≈" ni "approximate".
- [ ] Given una corrida local, When se genera el desglose, Then se titula "Agentic Quotient · 4 pillars" y no contiene la frase de escala 0–100.
- [ ] Given una corrida local, When se genera el footer, Then dice "Built by Xmartlabs" con el isotipo y linkea a xmartlabs.com, y no contiene "Raw metrics" ni el link al repo.
- [ ] Given más de 5 modelos en el período, When se genera "Models used", Then hay 5 filas más una fila "Others" con la suma del resto. Given una entrada `<synthetic>`, Then no aparece y no cuenta en el total.
- [ ] Given `--since` y `--until` que cubren exactamente un mes calendario, When se genera el perfil, Then el período se rotula como ese mes ("Sep 2026").

#### Delta 2026-10-01b (ADR 25)

- [ ] [antes] Given una corrida local, When se genera la página, Then el orden es hero, tendencia, diagnóstico, desglose, Activity, Portrait.
      [ahora] Given una corrida local, When se genera la página, Then el orden es hero, diagnóstico, desglose, tendencia + next level, models + readings, Activity, Portrait.
- [ ] Given un AQ por debajo de 88, When se genera la tendencia, Then a la derecha dice cuántos puntos faltan para el próximo tier, con el piso del tier actual y el del siguiente. Given un AQ ≥ 88, Then dice que Elite es el nivel más alto.
- [ ] Given una corrida local, When se genera Activity, Then muestra exactamente cinco conteos, en este orden: lines committed to git, subagents, prompts, sessions, errors.
- [ ] Given una corrida local, When se genera la página, Then no aparecen Steering, líneas vía Edit/Write, líneas en el shell, "How much did you ship?", máximo de ediciones ni go-to tool.
- [ ] Given AQ con lecturas, When se genera la fila de modelos, Then a la derecha va MCP vs CLI arriba y Tool diversity abajo.

### REMOVED

- [ ] La card "Which model do you reach for?". La reemplaza "Models used". No hay datos que migrar: el perfil se regenera en cada corrida.
- [ ] La frase de volumen del hero ("N reasoning blocks … N subagents … N errors recovered"). Los números siguen en Actividad.
- [ ] La franja de 5 números del hero. Pasa a Actividad.
- [ ] Los disclaimers entre gstack y AQ, y la nota "the slope is the honest signal".
- [ ] La gráfica de tool calls por mes. Los datos siguen en `stats.json` (`progression.monthly`).
- [ ] Las fuentes Merriweather y Josefin Sans y la paleta coral.
- [ ] Los `profile.html` generados antes no se tocan. La próxima corrida los sobrescribe en su output dir, como hoy.

## Decisiones abiertas

- **Cómo cortar la entrega** (ADR, abierta). Motor (AQ mensual, default de período, delta, tendencia) vs HTML (estructura, póster, fuentes, tema). Lo decide `/to-tickets`.
- **Cómo se obtiene el AQ de cada mes de la tendencia**: reusar los `scoring_inputs` mensuales y el replay, o puntuar cada mes con su propia acumulación. Tiene que cumplir el criterio de igualdad con `xl-ai-insights` en una sola fuente.
- **Cómo fijar la fecha actual en los tests**: los fixtures tienen fechas pasadas, y con el nuevo default una corrida sin ventana sobre ellos queda vacía.
- **Texto exacto de cada estado vacío** por gate de move, edge y quote.
- **Umbral de "aproximado"** en la tendencia: si se marca por mes o para toda la gráfica.

## Rollback

El cambio no escribe datos persistentes nuevos. `stats.json` y `summary.json` mantienen su forma, y `profile.html` se regenera en cada corrida. Revertir el commit (o los commits) vuelve al perfil anterior en la próxima corrida. El único cambio visible fuera del HTML es el default de período de `--local`: si hay que desarmarlo sin revertir el rediseño, el mismo perfil se puede generar con `--since` desde el inicio del historial. La clave `localStorage["gn-theme"]` que deja el toggle es inocua para el perfil viejo, que la ignora.
