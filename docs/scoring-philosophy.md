# Scoring that teaches healthy AI use

Gnomon's score is a learning aid, not a productivity ranking. It makes useful practices
visible so people can discover them, try them, and build better habits. A metric may remain
valuable even when it is easy to optimize deliberately: deliberate practice is the point.

## Evidence considered

The scoring review considered these external recommendations:

- Official Anthropic guidance to prefer the simplest adequate agent architecture, add
  multi-agent complexity only when task value and parallelism justify it, and retrieve
  relevant context just in time.
- Official OpenAI/Codex guidance to plan larger changes and to downroute work only after
  evaluation shows that the lower-tier model preserves the required result quality.
- DORA and SPACE research warning against treating activity, lines of code, or token volume
  as productivity, and favoring multidimensional outcomes and fast feedback loops.

Those sources support the direction—conditional planning, relevant pre-write evidence,
evaluated routing, and descriptive volume—but do not establish universal healthy thresholds.
The 50% Planning and 60% Context Intelligence targets are explicit, versioned product
hypotheses: trivial work is excluded and eligible work still has room for direct execution
when a formal plan or retrieval adds no value.

## Decisions

| Area | Decision | Why |
|---|---|---|
| Planning readiness | Grade ordered planning readiness only on eligible non-trivial changes and target 50% coverage | Small tasks should stay direct; larger work benefits from an explicit plan before editing. Planning Skill practice remains a separate educational term. |
| Planning skill practice | Measure recognized planning-skill use per authoritative human-started top-level session and scale its weight by session coverage | Child, fabricated synthetic, undated, and routing events are excluded. `__synth_ts__` is timestamp provenance only: it may credit an already-eligible root but can never create eligibility. Partial identity coverage remains numeric and auditable instead of becoming zero or erasing measured evidence. |
| Context Intelligence | Target evidence gathering before the first write in 60% of eligible changes | Grounding should inform implementation, not become after-the-fact ceremony. |
| Model routing | Reward completed, substantive work routed to a lower-tier model when linkage is observable | This teaches efficient model selection without guessing from incomplete telemetry. |
| Existing signals | Keep skills, MCPs, CLIs, ToolSearch, fanout, output, delegation, and model diversity scored | They are educational prompts for capabilities users should learn, not claims of output quality. |
| Recency | Keep the 65% recent / 35% full-window blend | Recent improvement stays visible while established habits retain influence. |

Change-session eligibility requires at least one code write, together with either two distinct
code files, code churn past a net-changed-lines floor, or ten substantive tool calls; doc,
config, lockfile, and test-only sessions are excluded (a mixed code+test session stays eligible
via its code files). Unsupported or incomplete telemetry is `N/A`, not zero. Score contracts are
versioned; changes between incompatible contracts are not labeled improvement or regression.

Eligibility conditions the ordered readiness signal, not every planning-related metric. Actual
planning Skill use remains separately scored to teach the reusable practice. A substantive
plan-file write, a planning-skill invocation paired with a plan-file, or at least three distinct
plan/task steps before the first code write prove ordered readiness (raised from two steps). A
bare Plan Mode toggle or a two-step throwaway todo, with no plan-file and no skill, does not
count: planning theater isn't planning. A plan produced in one session can also credit a later
session's eligible execution in the same working directory within a bounded time window
(consume-once — one plan credits exactly one execution), so planning in one session and
executing in another still counts. Below a minimum number of eligible sessions the signal is
dropped (and the remaining terms renormalized) rather than scored on too little data. These
readiness signals do not count as planning Skill practice.

## Volume is descriptive, not AQ

Usage volume must not increase AQ. Account tiers, provider limits, job roles, and task mix make
absolute usage unfair as a quality input. Mirdash may later use monthly human prompts to segment
adoption globally, with a per-tool breakdown:

| Usage level | Monthly prompts |
|---|---:|
| Sin actividad | 0 |
| Explorando | 1–24 |
| Ligero | 25–99 |
| Regular | 100–249 |
| Alto | 250–499 |
| Intensivo | 500+ |

These bands describe adoption only. They do not change AQ, normalize by subscription, or ship
Mirdash behavior in this change.

## Interpretation

Use AQ to ask, “Which capabilities or habits should I learn next?” Do not use it alone for
performance evaluation, compensation, or comparisons across score-contract versions. Pair it
with outcomes, code quality, delivery context, and human judgment.
