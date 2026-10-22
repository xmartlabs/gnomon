# Feature: docs-site — gnomon documentation site with metrics wiki, rubric and 3D landing
Branch: `brisbane/metrics-wiki-document` · Delivery: single-pr (user choice, L6): one PR with T1–T11; the user enables Pages before merging · Test runner: `python3 -m unittest discover -s tests -v` + `uv run --no-project --with-requirements docs/requirements.txt mkdocs build --strict`
Detailed design: `docs/superpowers/specs/2026-10-21-docs-site-design.md` · Step-level plan: `docs/superpowers/plans/2026-10-22-docs-site.md` (workers read both; this document does not copy them)

## Specs

- **S1 — Metrics wiki.** "Me gustaria hacer una weeky con todas las metricas, como es que se mide y porque se mide." The site has one page per AQ axis (12), per pillar (4), plus scoring overview, GStack, and insights. Each axis page covers what it measures, how it's computed (exact formula, citing code), and why it's measured. Acceptance: `tests/test_docs_metrics_sync.py` passes and `mkdocs build --strict` exits 0.
- **S2 — Rubric.** "Generar documentacion, una rubica". Each scored axis has 6 levels using the AQ tier floors 0/25/45/60/75/88, drawn as a calibrated scale. Each level states what it looks like and the next habit. A "Rubric at a glance" page has the matrix. Acceptance: a drift test asserts the levels match `TIER_FLOORS`.
- **S3 — Audience and purpose.** "La idea es vender este proyecto a clientes, entonces paasar esto como documentacionm. Paraque mejoren en sus proyectos" — the audience is "Todos" (leads and devs). Plain-language top layer, exact detail below, no marketing fluff.
- **S4 — No duplicated docs.** "me gustaria simplificar tambien que no queden documentos repetidos, entonces borremos los que ya no tienen sentido." Delete `docs/scoring-philosophy.md`, `docs/metrics-evaluation.md`, and `docs/metrics-by-source.md`, and shrink the README. These ship in the same single PR, merged after Pages is enabled.
- **S5 — GitHub Pages.** "Pueden estar en github y que se deployen como pages? Eso puede ser?" The site is MkDocs Material, deployed by `.github/workflows/docs.yml` to `https://xmartlabs.github.io/gnomon/`. Its scope is all docs ("Todo"). The user enables Pages manually.
- **S6 — 3D landing.** "una landing como contactanos si! ALgo super tindo para la landing, quiero que sea con animaciones 3d en js". The approved mockup is `docs/superpowers/specs/2026-10-21-docs-landing-mockup-v2.html`; v1 was rejected: "Es fea, no es linda la esfera. Yo ped que lo hagas como un experto". It becomes the site home, with the 3 spec'd defects fixed.
- **S7 — Contact destination.** "El contact us puedetraernos a esto https://www.xmartlabs.com/contact … la landing de la empresa es https://www.xmartlabs.com/". UTM parameters per the design.
- **S8 — Docs stay true to code.** This is an anti-goal of the design ("Docs that disagree with the code"). Every number is rendered from `docs/data/metrics.json`, which the stdlib drift test checks against `gnomon/scoring/aq.py` and `gnomon/config.py`.

## Tasks

| ID | Task (plan task) | S# | Route | Status | Commit / evidence |
|---|---|---|---|---|---|
| T1 | MkDocs scaffold | S5 | inline | done (uncommitted) | strict build exit 0; internal folders absent from site/ |
| T2 | Theme on design system v2 | S3,S5 | inline | pending | |
| T3 | Metrics data file + drift test | S1,S2,S8 | inline | pending | |
| T4 | Macro components (formula, scale, rail, matrix) | S1,S2,S8 | inline | pending | |
| T5 | Axis and pillar pages | S1,S2,S3 | inline | pending | |
| T6 | Scoring overview, GStack, insights, rubric matrix | S1,S2 | inline | pending | |
| T7 | Get started, sources, teams, project pages | S3,S5 | inline | pending | |
| T8 | Landing as site home | S6,S7 | delegated: Writer trigger (a), an independent unit with a disjoint surface running parallel to T2–T7 | done (uncommitted) | writer: strict build 0, 60fps metal, reduced-motion/no-WebGL/CDN-blocked → SVG, no overflow 360/390; parent spot check: build exit 0 + screenshots reviewed. Safari/Firefox untested. Risk: item 6 (render covered by screenshots only) |
| T9 | Docs workflow (Risk item 5, own commit) | S5 | inline | pending | |
| T10 | Cut-over: delete legacy docs, shrink README, fix links (Risk item 3) | S4 | inline | pending (precondition: Pages enabled before merge) | |
| T11 | Follow-up issues list (file only with OK) | S8 | inline | pending | |

## Log

- **L1 (2026-10-21, user, verbatim):** "Me gustaria hacer una weeky con todas las metricas, como es que se mide y porque se mide. 

Generar documentacion, una rubica /brainstorming"
- **L2 (2026-10-21):** Brainstorming produced the approved design doc, the axis-page mockup, and landing mockup v2 (v1 rejected). The inventory was verified at HEAD `1860ef0`, contract `19:19:19`, and has 12 axes.
- **L3 (2026-10-22, user, verbatim):** "Ok, me parece bien si, y usemos ODD". The plan was approved and execution follows ODD routing: inline by default, with a writer only for T8 (parallel unit).
- **L4 (2026-10-22):** RDD is on (global). The forecast is far above 400 authored lines (content-heavy), so the ask-on-risk chain strategy question is pending before the first commit.
- **L5 (2026-10-22):** The T8 writer finished. All three defects are fixed. The grey night is replaced by a low "midnight sun" sweep behind the gnomon (9 s night, 34 s day). This is new motion not in the approved mockup, so it is flagged to the user. The writer removed its own scratch.
- **L6 (2026-10-22, user, verbatim):** "Todos en el mismo pr". The delivery strategy is single-pr, and the plan's PR 1/PR 2 split collapses into one PR. The no-404 guarantee moves to "enable Pages before merging".
