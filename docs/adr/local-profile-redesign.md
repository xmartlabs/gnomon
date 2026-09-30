# Decisiones — Rediseño del perfil local (`profile.html`)

2026-09-29 · Sesión de brainstorming

Prototipo de referencia (datos de ejemplo, estructura anterior a los ADR 2–21): https://claude.ai/artifact/WELDY2Mz3DkXuzvdemd56D

---

## ADR 1 — El rediseño toca solo `profile.html`

**Contexto**
`xl-ai-insights --local` escribe `stats.json`, `report.md`, `narrative_input.md`, `profile.html` y, con `--summary`, `summary.json` (`gnomon/cli/local.py:592`). El único que ve una persona es `profile.html`, que arma `gnomon/output/profile_html.py`.

**Decisión**
El objeto de la feature es `profile.html`. Los otros archivos cambian solo si un ADR de abajo lo exige para alimentar la página, por ejemplo el AQ mensual.

**Alternativas consideradas**
- Rediseñar `summary.json` o `report.md` → son salidas para máquinas o insumos del upload a mirdash. Cambiarlos toca el contrato de scoring y el ingest, que es otra conversación.

**Consecuencias**
- ➕ El alcance queda acotado a lo que ve el usuario.
- ➖ Cualquier dato nuevo que la página necesite tiene que salir de `stats` sin romper lo que ya consume `summary.json`.

---

## ADR 2 — Se rediseña la estructura completa del perfil sobre el design system v2

**Contexto**
El dashboard self-hosted ya migró al design system v2 "instrument" (`docs/design/design-system-v2/`, `docs/design/design-system.md`). `profile.html` sigue con la estética heredada del upstream: cards con borde de color, gradientes, Merriweather y Josefin. En la primera vuelta se decidió solo reskinnear y después recomponer copiando `PersonProfile.jsx`. Con el prototipo en la mano, el usuario concluyó que el problema es la estructura y no solo el estilo.

**Decisión**
Se redefine qué contiene la página y en qué orden (ADR 3–21). Tokens, tipografía, componentes y reglas visuales salen del v2 sin cambios: sin cards, sin gradientes, jerarquía por tamaño de tipo y aire, hairlines, grids asimétricos y números en mono con `tabular-nums`.

**Alternativas consideradas**
- Reskin (misma estructura, tokens v2) → el resultado queda "parecido pero no igual" al dashboard y no resuelve que la página intente servir a tres lectores a la vez.
- Recomposición copiando `PersonProfile.jsx` → se prototipó y no convenció. Ese perfil es para el lead que mira al equipo, no para el dev que se mira a sí mismo.
- Paridad total con el perfil del dashboard → pierde quotes y moves, que es lo más personal, y obliga a un build de React dentro de un CLI que es stdlib pura.

**Consecuencias**
- ➕ El perfil local y el dashboard se leen como el mismo producto.
- ➕ Las reglas del v2 ("no cards", "missing data is grey") resuelven de antemano muchas discusiones de diseño.
- ➖ Es una reescritura de `profile_html.py`, no un cambio de CSS.

---

## ADR 3 — El lector principal es el dev que se mira; el que comparte es secundario

**Contexto**
Hoy la página sirve a la vez para autodiagnóstico, para compartir en redes y, de hecho, como preview de lo que verá el lead en el dashboard.

**Decisión**
Todo se ordena para el dev que quiere saber cómo trabaja con agentes y qué mejorar. Compartir es un caso secundario, resuelto con un bloque chico de share (ADR 13).

**Alternativas consideradas**
- Optimizar para compartir → convierte la página en un "wrapped" y entierra el diagnóstico.
- Tratarla como preview del dashboard → el dashboard ya tiene su perfil para el lead; imitarlo vuelve a hacer del local una copia.

**Consecuencias**
- ➕ Hay un criterio para decidir qué va arriba.
- ➖ Lo social queda en un segundo plano visual.

---

## ADR 4 — Diagnóstico arriba, retrato acotado y separado abajo

**Contexto**
La página actual mezcla métricas con curiosidades ("¿cuántas veces dijiste gracias?", "tu crash-out"). El v2 es un lenguaje de instrumento de medición.

**Decisión**
La parte de arriba es diagnóstico: nivel, tendencia, qué hacés y qué mejorar, desglose. Abajo, en una sección separada, va el retrato: curiosidades y quotes.

**Alternativas consideradas**
- Diagnóstico puro, sin curiosidades → le quita identidad al perfil local y el motivo para compartirlo; es lo único que el dashboard no tiene.
- "Wrapped" primero → contradice ADR 3.

**Consecuencias**
- ➕ Nadie confunde una curiosidad con una métrica.
- ➖ Obliga a clasificar cada bloque existente (ADR 11).

---

## ADR 5 — El AQ es el score protagonista; gstack va chico en el hero

**Contexto**
gnomon produce dos scores independientes: el AQ (0–100, tier, 4 pilares, 12 ejes, contrato versionado) y el scorecard gstack (Execution, Planning, Engineering, 0–10). Hoy tienen secciones de peso parecido y un disclaimer largo que explica la diferencia.

**Decisión**
El AQ es el diagnóstico. gstack aparece como tres números en tamaño menor en el hero, al lado del AQ, sin sección propia.

**Alternativas consideradas**
- Los dos como pares → obliga a explicar la diferencia cada vez; es el disclaimer que el usuario ya había recortado.
- Sacar gstack del perfil → el README vende "dos scores" como feature; es una decisión de producto que excede este rediseño.
- gstack como anexo debajo del desglose del AQ, junto a las lecturas sin nota → propuesta recomendada que el usuario descartó en favor del hero (ver "Decisiones que quedaron abiertas").

**Consecuencias**
- ➕ Desaparece el disclaimer largo entre los dos sistemas.
- ➖ El hero tiene que mostrar gstack sin que compita con el AQ: la jerarquía de tamaños es una restricción de diseño.

---

## ADR 6 — "What to work on" va arriba, con tag de origen y el eje marcado en el desglose

**Contexto**
`growth_edges_structured()` (`gnomon/scoring/insights.py:339`) devuelve hasta 3 edges ordenados por urgencia. Cada uno trae `axis` si sale de un eje del AQ, o `None` si sale de gstack.

**Decisión**
Los edges tienen su propia sección arriba. Cada uno muestra su origen como tag ("Craft · Verification" o "gstack · Engineering"). En el desglose del AQ se marcan los ejes que tienen un edge.

**Alternativas consideradas**
- Sección propia sin referencias → el consejo queda desconectado del número que lo justifica.
- Edges solo adentro del desglose → los edges de gstack no tienen eje donde colgarse y "qué mejorar" queda escondido entre 12 barras.

**Consecuencias**
- ➕ La conclusión está arriba y la evidencia es trazable.
- ➖ Requiere que el desglose esté siempre visible (ADR 8).

---

## ADR 7 — Los signature moves van arriba como "How you work", en par con los edges

**Contexto**
Los signature moves son 8 patrones con un gate cada uno (`_signature_moves_pool()` en `insights.py`). Se muestran hasta 5 y citan solo números. No todos son fortalezas: "You live in the shell" o "You direct, you don't deliberate" son estilo neutro. Cada uno lleva el tag de una etapa de gstack.

**Decisión**
Van arriba en dos columnas, "How you work" (3 moves) | "What to work on" (3 edges), titulados como estilo y no como "lo que hacés bien". Conservan su tag de etapa.

**Alternativas consideradas**
- Llevarlos al retrato → los mezcla con curiosidades, contra ADR 4.
- Sacarlos → el diagnóstico queda como un reporte de errores, sin contrapeso.

**Consecuencias**
- ➕ El diagnóstico muestra estilo y mejoras juntos.
- ➖ Con 0 moves la columna izquierda queda vacía; se resuelve con ADR 21.

---

## ADR 8 — El desglose del AQ se ve entero y sin pesos

**Contexto**
El AQ tiene 4 pilares y 12 ejes: Breadth 4, Craft 4, Efficiency 2, Savvy 2 (`gnomon/scoring/aq.py:683`). Los pesos (30/35/20/15) se mostraban en la página, y el usuario los sacó a mano en el prototipo.

**Decisión**
Los 4 pilares y sus 12 ejes están siempre visibles, con barra y valor, sin plegar. No se muestran los pesos de los pilares.

**Alternativas consideradas**
- Pilares visibles y ejes plegados → rompe la marca cruzada de ADR 6 y la regla v2 de "actions visible at rest".
- Mostrar solo los ejes que importan → alguien tiene que definir y mantener qué importa, y el lector no entiende por qué ve unos y no otros.

**Consecuencias**
- ➕ Todo edge apunta a algo visible.
- ➖ Es la sección más densa de la página.

---

## ADR 9 — El AQ titular es el del mes en curso, con delta y tendencia mensual

**Contexto**
`--local` sin flags lee todo el historial y calcula un solo AQ (`local.py:485`). El dashboard muestra un AQ por mes. La misma persona ve dos números distintos. La corrida ya arma `scoring_inputs` por mes (`_scoring_monthly_full`, `local.py:459`), y `gnomon/scoring/replay.py` sabe recomputar un AQ a partir de ellos: exacto con una fuente, aproximado con varias.

**Decisión**
El titular es el AQ del mes en curso. Al lado va el delta contra el mes anterior, y debajo del hero una gráfica de AQ mes a mes que cubre 6 meses: el mes en curso y los 5 anteriores, o menos si no hay tanta historia. En multi-fuente, los valores mensuales se marcan como aproximados.

**Alternativas consideradas**
- Tendencia de 3 meses, como la vista de equipo → corta para ver una dirección; con 6 se alinea con "Nivel en el tiempo · 6 meses" del perfil del dashboard y con la lectura de 6 meses que la corrida ya hace para la ventana de self-heal.
- Tendencia sobre todo el historial → con mucha historia la gráfica se vuelve ilegible.
- Mantener un AQ sobre todo el historial → casi no se mueve mes a mes, así que volver a mirarlo no tiene sentido, y no coincide con el dashboard.
- Sin eje temporal → pierde "¿estoy mejorando?", la segunda pregunta del lector.

**Consecuencias**
- ➕ El número local coincide con el del dashboard.
- ➕ Aparece el delta, que hoy no existe.
- ➖ Deja de ser un cambio solo de HTML: `local.py` cambia cómo elige el AQ titular y agrega un cálculo por mes.

---

## ADR 10 — Toda la página cubre un solo período: el mes calendario en curso

**Contexto**
Con el AQ titular mensual (ADR 9), si moves, edges y conteos siguieran sobre todo el historial, un edge podría señalar algo ya corregido. Sin flags, el upload (`xl-ai-insights`) sube el mes calendario en curso (`gnomon/cli/insights.py:59`).

**Decisión**
Todo lo que no es la tendencia de AQ (moves, edges, Actividad, modelos, retrato, quotes) se calcula sobre el mes calendario en curso, incluso si está incompleto, con la etiqueta "Sep 2026 · in progress · 29 days". No hay fallback al mes anterior cuando hay poco volumen: ese caso lo cubre el aviso de "Limited data" que ya existe (`_evidence()` < 0.5). El historial completo sigue disponible con `--since` y `--last`.

**Alternativas consideradas**
- Dos períodos (diagnóstico mensual, retrato sobre el historial) → el lector tiene que llevar la cuenta de qué bloque habla de qué.
- Historial completo salvo el AQ → misma incoherencia entre edges y AQ.
- Último mes completo → estable, pero no coincide con el dashboard hasta que cierra el mes.
- Últimos 30 días móviles → no se alinea con ningún mes del dashboard ni de la tendencia.
- Mes en curso con fallback al anterior si tiene poco volumen → descartado; alcanza con el aviso de "Limited data".

**Consecuencias**
- ➕ Todo lo que se ve en la página es coherente entre sí y con el dashboard.
- ➖ Cambia el default de `--local`, que hoy lee todo el historial.
- ➖ A principio de mes el AQ se mueve mucho y el retrato queda flaco.

---

## ADR 11 — "What we noticed" se reparte entre Actividad y Retrato

**Contexto**
Hoy son 12 cards que mezclan conteos con rasgos de personalidad.

**Decisión**
- A **Actividad** (conteos): ship (git vs Edit/Write, se fusiona con la franja de volumen), grind, errores y recovery, agentes (se fusiona con la franja), go-to tool.
- Al **Retrato** (rasgos): best time of day, weekends, prompt length, teammate/tool, politeness, longest run.
- **Sale** "Which model do you reach for?", porque la reemplaza la composición de modelos (ADR 12).

**Alternativas consideradas**
- Dejar "What we noticed" como bloque único en el retrato → vuelve a mezclar conteos con curiosidades.

**Consecuencias**
- ➕ El criterio es explicable: si es un conteo va a Actividad, si es un rasgo va al Retrato, si está duplicado sale.
- ➖ Algunas cards cambian de formato al fusionarse con la franja de volumen.

---

## ADR 12 — Actividad lleva los conteos, la composición de modelos del mes y las lecturas sin nota

**Contexto**
El usuario pidió una gráfica de modelos usados. Existe `stats["stack"]["models"]` con la lista completa de modelos y turnos. Por mes solo se guarda el top 3 (`progression.monthly[].models`). Steering, MCP vs CLI y tool diversity son lecturas "described, not graded". La primera versión del prototipo, con composición más una tabla de "top model by month", no convenció.

**Decisión**
Actividad contiene la franja de volumen, los conteos de ADR 11, una gráfica de **composición de modelos** del mes en curso (barras horizontales con %, turnos y rampa azul ordinal del v2), y Steering, MCP vs CLI y tool diversity marcados como no calificados. El hint de la sección pasa a ser del tipo "counts and readings — none of these are graded".

**Alternativas consideradas**
- Evolución de modelos por mes (columnas apiladas) → para un "otros" honesto hace falta guardar el total de turnos por mes en `accumulator.py`, y la feature ya creció con ADR 9.
- Composición y evolución juntas → es la versión del prototipo que no convenció: dos piezas que dicen casi lo mismo.
- Steering, MCP/CLI y diversity como anexo debajo del AQ, junto con gstack → descartado junto con esa ubicación de gstack (ADR 5).

**Consecuencias**
- ➕ La gráfica de modelos no requiere datos nuevos.
- ➖ Actividad deja de ser "solo conteos": convive con lecturas descritas, y el hint tiene que decirlo.

---

## ADR 13 — El share mantiene póster PNG, X y copy, con el póster rediseñado y siempre en claro

**Contexto**
Hoy hay tres mecanismos: intent de X, copy de caption y un póster de 1200px dibujado en `<canvas>` (~90 líneas de JS con colores coral fijos). El caption promociona paxel-local.

**Decisión**
Se mantienen los tres, en una fila chica al pie del hero. El póster se redibuja en lenguaje v2 con el contenido nuevo: tier, AQ del mes, delta, 4 pilares, 2–3 moves y como mucho 1 quote (el off-the-cuff, leyendo el reroll vivo como hoy). Sale siempre en tema claro, sin importar el tema de la página.

**Alternativas consideradas**
- Sin póster, solo X y copy → un screenshot del hero no muestra pilares ni moves, y compartir la página entera expone quotes verbatim.
- Solo póster → pierde el camino rápido de postear texto.
- Póster que sigue el tema de la página → la imagen compartida se vería distinta según quién la genere, y el canvas necesitaría dos paletas.

**Consecuencias**
- ➕ Se puede compartir sin exponer la página.
- ➖ Hay que reescribir el dibujo del canvas replicando tokens y fuentes en JS, porque el canvas no usa CSS.

---

## ADR 14 — El perfil lleva solo la marca gnomon, sin crédito al upstream

**Contexto**
La página actual dice "Roadmap · Builder Profile", linkea a roadmap.chat, acredita a Max Schilling en el footer y el caption apunta a `Photobombastic/paxel-local` (`REPO_URL`, `gnomon/scoring/gstack.py:35`). El README ya se presenta como gnomon y reconoce el fork en la sección de créditos; el `LICENSE` conserva el copyright original.

**Decisión**
Masthead, `<title>`, póster, caption y footer pasan a gnomon y linkean a `xmartlabs/gnomon`. El perfil no lleva crédito al upstream; ese reconocimiento queda en el README y el LICENSE.

**Alternativas consideradas**
- gnomon con una línea de crédito en el footer → recomendada; el usuario prefirió dejar el crédito solo en README y LICENSE.
- Dejar la marca como está → quien comparte su perfil promociona otro proyecto.

**Consecuencias**
- ➕ Una sola marca en todo lo que ve el usuario.
- ➖ Cambiar `REPO_URL` obliga a revisar sus otros usos en `gstack.py`.

---

## ADR 15 — Las fuentes van embebidas en el HTML

**Contexto**
El v2 usa Archivo e IBM Plex Mono, cargadas desde Google Fonts. El README promete que `--local` hace "zero network calls" y que nada sale de la máquina. El archivo ya embebe el logo en base64.

**Decisión**
Archivo (versión variable, 1 archivo para 400/500/600) e IBM Plex Mono (400 y 500, 2 archivos) se embeben como `@font-face` en base64, subset Latin. Son unos 60–100 KB. Los `.woff2` (OFL) viajan como package data. El canvas del póster usa las mismas fuentes.

**Alternativas consideradas**
- `<link>` a Google Fonts → al abrir la página, el browser le pide las fuentes a Google con la IP del usuario, y eso rompe la promesa del README.
- Solo fuentes del sistema → pierde la identidad del v2 y el póster sale distinto en cada máquina.

**Consecuencias**
- ➕ Sin red, y con el mismo aspecto en página y póster.
- ➖ Hay que verificar que los `.woff2` se incluyan en la instalación vía `uvx --from git+…` (`pyproject.toml`).
- ➖ Usar un peso de Plex Mono no embebido hace que el browser lo simule; la lista de pesos queda fija.

---

## ADR 16 — El modo oscuro funciona igual que en el dashboard

**Contexto**
El v2 tiene tokens dark revisados. El dashboard sigue al sistema, tiene toggle y persiste en `localStorage["gn-theme"]`, aplicando el tema antes de pintar.

**Decisión**
Mismo comportamiento: sigue a `prefers-color-scheme` por defecto, toggle en el masthead y persistencia en `localStorage["gn-theme"]`. Si `localStorage` no está disponible en `file://`, vuelve a seguir al sistema.

**Alternativas consideradas**
- Solo `prefers-color-scheme`, sin toggle → difiere del dashboard.
- Solo claro → desperdicia tokens ya diseñados.

**Consecuencias**
- ➕ Una sola experiencia de tema en todo el producto.
- ➖ En Safari con `file://` la elección puede no persistir entre aperturas.

---

## ADR 17 — La página se mantiene en inglés

**Contexto**
El perfil, el README y el CLI están en inglés. El dashboard está en español.

**Decisión**
`profile.html` queda en inglés.

**Alternativas consideradas**
- Español, como el dashboard → gnomon se lanzó open source en inglés y el perfil local es lo primero que ve cualquiera que lo instala.
- Bilingüe → duplica y mantiene todo el copy en dos idiomas; si hace falta, es una feature aparte que abarque también el dashboard.

**Consecuencias**
- ➕ Coherente con README y CLI.
- ➖ El perfil local y el dashboard hablan idiomas distintos.

---

## ADR 18 — El retrato mantiene las tres quotes con reroll

**Contexto**
"In your own words" muestra go-to prompt, biggest crash-out y off-the-cuff, todas verbatim y filtradas por `_safe_quote`. La crash-out y la off-the-cuff tienen reroll, y la off-the-cuff va al póster.

**Decisión**
Quedan las tres, con el mismo comportamiento. Con ADR 10 salen solo del mes en curso.

**Alternativas consideradas**
- Sacar la crash-out → es lo más personal del retrato y nunca va al póster.
- Solo go-to prompt → el retrato pierde casi todo su sentido.

**Consecuencias**
- ➕ El retrato conserva su identidad.
- ➖ El pool del mes es más chico, así que el reroll tiene menos variedad.

---

## ADR 19 — De los recortes de copy del prototipo, sobreviven "sin nota de /commands" y "sin pesos"

**Contexto**
Sobre el prototipo, el usuario recortó 5 textos: la frase de volumen del hero, la nota "The /commands are optional gstack tools", el hint "grounded in gstack. Not a ranking", la nota "the slope is the honest signal" y los pesos del AQ. Se decidió aplicar esos 5 exactos, no un criterio general. Después, la reestructura hizo que tres de ellos no tuvieran dónde aplicarse.

**Decisión**
Se mantienen dos: "What to work on" va sin la nota de /commands, y los pilares del AQ van sin pesos (ADR 8). Los otros tres no aplican a la nueva estructura. El texto de cada edge sigue nombrando comandos de gstack adentro del consejo.

**Alternativas consideradas**
- Tomarlos como criterio general ("copy mínimo, sin gstack, sin pesos") → sacar gstack del perfil de forma sistemática es una decisión de producto que excede el diseño.
- Posponerlos a otra feature → ya se habían visto en contexto y eran acotados.

**Consecuencias**
- ➕ El recorte quedó acotado y verificable.
- ➖ Quedan menciones a gstack dentro de los consejos.

---

## ADR 20 — Orden de la página

**Contexto**
Consecuencia de los ADR 3–13. La única ubicación que se discutió aparte fue la tendencia de AQ.

**Decisión**
```
Masthead      gnomon · Local profile · toggle de tema · "generated on this machine"
Hero          mes (in progress) · tier · AQ + delta · gstack chico · frase del pilar · share
Tendencia     AQ por mes (la última columna marcada in progress)
Diagnóstico   How you work (3 moves) | What to work on (3 edges)
Desglose AQ   4 pilares × 12 ejes, con los ejes que tienen edge marcados
Actividad     volumen, conteos, composición de modelos, lecturas sin nota
Retrato       6 curiosidades | In your own words (3 quotes)
Footer        gnomon · stats.json · repo
```

**Alternativas consideradas**
- Tendencia dentro del desglose del AQ, como evidencia → "¿hacia dónde voy?" es la segunda pregunta del lector y va arriba.

**Consecuencias**
- ➕ El recorrido responde en orden: dónde estoy, hacia dónde voy, qué hago, qué mejorar, por qué, cuánto, quién soy.

---

## ADR 21 — Los estados vacíos siempre se explican

**Contexto**
Con el período acotado al mes en curso (ADR 10), los vacíos son frecuentes: 0 moves o 0 edges, primer mes sin delta ni tendencia, quotes sin candidatas, ejes que se caen por falta de datos de la fuente (por ejemplo, Model mix con solo Cursor).

**Decisión**
Todo vacío muestra una línea gris al estilo `EmptyState` del v2, que dice qué falta y por qué: "No signature moves fired this month — …", "first month" en lugar del delta, "not measured for this source" en un eje caído. Esto vale también para el retrato: una quote sin candidatas muestra su card con la explicación.

**Alternativas consideradas**
- Ocultar lo que no tiene dato → rompe el par moves/edges y el grid; en el diagnóstico, la ausencia es información.
- Mixto (explicar en el diagnóstico, ocultar en el retrato) → recomendado; el usuario prefirió la regla uniforme.

**Consecuencias**
- ➕ Una sola regla, sin huecos inexplicables.
- ➕ Encaja con la regla v2 "missing data is grey, never red".
- ➖ Cada gate necesita un texto de vacío redactado, y a principio de mes la página puede tener muchas líneas grises.

---

## ADR 22 — El mes en curso sigue siendo calendario aunque el upload use 30 días móviles

2026-09-30 · Durante la implementación

**Contexto**
El ADR 10 se apoyó en un dato equivocado: que `xl-ai-insights` sube el mes calendario en curso. En realidad, para el mes en curso usa una ventana móvil de 30 días que termina hoy y la etiqueta con el mes (`_anchor_window` en `gnomon/upload/mirdash.py`). Solo los meses cerrados usan el mes calendario.

**Decisión**
El perfil local mantiene el mes calendario en curso del ADR 10. Se acepta que el AQ del mes en curso difiera del número del dashboard hasta que el mes cierre; para los meses cerrados coinciden.

**Alternativas consideradas**
- Ventana móvil de 30 días, igual que el upload → coincidiría siempre con el dashboard y evitaría el salto de principio de mes, pero la "página de septiembre" incluiría días de agosto. El usuario prefirió que la página hable de un mes calendario.
- Cambiar el upload a mes calendario → toca el contrato con el dashboard y estaba fuera del alcance de la spec.

**Consecuencias**
- ➕ La etiqueta del período es literal: el mes que dice es el mes que cubre.
- ➖ Durante el mes en curso, el número local y el del dashboard no coinciden. La igualdad con `xl-ai-insights` solo se garantiza para meses cerrados.
- ➖ A principio de mes el AQ se mueve mucho (ya anotado en el ADR 10).

---

## ADR 23 — Resoluciones del diseño hi-fi

2026-09-30 · Durante la implementación

**Contexto**
El diseño de alta fidelidad (canvas, artboards `ProfileLight`, `ProfileDark`, `ProfileEmpty` y `Poster`) resolvió visualmente puntos que la spec y los ADR no cubrían. El usuario los confirmó todos.

**Decisión**
1. Los ejes del AQ se muestran en escala 0–100, no como "puntos / máximo del eje", para no exponer los pesos (ADR 8).
2. Los edges de origen gstack sin dimensión única ("Add a reflex", "Stop the grind") se rotulan "gstack · Engineering". "Go deeper" se rotula "gstack · Balanced".
3. En el perfil, el consejo de los edges del AQ no abre con "<Pilar> · <Eje> is your thinnest AQ signal", que repite el tag de origen.
4. La frase del hero dice "thinnest pillar" y no "thinnest axis", porque nombra un pilar.
5. En multi-fuente, la tendencia marca los valores aproximados con un prefijo "≈" y una línea debajo de la gráfica. La marca se aplica por mes.
6. La sección de rasgos del Retrato se llama "Curiosities".
7. El póster no incluye gstack ni la frase del pilar.
8. La lectura MCP vs CLI usa un texto neutral cuando MCP lidera; "CLI-first" solo aparece cuando CLI lidera.

**Alternativas consideradas**
- Mostrar "puntos / máximo del eje" → permite sumar ejes para llegar al pilar, pero revela los pesos que el ADR 8 decidió ocultar.
- Dejar el copy del código tal cual (puntos 3, 4 y 8) → el tag repetido, la palabra "axis" para un pilar y "CLI-first" cuando MCP lidera son errores de copy, no decisiones.

**Consecuencias**
- ➕ Cierra las ambigüedades del diseño antes de implementarlas.
- ➖ Con los ejes en 0–100, el lector no puede reconstruir el score del pilar sumando ejes.

---

## Glosario

| Término | Significado |
|---|---|
| AQ (Agentic Quotient) | Score 0–100 de cómo operás agentes. 4 pilares (Breadth, Craft, Efficiency, Savvy) y 12 ejes. Lo calcula `compute_aq()` en `gnomon/scoring/aq.py` |
| Tier | Nivel derivado del AQ: Elite ≥88, Advanced ≥75, Proficient ≥60, Adequate ≥45, Apprentice ≥25, Novice |
| Pilar | Cada uno de los 4 grupos del AQ |
| Eje | Cada una de las 12 mediciones dentro de un pilar (Orchestration, Verification, Model mix…) |
| gstack scorecard | Tres scores 0–10 de cómo construís: Execution, Planning, Engineering |
| Edge (growth edge) | Consejo accionable derivado de tus datos; hasta 3, con `axis` si sale del AQ o `None` si sale de gstack. Se muestra en "What to work on" |
| Signature move | Patrón de trabajo detectado por un gate sobre tus números; hasta 5, con tag de etapa gstack. Se muestra en "How you work" |
| Lectura sin nota (reading) | Medición que se describe y no se califica: Steering, MCP vs CLI, tool diversity |
| Diagnóstico | Parte superior de la página: hero, tendencia, moves/edges, desglose del AQ |
| Actividad | Sección de conteos y lecturas sin nota del mes en curso, incluida la composición de modelos |
| Retrato | Sección inferior y separada: curiosidades y quotes |
| Mes en curso | Mes calendario actual hasta hoy, parcial, etiquetado "in progress". Es el período de toda la página salvo la tendencia |
| Delta | Diferencia de AQ entre el mes en curso y el anterior |
| Tendencia | Gráfica de AQ por mes |

## Decisiones que quedaron abiertas

- [ ] **Motivo de poner gstack en el hero (ADR 5).** El usuario eligió el hero sobre la recomendación de anexo y no dio el motivo. Lo desbloquea el usuario; sin él, el ADR no protege la decisión de que alguien la vuelva a proponer.
- [ ] **Cómo cortar la entrega.** Hay cambios de motor (AQ mensual, default de período, delta) y cambios de HTML (estructura, póster, fuentes). Se decide en el paso de tickets (`/to-tickets`).
