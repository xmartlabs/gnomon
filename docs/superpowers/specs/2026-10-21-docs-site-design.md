# gnomon documentation site — design

Date: 2026-10-21 · Status: draft for approval · Approved mockup: [`2026-10-21-docs-site-mockup.html`](./2026-10-21-docs-site-mockup.html)

## Intent

gnomon is going to be sold to client companies. Its documentation has two jobs:

1. **Sell.** A technical lead or manager at a client should be able to see what gnomon measures and why each measurement matters to their business.
2. **Help people improve.** A developer at that client who looks at their own profile should be able to find out exactly how each number is computed, where they sit, and which habit moves them up.

Both readers use the same site (the user said "todos"). Each metric page therefore has two layers. The top is short and in plain language: what the metric measures and why it matters. Below that is the detail: the exact formula, the rubric, and how to improve.

Today the documentation is split across an ~800-line `README.md` and three metric docs under `docs/`. All of them have drifted from the code (see "Known drift" below). The user wants **one** place for documentation, with no repeated documents, published as a website.

## Goals

- Publish all of gnomon's user-facing documentation as a GitHub Pages site at `https://xmartlabs.github.io/gnomon/`. That covers install, usage, outputs, metrics, sources, privacy, sharing, the self-hosted dashboard, miraudit, and contributing.
- Give every metric gnomon computes and shows a page that explains **what** it measures, **how** it is computed (exact formula, weights, targets, minimums), and **why** it is measured.
- Give each scored AQ axis a **rubric**. A rubric has six levels. Each level describes in plain words what working at that level looks like and names the one concrete habit that moves you to the next level.
- Make the site accurate to the current score contract `19:19:19` (`gnomon/scoring/versioning.py`). Every formula cites the code path it comes from.
- Remove duplicated documentation. Each fact lives in exactly one place.

## Non-goals

- Changing any scoring logic, weights, targets, or the score contract.
- Fixing drift inside code or the dashboard: docstrings, tooltips in `gnomon/scoring/gstack.py`, and dashboard tiles. These go into GitHub issues (see "Follow-up issues"). They are not fixed in this work.
- Translating the site. It is English only.
- Touching internal/historical docs: `docs/plans/`, `docs/specs/`, `docs/superpowers/`, `docs/design/`, `docs/adr/`. They stay in the repo and are **not** published on the site.

## Anti-goals (failure even if it "works")

- **Docs that disagree with the code.** This is the problem being solved; repeating it is the worst outcome.
- **Marketing fluff.** The site sells through transparency and specifics, not adjectives. No inflated claims and no "revolutionary". It follows the copy rules in the design system: plain verbs, sentence case, no filler.
- **Duplicated content.** The same text must not be maintained in two files, whether README vs. site or axis page vs. overview page.
- **Implying a missing signal scores zero.** When a source can't record a signal, the term or axis is dropped and its weight is redistributed (`wsum` / `build_pillar` in `gnomon/scoring/aq.py`). The docs must say this clearly wherever coverage is shown. It is a selling point: nobody is penalized for the tool they use.
- **A templated look.** The user rejected the first generic wireframe. The site must carry gnomon's own visual identity (see "Visual design").

## Constraints

- The repo `xmartlabs/gnomon` is public. GitHub Pages is not enabled yet (the API returned 404 on 2026-10-21).
- **Enabling Pages is a manual, outward-facing step.** In Settings → Pages, set "Source: GitHub Actions". The user does it, or the builder does it only with the user's explicit OK.
- The Python package is stdlib-only (`pyproject.toml`: `dependencies = []`, `requires-python >= 3.8`). Docs tooling must **not** become a runtime dependency of the package.
- Existing workflows (`ci.yml`, `dashboard-deploy.yml`, `dashboard-image.yml`, `release.yml`) must keep working unchanged.
- The content must match code at HEAD. Where these docs and the code disagree, the code wins.

## Decisions made with the user

1. **Platform.** Static site built with **MkDocs + Material for MkDocs**, deployed to GitHub Pages by a new GitHub Actions workflow. The workflow runs on pushes to `main` that touch the docs sources or the site config, and on manual dispatch.
2. **Scope.** The site holds **all** user-facing documentation, not only metrics.
3. **Language.** English.
4. **Transparency.** Show exact formulas, weights, targets, and thresholds. The repo is open source, so hiding them protects nothing, and transparency is the selling point.
5. **Unscored or provisional metrics are shown, labelled, not hidden.**
   - Steering leverage is labelled "Not scored yet" (`STEERING_LEVERAGE_BAND_VALIDATED = False`). The page explains that Efficiency is currently Recovery alone.
   - Context Intelligence's 0.60 target is labelled "Provisional" (never fitted, per `aq.py`).
6. **Deletions.**
   - Delete `docs/scoring-philosophy.md`, `docs/metrics-evaluation.md`, and `docs/metrics-by-source.md`. Their still-true content moves into the site, corrected against the code.
   - Shrink `README.md` to a short landing: what gnomon is, a one-command install, a quick start, and links to the site. Everything else in it moves to the site.
7. **Rubric shape.** Six levels per axis. Each level has three parts: level name with its score range, "what it looks like", and "next step" (omitted on the top level).
8. **Visual direction.** Follow the approved mockup. It is built on gnomon's design system v2, "the instrument direction" (`docs/design/design-system.md`, tokens in `docs/design/design-system-v2/design_system/tokens/`). The rubric is drawn as a **calibrated scale** (see "Visual design").

## Landing page

Decided with the user: the site's front page is a **separate sales landing**, not a docs page. It ends in a **"Contact us"** call to action. The user asked for it to be "super lindo" and to use **3D animations in JavaScript**.

- **Job.** Make a technical lead at a client company want to contact Xmartlabs, and give a developer a clear path into the docs.
- **Visual.** It shares design system v2's identity and may be bolder than the docs pages. The 3D signature comes from gnomon's own world: the sundial pin whose shadow measures.
- **Quality floor.** With reduced motion, or without WebGL, the page shows a static frame that still looks good. Content never lives only inside the canvas. Rendering pauses when the page is off-screen.
- **Design: approved mockup [`2026-10-21-docs-landing-mockup-v2.html`](./2026-10-21-docs-landing-mockup-v2.html).** The user rejected the first attempt (`…-landing-mockup.html`) as "fea": a flat, diagram-like dial. That file stays only as a reference for what not to do. The approved direction:
  - A night-blue studio hero with a physical sundial: a steel case with a polished bezel, a matte porcelain dial with the AQ scale printed on it, a blue enamel level band, and a blue-steel obelisk gnomon.
  - A real moving sun whose soft shadow sweeps the scale, with a live "Shadow at NN · Level" caption.
  - Built with three.js and physically based materials.
  - The rest of the page keeps the v1 sections and copy.
- **Defects to fix when building**, seen in the v2 screenshots:
  - A shadow sliver leaks onto the backdrop to the left of the dial.
  - A ~2 s "night" gap between dusk and dawn leaves the dial flat grey.
  - The shadow edge dithers under zoom.
- **Not tested yet:** Safari, Firefox, and weaker GPUs. Testing them is part of building.
- **Integration.** The landing becomes the site's home page, through a Material template override, and keeps its own layout and dark hero. The docs pages keep the light/dark docs theme. Whether three.js is loaded from a CDN or vendored is left to the builder; either way it stays pinned, and the static SVG fallback covers a CDN failure.
- **Copy the owner hasn't explicitly confirmed** (kept as written unless they object):
  - "Tell us about your team and the agents it uses, and we will get back to you."
  - "Bring gnomon to your team."
- **Contact destination.** Decided with the user: "Contact us" links to `https://www.xmartlabs.com/contact`. The company name or logo links to `https://www.xmartlabs.com/`. *My call:* both links carry `utm_source=gnomon-docs&utm_medium=landing`, so sales can tell which leads came from gnomon. Each link that differs in intent also gets its own `utm_content` value, such as `hero-cta` and `footer-cta`.

## Site structure

Navigation, as approved in the mockup:

- **Get started** — Why gnomon · Install & quick start · Usage & outputs
- **Metrics**
  - How scoring works: AQ formula, the 4 pillars and their weights, levels, "missing signals are not zeros", the one-month window, minimum sessions, the score contract.
  - **Breadth** (30% of AQ) — Orchestration · Skill fluency · Tool command · Discipline
  - **Craft** (35%) — Verification · Grounding · Context intelligence · Compounding
  - **Efficiency** (20%) — Recovery · Steering leverage (not scored yet)
  - **Savvy** (15%) — Model mix · Token economy
  - GStack scorecard: Execution, Planning, Engineering (0–10), with their verdict bands.
  - Insights & trend: tier and archetype, signature moves, growth edges, steering reading, the 6-month trend, and descriptive extras.
  - Rubric at a glance: one matrix of every axis × level.
- **Sources** — Supported tools · What each source measures (capability matrix built from `SOURCE_CAPS` in `gnomon/config.py`)
- **Teams** — Sharing a profile · Self-hosted dashboard, which includes a "What the dashboard shows" section covering each team and person view (average AQ and delta, tier distribution, pillar averages, model mix, team trend, cost from `dashboard/src/lib/pricing.ts`) with what and how, but no rubric. *My call.*
- **Project** — Privacy · miraudit · Contributing

Each pillar entry in the nav is a short page: what the pillar captures, its weight, and links to its axes.

## Axis page template

Every axis page follows the mockup, in this order:

1. Breadcrumb (`Metrics / <Pillar>`), title, and a one-to-two-sentence **thesis** in plain language that names what the axis measures.
2. **Why it matters.** A short paragraph aimed at a technical lead.
3. **How it's computed.** A spec-sheet table with one row per term: the term's weight inside the axis, a plain-language name and definition, and its full-credit target. Follow it with eligibility rules (minimum sessions, what counts as a change session, and so on) and the code path.
4. **Rubric.** The calibrated scale with six bands.
5. **How to improve.** Concrete actions, grounded in what the code actually rewards.
6. **Right rail, "at a glance".** The axis's weight inside its pillar, its effective share of total AQ (pillar weight × axis weight, rounded), and per-source coverage. Coverage states are "Full", "Partial (which half)", or "Not scored", always in words, never colour alone.

Content source: the code inventory taken at HEAD `1860ef0` (summarised in "Metric inventory" below). The builder re-verifies every number against the code while writing.

## Rubric

- **Levels and cut-offs.** The levels reuse the AQ tier names and floors from `TIER_FLOORS` in `gnomon/scoring/aq.py`: Novice 0, Apprentice 25, Adequate 45, Proficient 60, Advanced 75, Elite 88. They are applied to the axis's **fill**: axis score ÷ the axis's effective weight, as a percentage. One level then means the same thing on every axis and for the overall AQ. The code defines tiers only for total AQ. Applying them per axis was proposed in the mockup and approved by the user with it. The profile already shows each axis's fill on a 0–100 scale as `normalized_score` (`gnomon/output/profile/sections/breakdown.py:148-155`), so a reader can place themselves on the scale. For an axis whose sibling is withheld (Recovery while Steering leverage is not scored), the rail shows the effective weight that `build_pillar` computes.
- **Rubric text.** Each band's "what it looks like" and "next step" is written from the axis's actual terms and targets. A rubric must never reward something the code doesn't measure.
- **Single source of truth.** Rubric content lives once in a data file. Both the axis pages and the "Rubric at a glance" page render from it, so nothing is written twice. *My call; the builder picks the mechanism, such as the `mkdocs-macros` plugin or a small hook.*
- **GStack scorecard.** It uses its own existing verdict bands from `gnomon/scoring/gstack.py`, not the six AQ levels: excellent ≥8, good ≥6.5, adequate ≥5, weak ≥3, poor below that on the 0–10 scale. It gets no six-level rubric.

## Visual design

The site must look like the approved mockup. Its rules come from design system v2:

- **Colour.** Instrument blue (`--blue-500` `#2A78D6` for marks and fills, `--blue-600` for text links), cool greys, and status colours only for status. Full dark mode, using the same token remap as the dashboard.
- **Type.** Archivo for language; IBM Plex Mono for every figure, label, and code span, with tabular numbers. Labels are 11px uppercase and tracked.
- **Layout.** No cards. Hierarchy comes from type, hairline rules, and whitespace. The grid is asymmetric: left nav, content, right rail.
- **Signature element: the calibrated scale.** A 0–100 ruler with minor ticks every 5, major ticks every 25, and strong cut marks at the level floors. Below it is a track filled with the ordered blue ramp, and under each segment its band text. On narrow screens it collapses to a vertical list of bands.
- **Quality floor.** Responsive to mobile, visible keyboard focus, `prefers-reduced-motion` respected, and colour never the only carrier of meaning.

Material for MkDocs is themed to this using custom CSS (`extra_css`) and template overrides. The calibrated scale is a reusable component used on all scored axis pages. *Exactly how it is implemented is left to the builder.*

## Content migration

| Current location | Goes to |
|---|---|
| `README.md` "Why gnomon", "Quick start", "Usage", "Outputs" | Get started pages |
| `README.md` "What it measures" (`README.md:226-386`) | Metrics section (corrected) |
| `README.md` "Sources" | Sources pages |
| `README.md` "Privacy", "Sharing your profile", "Self-hosted team dashboard", "miraudit", "Project goals and alternatives" | Project/Teams pages, with goals and alternatives folded into "Why gnomon" |
| `README.md` "Docs", "Contributing", "License and credits" | README keeps a short license/credits line; the rest moves to the site |
| `docs/scoring-philosophy.md` | How scoring works, plus per-axis "Why it matters" |
| `docs/metrics-by-source.md` | Sources → What each source measures (rebuilt from `SOURCE_CAPS`) |
| `docs/metrics-evaluation.md` | Its user-relevant parts go to "How scoring works" (calibration and contract). The internal evaluation-loop material is dropped. |
| `CONTRIBUTING.md` | Stays at the repo root, because GitHub surfaces it. The site page includes it, for example via snippets, rather than copying it. |
| `skills/miraudit/README.md` | Stays next to its skill. The site's miraudit page includes it or links to it rather than copying it. |
| `dashboard/deploy/README.md` (operator guide for VM deploys) | Stays next to the deploy code. The "Self-hosted dashboard" page includes it rather than copying it. Its link to `docs/specs/...` (not published) becomes an absolute GitHub URL. *My call.* |

Links elsewhere in the repo that point at deleted files must be updated (for example `README.md` and `CONTRIBUTING.md`).

## Metric inventory (HEAD `1860ef0`, contract `19:19:19`)

The inventory is the starting point for content. Re-verify each item against the code while writing.

- **AQ** = `round(Σ pillar.weight/100 × pillar.score)`, computed once over the merged one-month corpus of all sources (`aq.py:693-695`, `aggregate.py`).
  - Pillar weights: Breadth 30, Craft 35, Efficiency 20, Savvy 15.
  - `sat(x, t) = min(1, x/t)`.
  - A term the source can't measure is dropped and its weight redistributed (`aq.py:262-285`, `649-691`).
  - Rate terms are scored only when `tool_calls × target > 1`.
  - Session-share terms need ≥5 eligible sessions.
- **Breadth**
  - Orchestration (33): quality = 0.40·distinct subagent types/8 + 0.40·median fan-out/5 + 0.20·harness credit; frequency is delegated ÷ orchestratable sessions with target 0.78 and weight 30%, phased in over 5 sessions. Rationale: span of control 5–7.
  - Skill fluency (22): distinct skills/40, skill uses at 0.009 per call, and a process-skill credit.
  - Tool command (28): distinct MCP servers/15 and distinct CLIs/40.
  - Discipline (17): planning habit at a 0.30 target and ordered planning at a 0.50 target.
- **Craft**
  - Verification (35): tested change sessions, plus review skills at 0.004 per call.
  - Grounding (25): explore ÷ doing at a 1.0 target. The known limitation is that it sits near the ceiling.
  - Context intelligence (20): MCP knowledge calls made before a write, provisional target 0.60.
  - Compounding (20): writes to memory and instruction files at 0.0018 per call, plus a retro/plan skill credit.
- **Efficiency**
  - Steering leverage (50): withheld.
  - Recovery (50): 0.85·error recovery + 0.15·(1 − retries per 100 tools / 2.0).
- **Savvy**
  - Model mix (50): distinct models/3, off-top-model share at 0.30, and routing to a lower tier at 0.40.
  - Token economy (50): CLI ÷ (CLI + MCP) at 0.70.
- **Outside AQ:** the GStack scorecard (`gstack.py:297-418`), archetype (`archetype.py`), signature moves and growth edges (`insights.py`), the trend (`trend.py`), model usage, and dashboard cost and team views (`dashboard/src/lib/metrics.ts`).
- **Source capabilities:** `SOURCE_CAPS` in `gnomon/config.py:40-48` and `PLANNING_SESSION_SCOPE_BY_SOURCE`. For example, Verification is full on Claude, Codex, Cursor and both Antigravity variants, and partial (tests only) on Gemini, Pi and opencode, which cannot report review skills. Coverage is derived from `SOURCE_CAPS` only. Data-dependent gates (at least 5 sessions, timestamped tool events) are not source properties, so they are explained in each axis's eligibility text instead. *Corrected 2026-10-22: an earlier draft said "not scored on Gemini and Pi", which was wrong.*

## Keeping docs honest

*My call:* add a lightweight test under `tests/` that fails when the documented weights and targets differ from the code constants. It compares the data file behind the rubric and formula tables with `gnomon/scoring/aq.py`. That makes drift a CI failure instead of a silent problem. The builder decides the exact shape.

## Delivery order

*My call.* Deliver in two pull requests so readers never hit a 404:

1. **Site + workflow.** Build the site and add the deploy workflow; pull requests run a build-only check. Nothing is deleted and the README is unchanged. The user enables Pages (Settings → Pages → Source: GitHub Actions) before this merges.
2. **Cut-over, once the site is live.** Delete the three old docs, shrink the README, and update links that point at the deleted files.

The drift test must stay stdlib-only, because `ci.yml` runs plain `unittest`.

## Follow-up issues (file, don't fix)

Filing them on the public repo is outward-facing. The builder hands the user the list and files them only with an explicit OK.

These are drift in code and the dashboard that the docs work uncovered, verified on 2026-10-21:

1. The `compute_aq` docstring says "Agentic Quotient v4"; the contract is 19.
2. `AQ_PILLAR_NOTES["Breadth"]` in `gstack.py` still mentions "structured tracking", but the task-tool term was removed in v17.
3. The Context Intelligence tooltip says "before the first Edit"; the code checks "before a later Edit".
4. The dashboard's actions-per-prompt is `tool_calls/prompts` including subagent calls. The engine uses top-level calls ÷ instructions.
5. The dashboard's planning-ratio tile renders as a percentage even though the ratio can exceed 1, so it can show values like 147%.

## Left to the builder

- MkDocs plugin choices, the folder layout for the site sources, and how internal `docs/` folders are excluded from the build.
- How docs dependencies are pinned and installed. They are used only by the docs workflow and are never package dependencies.
- How the calibrated scale and the rubric data file are implemented.
- The exact page copy. It must follow the anti-goals and match the code.
- Whether the docs workflow also builds (without deploying) on pull requests, to catch broken links.

## Risk

Two items from the high-risk list apply:

- **Item 5 (delivery):** a new GitHub Actions deploy workflow and new docs-only dependencies.
- **Item 3 (contracts):** deleted docs that other files link to.

There is no change to scoring or runtime code.
