# Gnomon Design System

**gnomon** reads your sessions with coding agents — Claude Code, Cursor, Codex — scores how
you work with them, and suggests improvements. Historically the result died in a local
`profile.html` that nobody else saw. The product this system dresses is the **self-hosted team
dashboard**: any team runs `docker compose up -d`, points the gnomon CLI at their own server,
and gets the aggregate view without sending data to a third party.

Three people touch it, and only one of them lives in it:

| Role | Relationship to the UI |
| --- | --- |
| The operator who deploys | Terminal only — `.env` plus `docker compose up -d`. Never opens a screen. |
| The engineer who uploads | One pass through a browser screen, once. The user with the most to lose: what they upload describes how they work. |
| The lead who reads | Uses the product daily and installs nothing. **The dashboard is designed for this person.** |

Two scores sit at the centre of everything:

- **AQ · Agentic Quotient (0–100)** — how you *operate* agents. Four fixed-weight pillars:
  Breadth 30% (how much machinery you move), Craft 30% (how well), Efficiency 25% (the return
  on each intervention), Savvy 15% (judgment). Tiers: Pilot &lt;65, Operator 65–79, Architect 80+.
- **gstack scorecard (0–10 each)** — how you *build*: Execution, Planning, Engineering.

Below both sit deterministic counters (planning ratio, error recovery, git churn, fanout…).
**The distinction matters and the UI must preserve it:** the scores are opinionated rubrics,
the counters just count. Counters are never dressed up as judgments.

## Sources

No brand materials, codebase, repository or Figma file were provided for gnomon. This system was
authored from scratch against a direction the product owner chose:
*measuring instrument + Swiss minimal, accent `#2A78D6`, light default with dark, sober tone,
web app only.* It also encodes the composition decisions validated during the wireframe phase
(see `ui_kits/dashboard/README.md`).

Two substitutions are flagged and awaiting real assets:

1. **Typefaces** — no font binaries exist. Archivo and IBM Plex Mono are Google Fonts stand-ins
   (see `tokens/fonts.css` for how to swap them).
2. **Icons** — no icon set exists. The dashboard needs almost none; where a glyph is unavoidable
   the system uses Unicode geometry (▲ ▼ ‹ › ● ○). If an icon set is adopted, Lucide is the
   nearest match to this direction (1.5px stroke, square terminals) and should be pulled in
   properly rather than hand-drawn.

**The gnomon mark now exists.** Two triangles — the rod and the shadow it casts — see
`assets/logo/logo.card.html` for the mark, lockup, clear space, sizes, and the dark-background
pair. The wordmark pairs it with the word *gnomon* in Archivo.

---

## CONTENT FUNDAMENTALS

**Product language is Spanish (Rioplatense).** Interface copy is Spanish; the design system's own
specimen cards use English glosses so the system reads for any implementer.

**Sentence case everywhere except section labels.** Titles are sentence case with a full stop
when they are sentences: *"Breadth es el pilar más flojo del equipo."* Section labels are the one
exception — mono, uppercase, tracked out: `CUATRO PILARES`, `TOKENS · COSTO`.

**Second person, never first.** The product addresses the reader: *"planificá amplio, ejecutá
angosto"*, *"corré gnomon push"*. It never says "we" and never speaks as gnomon in first person.
Voseo, not tuteo — *corré*, *revisá*, *probá*.

**Findings are stated, not softened.** The coaching tone is sober, not encouraging:

> Breadth es el pilar más flojo del equipo.
> Solo 2 de 6 personas orquestan subagentes. Impacto estimado: +5 AQ de equipo.

Not *"¡Hay una oportunidad de mejora en Breadth!"* — no exclamation marks, no cheerleading, no
hedging. A finding is a measurement with a consequence attached.

**Every number carries its denominator and its comparison.** `72 /100`, `▲ +4 vs julio`,
`5 personas subieron este mes`. A bare figure with no scale is not shipped.

**Nothing is claimed about people beyond what was measured.** The product scores *how someone
operates agents*, never the person. Copy says *"Breadth 58 es tu pilar más flojo"*, never
*"sos flojo en Breadth"*. Archetype lines are descriptive and reusable, not verdicts:
*"Explorador — probá rápido, decidí después"*.

**Jargon is defined in place, once.** AQ, Breadth, gstack, fanout, compounding writes are all
project vocabulary. Each gets a tooltip at first appearance on a screen; the label itself stays
1–3 words. Definitions beside a title are a known anti-pattern here.

**Empty and error copy names the cause and the fix.**
*"Nadie subió sesiones en Junio 2026. Los datos aparecen cuando alguien corre `gnomon push`
apuntando a este servidor."* Never *"No data available"*.

**No emoji.** Not in the product, not in the CLI output, not in the design system.

---

## VISUAL FOUNDATIONS

### The governing idea

gnomon is an instrument. Its screens should read like a well-set measuring device: precise,
unornamented, quiet at rest, and legible at a glance. **Hierarchy comes from type size and
whitespace, never from containers.** This is the single most important rule in the system and the
one that was fought for during the wireframe phase.

### What this system does not do

There are **no cards**. No bordered, shadowed, rounded rectangle wrapping a metric. No card with a
coloured left border. No icon-in-a-tile. No gradients — not in backgrounds, not in bars, not
anywhere. No decorative illustration. No emoji. No blur, no glassmorphism, no transparency
effects. If information needs grouping, it gets a `SectionLabel`, a hairline, and whitespace.

### Layout

Content is centred in a `--layout-max` of 1180px with a 32px gutter. Sections are **asymmetric
by default**: `1.15fr auto 1fr`, `1fr auto 1.25fr`, `1.35fr auto 1fr` — never three equal
columns, which is what a card grid looks like. The `auto` track is a 1px vertical rule
(`Divider orientation="vertical"`). Horizontal sections are separated by 48px plus a hairline.
The vertical rhythm runs 96 / 80 / 48 / 32 / 24 / 16 / 12 / 8.

### Type

Two families, strictly divided by job:

- **Archivo** (`--font-ui`) for language: titles, body, labels of things.
- **IBM Plex Mono** (`--font-figure`) for every figure, always with `tabular-nums` so numbers
  align down a column. Also for section labels, units, and code.

The metric scale is deliberately extreme — 88 / 64 / 40 / 28 / 20px. **One `xl` figure per
screen**, and that figure is the screen's subject: the team's AQ on the dashboard, the person's AQ
on a profile. Titles run 32 / 24 / 19, body 16 / 15 / 13, labels 12 / 11. Metrics get
`-0.025em` tracking, titles `-0.015em`, labels `+0.1em` uppercase. Long prose gets
`text-wrap: pretty`.

### Colour

Cool desaturated greys carry almost everything; **instrument blue `#2A78D6` is the only
chromatic colour in normal use** — accent, links, primary action, chart fills. The blue ramp
doubles as the data palette (`--chart-1` … `--chart-4`, then grey), so a set of series reads
as ordered rather than categorical. Series in a share-of-total chart must therefore be sorted
descending.

The ramp splits by job: `--blue-500` is the brand hue and is used for fills that carry no text
(chart series, the mark's darker triangle — `--accent-mark`; its lighter triangle is
`--accent-mark-shadow`), while `--accent` resolves to `--blue-600` because links and primary
buttons must clear 4.5:1. Never put text on `--accent-mark` or `--accent-mark-shadow`.

Status colours are strictly rationed: moss green for a real rise, clay red **only** for a real decline
or an error, ochre for a warning, grey for flat or missing. **Colour is never the sole carrier of
meaning** — every trend renders a glyph and a number too (`▲ +6`, `▼ −3`, `= 0`, `— sin datos`),
so the screen survives greyscale and colour-blindness.

`--text-tertiary` is the lightest grey allowed to carry **words** (4.5:1 in both themes).
`--text-decorative` is lighter still and restricted to `aria-hidden` marks — chevrons, hairline
glyphs — never to text.

Backgrounds are flat: `--surface-page` is plain white in light, near-black in dark. There are no
background images, patterns, textures or full-bleed photographs anywhere in this system.

### Rules, corners, elevation

Three hairline weights carry the whole layout: `--rule-strong` (under the header, above table
headers, above pillar columns), `--rule-default` (between sections and columns),
`--rule-subtle` (between rows in a list or table). One 2px variant exists for a strong emphasis
rule and for a chart's reference tick.

Corners are near-square: 0 by default, 2px on controls, 3px at most, and `999px` only for the
small round tooltip marker. **Elevation is a single token**, `--shadow-overlay`, and it is only
for things that must detach from the page — tooltips and dialogs. Nothing else casts a shadow.

### Cards (the exception)

The system has no card component. If a future surface genuinely needs an enclosed panel, it is a
1px `--rule-default` border, `--radius-sm`, `--surface-raised`, and **no shadow** — and it
should be argued for first.

### Interaction

- **Hover** — surfaces lighten one step (`--surface-hover`); accent fills darken one step
  (`--accent-hover`). Links darken and keep their underline.
- **Press** — one step further (`--surface-active` / `--accent-pressed`). Nothing scales,
  nothing shrinks, nothing bounces.
- **Focus** — a 2px `--focus-ring` outline at 2px offset, on every interactive element
  including table rows.
- **Affordance never depends on hover.** A clickable table row carries a persistently visible
  "Ver perfil ›" link. This is a hard rule: a reveal-on-hover action is treated as a bug.
- **Disabled** — 40% opacity plus `not-allowed`.
- **Touch targets** — 32px minimum, 40px standard.

### Motion

Movement is confirmation, never entertainment: 80 / 120 / 180 / 320ms with `ease-out` for
entrances and `ease-in-out` for state changes. The only animation in the shipped dashboard is a
chart slice offsetting 4px on hover and a table row's background fading in. No page transitions,
no staggered reveals, no parallax. `prefers-reduced-motion` zeroes every duration.

### Charts

Charts are drawn with the same restraint as the type: no axes, no gridlines, no legends with
redundant values. Column charts put the value above the column and emphasise only the current
period. Bars are a flat `--chart-track` rail with a solid fill. Donuts cap at 4–5 slices and
hold their percentages in the hover, keeping the resting state quiet. Bar heights are computed in
**pixels, never percentages** — a percentage height inside an auto-height flex column collapses
to zero.

### Dark theme

`[data-theme="dark"]` remaps the same token names — no component knows which theme is active.
Surfaces go near-black, the accent lightens to `--blue-300` so it holds contrast on dark, and
the data ramp inverts direction. Light is the default.

### Accessibility commitments

WCAG 2.2 AA. Body text on page meets 4.5:1; rules and chart fills meet 3:1. Information is never
colour-only. Every chart carries an `aria-label` describing its values. Labels are always
visible — placeholders never stand in for them. Errors are specific and actionable, announced with
`role="alert"`. Definitions live in keyboard-reachable tooltips, not the native `title`
attribute — `SectionLabel` delegates its `hint` to `Tooltip`, whose marker carries a 24×24px
hit area around a 16px visual circle. Headings run h1 → h2 → h3 in order: each screen opens with one `h1`, and every real section
title is a `SectionLabel as="h2"` — that component is the only thing carrying the outline, since
it replaced card headers throughout the system.

---

## ICONOGRAPHY

**gnomon is an almost icon-free product, on purpose.** A dashboard whose job is to be read does
not need a glyph beside every label, and icons-in-tiles is exactly the card-grid look this system
rejects.

What exists:

- **Unicode geometry** for the few marks that carry meaning: `▲` `▼` for trend direction,
  `=` for flat, `—` for no data, `‹` `›` for stepping and row actions, `●` `○` for the
  theme toggle, `i` in a hairline circle for a tooltip marker. These are set in
  `--font-figure` so they align with figures.
- **The mark** in the wordmark — the gnomon of a sundial and the shadow it casts, two triangles
  drawn as an inline SVG (`assets/logo/`). It is the only piece of brand geometry.
- **Two inline SVG marks**, both 1.5px stroke on `currentColor`: a crescent moon and a sun, for
  the theme toggle. They are the only drawn glyphs in the product and follow the Lucide stroke
  spec below, so they swap out cleanly if that set is adopted.
- **No icon font, no sprite sheet, no PNG icons, no emoji.**

If an icon set becomes necessary (a settings surface, a nav rail), use **Lucide** from CDN at
`strokeWidth={1.5}`, sized 16 or 20, coloured `currentColor` — its square terminals and even
stroke match the instrument direction. Load it properly; never hand-draw an approximation.

---

## Index

| Path | What it is |
| --- | --- |
| `styles.css` | The entry point consumers link. `@import` list only. |
| `tokens/fonts.css` | Font families + the substitution note. |
| `tokens/colors.css` | Greys, green ramp, signal colours, semantic aliases, dark theme. |
| `tokens/typography.css` | Families, weights, metric/title/body/label scales, composed roles. |
| `tokens/spacing.css` | 4px scale, layout widths, control heights. |
| `tokens/borders.css` | Rule weights, radii, the single overlay shadow, focus ring. |
| `tokens/motion.css` | Durations, easings, reduced-motion override. |
| `tokens/base.css` | Minimal resets, link and focus defaults, tabular figures. |
| `guidelines/*.card.html` | 13 foundation specimens: colour, type, spacing, corners. |
| `assets/logo/` | The gnomon mark — lockup, clear space, sizes, on-dark pair, don'ts. |
| `components/core/` | Button, IconButton, Badge, SectionLabel, Divider |
| `components/forms/` | Input, Select |
| `components/data/` | Metric, Trend, PillarBar, DataTable, DonutChart, ColumnChart |
| `components/feedback/` | Tooltip, EmptyState |
| `ui_kits/dashboard/` | The hi-fi team dashboard + person profile, click-through. |
| `SKILL.md` | Agent Skills entry point if this is used from Claude Code. |

### Intentional additions

This system had no source inventory to mirror, so the component set was authored to the product's
needs rather than to a generic checklist. Four data primitives — `Metric`, `Trend`,
`PillarBar`, `DataTable` — plus two charts exist because gnomon is a measurement product and
these carry most of every screen. Conversely, primitives a design system "usually" has and gnomon
does not use (Checkbox, Radio, Switch, Tabs, Toast, Dialog, Avatar, Accordion) were deliberately
**not** built: nothing in the product calls for them yet, and an unused primitive is something
implementers will trust and designers will not recognise. Ask before adding one.

### Known gaps

- **Responsive behaviour is unspecified.** Every screen is designed for ~1180px desktop. The
  asymmetric grids and the 88px metric need explicit rules below ~900px.
- **Loading states are undefined.** The dashboard loads a whole month at once; skeletons for the
  large figures and the bars still need designing.
- No print stylesheet, though a printable monthly report is a plausible next surface.
