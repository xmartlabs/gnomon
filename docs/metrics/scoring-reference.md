<span class="gn-label">Metrics</span>

# Scoring reference

<p class="gn-thesis">The details behind the AQ for anyone who reads the uploaded payload, replays it, or changes the scoring: the contract version, the two time windows, how terms are dropped, the payload fields, replay limits, and the targets that are product hypotheses.</p>

This page assumes you have read [How scoring works](how-scoring-works.md). Formulas, weights and targets for each axis are on the axis pages.

## Contract version

Current runtime contract: **scoring inputs version 19**, **AQ version 19**, and **GStack version 19** (`score_contract_id = 19:19:19`). Compare scores only when the contract IDs match.

- The scoring inputs version changes when the meaning of a stored counter changes.
- The AQ and GStack versions change when a formula, weight or target changes.

Source: `gnomon/scoring/versioning.py`. `tests/test_documentation_contract.py` checks this paragraph against the code, so a contract bump updates it in the same change.

## Scoring window and evidence window

The payload carries two time scales, and they are different on purpose.

- **Scoring window.** The AQ is computed once over a trailing `--window=N` calendar-month window (default 1). There is no recency blend. The payload declares the span the run actually covered as `context.window_months`, derived from the run's dates rather than from the flag: a flagless local run declares 1, and an upload run with no bounds declares `null`.
- **Evidence window.** `noticed_stats_monthly` is separate six-month evidence: per-calendar-month counts that each upload re-states, so a later run corrects earlier months instead of freezing them. It is not the AQ scoring window and nothing in it is scored. Six months matches the 180-day Claude Code retention gnomon offers to set.

| Field | Scope |
|---|---|
| `scoring_inputs_by_source[*].window`, `profile`, `profiles_by_source`, `source_usage` | Requested scoring window |
| `noticed_stats_monthly`, `scoring_inputs_by_source[*].monthly`, `source_usage_monthly` | Per calendar month evidence |

`profile.aq` is the canonical combined AQ, scored once over the merged corpus of all sources. Per-source scores and their aggregate diagnostic (`profiles_by_source.aggregate.aq_diagnostic`) are not a replacement combined score.

Source: `gnomon/scoring/aq.py` (`DEFAULT_SCORING_WINDOW_MONTHS`), `gnomon/cli/local.py`, `gnomon/output/summary.py`.

## Dropped terms and evidence floors

A term the corpus cannot measure returns no value, and `wsum` drops it and renormalizes the remaining weights of the axis. A zero is kept only for a measured zero: the signal could be recorded, and it was absent. When no term of an axis is measurable, the axis itself is dropped from its pillar.

- **Rate terms** are `count / volume.tool_calls_total` over the whole corpus. A missing or insufficient denominator drops the term and renormalizes its weight rather than scoring a synthetic zero. "Insufficient" means the month's tool calls times the per-call target are not above `RATE_MIN_EXPECTED_AT_TARGET` (1.0), where a single occurrence would already max the term.
- **Session-share terms** need at least `MIN_ELIGIBLE_SESSIONS` (5) eligible sessions. Below that the term is dropped.
- **`partial_terms`** appears on an axis that scored fewer than all of its configured terms. It reports `{scored, total, weight_scored}`, where `weight_scored` is the share of the configured weight that survived. Its absence means no term was dropped.

**Known limitation.** A capability counts for the corpus when any contributing source has it, because the merged capability set is a union. One capable source therefore keeps a capability-gated rate term live for the whole corpus, and tool calls from sources that can never emit the signal still sit in its denominator.

Source: `gnomon/scoring/aq.py` (`wsum`, `rate`), `gnomon/config.py`.

## Actions per prompt and steering

`behavior.actions_per_prompt` is top-level tool calls per human instruction:

```text
(volume.tool_calls_total - volume.sidechain_tool_calls) /
volume.total_instructions
```

- `volume.total_instructions` counts typed prompts and bare slash commands.
- `volume.tool_calls_total` stays sidechain-inclusive, because rate terms and cross-source aggregation use it.
- `volume.sidechain_tool_calls` makes delegated volume observable. It is not scored.

`agentic.steering_leverage.actions_per_prompt` is published even when steering is not graded. Its `state` is one of:

| State | Meaning |
|---|---|
| `withheld_unvalidated_band` | The steering band is not validated, so the term is withheld. This is the current state. |
| `unmeasured_sidechain_labels` | Delegation was observed but sidechain calls cannot be labelled, so the term is dropped. |
| `scored` | The term is measurable and a validated band is active. |

Dropped Steering weight is renormalized within Efficiency, so Recovery carries the pillar. The unmeasured-label case is driven by observed delegation, not by capability alone. See [Steering leverage](efficiency/steering-leverage.md).

Source: `gnomon/scoring/aq.py` (`STEERING_LEVERAGE_BAND_VALIDATED`).

## Metric × source coverage

The source-level coverage contract is the matrix on [What each source measures](../sources/coverage.md), built from `SOURCE_CAPS` in `gnomon/config.py`. A capability-specific term drops and renormalizes when a source cannot emit its signal. It scores zero only when the signal is measurable and absent.

`sidechain_label_state` is corpus-wide: every contributing source must provide a trustworthy top-level numerator for a combined steering reading.

## Signal detection notes

- **Shells.** `PowerShell` is scored as a shell alongside `Bash`, so its calls count on the explore/doing ratio behind Grounding and in `cli_calls` and `clis_distinct`. CLI extraction is shell-agnostic. The test-command detection behind Verification still reads `Bash` syntax only.
- **Workflow fan-out.** `Workflow` dispatch fan-out comes from the dispatched-agent transcripts under `.../subagents/workflows/wf_*/agent-*.jsonl`, one credit per distinct dispatched agent, not from the number of `Workflow` calls. An `Agent` or `Task` call is still one dispatched agent.
- **Compounding.** Besides memory and ADR file writes, Compounding credits MCP knowledge-write calls (mem0 `add_memory`/`update_memory`, engram `mem_save`/`mem_update`), deduplicated per persisted target within a session. Reads, deletions and fetch-only knowledge servers credit nothing.
- **Model mix.** Lower-tier routing is judged with explicit provider tier tables for Anthropic and OpenAI models (`_MODEL_TIERS`). A model outside those tables, an incomplete or non-substantive subagent run, or linkage that cannot be observed is left out rather than guessed.

Source: `gnomon/taxonomy.py`, `gnomon/cli/accumulator.py`, `gnomon/scoring/aq.py`.

## Replay

`gnomon.scoring.replay.replay(payload)` recomputes the AQ from the persisted scoring inputs in a payload. It never reads local transcripts. A payload scored under an older formula version replays normally and gets the current formula. Replay refuses, rather than guesses, when:

- the payload has no `payload_features` block;
- its counter definitions (`scoring_inputs_version`) fall outside the range the live code can read;
- its `actions_per_prompt` basis predates `TOP_LEVEL_ACTIONS_INPUTS_VERSION`;
- it declares a scoring window other than the calibrated one-month window, including `null`.

Replay returns `aq_exactness`. Single-source payloads are `exact`. Multi-source payloads are approximate: `approximate_weighted_mean_unblended` for every current payload, and `approximate_weighted_mean` only for payloads from before version 11 that still carry a recency bucket. `profiles_by_source_status` independently reports whether per-source profiles are `exact` or `not_replayable_by_source_bucket_trimmed`. Consumers must branch on these fields.

Source: `gnomon/scoring/replay.py`.

## Upload payload budget

Uploads are serialized and checked before the POST against the 900 KiB ingest limit (`900 * 1024` bytes), the same limit the dashboard's ingest route enforces. An oversized payload raises `PayloadTooLarge`. It is never truncated or uploaded in part.

A heavy real payload (eight sources, several months) measured at about 89% of the limit. The biggest fields are `scoring_inputs_by_source` and `profiles_by_source`, which is why the merged-corpus block that would make multi-source replay exact is not shipped.

`payload_features` says what a payload carries: `supported`, `emitted`, `omitted` (a list of `{feature, reason}`), and `recency_blend.enabled`. Since version 11, `bucket_scoring_inputs` is listed in `omitted` with reason `recency_blend_removed`, so a reader can tell "this runtime no longer blends" from a budget trim or an older client.

Source: `gnomon/upload/mirdash.py`, `gnomon/cli/local.py`, `tests/test_payload_budget.py`.

## Targets are product hypotheses

These sources shaped the direction of the planning and context targets:

- Anthropic's guidance to prefer the simplest agent architecture that works, to add multi-agent complexity only when the task's value and parallelism justify it, and to retrieve context just in time.
- OpenAI's Codex guidance to plan larger changes, and to move work to a lower-tier model only after evaluation shows it keeps the required quality.
- DORA and SPACE research, which warns against treating activity, lines of code or token volume as productivity.

They support conditional planning, relevant evidence before writing, evaluated routing and descriptive volume, but they do not set universal healthy thresholds. The 50% Planning readiness, 30% Planning practice and 60% Context Intelligence targets are explicit, versioned product hypotheses: trivial work is excluded, and eligible work still leaves room for direct execution when a formal plan or retrieval adds nothing. The two planning figures use different denominators: 50% of eligible *non-trivial changes* for readiness, 30% of *all eligible top-level sessions* for practice.

| Area | Decision | Why |
|---|---|---|
| Planning readiness | Grade ordered planning readiness only on eligible non-trivial changes and target 50% coverage | Small tasks should stay direct. Larger work benefits from a plan before editing. |
| Planning practice | Count a top-level, human-started session as planned when it uses plan mode or a recognized planning skill, and scale the term's weight by session coverage. Target 30% of sessions | Plan mode and a planning skill are the same practice. The todo family is excluded, because it is the agent's own bookkeeping and already earns ordered readiness. 30% is close to the share of eligible sessions that carry a substantive code change at all. |
| One home per planning signal | Plan mode, todo and task tools are their own category, counted on neither side of Grounding's explore/doing ratio | Otherwise one way of planning would raise the ratio and another would lower it. |
| Context Intelligence | Target evidence gathering before the first write in 60% of eligible changes | Grounding should inform the change, not follow it. |
| Model routing | Reward completed, substantive work routed to a lower-tier model when the link is observable | It teaches model choice without guessing from incomplete telemetry. |
| Rate denominators | Score rate terms per tool call, not per session | A one-shot two-minute session is not the same unit of work as a multi-hour one. |
| One combined score | Publish one AQ, scored from the merged corpus | Distinct counts are unions: seven MCP servers across three tools really is seven. |
| Recency | Score the requested window once, with no recency blend | A point should mean the span it labels. |

**Ordered planning readiness.** A change session is eligible when it has at least one code write and also touches two distinct code files, passes 80 net changed lines, or makes ten substantive tool calls. Pure doc, config, lockfile, and test-only sessions are excluded; a mixed code and test session stays eligible through its code files. Readiness is proven, before the first code write, by a substantive plan-file write, a planning skill paired with a plan file, or at least three distinct plan/task steps. A bare plan-mode toggle or a two-step todo with no plan file and no skill does not count. A plan from one session can credit a later eligible session in the same working directory within 72 hours, consume-once: one plan credits exactly one execution. Below 5 eligible sessions the term is dropped and the rest renormalized.

The two planning terms measure different things. Readiness asks whether a substantive plan existed before the first write on changes that matter. Practice asks how often you plan at all. A bare plan-mode toggle earns practice but not readiness.

See [Discipline](breadth/discipline.md), [Context intelligence](craft/context-intelligence.md) and the [GStack scorecard](gstack.md) for where these targets are used.

Source: `gnomon/scoring/aq.py` (`PLANNING_TARGET`, `PLANNING_PRACTICE_TARGET`, `CONTEXT_INTELLIGENCE_TARGET`, `CHURN_MIN`, `WINDOW`, `PLAN_MIN_STEPS`, `MIN_ELIGIBLE_SESSIONS`), `gnomon/cli/accumulator.py`.
