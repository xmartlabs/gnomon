# gnomon dashboard — design system (huashu-design)

Source of truth for the UI. The three screens were designed as hi-fi HTML mockups
(`docs/design/mockups/*.html`, verified via Playwright screenshots `*.png`). The
Next.js implementation (Tasks 6/8/9) must match these — do not hand-invent visuals.

## Screens

| Screen | Mockup | Implements |
|--------|--------|------------|
| CLI sign-in | `mockups/cli-auth.html` | Task 6 — `/cli-auth` |
| Team overview | `mockups/team-overview.html` | Task 8 — `/` |
| Person profile | `mockups/person-profile.html` | Task 9 — `/p/[personId]/[monthKey]` |

## Tokens (CSS variables → `globals.css`)

```css
:root {
  --bg-base:      #14181f;   /* app background (+ a single faint radial glow, not a wash) */
  --bg-surface:   #1b212b;   /* cards, table, form */
  --bg-elev:      #232b37;   /* inputs, tracks, toggle, inner wells */
  --text-primary: #f2f4f7;
  --text-secondary:#c2c8d2;
  --text-muted:   #7d8698;
  --border:       rgba(255,255,255,.07);
  --border-strong:rgba(255,255,255,.12);
  --accent:       #ee1a64;   /* pink — primary, Opus, Elite, deltas up-context */
  --purple:       #6d6ff2;   /* secondary — Advanced, Fable */
  --teal:         #2dd4bf;   /* tertiary series — Haiku */
  --amber:        #f5b642;   /* quaternary series / cost accent */
  --good:         #34d399;   /* positive delta, coverage ok */
}
```

Series color order for charts / model mix / stat accent bars: **accent → purple → teal → amber → slate**.

## Typography

Two Google fonts, loaded via `next/font/google` (self-hosted at build, no runtime CDN):

- **Space Grotesk** — all UI text, headings, labels. Weights 400/500/600/700.
- **IBM Plex Mono** — every number: AQ, tokens, cost, deltas, axis scores, month labels. Weights 400/500/600.

```ts
// app/layout.tsx
import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
const sans = Space_Grotesk({ subsets: ["latin"], variable: "--font-ui", weight: ["400","500","600","700"] });
const mono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400","500","600"] });
// <html className={`${sans.variable} ${mono.variable}`}>
```

Map to `--font-ui` / `--font-mono` and set `body { font-family: var(--font-ui) }`. Anything numeric uses `font-family: var(--font-mono)`.

## Component patterns (shared)

- **Cards**: `--bg-surface`, `1px solid --border`, `border-radius: 16px`. Profile header cards 22px.
- **Section heading**: 11–12px, uppercase, `letter-spacing:.16em`, `--text-muted`, weight 600.
- **Stat card**: uppercase label + big mono value (`--font-mono`, ~34px) with muted `/unit`; left 3px accent bar cycling the series colors; one-line footer with delta.
- **Tier badge**: pill, 1px border, tinted bg. Elite→accent, Advanced→purple, Proficient→slate.
- **Table**: uppercase mono-spaced header row (sortable headers are `<button>`, active shows `↓`/`↑` in accent); numeric columns right-aligned + mono; avatar = rounded 9px square with initials on a series-color gradient; row hover `rgba(255,255,255,.018)`.
- **Bars** (usage-over-time, level-over-time): flat series colors, subtle shadow, rounded top; most-recent level bar in `--accent`, older bars in `--purple` at .5 opacity.
- **Sparkline / trend**: 2px inline SVG polyline in the row's series color, end dot.
- **Toggle** (Tokens/Cost): pill segmented control, active segment `--accent` on white text.
- **Coach card**: `--purple` border, faint purple gradient fill, `✦ AI COACH` eyebrow + `optional · LLM_API_KEY` badge. Hidden entirely when the coach text is null.

## Anti-slop guardrails (applied)

- No emoji icons (the single `✦` coach glyph is a typographic mark, not an icon set).
- No gradient wash — one faint radial glow per screen, positioned, not full-bleed.
- Numbers always mono; never invent colors outside the token set.
- Real fake data throughout (Ada/Alan/Grace/Katherine — same team as `scripts/seed.ts`), never lorem or fabricated stats-as-decoration.

## Empty state (design spec §Error handling)

No uploads yet → overview shows an onboarding card (same card styling) with the exact CLI command:
`xl-ai-insights --mirdash-base=http://localhost:3000`, mono, copyable.
