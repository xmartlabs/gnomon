# Handoff: gnomon — self-hosted team dashboard

## Overview

**gnomon** reads a developer's sessions with coding agents (Claude Code, Cursor, Codex), scores how they work with them, and suggests improvements. Until now the result died in a local `profile.html` that nobody else saw, and the only way to see a whole team was to upload to a third-party server.

This handoff covers the **self-hosted team dashboard**: a team runs `docker compose up -d`, points the gnomon CLI at their own server, and gets the aggregate view without sending data anywhere. One container, one volume, zero external services.

Two screens ship:

1. **Equipo** — the team dashboard. The default view.
2. **Perfil de persona** — opened from any row of the people table.

Three people touch the product, and only one lives in it:

| Role | Relationship to the UI |
| --- | --- |
| The operator who deploys | Terminal only: `.env` + `docker compose up -d`. The container refuses to boot without `TEAM_TOKEN`, so a misconfigured deploy fails loudly instead of serving an open endpoint. Never opens a screen. |
| The engineer who uploads | One pass through a browser screen, once. **Out of scope for this handoff.** |
| The lead who reads | Uses the product daily, installs nothing. **Both screens here are designed for this person.** |

### Domain vocabulary you need to implement it correctly

- **AQ · Agentic Quotient (0–100)** — how someone *operates* agents. Four fixed-weight pillars: **Breadth** 30% (how much machinery you move), **Craft** 30% (how well), **Efficiency** 25% (the return on each intervention), **Savvy** 15% (judgment). Tiers: **Pilot** &lt;65, **Operator** 65–79, **Architect** 80+.
- **gstack scorecard (0–10 each)** — how someone *builds*: Execution, Planning, Engineering. Independent of AQ. A tidy builder can have a thin AQ, and that is information, not a contradiction.
- **Counters** — deterministic measurements (planning ratio, error recovery, git churn, fanout, compounding writes…). **The distinction matters and the UI must preserve it: the scores are opinionated rubrics, the counters just count.** Never present a counter as a judgment.

---

## About the Design Files

The files in this bundle are **design references created in HTML** — prototypes showing the intended look and behaviour. They are **not production code to copy directly.**

The task is to **recreate these designs in the target codebase's existing environment** (React, Vue, Svelte, whatever the app uses) following its established patterns, libraries and conventions. If no environment exists yet, pick the framework that suits the project and implement there.

Two things in this bundle *are* meant to be used more literally:

- **`design_system/styles.css` + `design_system/tokens/`** — plain CSS custom properties with no dependencies. Copy these in as-is (or port the values into the codebase's existing token layer). They are the source of truth for every colour, size and duration below.
- **`design_system/components/**/*.jsx`** — self-contained React components that import nothing but React and reference styling only through CSS custom properties. If the target app is React, these can be adapted directly. If not, they document exactly what each primitive must do.

`screens/` and `wireframes/` are references to read, not code to ship. `wireframes/*.dc.html` uses a proprietary prototyping runtime (`support.js`) — **ignore that runtime entirely**; those files are included only so you can see the low-fidelity structure the hi-fi screens came from.

---

## Fidelity

**High-fidelity.** Final colours, typography, spacing, interactions and copy. Recreate pixel-perfectly using the codebase's own libraries where they exist.

One qualifier: the two typefaces are **Google Fonts stand-ins** (see Assets), chosen because gnomon has no brand fonts yet. Everything else — the values, the composition, the behaviour — is final and was reviewed.

---

## The governing design rule

Before any specific measurement: **hierarchy comes from type size and whitespace, never from containers.**

This system has **no cards**. There is no bordered, shadowed, rounded rectangle wrapping a metric anywhere. No card with a coloured left border. No icon-in-a-tile. No gradients — not in backgrounds, not in bars, not anywhere. No decorative illustration, no emoji, no blur, no transparency effects. Grouping is done with a section label, a 1px hairline, and whitespace.

This was argued for and validated during the wireframe phase. It is a constraint, not a preference. **If you find yourself reaching for a `<Card>` from the codebase's component library, that is the wrong instinct here.**

Corollaries that follow from it and that are equally binding:

- **Asymmetric grids**, never equal thirds — `1.15fr auto 1fr`, `1fr auto 1.25fr`, `1.35fr auto 1fr`. Equal thirds read as a card grid. The `auto` track is a 1px vertical rule.
- **Bold is rationed** — figures and headline titles only. Never body copy, never names in a table.
- **Actions are visible at rest.** A clickable table row carries a persistent "Ver perfil ›". A reveal-on-hover action is treated as a bug.
- **Definitions live in tooltips**, so labels stay 1–3 words.
- **Back navigation is always on screen.**
- **Red is only for a real decline or an error.** Neutral and missing data are grey.
- **Colour is never the sole carrier of meaning** — every trend renders a glyph *and* a number.

---

## Screens / Views

### Shared: page shell and header

**Layout.** Content is centred: `max-width: 1180px` (`--layout-max`), `padding: 24px 32px 96px`.

**Header.** Flex row, `align-items: center`, `gap: 24px`, `padding-bottom: 12px`, `border-bottom: 1px solid var(--rule-strong)`, `margin-bottom: 48px`.

- **Left — wordmark, as a button that returns to the team screen.** An accent triangle (the gnomon of a sundial — the thing that casts the shadow) built with CSS borders: `border-left: 7px solid transparent; border-right: 7px solid transparent; border-bottom: 16px solid var(--accent-mark)`, `width: 0; height: 0`. Then the word `gnomon` in Archivo, `font-weight: 600`, `22px`, `letter-spacing: -0.03em`, `--text-primary`. Gap 8px. `aria-label="gnomon — volver al tablero"`.
- **Right (`margin-left: auto`, gap 16px)** — a `Select variant="inline"` labelled "Mes" (`August/July/June 2026`), then a bordered `IconButton` theme toggle.

**Theme toggle.** Sets `data-theme="dark"|"light"` on `<html>`. Renders a **crescent moon** when light (switch to dark) and a **sun** when dark (switch to light), both inline SVG, `17×17` in a `20×20` viewBox, `fill: none`, `stroke: currentColor`, `stroke-width: 1.5`, `stroke-linecap: round`. Moon path: `M16.3 12.4A7 7 0 0 1 7.6 3.7a7 7 0 1 0 8.7 8.7z`. Sun: `circle cx=10 cy=10 r=3.6` plus eight rays. `aria-label` flips with state; the SVGs are `aria-hidden`.

---

### 1. Equipo (team dashboard) — default view

**Purpose.** The lead understands in about five seconds how the team is doing this month and what is worth improving, then drills into a person.

**`h1`** — `Equipo · <month>`, `--type-title-lg` (32px/600), `letter-spacing: -0.015em`, `margin: 0 0 24px`. The month portion is set in the figure font at weight 500. **This `h1` renders in every state, including the empty month** — it is the screen's identity, not part of the data branch.

#### Hero row

Flex, `align-items: flex-end`, `gap: 40px`.

1. **Team AQ.** A `Metric size="xl"`: mono label `AQ DEL EQUIPO` (11px, uppercase, `+0.1em`, `--text-tertiary`) above the figure at **88px**, `line-height: 0.88`, `letter-spacing: -0.025em`, tabular numerals. Unit `/100` at 13px secondary. Trailing: `Trend size="lg"` → `▲ +4 vs julio`.
   - Values: August 72 (`▲ +4 vs julio`), July 68 (`▲ +1 vs junio`).
2. **History column chart**, fixed `width: 210px`, `flex: none`, height 96px. Three columns (jun 67, jul 68, ago 72). Value above each column in mono 13px; month label below in mono 11px uppercase tertiary. The **current period is the only accented column** (`--chart-1`); the rest are `--chart-4`. `role="img"` with a full `aria-label`.
3. **Tokens and cost** (`margin-left: auto`, gap 32px, right-aligned): two `Metric size="md"` (40px) — `48.2M` labelled TOKENS, and `$310` labelled COSTO with `Trend delta={-8}`.

Then a `--rule-default` hairline with 48px margins.

#### Pillars vs coaching

Grid `1.15fr auto 1fr`, gap 40px, `align-items: start`. Middle track is a 1px vertical `--rule-default`.

**Left — `h2` "CUATRO PILARES"** with a tooltip: *"Promedio del pilar entre quienes subieron datos este mes. Breadth = cuánta maquinaria movés · Craft = qué tan bien · Efficiency = cuánto rinde cada intervención · Savvy = criterio"*. Four `PillarBar`s, gap 20px:

| Pillar | Weight | Value |
| --- | --- | --- |
| Breadth | 30% | 64 |
| Craft | 30% | 78 |
| Efficiency | 25% | 70 |
| Savvy | 15% | 81 |

Each bar: name at `--type-title-sm` (19px), weight in mono 11px tertiary, value right-aligned in mono **28px**/500, and below it an 8px track (`--chart-track`) with an absolutely-positioned `--chart-1` fill at the value's percentage.

**Right — `h2` "QUÉ MEJORAR ESTE MES".** This is the coaching block; the product's tone is coaching, not ranking.

- `h3`, `--type-title-md` (24px/600), `text-wrap: pretty`: **"Breadth es el pilar más flojo del equipo."**
- Body 15px `--text-secondary`: "Solo 2 de 6 personas orquestan subagentes. Impacto estimado: **+5 AQ** de equipo." — the `+5 AQ` in `--accent`, figure font, weight 500.
- A `--rule-subtle` hairline.
- `h4` 19px: "4 perfiles con sesiones largas sin checkpoints."
- Body 13px secondary: "Baja Efficiency sin bajar el volumen de trabajo."

Then another `--rule-default` hairline, 48px margins.

#### Model mix vs tier split

Grid `1fr auto 1fr`, gap 40px.

**Left — `h2` "MODELOS MÁS USADOS"**, tooltip *"Distribución de tokens por modelo en el mes. Pasá el mouse por una porción para ver su porcentaje."* A **176px donut** with the legend centred beside it (`justify-content: center`, gap 32px).

- Sonnet 4.5 46% · Opus 4.1 31% · GPT-5 15% · Otros 8% — **sorted descending**, because the palette is an ordered ramp (`--chart-1` … `--chart-4`), not categorical colours.
- SVG `viewBox="0 0 100 100"`, radius 46, centre 50,50, arcs `A46 46 0 <largeArc> 1`, `stroke: var(--surface-page)`, `stroke-width: 0.8`.
- **Legend shows names only** — no percentages. That keeps the resting state quiet; the numbers live in the hover.
- **Hover / focus:** the slice translates 4px outward along its mid-angle (`transition: transform 120ms ease-out`) and a tooltip appears at the centre — `--surface-raised`, 1px `--rule-strong` border, `--shadow-overlay`, padding 4px 8px — showing name + percentage. Each `<path>` is `tabIndex={0}` with its own `aria-label`, and hovering a legend row activates the matching slice.

**Right — `h2` "CÓMO SE REPARTE EL EQUIPO".** Three rows, `padding: 12px 0`, separated by `--rule-subtle` (last row none): tier name 19px, range in mono 11px tertiary, count right-aligned in mono 28px.

- Architect 80+ → 1 · Operator 65–79 → 3 · Pilot &lt;65 → 2
- Caption 13px secondary: "Tier medio: Operator · 5 personas subieron este mes".

#### People table

`h2` "Personas", `--type-title-lg` (32px), `margin: 80px 0 20px`.

**Rule-only table: no outer border, no zebra striping.** `th`: mono 11px uppercase `+0.1em` tertiary, `border-bottom: 1px solid var(--rule-strong)`, `padding: 0 12px 8px 0`. `td`: `border-bottom: 1px solid var(--rule-subtle)`, `padding: 12px 12px 12px 0`.

| Nombre | AQ | Tier | Trend | Top pilar | Último upload |
| --- | --- | --- | --- | --- | --- |
| Ana P. | 84 | Architect | ▲ +6 | Craft | hace 2 días |
| Bruno M. | 75 | Operator | ▲ +2 | Savvy | hace 5 días |
| Carla S. | 71 | Operator | ▼ −3 | Efficiency | hace 1 semana |
| Elena V. | 69 | Operator | ▲ +1 | Craft | hace 3 días |
| Fede L. | 62 | Pilot | = 0 | Savvy | hace 4 días |
| Diego R. | 58 | Pilot | — sin datos | Breadth | junio |

- AQ is a **figure column**: mono, 20px, weight 500, tabular numerals, so values align down the column.
- Tier renders a `Badge` — `tone="accent"` for Architect, `tone="neutral"` otherwise.
- Trend renders a `Trend`; `delta={null}` for Diego gives "— sin datos" in **grey, never red**.
- "Último upload" is a muted column: 13px `--text-secondary`.
- **A final unlabelled column holds a persistently visible "Ver perfil ›"** in `--accent`, 13px, underlined.
- The whole row is interactive: `cursor: pointer`, `tabIndex={0}`, `role="button"`, `aria-label="Abrir perfil de Ana P."`, Enter/Space activate, hover background `--surface-hover` fading in over 120ms.

#### Empty state

Selecting **Junio 2026** replaces the entire content region below the `h1` — **never show empty figures beside it.**

Left-aligned block, `max-width: 520px`, `padding: 96px 0`, gap 12px:

- Mono eyebrow label with the month.
- `h2` at `--type-title-lg`: **"Nadie subió sesiones en Junio 2026."**
- Body 16px secondary: "Los datos aparecen cuando alguien corre `gnomon push` apuntando a este servidor." — `gnomon push` in the figure font at 14px.
- `Button variant="link"`: "← Ver Agosto 2026", which returns to the month with data.

**Always give a way out.** An empty state without an action is a dead end.

---

### 2. Perfil de persona

**Purpose.** The person (or their lead) understands how they operate with agents and what to improve. The structure mirrors the report gnomon already generates locally.

**Breadcrumb** — `Button variant="link"`: "← Equipo", `margin-bottom: 32px`. This is the only way back and it is always visible.

#### Header

Flex, `align-items: flex-end`, gap 40px.

- **Left (`max-width: 460px`):** `h1` with the name at **40px**/600, `-0.015em`. Below it the email in mono 12px uppercase `+0.1em` tertiary. Below that the **archetype line** at 19px italic `--text-secondary`, in quotes — e.g. *"Blueprint, then bulldozer — planificá amplio, ejecutá angosto"*. Archetypes are descriptive and reusable, never verdicts about the person.
- **Right (`margin-left: auto`):** the AQ at **96px**, `line-height: 0.88`, tabular numerals, beside a stacked `/100` (mono, secondary) and the tier `Badge`.

Then a `--rule-default` hairline, 40px margins.

#### Suggestions vs scorecard

Grid `1fr auto 1.25fr`, gap 40px.

**Left — `h2` "SUGERENCIAS"**, tooltip *"Cada sugerencia sale de un eje concreto de la rúbrica."* **Suggestions come first on purpose** — the product's tone is coaching. Two per person, each 19px `text-wrap: pretty`; the first has a `--rule-subtle` bottom border with 24px padding/margin.

Ana's: *"Craft 92: podés mentorear Breadth al resto — solo vos y Bruno orquestan subagentes."* / *"Efficiency: 3 sesiones de más de 2h sin checkpoint la semana pasada."*

**Right — `h2` "SCORECARD"**, tooltip *"El scorecard gstack juzga cómo construís; el AQ juzga cómo operás la máquina."* Three columns, gap 24px, **no boxes**: value at 40px mono, name at 15px, description at 13px secondary.

- Execution 9.1 — "cuánto shippea y qué tan rápido"
- Planning 9.8 — "pensar antes de construir"
- Engineering 8.6 — "qué tan limpio es el trabajo"

Then a `--rule-subtle` hairline and **`h3` "NIVEL EN EL TIEMPO · 6 MESES"**: a six-column chart (mar–ago), height 110px, current month accented. Give the label enough clearance that the per-column values do not collide with it.

#### Four pillars with their axes

`h2` "CÓMO OPERA AGENTES · CUATRO PILARES", then a four-column grid, gap 40px. Each pillar is a **`border-top: 2px solid var(--rule-strong)` with `padding-top: 12px`** — a rule above, not a box around.

Header row: pillar name 19px, points right-aligned in mono 28px, `/max` in mono 11px tertiary. Below, its axes as small `PillarBar`s (`max={10}`, 6px track, 13.5px labels), gap 12px.

| Pillar | Max | Axes |
| --- | --- | --- |
| Breadth | 30 | Tool range, Skill use, MCP reach |
| Craft | 35 | Verification, Error recovery, Iteration |
| Efficiency | 20 | Actions/prompt, Fanout, Planning |
| Savvy | 15 | Compounding, Judgment |

Points are `round(pillarPercent × max / 100)`. Axis values in the prototype are derived from the pillar percentage with small offsets `[+0.5, −0.1, −0.6]` purely so the mock looks plausible — **replace with real rubric axis values.**

#### Explore vs usage

Grid `1.35fr auto 1fr`, gap 40px.

**Left — `h2` "EXPLORE"**, tooltip *"Contadores deterministas: no opinan, solo cuentan."* A four-column grid, gap 24px 32px, **no containers**: value at 28px mono, key at 13px secondary.

planning ratio 82% · error recovery 98% · error rate 2.6 · iter depth 2.3× · git churn 8.2M · fanout mediana 3.5 · compounding writes 91 · días activos 14

**Right — `h2` "USO DEL MES"**: three `Metric size="sm"` with captions (153 sesiones · 1.062 prompts · 14 acciones/prompt), then this person's model mix as three small `PillarBar`s — Opus 4.8 60%, Fable 5 28%, Haiku 4.5 12% (the two smaller ones `tone="muted"`).

---

## Interactions & Behavior

- **Navigation.** The prototype holds `view: 'team' | 'person'` in state with no router. In production use real routes — `/` and `/p/:personId/:month` (gnomon's existing local report uses `/p/1/2026-06`).
- **Open a profile.** Click the row, press Enter/Space with the row focused, or click "Ver perfil ›".
- **Return.** The "← Equipo" breadcrumb, or the wordmark.
- **Month select.** Changes the team AQ and its trend; `Junio 2026` triggers the empty state. It also resets the view to the team screen.
- **Donut hover.** `onMouseEnter`/`onMouseLeave` on each slice *and* each legend row; `onFocus`/`onBlur` for keyboard. 4px offset plus centre tooltip.
- **Row hover.** Background `--surface-hover`, 120ms.
- **Hover generally.** Surfaces lighten one step; accent fills darken one step (`--accent-hover`). Links darken and keep their underline.
- **Press.** One step further (`--surface-active` / `--accent-pressed`). **Nothing scales, nothing shrinks, nothing bounces.**
- **Focus.** `outline: 2px solid var(--focus-ring)` at `outline-offset: 2px`, on every interactive element **including table rows**.
- **Disabled.** 40% opacity plus `cursor: not-allowed`.
- **Motion.** 80/120/180/320ms; `ease-out` for entrances, `ease-in-out` for state changes. The only animations shipped are the donut slice offset and the row background fade. No page transitions, no staggered reveals, no parallax. `prefers-reduced-motion` zeroes every duration (already handled in `tokens/motion.css`).
- **Touch targets.** 32px minimum, 40px standard. Tooltip markers carry a 24×24px hit area around a 16px visual circle.

### Not yet designed — you will need these and they are not in the bundle

- **Loading states.** The dashboard loads a whole month at once. Skeletons for the large figures and the bars still need designing; ask before inventing them.
- **Responsive behaviour.** Everything is designed for ~1180px desktop. The asymmetric grids should collapse to a single column below ~900px and the 88/96px figures step down to roughly 64px, but **the exact rules have not been designed** — flag this rather than guessing silently.
- **Error / fetch-failure states.**

---

## State Management

```
view:     'team' | 'person'
personId: string
month:    'Agosto 2026' | 'Julio 2026' | 'Junio 2026'
dark:     boolean          // writes data-theme onto <html>
```

Local, per-component state: `hoverModel` (active donut slice), row hover index, tooltip open.

Derived: `emptyMonth = month === 'Junio 2026'`.

**Real data fetching** (all fixtures in the prototype — see `screens/data.js`): one endpoint per month returning the team aggregate (AQ, history, pillars, model mix, tier split, tokens/cost) plus the people list; one per person/month returning their scorecard, pillars with axes, counters and usage. **Everything is served from the team's own container — no external calls, no third-party analytics.** That constraint is the product's reason for existing; do not add a CDN-hosted tracker or an external API.

---

## Design Tokens

All defined in `design_system/tokens/` and reachable from `design_system/styles.css`. **Use the token names, not the literals** — the dark theme remaps the same names, so a component that reads tokens needs no theme awareness.

### Colour — accent (instrument blue)

`--blue-50 #EBF2FC` · `100 #CFE0F7` · `200 #9EC2EF` · `300 #6BA1E4` · `400 #4189DC` · **`500 #2A78D6`** · `600 #1F60B0` · `700 #17498A` · `800 #103361` · `900 #0A2242`

**The ramp splits by job, and this matters:** `--blue-500` (#2A78D6) is the brand hue, used for fills that carry no text — chart series, the wordmark triangle (`--accent-mark`). `--accent` resolves to `--blue-600` because links and primary buttons must clear 4.5:1, and #2A78D6 on white is only 3.9:1. **Never put text on `--accent-mark`.**

### Colour — neutrals

`--grey-0 #FFFFFF` · `25 #FBFBFB` · `50 #F4F5F5` · `100 #E9EAEA` · `200 #D5D7D7` · `300 #B4B7B7` · `400 #8B8F8F` · `500 #6A6E6E` · `600 #4E5252` · `700 #383B3B` · `800 #232626` · `900 #141616` · `950 #0A0B0B`

### Colour — signal

Green is no longer the accent, so "positive" has its own ramp: `--moss-100 #DCEDE3` · `--moss-500 #15734A` · `--moss-600 #0F5A39`. Negative: `--clay-100 #F6E3DF` · `--clay-500 #A23B2A` · `--clay-600 #85301F`. Warning: `--ochre-100 #F5EBD4` · `--ochre-500 #8A6516`.

### Colour — semantic (light / dark)

| Token | Light | Dark |
| --- | --- | --- |
| `--text-primary` | `--grey-900` | `--grey-50` |
| `--text-secondary` | `--grey-500` (5.16:1) | `--grey-400` |
| `--text-tertiary` | `#6E7272` (4.87:1) | `#9AA0A0` (7.42:1) |
| `--text-decorative` | `--grey-400` | `--grey-500` |
| `--text-inverse` | `--grey-0` | `--grey-950` |
| `--surface-page` | `--grey-0` | `--grey-950` |
| `--surface-raised` | `--grey-0` | `--grey-900` |
| `--surface-sunken` | `--grey-50` | `--grey-900` |
| `--surface-hover` | `--grey-50` | `--grey-800` |
| `--surface-active` | `--grey-100` | `--grey-700` |
| `--surface-inverse` | `--grey-900` | `--grey-50` |
| `--rule-strong` | `--grey-900` | `--grey-300` |
| `--rule-default` | `--grey-200` | `--grey-700` |
| `--rule-subtle` | `--grey-100` | `--grey-800` |
| `--accent` | `--blue-600` | `--blue-300` |
| `--accent-hover` | `--blue-700` | `--blue-200` |
| `--accent-pressed` | `--blue-800` | `--blue-100` |
| `--accent-on` | `--grey-0` | `--grey-950` |
| `--accent-mark` | `--blue-500` | `--blue-300` |
| `--positive` | `--moss-500` | `#7FC79E` |
| `--negative` | `--clay-500` | `#D98A78` |
| `--warning` | `--ochre-500` | `#D6AC5C` |
| `--neutral` | `--grey-400` | `--grey-500` |
| `--chart-1` | `--blue-500` | `--blue-300` |
| `--chart-2` | `--blue-300` | `--blue-500` |
| `--chart-3` | `--blue-100` | `--blue-800` |
| `--chart-4` | `--grey-300` | `--grey-600` |
| `--chart-track` | `--grey-100` | `--grey-800` |
| `--focus-ring` | `--blue-500` | `--blue-300` |

**`--text-tertiary` is the lightest grey allowed to carry words** (4.5:1 in both themes). `--text-decorative` is lighter and restricted to `aria-hidden` marks — the select chevron. Never text.

### Typography

Two families, strictly divided by job:

- `--font-sans` / `--font-ui`: **Archivo**, 400/500/600/700 — for language.
- `--font-mono` / `--font-figure`: **IBM Plex Mono**, 400/500/600 — for **every figure**, always with `font-variant-numeric: tabular-nums` so numbers align down a column. Also section labels, units, and code.

| Role | Size | Weight | Line height | Tracking |
| --- | --- | --- | --- | --- |
| `--type-metric-xl` | 88px | 500 | 0.88 | −0.025em |
| `--type-metric-lg` | 64px | 500 | 0.88 | −0.025em |
| `--type-metric-md` | 40px | 500 | 0.88 | −0.025em |
| `--type-metric-sm` | 28px | 500 | 1.15 | −0.025em |
| metric-xs | 20px | 500 | — | — |
| `--type-title-lg` | 32px | 600 | 1.15 | −0.015em |
| `--type-title-md` | 24px | 600 | 1.15 | −0.015em |
| `--type-title-sm` | 19px | 600 | 1.3 | — |
| body-lg | 16px | 400 | 1.5 | 0 |
| `--type-body` | 15px | 400 | 1.5 | 0 |
| `--type-body-sm` | 13px | 400 | 1.5 | 0 |
| label-lg | 12px | 500 | 1.2 | +0.1em, uppercase |
| `--type-label` | 11px | 500 | 1.2 | +0.1em, uppercase |

**One `xl` figure per screen**, and that figure is the screen's subject. Long prose gets `text-wrap: pretty`.

### Spacing

4px base, with 2 and 6 reserved for optical work inside controls:
`--space-1` 2 · `2` 4 · `3` 6 · `4` 8 · `5` 12 · `6` 16 · `7` 20 · `8` 24 · `9` 32 · `10` 40 · `11` 48 · `12` 64 · `13` 80 · `14` 96

Layout: `--layout-max` 1180px · `--layout-gutter` 32px · `--layout-column-gap` 40px · `--layout-section-gap` 48px.
Control heights: `--control-sm` 32 · `--control-md` 40 · `--control-lg` 48.

### Rules, radii, elevation

Rule weights: `--rule-width` 1px, `--rule-width-strong` 2px. Three semantic weights — `--rule-strong` (under the header, above table headers, above pillar columns), `--rule-default` (between sections and columns), `--rule-subtle` (between rows).

Radii stay near-square: `--radius-none` 0 (the default) · `--radius-sm` 2px (controls) · `--radius-md` 3px · `--radius-full` 999px (only the tooltip marker).

**Elevation is a single token** and only for things that must detach from the page — tooltips and dialogs:
`--shadow-overlay: 0 1px 2px rgba(10,11,11,.06), 0 8px 24px rgba(10,11,11,.10)` (dark: `0 1px 2px rgba(0,0,0,.5), 0 8px 24px rgba(0,0,0,.6)`). **Nothing else casts a shadow.**

Focus: `--focus-ring-width` 2px, `--focus-ring-offset` 2px.

### Motion

`--duration-instant` 80ms · `--duration-fast` 120ms · `--duration-normal` 180ms · `--duration-slow` 320ms.
`--ease-out: cubic-bezier(.22,.61,.36,1)` · `--ease-in-out: cubic-bezier(.4,0,.2,1)`.
All zeroed under `prefers-reduced-motion: reduce`.

---

## Accessibility commitments

WCAG 2.2 AA, verified on the built screens:

- Body text meets 4.5:1; rules and chart fills meet 3:1.
- **Information is never colour-only** — every trend renders a glyph and a number (`▲ +6`, `▼ −3`, `= 0`, `— sin datos`).
- Every chart carries an `aria-label` describing its values.
- Labels are always visible; placeholders never stand in for them.
- Errors are specific and actionable, announced with `role="alert"`. Never "Invalid input".
- Definitions live in keyboard-reachable tooltips, **not** the native `title` attribute (unreachable by keyboard, invisible on touch). Markers are 24×24px.
- **Headings run h1 → h2 → h3 in order in every state, including the empty month.** `SectionLabel` takes an `as` prop precisely because it replaced card headers and is therefore the only thing that can carry the outline. Its default is `div` — pass `as="h2"` for any label that titles a real section.

---

## Content guidelines

**Product language is Spanish (Rioplatense), voseo** — *corré*, *revisá*, *probá*. (The design system's own specimen cards use English glosses so the system reads for any implementer; the product does not.)

- **Sentence case everywhere except section labels**, which are mono, uppercase, tracked out.
- **Second person, never first.** The product never says "we" and never speaks as gnomon in first person.
- **Findings are stated, not softened.** No exclamation marks, no cheerleading, no hedging. A finding is a measurement with a consequence attached.
- **Every number carries its denominator and its comparison** — `72 /100`, `▲ +4 vs julio`. A bare figure with no scale does not ship.
- **Nothing is claimed about people beyond what was measured.** *"Breadth 58 es tu pilar más flojo"*, never *"sos flojo en Breadth"*.
- **Jargon is defined in place, once**, via tooltip at first appearance. AQ, Breadth, gstack, fanout, compounding writes are all project vocabulary.
- **Empty and error copy names the cause and the fix.** Never "No data available".
- **No emoji** — not in the product, not in the CLI output.

---

## Assets

**There are no image assets, and that is deliberate.**

- **No logo exists.** Nothing was drawn or reconstructed. `design_system/assets/wordmark/wordmark.card.html` holds three typographic wordmark proposals; the screens use proposal A (accent triangle + lowercase Archivo). **The client still needs to pick one.**
- **No photos or avatars of people** — an explicit product decision, not an omission.
- **Icons: two inline SVGs only** (the crescent moon and sun for the theme toggle), 1.5px stroke on `currentColor`. Everything else that reads as an icon is Unicode geometry in the figure font: `▲ ▼` trend direction, `=` flat, `—` no data, `‹ ›` stepping and row actions, `i` in a hairline circle for tooltips. No icon font, no sprite sheet, no PNG icons.
- **The wordmark triangle is CSS borders**, not an SVG.
- If an icon set becomes necessary, use **Lucide** at `strokeWidth={1.5}`, sized 16 or 20, `currentColor` — it matches the two existing SVGs. Load it properly; never hand-draw approximations.

### ⚠ Fonts are substitutions

No font binaries exist for gnomon. **Archivo** and **IBM Plex Mono** are Google Fonts stand-ins chosen for the "measuring instrument" direction (industrial grotesque + drafting-table monospace). `tokens/fonts.css` loads them from the Google Fonts CDN.

If real brand fonts turn up, drop the `.woff2` files in and replace the `@import` with local `@font-face` rules **keeping the same custom property names** — nothing else needs to change. Note that a CDN font load conflicts with the product's zero-external-services promise; for a truly self-contained container, **self-host the font files**.

---

## Files

```
design_handoff_gnomon/
├── README.md                        ← this file, self-sufficient
├── design_system/
│   ├── DESIGN_SYSTEM.md             the full design guide: content
│   │                                fundamentals, visual foundations, iconography
│   ├── styles.css                   entry point — @import list only
│   ├── tokens/                      colors, typography, spacing, borders,
│   │                                motion, fonts, base resets
│   ├── components/
│   │   ├── core/                    Button, IconButton, Badge, SectionLabel, Divider
│   │   ├── forms/                   Input, Select
│   │   ├── data/                    Metric, Trend, PillarBar, DataTable,
│   │   │                            DonutChart, ColumnChart
│   │   └── feedback/                Tooltip, EmptyState
│   ├── guidelines/                  13 foundation specimen cards (colour, type,
│   │                                spacing, corners) — open in a browser
│   └── assets/wordmark/             three wordmark proposals
├── screens/                         ← THE HI-FI DESIGN. Open index.html
│   ├── index.html                   shell + bootstrap
│   ├── App.jsx                      view / month / theme state
│   ├── AppHeader.jsx                wordmark, month select, theme toggle
│   ├── TeamDashboard.jsx            team screen, coaching, tier split, empty state
│   ├── PersonProfile.jsx            profile, scorecard, pillar axes, counters
│   ├── data.js                      fixture data
│   └── README.md                    kit notes + the carried-over constraints
└── wireframes/                      lo-fi origin, context only — ignore support.js
    ├── Gnomon Dashboard.dc.html     the validated wireframe
    └── Gnomon Wireframes.dc.html    the three directions explored (1a chosen)
```

**Every component has three files:** `<Name>.jsx` (implementation), `<Name>.d.ts` (props contract with adherence rules in the JSDoc), `<Name>.prompt.md` (what it is, when to use it, and the rules that govern it). **Read the `.prompt.md` files** — they carry the intent that the code alone does not.

### How `screens/index.html` runs

It fetches the component sources, strips module syntax, transforms them with in-browser Babel, and runs them as one script — a prototype convenience so the screens render from a plain file with no build step. **Do not replicate that mechanism.** In a real app, import the components normally.

---

## Out of scope (decided, not forgotten)

- **Company / multi-team view** — cut deliberately. gnomon measures **one team as a whole**.
- **Browser login and CLI-linking screen** — the engineer links via terminal with a `TEAM_TOKEN`.
- **The operator's setup screen** — their entire experience is `.env` plus `docker compose up -d`. There is no configuration UI by design; the terminal is the screen.
- **Nudges or reminders aimed at people who did not upload.**

If any of these come back into scope, they need design work first — do not improvise them from this bundle.
