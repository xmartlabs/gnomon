# gnomon dashboard — design system v2 · "the instrument direction"

Replaces "The Ledger" (cream/terracotta, Fraunces + Archivo) in full. Nothing of the old
visual identity survived this pass — new palette, new typefaces, new components, dark mode.
`/cli-auth` is the one screen this redesign does not touch (out of scope in the handoff);
it still runs on the old Ledger tokens, kept side by side in `globals.css` under different
custom-property names so nothing collides.

## Source of truth

[`design-system-v2/`](./design-system-v2/) is the hi-fi handoff bundle, copied into the repo
verbatim so it survives after the original `~/Downloads` folder is gone:

- `design-system-v2/HANDOFF.md` — the full handoff brief (screens, copy rules, a11y commitments,
  interaction spec). Read this first for anything not covered below.
- `design-system-v2/design_system/tokens/*.css` — every CSS custom property, ported into
  `dashboard/src/app/globals.css` under the same names.
- `design-system-v2/design_system/components/**/*.jsx` (+ `.d.ts` + `.prompt.md`) — the reference
  implementation every component in `dashboard/src/components/ds/` was ported from.
- `design-system-v2/screens/*.jsx` — the two reference screens (`TeamDashboard.jsx`,
  `PersonProfile.jsx`) the actual pages were built against.

## Screens

| Screen | Route | Reference |
| --- | --- | --- |
| Equipo (team dashboard) | `/` | `design-system-v2/screens/TeamDashboard.jsx` |
| Perfil de persona | `/p/[personId]/[monthKey]` | `design-system-v2/screens/PersonProfile.jsx` |

Both live under `dashboard/src/app/(dashboard)/`, a route group with its own
`layout.tsx` (masthead: wordmark, month select, theme toggle). `/cli-auth` sits outside that
group and keeps the root layout's old styling untouched.

## The governing rule

**No cards.** Hierarchy comes from type size and whitespace, never from a bordered/shadowed
container. Grouping is a `SectionLabel`, a 1px hairline (`Divider`), and space — nothing else.
Corollaries, all binding:

- Asymmetric grids (`1.15fr auto 1fr`, `1fr auto 1.25fr`, `1.35fr auto 1fr`), never equal thirds.
- Bold is rationed to figures and headline titles — never body copy, never a table name.
- Actions are visible at rest ("Ver perfil ›" on every row, not a hover reveal).
- Definitions live in keyboard-reachable `Tooltip`s, not the native `title` attribute.
- Red (`--negative`) is only for a real decline or an error. Missing data is grey, never red.
- Colour is never the only carrier of meaning — every `Trend` renders a glyph and a number.

## Tokens

Ported verbatim into `globals.css`, appended after the old Ledger block (untouched, still
serving `/cli-auth`) rather than replacing it. Nothing here is registered into Tailwind's
`@theme` — components read the custom properties directly via inline `style` objects, exactly
like the reference components do, which is what makes them portable copy-paste.

- **Colour** — instrument blue (`--blue-50`…`--blue-900`, brand hue `#2A78D6`), cool greys
  (`--grey-0`…`--grey-950`), signal ramps (moss/clay/ochre for positive/negative/warning).
  Semantic tokens (`--text-*`, `--surface-*`, `--rule-*`, `--accent*`, `--chart-*`) remap
  entirely under `[data-theme="dark"]` — components never branch on theme, only read tokens.
- **Typography** — `--font-ui` (Archivo, self-hosted via `next/font/google`, reusing the same
  instance `/cli-auth` already loads) for language; `--font-figure` (IBM Plex Mono, new) for
  every number, label and code span, always `tabular-nums`. Composed roles: `--type-metric-xl`
  (88px) down to `--type-label` (11px uppercase tracked).
- **Spacing** — 4px base (`--space-1`…`--space-14`), `--layout-max: 1180px`.
- **Borders/radii/elevation** — two rule weights, near-square radii, one shadow token
  reserved for the `Tooltip` and nothing else.
- **Motion** — 80/120/180/320ms, zeroed under `prefers-reduced-motion: reduce`.

## Dark mode

New. `data-theme="light"|"dark"` on `<html>`, toggled by `ThemeToggle`
(`dashboard/src/components/ThemeToggle.tsx`) and persisted to `localStorage["gn-theme"]`. An
inline script in `app/layout.tsx` applies the saved-or-system theme **before** paint (no flash);
`<html>` carries `suppressHydrationWarning` because that script deliberately makes the
server-rendered markup and the first client paint disagree on that one attribute — expected,
not a bug.

## Components

`dashboard/src/components/ds/` — ported from `design_system/components/`, same names, same
prop shapes where the DOM allowed it (TSX types instead of the reference's untyped `props`):
`Button`, `IconButton`, `Badge`, `SectionLabel`, `Divider`, `Select`, `Metric`, `Trend`,
`PillarBar`, `DataTable`, `DonutChart`, `ColumnChart`, `Tooltip`, `EmptyState`.

Page-specific composition (not in the reference bundle, built to wire the primitives above to
real data): `AppHeader`, `MonthSelect`, `PeopleTable`, `TierSplit`, `TeamCoaching`,
`SuggestionsCard`.

**`DonutChart` note:** its slice path math rounds every coordinate to 2 decimal places.
`Math.cos`/`Math.sin` can differ in their last bit between Node (server render) and the
browser (client hydration) for the same input, which turns into a byte-different SVG `d`
string and a hydration mismatch React "won't patch up." Rounding collapses that noise below
anything that matters at a 176px chart. Its `<svg>` uses `role="group"`, never `role="img"` —
`img` forbids exposing focusable descendants, which would silence every slice's own
`aria-label` and make the whole chart unreachable by keyboard despite `tabIndex={0}` on each
`<path>`.

## Domain data — kept real, not the handoff's placeholder numbers

The handoff's own fixture data (`screens/data.js`) uses a 3-tier system (Pilot &lt;65, Operator
65–79, Architect 80+) and pillar weights 30/30/25/15. gnomon's real scoring engine
(`gnomon/scoring/aq.py`, untouched by this branch) uses six tiers — Elite ≥88, Advanced ≥75,
Proficient ≥60, Adequate ≥45, Apprentice ≥25, Novice — and weights 30/35/20/15. **Confirmed with
the user rather than assumed** (this exact fictional taxonomy appeared verbatim in two
independent design handoffs, which made it worth asking about explicitly instead of guessing
again). The dashboard shows the real six tiers and real weights everywhere; the handoff's
numbers were illustrative fixture data, not a product decision to adopt.

`TierSplit` (`Cómo se reparte el equipo`) only lists tiers with at least one person in them this
month — unlike `PillarBar`'s always-show-all-four pillars, an all-zero row for a tier nobody is
near reads as noise in this shorter list.

## Coach integration

`Qué mejorar este mes` (team) and `Sugerencias` (person) are the coaching surfaces the handoff
calls primary. Both are optional, gated on `LLM_API_KEY` exactly like the pre-existing AI coach
feature (`dashboard/src/lib/coach.ts`'s `getTeamInsight`/`getPersonSuggestions`, cached under
`coach-team:`/`coach-suggestions:` keys, never colliding with the original `coach:` prefix).
When the key is unset, the whole column collapses — decided **synchronously** via
`coachEnabled()` before the async generation call ever resolves, so there is never a dead
half-width column waiting on an LLM round-trip that will never come.

## Deliberate scope reductions vs. the previous (Ledger) implementation

The hi-fi reference screens don't show these, so they were dropped rather than carried forward
by default — flagged here instead of silently disappearing:

- **No column sorting** on the Personas table. The reference `DataTable` component has none;
  the table is presented pre-sorted by AQ.
- **No per-person month stepper** (previous/next arrows) on the profile page. The only
  month-changing control in this design is the header's global "Mes" select, which — per the
  handoff's own spec — always routes back to the team screen, even when triggered from a
  profile. A person's own history is visible only via the "Nivel en el tiempo" chart now.
- **No discrete AQ delta annotation** next to the person header's 96px figure (the team header
  keeps its `Trend`). The reference never shows one there.
- **"Último upload"** shows the raw `monthKey` (e.g. `2026-06`), not a relative string like
  "hace 2 días" — the dashboard has no upload-timestamp-to-relative-time formatter yet, and the
  monthKey is an honest substitute rather than fabricated precision.
- **No usage-over-time stacked chart** (tokens/cost by month, with a unit toggle) on the team
  screen. The reference has no equivalent — only the 3-month AQ history and the current month's
  model-mix donut.

None of these are backend limitations — the underlying data (`prevMonthKey`/`nextMonthKey`,
`uploadedAt` timestamps, the full monthly usage series) is still there in `lib/metrics.ts` and
`lib/db.ts`. Reintroducing any of them is a UI-only change if a future design calls for it.

## Verification

Unit (Vitest) 152 passed · E2E (Playwright) 19 passed, rewritten against this design's markup
and copy · `pnpm build` clean · manually reviewed in both themes at 1180px and 1600px viewports
(the 1600px pass caught a real bug: the old Ledger cream background bled through the side
gutters because `background` and `max-width` were on the same element — fixed by splitting the
dashboard layout into a full-width background wrapper with a centered, width-capped child).
