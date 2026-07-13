# Scoring changes since v0.3.0: technical validation

This document is a review aid for maintainers deciding whether the scoring changes after
`v0.3.0` are technically and product-wise defensible. It describes what the released code
counted, what `HEAD` counts, why each change was made, and which claims remain hypotheses.

## Executive verdict

**Verdict: sound direction, but approve only after two contract inconsistencies are fixed.**

The move from cumulative counts to per-session habits, conditional planning, pre-write
grounding, explicit `N/A`, and a versioned score contract is technically coherent. The
65% recent / 35% full-window blend is also internally consistent. Two current-branch details
are not ready to be treated as authoritative documentation:

1. `compute_aq()` scores v5 Context Intelligence against **60%**, but its exported
   `score_formula` says **40%**. The executable score is 60%; the signal metadata is wrong.
2. [`scoring-philosophy.md`](scoring-philosophy.md) still says ordered Planning targets 60%,
   while commit `38aad1a` changed both Planning targets to **40%**.

Model routing is conceptually sound but needs monitoring: the OpenAI tier table understands
`pro`, `mini`, and `nano`, but currently collapses names such as `gpt-5.6-sol`,
`gpt-5.6-terra`, and `gpt-5.6-luna` into the same generic `gpt-` tier. Modern Codex `exec`
compositors also contribute only their first recovered nested tool to child-routing work
counts. These limitations do not corrupt the rest of AQ, but they reduce routing coverage.

### Review outcome by area

| Area | Assessment | Reviewer decision |
|---|---|---|
| Per-session normalization | **Sound** | Removes a demonstrated window-volume artifact without changing the intended habit. |
| Planning eligibility and ordering | **Sound with monitoring** | The construct is better; the 40% target is a product hypothesis, not an externally proven healthy rate. |
| Context Intelligence | **Sound with monitoring** | Pre-write evidence on eligible work is meaningful; 60% is provisional and exported metadata currently disagrees with code. |
| Linked lower-tier routing | **Sound with monitoring** | Conservative linkage and `N/A` are correct; model-tier coverage and composed-tool counting are incomplete. |
| Capability-aware `N/A` | **Sound** | Unobservable behavior is dropped and remaining weights are renormalized instead of scoring it as failure. |
| 65/35 AQ recency blend | **Sound** | Recent improvement dominates while the full window stabilizes; the full window intentionally includes recent activity. |
| Contract versioning and privacy projection | **Sound with monitoring** | Contract IDs prevent in-process mixed blending and declare comparison policy; downstream consumers must enforce it. Session IDs are stripped, but custom skill/MCP names remain disclosed. |
| Descriptive usage levels | **Sound** | Volume does not affect AQ; proposed adoption bands remain outside this repository change. |

## Exact comparison scope

| Boundary | Ref | Commit | Meaning |
|---|---|---|---|
| Released baseline | `v0.3.0` | `179780c86e34cc6aa436311e6dfbd4443666b62f` | Latest published GitHub release, published 2026-07-07. |
| Main before this branch | `origin/main` | `bcc87456fed596d2a1e27be39852ffde98a71232` | Main changes after the release, through PR #35. |
| Scoring v5 commit | `f30b42d` | `f30b42d15316f6f790773c0d17d86e68afc96ad4` | Healthy Scoring v5 implementation. |
| Current candidate | `HEAD` | `38aad1a8310743016f5b89936a2df05bd9d8669a` | v5 plus the follow-up reduction of both Planning targets. |

The release-to-candidate diff is `v0.3.0...HEAD`. The scoring-v5-only diff is
`origin/main...HEAD`. Release workflow, version bump, and upload-release enforcement commits
(`6e08076`, `6823b4d`, and `caa50bc`) are in the first range but are not scoring behavior and
are intentionally excluded from the metric conclusions below.

## Reviewer quick path

1. Review top-level formulas in `gnomon/scoring/aq.py::compute_aq` and
   `gnomon/scoring/gstack.py::compute_scores`.
2. Review eligibility and ordering in
   `gnomon/cli/accumulator.py::derive_ordered_behavior` and
   `gnomon/taxonomy.py::is_substantive_tool`.
3. Review Claude/Codex linkage in `Accumulator._routing_snapshot` and
   `gnomon/sources/codex.py::_codex_events`.
4. Run the verification commands in [Reviewer verification](#reviewer-verification).
5. Resolve the two contract inconsistencies in the executive verdict before treating the
   document set as authoritative.

## Top-level score structure

### AQ

AQ remains a weighted sum of four 0–100 pillars:

```text
AQ = 0.30 × Breadth + 0.35 × Craft + 0.20 × Efficiency + 0.15 × Savvy
```

Those pillar weights did **not** change. Axis weights are also unchanged except for the Craft
rebalance required to add Context Intelligence:

| Pillar | v0.3.0 axes | Current axes |
|---|---|---|
| Breadth (30%) | Orchestration 33%; Skill fluency 22%; Tool command 28%; Discipline 17% | Same axis weights; internal terms changed. |
| Craft (35%) | Verification 40%; Grounding 30%; Compounding 30% | Verification 35%; Grounding 25%; **Context Intelligence 20%**; Compounding 20%. |
| Efficiency (20%) | Steering leverage 50%; Recovery 50% | Unchanged. |
| Savvy (15%) | Model mix 50%; Token economy 50% | Same axis weights; Model mix gained a conditional routing term. |

Consequently, Context Intelligence can move total AQ by at most **7 points**
(`35% × 20% × 100`). Ordered Planning can move AQ by at most **1.02 points** through
Discipline (`30% × 17% × 20% × 100`). Linked routing can move AQ by at most **2.25 points**
(`15% × 50% × 30% × 100`).

### GStack

GStack still reports three independent 0–10 axes—Execution, Planning, and Engineering. It does
not combine them into another weighted total. Execution and Engineering are unchanged from
`v0.3.0`; Planning changed internally:

| Planning term | v0.3.0 | Current |
|---|---:|---:|
| Explore-before-build, target ratio 0.65 | 45% | 30% |
| Reasoning depth, target 12 blocks/session | 30% | 30% |
| Planning ceremony/practice | 25%, any plan signal, target 50% of sessions | 25%, actual planning Skill, target 40% of sessions |
| Ordered planning readiness | — | 15%, target 40% of eligible sessions |

When a term is unobservable, `_axis_value()` removes it and renormalizes the remaining term
weights. Therefore a displayed GStack Planning axis can have different effective weights by
source; this is intentional capability normalization, not a zero score.

## Complete changed-metric register

The scoring helpers use `sat(x, target) = min(1, x / target)`. Current rate terms use
`rate(count, target) = sat((count / sessions), target)`.

| Metric or term | v0.3.0 definition | Current definition | Telemetry and `N/A` behavior | Example and reason | Assessment |
|---|---|---|---|---|---|
| AQ Orchestration: agent runs | `sat(agent_calls, 400)`, 20% of Orchestration | `rate(agent_calls, 1.0)`, same weight | Canonical `Agent`/delegate calls; whole axis is `N/A` without `delegate` capability. | Ten calls over ten sessions now score 100%; the old term scored 2.5%. This measures habit rather than corpus size. | **Sound** |
| AQ Orchestration: harness | Named `harness`/`trisel` signal gave 1.0, otherwise 0.6. | 1.0 when one session has at least three distinct subagent roles, otherwise 0.6. | Per-session subagent-role sets; requires delegation capability through the parent axis. | Three roles in separate sessions no longer impersonate coordinated fanout. | **Sound** |
| AQ Skill fluency: total use | `sat(skills_total, 1500)`, 30% of axis. | `rate(skills_total, 10)`, same weight; distinct-skill target 40 remains absolute. | Skill tool, attribution, and supported `SKILL.md` reads; axis `N/A` without `skills`. | 100 uses/10 sessions and 200/20 now both receive full rate credit; before they scored 6.7% and 13.3%. | **Sound with monitoring**—10/session is provisional. |
| AQ Tool command: ToolSearch | `sat(calls, 300)`, 20% of axis. | `rate(calls, 0.30)`, same weight. | Claude records ToolSearch; unsupported sources drop the term. MCP/CLI distinct-count terms remain 40%/40%. | Three calls in ten sessions now reach target instead of scoring 1%. | **Sound with monitoring**—provider-specific educational signal remains deliberately graded. |
| AQ Discipline | 60% task-tool absolute target 1500; 40% binary planning Skill **or any plan session**. | 40% structured task calls at 1/session; 40% binary actual planning Skill; 20% ordered Planning at 40% eligible coverage. `sdd-tasks`/`sdd-ff` count as structured task work. | Capability-gated task and Skill terms; ordered term is `N/A` when ordering is unmeasured or no session is eligible. | Four planned of ten eligible sessions saturate only the ordered term. Plan/todo tools prove readiness but no longer masquerade as Skill practice. | **Sound with monitoring**—40% is empirical/product calibration, not a universal norm. |
| AQ Verification | 50% shell tests at 150 absolute; 50% review Skills at 100 absolute. | Same weights, each at 1.5/session. Review detection adds `review-*`, `judgment-*`, and `jd-judge-*` while excluding planning reviews. | Shell tests are source-independent; Skill half drops without `skills`. | Fifteen tests and 15 reviews over ten sessions reach target; corpus length no longer controls the result. | **Sound with monitoring**—name matching can produce false positives/negatives. |
| AQ Context Intelligence | No axis in the release. A post-release experiment briefly used call/server volume, then was removed. Main before v5 used grounded/write-session coverage at a 40% target. | Evidence-before-first-write coverage over **eligible** sessions; target 60%. | Direct Read/Grep/Glob/NotebookRead or qualifying knowledge/project/data/design MCP and supported knowledge CLI evidence before the first write. `N/A` if ordered facts are unmeasured, there is no tool activity, or no session is eligible. | Three grounded of ten eligible gives 50% axis credit; six gives full credit. Small write sessions do not enter the denominator. | **Sound with monitoring**—60% is explicitly provisional; exported formula currently says 40% and must be fixed. |
| AQ Compounding | 60% `sat(writes, 30)` + 40% compounding-Skill presence. | 60% `rate(writes, 0.25)` + unchanged Skill term. | Compounding paths plus Skill recognition; Skill half drops when unsupported. | One compounding write every four sessions reaches target regardless of window size. | **Sound with monitoring**—target remains provisional. |
| AQ Token economy: ToolSearch | `sat(calls, 300)`, 50%; CLI share target 70%, 50%. | `rate(calls, 0.30)`, 50%; CLI share unchanged. | ToolSearch half drops when unsupported; CLI share remains measurable. | Same normalization rationale as Tool command. | **Sound with monitoring** |
| AQ Model mix | 50% distinct models, target 3; 50% offload from most-used model, target 30%. | If routing is measured: 35% distinct + 35% offload + 30% linked lower-tier routing. Otherwise the old 50/50 formula remains. | Model axis needs `model`; linked routing is measured only for Claude/Codex. Unsupported/ambiguous routing is `N/A`, not zero. | With diversity/offload full and routing score 0, Model mix is 70%; with routing full it is 100%; unsupported remains 100% under the old two-term formula. | **Sound with monitoring**—tier naming and Codex composed calls limit coverage. |
| GStack Planning | Explore 45%, thinking 30%, any plan-session ceremony 25% at 50% of all sessions. | Explore 30%, thinking 30%, actual planning Skill 25% at 40% of all sessions, ordered readiness 15% at 40% of eligible sessions. | Thinking and Skill terms are capability-gated; ordered readiness is `N/A` without reliable order or eligible work. | In ten sessions, three Skill sessions score 75% of the Skill term; two planned of five eligible sessions score 100% of ordered readiness. | **Sound with monitoring**—the split fixes construct mixing, but both 40% targets need production recalibration. |
| AQ recency | One full-window AQ. | Axis-by-axis blend: 65% rolling recent 30 days + 35% requested full window. | Missing recent data falls back to full-window. Per-source capabilities survive each component; unavailable axes are blended only where present. | Recent AQ 80 and full-window AQ 60 produce 73. The full window contains recent activity by design. | **Sound** |

All other AQ and GStack formulas remain scored. In particular, skills, MCPs, CLIs, fanout,
ToolSearch, tool output, delegation, task tooling, review/testing, compounding, model count,
offload share, Steering leverage, Recovery, and Engineering were not removed to make the score
harder to optimize. Their purpose is educational adoption, not strict productivity measurement.
See [`scoring-philosophy.md`](scoring-philosophy.md) for that product philosophy.

## How eligibility and ordering work now

A session is eligible only when both conditions hold:

```text
has canonical write
AND (writes at least 2 distinct normalized paths OR has at least 10 substantive calls)
```

The canonical write tools are `Edit`, `Write`, `MultiEdit`, and `NotebookEdit`. A shell command
that writes a file does not by itself satisfy this v5 eligibility write predicate. The write
itself is substantive, so the one-file threshold is exactly nine other substantive calls plus
the write.

Substantive calls are the positive produce/explore/execute/delegate taxonomy classes after
removing planning/task ceremony, scheduling, questions, ToolSearch, passive shell lifecycle,
and status/wait/poll tools. Repeated `Read`, `Grep`, `Glob`, or `NotebookRead` calls against the
same normalized target count once, even when different read tools or path aliases such as
`a.py` and `./a.py` are used. Relative paths are normalized against session `cwd`.

Events are ordered by timestamp and then by adapter ordinal. Undated tool events make ordered
facts unmeasured rather than guessing. Session keys are source-qualified so identical raw IDs
from two providers do not collide.

### Planning success

An eligible session is planned only if, before the first write, it has either:

- `EnterPlanMode` or `ExitPlanMode`; or
- at least two distinct actionable steps accumulated from `TodoWrite`/`TaskCreate` events.

Codex `update_plan.plan[*].step` is canonicalized into `TodoWrite`; repeated identical steps do
not manufacture a two-step plan. A plan created after the first write does not count.

This ordered readiness is intentionally separate from **Planning Skill practice**. Skill
practice counts actual planning-Skill use and remains an all-session educational metric. Plan
mode, todo tools, and planning agents can establish ordered readiness but do not receive Skill
credit.

### Context Intelligence success

An eligible session has evidence only when a qualifying evidence event occurs before the first
write. Current ordered evidence includes:

- `Read`, `Grep`, `Glob`, and `NotebookRead`;
- knowledge MCP calls;
- explore-class project, data, or design MCP calls; and
- recognized knowledge CLI commands carried through canonical Bash facts.

Native WebFetch/WebSearch grounding is disabled. Knowledge Skills and knowledge Agent labels
still feed the legacy pre-v5 grounding state machine, but do not by themselves set v5 ordered
evidence. This distinction should be monitored: it is conservative, but it means equivalent
research performed through those transports is not equivalent under the current v5 numerator.

## Model routing in detail

The routing numerator is the number of eligible pairs where the child model tier is lower than
the lead model tier. The denominator contains only linked pairs that are:

1. proven completed;
2. on recognized Anthropic or OpenAI tiers; and
3. substantive, meaning at least one canonical write or at least five substantive calls.

```text
routing_rate = successful_lower_tier_pairs / eligible_completed_substantive_pairs
routing_score = min(1, routing_rate / 0.40)
```

One success among three eligible pairs scores 83.3%; two among five reaches full credit. Same-
or higher-tier completed work stays in the denominator as a failure. Incomplete, cancelled,
aborted, unknown-model, and non-substantive attempts are excluded. Missing or ambiguous
linkage makes routing `unmeasured`; a provider with no linkage support is `unsupported`.

### Claude linkage

Claude joins the parent `Agent` call/result or asynchronous task notification to child sidechain
facts using tool-use and agent IDs. It takes the lead model from the parent invocation and the
child model from `resolvedModel` or a unique sidechain model. Known cancellation/kill states are
measured exclusions. Missing results, orphan children, inconsistent identity, or unknown
lifecycle make routing unmeasured rather than guessed.

### Codex linkage

Codex groups child work and lifecycle by `turn_context.turn_id`; old `task_complete` or
`turn_aborted` events in a reused child thread cannot contaminate another turn. Exact
submission/turn identity outranks stable child identity, with one-to-one event-order fallback.
Ambiguous matches, unmatched parent spawns, missing turn IDs, or completed children without a
proven lead model make routing unmeasured. The conservative JavaScript-literal parser recovers
modern `exec` compositor calls without evaluating executable code.

### Tier and parser limitations

Anthropic tiers are `opus > sonnet > haiku`. OpenAI matching is currently
`pro > generic gpt/codex > mini > nano`. This is a hand-maintained name heuristic, not provider
metadata. New aliases can silently become unknown or collapse to the same tier. In particular,
the current `sol/terra/luna` suffixes are not distinguished.

The normal Codex event stream expands every recoverable nested compositor tool, but the child
routing pre-pass calls `_codex_tool()` once and therefore counts only the first nested tool.
That can undercount read/execute-heavy children that do not write. Malformed Claude
`toolStats.editFileCount` is also converted with an unguarded `int()`, so invalid provider data
can abort accumulation rather than become unmeasured. Both are implementation follow-ups, not
reasons to abandon the routing construct.

## Source capabilities and `N/A`

| Source | Planning Skill | Ordered Planning/CI | Model mix | Linked routing |
|---|---|---|---|---|
| Claude | Native Skill/attribution telemetry | Measured when tool order is dated | Measured | Supported through Agent result/sidechain linkage |
| Codex | `SKILL.md` shell-read recognition | Measured when canonical events are dated | Measured from `turn_context` models | Supported through parent spawn and child turn lifecycle |
| Cursor | Unsupported; Skill term is removed | Canonical plan/todo/write facts may be measured; otherwise `N/A` | Model count/offload remain measurable | `unsupported`; routing term is `N/A`, not zero |
| Gemini, Pi, OpenCode | No first-class routing linkage | Canonical dated tools may contribute | Measured when source exposes model | `unsupported` |
| Antigravity CLI | Supported through Skill reads | Canonical dated tools may contribute | Measured; thinking term is `N/A` | `unsupported` |
| Antigravity IDE | Skills/thinking available where decoded | Limited by exposed IDE telemetry | Entire Model mix is `N/A` because model is masked | `unsupported` |

AQ drops an entire axis when its required capability is unavailable, then renormalizes the
other axes in that pillar. Within `wsum()` and GStack `_axis_value()`, individual unavailable
terms are dropped and remaining coefficients are renormalized. A measured zero remains zero;
only absent capability or unreliable telemetry becomes `N/A`.

## Recency, aggregation, and contract boundaries

AQ is computed per source, preserving that source's capabilities, and then aggregated by tool
activity. With the rolling blend, source weight is the sum of component configured weight times
component tool calls. GStack, archetype, Steering, and signature moves remain full-window; AQ-
derived growth edges are refreshed from blended AQ.

The current versions are:

| Contract field | v0.3.0 | Main before v5 | Current |
|---|---:|---:|---:|
| `scoring_inputs_version` | 2 | 4 | 5 |
| `aq_version` | implicit AQ v2 | implicit AQ v2 | 3 |
| `gstack_version` | implicit | implicit | 3 |
| `score_contract_id` | absent | absent | `5:3:3` |

`_blend_aq()` rejects missing or mismatched score contracts, so v4 and v5 inputs cannot be
silently blended in-process. The shareable summary declares
`comparison_policy = same_score_contract_id_only`; downstream UIs must honor this and must not
label a v4→v5 difference as improvement or regression. Gnomon emits the policy but cannot
prevent an external consumer from ignoring it.

## Privacy projection and volume

Raw parent, child, turn, and grounded-session identifiers are used locally for joins and
deduplication but are removed by `build_scoring_inputs()`. The shareable routing projection
keeps provider, lead/child model, completion/lifecycle flags, and work counters. Grounding keeps
counts, not session names.

This is selective minimization, not anonymization. The existing summary intentionally includes
model names and raw custom skill/MCP server names; those identifiers can contain customer or
environment information and are disclosed in the README.

Volume does not add AQ points. Session count is a denominator for habit rates, not a reward for
having a larger subscription or more available work. The proposed Mirdash Usage Levels remain
descriptive and outside this branch:

| Usage level | Monthly human prompts |
|---|---:|
| Sin actividad | 0 |
| Explorando | 1–24 |
| Ligero | 25–99 |
| Regular | 100–249 |
| Alto | 250–499 |
| Intensivo | 500+ |

## Release-to-current change inventory

| Commit | Scope | Important files/symbols | Verification evidence |
|---|---|---|---|
| `9c35b22` | Main: expose top Skill/MCP names and counts; no formula change. | `Accumulator`, `build_summary` | `tests/test_gnomon.py`, `tests/test_structured_profile.py` |
| `1ad92ec` | Main: absolute→per-session AQ rates, behavioral harness, initial volume-based CI experiment, knowledge taxonomy. | `compute_aq`, `classify_mcp_subcategory`, `build_scoring_inputs` | scoring vectors; `tests/test_gnomon.py` |
| `fa45055` | Main: remove gameable call-volume CI experiment while preserving rate changes. | `compute_aq` | scoring vectors; `tests/test_gnomon.py` |
| `d0cbeff` | Main: reintroduce CI as monotonic grounded-session coverage and ordered knowledge-before-write state. | `Accumulator._consume_knowledge_grounding`, `compute_aq` | `tests/test_scoring_inputs_by_source.py`, scoring vectors |
| `edb86b1` | Main: 65/35 rolling AQ, expanded review recognition, SDD task-skill credit, write-session CI denominator. | `_blend_aq`, `_review_skill_uses`, `_task_skill_uses` | `tests/test_rolling_aq.py`, `tests/test_skill_recognition.py` |
| `727a7ca` | Main: expand grounding inputs to MCP subcategories, knowledge Skills/agents, CLI, and initially web. | `KNOWLEDGE_SKILL_NEEDLES`, `bash_runs_knowledge`, `Accumulator.observe` | `tests/test_scoring_inputs_by_source.py` |
| `bcc8745` | Main: cumulative 65/35 implementation, source capability/activity weighting, disable web grounding. | `_blend_aq`, `score_by_source`, `ENABLE_WEB_CONTEXT_GROUNDING` | `tests/test_rolling_aq.py`, scoring vectors |
| `f30b42d` | Branch: v5 eligibility/order, separate planning Skill, linked routing, contract 5:3:3, privacy projection. | `derive_ordered_behavior`, `_routing_snapshot`, `_codex_events`, `score_linked_routing`, `versioning.py` | `tests/test_scoring_v5.py` |
| `38aad1a` | Branch: Planning Skill target 50→40% and ordered Planning target 60→40%. | `compute_aq`, `compute_scores`, `score_breakdown` | `tests/test_scoring_v5.py`, scoring vectors |

## Known limitations and monitoring recommendations

1. **Fix contract text before approval.** Align Context Intelligence's exported formula with
   its executable 60% target, and update the philosophy document's Planning target to 40%.
2. **Treat 40% Planning and 60% CI as hypotheses.** Recalibrate by source and task mix after a
   stable contract has enough production data. Do not optimize the threshold from a handful of
   high-volume users.
3. **Track eligibility rate itself.** If too few write sessions qualify, the ordered terms will
   be statistically unstable even though AQ remains numerically well formed.
4. **Audit evidence parity.** Measure how often Web, knowledge Skill, or knowledge Agent work is
   excluded from the v5 numerator despite providing genuine pre-write context.
5. **Version model tiers.** Add provider/model aliases from observed telemetry and regression
   tests before claiming routing coverage for `sol/terra/luna` or future names.
6. **Expand all Codex compositor tools in the routing pre-pass** and make malformed Claude
   `toolStats` become unmeasured instead of raising.
7. **Monitor capability renormalization.** Cross-source scores are fairer than forced zeros, but
   two users can receive the same axis label with different effective ingredients.
8. **Keep volume descriptive.** Segment adoption in Mirdash if useful, but do not feed account-
   constrained usage back into AQ.

## Reviewer verification

```bash
# Prove the immutable comparison boundaries
git rev-parse v0.3.0 origin/main HEAD
git log --oneline --no-merges v0.3.0..HEAD

# Inspect the scoring-only ranges
git diff v0.3.0...origin/main -- gnomon/scoring gnomon/cli/accumulator.py gnomon/taxonomy.py
git diff origin/main...HEAD -- gnomon/scoring gnomon/cli/accumulator.py gnomon/sources/codex.py gnomon/taxonomy.py

# Focused behavioral verification
python3 -m unittest tests.test_scoring_v5 tests.test_rolling_aq \
  tests.test_scoring_inputs_by_source tests.test_skill_recognition -v

# Full repository verification
python3 -m unittest discover -s tests -v
git diff --check
```

The current implementation has broad regression coverage for threshold boundaries, late
plan/evidence rejection, path normalization, read deduplication, source-qualified ordering,
Cursor `N/A`, Claude/Codex lifecycle, contract rejection, and session-ID stripping. Tests prove
the implemented contract; they do not prove that 40% or 60% is the universally healthy target.

