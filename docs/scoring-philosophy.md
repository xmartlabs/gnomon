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
The 50% Planning readiness, 30% Planning practice and 60% Context Intelligence targets are
explicit, versioned product
hypotheses: trivial work is excluded and eligible work still has room for direct execution
when a formal plan or retrieval adds no value. The two Planning figures are different
denominators, not a contradiction — 50% of eligible *non-trivial changes* for readiness, 30%
of *all eligible top-level sessions* for practice.

## Decisions

| Area | Decision | Why |
|---|---|---|
| Planning readiness | Grade ordered planning readiness only on eligible non-trivial changes and target 50% coverage | Small tasks should stay direct; larger work benefits from an explicit plan before editing. Planning practice remains a separate educational term. |
| Planning practice | Measure planning per authoritative human-started top-level session — plan mode OR a recognized planning Skill, either one — and scale its weight by session coverage. Target 30% of sessions | Plan mode and a planning Skill express the same practice: a plan existed before code. Counting only Skills penalized planning in plan mode, which is a tool preference and not a discipline difference. The todo family is excluded because it is the agent's own execution bookkeeping and already earns ordered readiness. 30% is anchored on the share of eligible sessions that carry a substantive code change at all (374/1181 on a real corpus), so NOT planning the rest is correct rather than a gap. Child, fabricated synthetic, undated, and routing events are excluded. `__synth_ts__` is timestamp provenance only: it may credit an already-eligible root but can never create eligibility. Partial identity coverage remains numeric and auditable instead of becoming zero or erasing measured evidence. |
| One home per planning signal | Plan-mode, todo and task tools form their own tool category, counted on neither side of the explore-to-doing ratio, and planning Skill/subagent dispatches are subtracted from that ratio's denominator | Before this, entering plan mode raised the explore numerator while invoking a planning Skill raised the doing denominator — the axis rewarded one way of planning and penalized the other. Once plan mode also scored the practice term, the same action would have paid twice inside one axis. |
| Context Intelligence | Target evidence gathering before the first write in 60% of eligible changes | Grounding should inform implementation, not become after-the-fact ceremony. |
| Model routing | Reward completed, substantive work routed to a lower-tier model when linkage is observable | This teaches efficient model selection without guessing from incomplete telemetry. |
| Existing signals | Keep skills, MCPs, CLIs, ToolSearch, fanout, output, delegation, and model diversity scored | They are educational prompts for capabilities users should learn, not claims of output quality. |
| Recency | Keep the 65% recent / 35% full-window blend | Recent improvement stays visible while established habits retain influence. |

Change-session eligibility requires at least one code write, together with either two distinct
code files, code churn past a net-changed-lines floor, or ten substantive tool calls; doc,
config, lockfile, and test-only sessions are excluded (a mixed code+test session stays eligible
via its code files). Unsupported or incomplete telemetry is `N/A`, not zero. Score contracts are
versioned; changes between incompatible contracts are not labeled improvement or regression.

Eligibility conditions the ordered readiness signal, not every planning-related metric. Planning
practice remains separately scored to teach the reusable habit. A substantive
plan-file write, a planning-skill invocation paired with a plan-file, or at least three distinct
plan/task steps before the first code write prove ordered readiness (raised from two steps). A
bare Plan Mode toggle or a two-step throwaway todo, with no plan-file and no skill, does not
count: planning theater isn't planning. A plan produced in one session can also credit a later
session's eligible execution in the same working directory within a bounded time window
(consume-once — one plan credits exactly one execution), so planning in one session and
executing in another still counts. Below a minimum number of eligible sessions the signal is
dropped (and the remaining terms renormalized) rather than scored on too little data.

The two planning terms measure different things and the distinction is deliberate. Ordered
readiness asks whether a plan existed *before the first write*, with substance, on changes that
matter. Planning practice asks how *often* you plan at all, across every eligible session. So a
bare Plan Mode toggle earns planning practice but still does not earn ordered readiness: deciding
to plan is a habit worth counting, and producing a substantive plan before editing is a separate,
stricter claim.

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
