# UI kit · gnomon team dashboard

The hi-fi build of the two screens the product actually ships. Open `index.html`.

## Screens

**Tablero de equipo** (default) — the lead's daily view, in reading order:

1. Team AQ as an 88px figure with its trend, a 3-month column chart, and tokens/cost on the right.
2. The four pillars against the month's coaching finding, split by a vertical rule.
3. Model mix (donut, hover to inspect) against the tier split.
4. `Equipo` — the per-person table, every row opening a profile.

**Perfil de persona** — reached from any table row:

1. Name, email and archetype line against a 96px AQ and the tier badge.
2. **Suggestions first**, then the gstack scorecard and the 6-month level history. Suggestions
   lead because the product's tone is coaching, not ranking.
3. The four pillars broken into their rubric axes.
4. Explore (deterministic counters) against usage and this person's model mix.

**Estado vacío** — pick *Junio 2026* in the header. It replaces the entire content region rather
than showing empty figures, and always offers a way back to a month with data.

**Dark theme** — the ● / ○ toggle in the header flips `data-theme` on `<html>`. No component
reads the theme; the tokens do all the work.

## Composition decisions carried over from the wireframes

These were argued for and validated during the wireframe phase. They are not stylistic
preferences — treat them as constraints:

- **No cards.** Hierarchy is type size, whitespace and hairlines.
- **Asymmetric grids** (`1.15fr auto 1fr`, `1.35fr auto 1fr`), never equal thirds.
- **Bold is rationed** — figures and headline titles only, never body copy or names.
- **Actions are visible at rest.** Table rows carry "Ver perfil ›" without hovering.
- **Definitions live in tooltips**, so labels stay 1–3 words.
- **Back navigation is always on screen** — the profile's breadcrumb, the wordmark.
- **Red is only for real declines.** Neutral and missing data are grey.
- **One team, as a whole.** There is no company or multi-team view; that was cut deliberately.
- **No avatars or photos of people.**

## Out of scope (decided, not forgotten)

Company / cross-team comparison, the browser login and CLI-linking screen, the operator's setup
screen (`.env` + `docker compose up -d`, with the container refusing to boot without
`TEAM_TOKEN`), and nudges aimed at people who did not upload.

## Files

| File | Contents |
| --- | --- |
| `index.html` | Shell + bootstrap. Loads component sources, transforms them, mounts `App`. |
| `App.jsx` | View state (team / person), month, theme. |
| `AppHeader.jsx` | Wordmark, month select, theme toggle. |
| `TeamDashboard.jsx` | Team screen, coaching block, tier split, empty state. |
| `PersonProfile.jsx` | Profile screen, scorecard, pillar axes, counters. |
| `data.js` | Fixture data — six people, team aggregates, counters. |

## Implementation notes

- The kit reads component sources directly so it renders before the design-system bundle exists.
  In a real app, import the components instead.
- All data is fixture data in `data.js`. Real endpoints: one per month for the team aggregate
  plus the people list, one per person/month for the profile — both served from the team's own
  container, with no external calls.
- Chart bar heights are computed in pixels. Percentage heights inside an auto-height flex column
  collapse to zero.
