# gnomon dashboard — design system · "The Ledger" (huashu-design)

Chosen direction (from `/design-directions`, proposal A). An **editorial, warm, print-report**
aesthetic: cream stock, espresso ink, one terracotta accent, Fraunces display + Archivo body,
hairline rules instead of boxes. An AQ report *is* a periodical — so it's typeset like one.

Source of truth for the UI. The three screens are Playwright-verified hi-fi mockups in
`docs/design/mockups/*.html` (`*.png`). The Next.js implementation (Tasks 6/8/9) must match them —
do not hand-invent visuals. The three exploration directions are kept in `docs/design/directions/`.

## Screens

| Screen | Mockup | Implements |
|--------|--------|------------|
| CLI sign-in | `mockups/cli-auth.html` | Task 6 — `/cli-auth` |
| Team overview | `mockups/team-overview.html` | Task 8 — `/` |
| Person profile | `mockups/person-profile.html` | Task 9 — `/p/[personId]/[monthKey]` |

## Tokens (CSS variables → `globals.css`)

```css
:root {
  --paper:    #F6F1E6;   /* ground — cream stock */
  --paper-2:  #EFE8D8;   /* recessed panel / track wells */
  --ink:      #262016;   /* espresso ink — text, primary button, dark bars */
  --ink-60:   #6E655A;   /* secondary text */
  --ink-30:   #B4AA9A;   /* tertiary text / strong rule */
  --hairline: #D8CFBC;   /* hairline rules (the primary structural device) */
  --accent:   #B4451F;   /* terracotta — THE one accent (links, gains-context, active) */
  --gain:     #4A6A45;   /* muted moss — positive deltas */
  --loss:     #9A3B22;   /* burnt — negative deltas (kept in the accent family) */
  --parch:    #C9B99A;   /* parchment — 3rd chart series / older level bars */
}
/* page gutter outside the sheet */
html { background: #E9E2D2; }
body { background: var(--paper); color: var(--ink); }
```

Chart / model-mix series order: **ink (Opus) → terracotta (Fable) → parchment (Haiku)**. Segments
separated by a 2px `--paper` gap, not borders.

## Typography

Two Google fonts via `next/font/google` (self-hosted at build, no runtime CDN):

- **Fraunces** — display: headings, all big numerals (AQ, stat values, table AQ cell), the logo,
  tier badges, pillar names, italic archetype/annotation lines. Use optical-size axis (`opsz`)
  wide open at large sizes; italic in terracotta for accents. Weights 300–700, `ital` axis.
- **Archivo** — body: paragraphs, labels, table cells, buttons, inputs. Weights 400/500/600.

```ts
// app/layout.tsx
import { Fraunces, Archivo } from "next/font/google";
const display = Fraunces({ subsets: ["latin"], variable: "--font-display", axes: ["opsz"], weight: ["300","400","500","600","700"], style: ["normal","italic"] });
const body = Archivo({ subsets: ["latin"], variable: "--font-body", weight: ["400","500","600"] });
// <html className={`${display.variable} ${body.variable}`}>
// body { font-family: var(--font-body) }  .serif { font-family: var(--font-display) }
```

All numerals use `font-variant-numeric: tabular-nums`.

## Component patterns (the grammar)

- **No boxes — rules.** Structure comes from hairlines (`1px --hairline`) and heavy rules
  (`2px --ink`), not from bordered/rounded cards. Sections open with a 2px ink rule or an eyebrow.
- **Eyebrow label**: 11px, `letter-spacing:.18em`, uppercase, `--ink-60`, weight 600.
- **Section heading**: Fraunces 600, ~22–26px, `opsz` ~60.
- **Masthead**: Fraunces logo `gnomon` with a terracotta full-stop (`gnomon.`), small-caps
  "Team Dashboard" sub, right-aligned meta. Page opens with a 4px top ink rule.
- **Signature (the 120%)**: the drop-stat — a giant Fraunces numeral (team avg AQ ~148px on
  overview, person AQ ~120px on profile) with an inked italic annotation (`↗ +4 vs last month`).
  Everything else stays calm hairlines at 80%.
- **Stat column**: eyebrow + Fraunces value with muted `/unit` small, ruled left divider.
- **Tier badge**: NO pill. Fraunces small-caps + a leading dot in the tier's color. Elite→terracotta,
  Advanced→ink, Proficient→ink-60.
- **Table**: heavy ink header rule, uppercase Archivo column labels, hairline row dividers; Name in
  Fraunces, AQ cell in Fraunces ~22px, top-pillar in Fraunces italic, numeric columns right-aligned
  tabular. Sortable headers are `<button>` (active shows a small caret in accent).
- **Bars** (usage-over-time, level-over-time): flat fills, 2px ink baseline, dashed hairline
  gridlines with tabular labels; most-recent level bar in `--ink`, older bars in `--parch`.
  Fraunces total label above each column.
- **Sparkline / trend**: 1.8px SVG polyline — terracotta for up, ink-60 for down, ink-30 flat.
- **Toggle** (Tokens/Cost): 1px ink outline segmented; active segment ink fill, paper text.
- **Buttons**: primary = ink fill / paper text, 2px radius; secondary = ink outline; ghost = terracotta
  text with a terracotta underline (link-like).
- **Inputs**: no box — a single `--ink-30` bottom rule that turns terracotta on focus; uppercase
  eyebrow label above.
- **Coach card**: opens with a 2px terracotta rule, `AI COACH` eyebrow + `optional · LLM_API_KEY`
  badge, body set in Fraunces. Hidden entirely when the coach text is null.
- **Colophon**: a footer line ("gnomon · the AQ report · self-hosted" / window meta) in `--ink-60`.

## Anti-slop guardrails (applied)

- No emoji icons; the `§` privacy mark and `↗` annotation tick are typographic glyphs.
- No gradients at all — the warmth is the paper color, not a wash.
- No rounded-card-with-left-border cliché — hairline rules carry structure.
- Numerals always Fraunces + tabular; colors never invented outside the token set.
- Real fake data throughout (Ada / Alan / Grace / Katherine — same team as `scripts/seed.ts`).

## Empty state (design spec §Error handling)

No uploads yet → overview shows a ruled onboarding block (not a boxed card) with the exact CLI
command `xl-ai-insights --mirdash-base=http://localhost:3000` set in a mono/Archivo run, copyable.
