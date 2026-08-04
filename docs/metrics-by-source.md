# Metrics by source

Quick session reference. Keep only current coverage, current caveats, upload contract.

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Working as documented |
| ❌ | Not captured |
| ⚠️ | Partial |
| ⛔ | Not available by design |
| ➖ | Source-agnostic |

## Metric × source

Antigravity has two surfaces: **CLI** (`agy`, read offline from the SQLite+protobuf conversation
DBs) and **IDE** (encrypted `*.pb`, read by driving the running language server's local API
directly — no external dependency). Both decode to the same normalized events.

| Metric | Claude | Codex | Cursor | Gemini | Antigravity CLI | Antigravity IDE |
|---|---|---|---|---|---|---|
| total_sessions / total_prompts / tool_calls | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| git_churn | ➖ ✅ | ➖ ✅ | ➖ ✅ | ✅ | ✅ | ⚠️ best-effort cwd |
| tool_churn | ✅ | ✅ | ⚠️ twin-message dedup | ✅ | ✅ | ⚠️ create-file content only |
| deletions | ✅ | ✅ | ✅ | ⚠️ write-only coverage | ⚠️ write-only | ❌ |
| iteration_depth | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| error_rate / error_recovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (run-command exit codes) |
| thinking_blocks | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ (planner thinking) |
| fanout / delegate_actions | ✅ | ✅ | ✅ | ⛔ | ⚠️ invoke_subagent only | ❌ |
| planning_ratio | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| model tokens | ✅ | ✅ | ✅ | ✅ | ✅ | ⛔ masked by server |
| skills | ✅ | ✅ | ⛔ | ✅ | ⚠️ via SKILL.md read | ⚠️ via SKILL.md read |
| mcp_calls | ✅ | ✅ | ✅ | ❌ | ✅ (`server::tool`) | ✅ (`server::tool`) |
| compounding_writes | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| active_hours | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (real per-step ts) |
| actions_per_prompt | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Session caveats

- **Rate terms are scored per tool call, not per session.** Test runs, review skills,
  ToolSearch, task planning, skills and compounding writes are `count / tool_calls_total`
  over the whole corpus — a Codex one-shot (~18 calls, ~2.7 min) is not one Claude session
  (~68 calls, ~37 min), and a per-session denominator let the short ones act as pure
  denominator. There is no per-source weighting: pooling both sides over the same unit
  already makes the corpus rate the tool-call-share-weighted mean of its sources' rates.
  A payload that omits `volume.tool_calls_total` scores those terms N/A (dropped and
  renormalized) rather than zero, so a legacy block does not publish a phantom collapse.
- **Capability dilution is a known limitation, not something rates correct.** The
  denominator is every tool call in the corpus, including calls from a source that could
  never emit the signal being scored — `available_caps` is a UNION, so one capable source
  keeps a term live for the whole corpus. Adding an OpenCode corpus alongside Claude lowers
  ToolSearch-based axes with no behavior change (measured: Token economy 1.00 -> 0.63).
  This predates the per-tool-call change and is unchanged by it; excluding an incapable
  source's calls from cap-gated denominators is tracked separately.
- **Planning practice** has authoritative root/child identity for Claude, Codex,
  Cursor, and OpenCode. Other active sources contribute unmeasured sessions (`U`) to
  coverage instead of forcing the measured `P/E` share to zero or unavailable.
- **Planning practice** counts plan mode as well as planning Skills, so the signal is
  reachable per source: Claude Code emits `ExitPlanMode`, Cursor's `create_plan` and
  `switch_mode(plan)` normalize to `EnterPlanMode`, and Codex has no plan mode but does
  reach the term through shell `SKILL.md` reads. Cursor cannot emit a first-class `Skill`
  at all, so plan mode is its only path in.
- Authoritative root/child identity does **not** imply the planning signal is reachable.
  OpenCode has the identity (so its eligible denominator accrues) but emits no plan-mode
  tool and no skill signal, so its numerator can never fire. It therefore lacks the
  `planning_signal` capability and both the **Planning practice** term and AQ
  **Discipline**'s planning term are dropped and renormalized for OpenCode-only corpora,
  rather than scored 0 on telemetry the source cannot produce. A source that *can* emit the
  signal and simply never planned still scores 0 — the cap keys off capability, not off the
  share being zero.
- `git_churn` is parser-independent once source yields a real `cwd`. Antigravity CLI yields a real
  `cwd` (from `trajectory_metadata_blob`); the IDE derives it best-effort from edit/command paths.
- Codex now counts `apply_patch` churn per file, so churn, deletions, and iteration depth are meaningful there.
- Gemini captures tool activity, thinking, tokens, and errors, but deletions stay partial because `write_file` has no old-string diff.
- Gnomon does not extract delegation signals from Gemini, Pi, or OpenCode, so the
  **Orchestration** AQ axis is dropped (caps lack `delegate`), not scored 0. OpenCode itself
  supports child sessions; their parent identity is still used to scope Planning practice.
- Gemini MCP usage is not captured because tool names do not use `mcp__` naming.
- **Antigravity CLI** is fully scored offline: prompts, tool calls, tokens, and model are decoded
  from the protobuf step payloads (stdlib decoder, no deps).
- **Antigravity IDE** transcripts are encrypted; gnomon reads them by calling **every** running
  language server's local API (one per open workspace; auto-launched when the unencrypted usage
  index shows in-window history; no external dependency). It yields prompts, tool calls (with
  commands), thinking, real per-step timestamps, and run-command error codes — but the server
  **masks the model id** (`MODEL_PLACEHOLDER_*`) and does not expose token counts.
- **MCP** is detected on both surfaces: the CLI names MCP tools `server::tool` (→ `mcp__server__tool`),
  the IDE emits a dedicated `MCP_TOOL` step (`mcpTool.serverName` + `toolCall.name`). Counted as
  `mcp_calls` + distinct servers.
- **Skills** (Cursor): counted when a skill file is read via `Read`/`Bash` (`skills/<name>/SKILL.md`),
  or listed in injected `<manually_attached_skills>` on user turns (not the full `available_skills` catalog).
- **Orchestration** (Cursor): measured from `Task`/`task_v2` dispatches in the parent Composer
  session — not UI multitask tabs. `fanout_median` is the median agents-per-delegating-session;
  AQ combines coordination quality with the raw share of orchestratable sessions that delegate.
  That raw `frequency` is normalized against the provisional `0.78` target as
  `frequency_score`; its scoring weight rises progressively from 0% to 30% across the first five
  orchestratable sessions. The target remains provisional because the current three-user sample
  is insufficient for recalibration. `max_session_fanout`, `parallel_dispatch_turns`, and
  `parallel_session_share` are descriptive metrics, not AQ inputs. `parallel_session_share` means
  the share of sessions with at least two agent invocations; it does not prove temporal concurrency.
- **Git churn** requires local repo access: if `git_repos_seen == 0` but tool churn is high,
  `summary.json` includes `churn.git_coverage_warning` (common on upload/CI without `state.vscdb` + `.git`).
- **Model mix** (AQ Savvy axis) is **not scored** for Cursor — every included model costs one
  request, so routing between Composer 2.5 and cheaper models is not a cost signal. Model ids
  are still collected for descriptive stats when `state.vscdb` (or CLI `~/.cursor/chats` sidecar)
  is available; `stack.model_signal_missing` flags runs where assistant turns exist but no model
  id was recovered.

## Uploaded summary contract

Current runtime contract: **scoring inputs version 12**, **AQ version 12**, and **GStack version 12** (`score_contract_id = 12:12:12`). Previous-contract scores
must not be shown as improvement or regression against v12. v12 changes what
`behavior.actions_per_prompt` counts; v11 removes the recency blend,
so the published AQ is the scoring window's own score; v10 narrowed that window from six
calendar months to one, so a point is scored on the month it labels and the same behaviour
yields roughly a sixth of the counts a v9 point was scored against. No field was added,
renamed or reshaped in the v10 or v11 move; what changed was the span each field covers and
what is done with it — which is precisely why the contract ID has to move.

**`actions_per_prompt` counts top-level actions only, since v12.** Before v12 the numerator
was every tool call in the corpus, subagent calls included, while the denominator
(`volume.total_prompts`) has always excluded subagent dispatch instructions — a subagent
prompt is not a human prompt. The two sides of one ratio therefore described two different
populations by construction, not by workload, and the consequence was scored: the
Steering-leverage band is full between 5 and 20 actions per prompt and decays to zero at 60,
so one delegation of 200 subagent calls off a single prompt read as `app = 200` and scored
0.0 — the same behaviour the Orchestration axis rewards. v12 removes subagent calls from the
numerator (not by adding dispatches to the denominator: a dispatch is one instruction, so 200
subagent calls over 1 dispatch would still read as 200 unsteered actions). Measured on a real
corpus the ratio reads 25.3 before and 10.0 after. The delegated work is still measured — by the
Orchestration axis and by every per-tool-call rate numerator, none of which is subagent-gated.

An earlier revision of this paragraph ended "the axis moves from 0.868 to 1.000". That was a
true statement about one corpus generalised into a claim about the population, where it is false
for 41 of the 48 measured users: they were already inside the band, so shrinking their ratio
could only move them down or leave them still. The claim is deleted rather than softened. What
v12 actually does is fix the numerator and **withhold the term** — see below.

**The denominator was wrong in the mirror image, and v12 fixes that too.** A bare
`<command-name>` turn is a human instruction, but it carries no typed text, so
`Accumulator.observe` counted it in `command_invocations` and not in `prompts_count` — while
the tool calls it drove stayed in the numerator. A corpus of 10 slash commands driving 300
top-level calls read `total_prompts = 0`, so `app = 0`, and `app <= 0` scores the axis 0.0;
a mixed 2-typed/8-command corpus read 300 / 2 = 150 and also scored 0.0. Both are strictly
worse than the 200-subagent case above, on corpora with no delegation at all. The ratio now
divides by **`volume.total_instructions`** — typed-text turns plus bare slash commands.
`volume.total_prompts` deliberately keeps its narrower meaning, because that is the population
`avg_prompt_length_chars`, `median_prompt_length_chars` and `polite_prompts` are built from,
and admitting a zero-length turn there would misreport how long a human's prompts are. The
scored ratio therefore reconciles from the payload alone:
`(tool_calls_total - sidechain_tool_calls) / total_instructions`.

**`behavior.sidechain_label_state` says whether the top-level numerator can be trusted for the
source.** claude carries `isSidechain` natively and codex, cursor and opencode synthesize it;
gemini, pi and antigravity never emit it. Of those three only `antigravity` also carries the
`delegate` capability (and maps `invoke_subagent → Agent`), so it is the one source that can
genuinely delegate and genuinely cannot label — its subagent calls stay in the top-level count
and the field there is the pre-v12 mixed ratio wearing a v12 label. Where that is observed the
state reads `"unmeasured"` and `compute_aq` DROPS the Steering-leverage term, renormalizing
Efficiency's remaining axis weight, rather than scoring 0.0 on a signal the adapter cannot
emit — the same treatment `linked_model_routing_state` already gets, and the same reasoning as
`PLANNING_SESSION_SCOPE_BY_SOURCE` one level down. The verdict follows OBSERVED delegation, not
capability alone: a source that cannot label but never dispatched has an exact ratio and stays
scored, which is also why gemini and pi need no special case (without `delegate` they cannot
dispatch at all). This flag is a claim about the ADAPTER and is independent of the band verdict
below: "stays scored" here means this particular reason does not fire, not that the term is
graded — in v12 nothing is.

**The 5–20 band is unchanged, unfitted, and deliberately not re-fitted in v12.** Removing
subagent calls from the numerator is a contraction, so it helps only above 20, is neutral
inside the band, and harms anything it pushes below 5. Measured on the 48 uploaded corpora
whose latest row anchors at 2026-06 or later: median 10.8, p25 8.0, p75 13.5, max 22.9 — only
4 above 20, where the maximum gain is +0.7 AQ, and 41 inside the band where the change can
only hurt. A re-fit was derived and rejected: the per-user contraction spans 0.00–0.97, so no
pair of thresholds tracks it, and the best central-case band still left 9 users worse (mean
−0.66 AQ, worst −8.9). `gnomon/scoring/aq.py`'s PROVENANCE block carries the sensitivity table,
the measured spread of the sidechain-calls-per-dispatch constant (claude ≈38, codex ≈24), and
the correction of an earlier claim that the band had ever been fitted at all — it had not.

**So v12 does not score the term through it.** These three thresholds were **never fitted**
against any population — not "fitted and then invalidated by v12", never fitted at all — and v12
changed the population they judge on top of that. `STEERING_LEVERAGE_BAND_VALIDATED = False` in
`gnomon/scoring/aq.py` states that the band is not yet validated, and while it is False
`compute_aq` sets `lever = None`, the Steering-leverage axis drops through
`build_pillar._live`, and Efficiency renormalizes its remaining Recovery axis from weight 50 to
100. That is deliberately the *same* mechanism the unlabelling-source case uses, not a second
one. The constant is registered in `CALIBRATION_CONSTANT_NAMES`, so flipping it back on moves
the calibration digest and cannot happen without a contract bump — which is precisely the
failure it exists to prevent: re-enabling the term without a fitted band.

The reason is the same one behind `partial_terms`, the capability coverage flags, the pillar's
`not_applicable` and `_fanout_median`'s deliberate `None` — this codebase encodes "we could not
measure this" instead of publishing a number it cannot stand behind. A uniform, explained
absence beats an unexplainable −8.9 AQ for the heaviest delegators.

The **count keeps being published**: `agentic.steering_leverage.actions_per_prompt` carries the
measured ratio whether or not it is graded (the value stands, the interpretation is withheld),
and `agentic.steering_leverage.state` distinguishes the two absences a reader would otherwise
conflate — `"unmeasured_sidechain_labels"` (your source cannot label subagent calls; survives
the band being fitted) versus `"withheld_unvalidated_band"` (the band is not fitted yet;
disappears when it is), with `"scored"` when the term is live. The adapter verdict is reported
first, because it is the one that outlives the band.

**What it costs, measured rather than asserted.** Efficiency has exactly two axes, so the effect
is closed-form: `ΔAQ = 10 × (recovery − lever)`, bounded by the Recovery shortfall and zero for
anyone Recovery already scores full. Over the same 48 corpora (`.context/refit_steering_band.py`,
`withhold_report`): mean −0.88 AQ against v11 as published, median −0.66, 40 of 48 users move by
at most one published point and 19 do not move at all; Pearson *r* against delegation intensity
is −0.16, so the cost is **not** concentrated on delegators. Against v12 as it would otherwise
ship — the contracted ratio graded by the unfitted band — it is a mean **+0.30 AQ**, and the four
users that band hits hardest (−9.09, −8.70, −8.18, −7.77 AQ) come back to +0.10, −1.22, −1.10 and
−0.17. The single −8.62 outlier is the user whose Recovery is 0.138: withholding stops half a
pillar of unvalidated credit from masking a signal that *is* measured.

**What replaces it.** The first cohort uploaded under `12:12:12` carries
`volume.sidechain_tool_calls`, so the per-user delegated share stops being projected
(`k × delegate_actions / tool_calls_total`, with `k` measurably not a constant) and becomes
measured (`sidechain_tool_calls / tool_calls_total`). At that point the band is derived from that
real distribution, the projection is deleted, and the flag flips — as a contract bump with a
documented reason next to the fitted values and the population they were fitted on. Flipping it
back on without a fitted band is the failure this flag exists to prevent.

`volume.tool_calls_total` is deliberately **unchanged** and still counts subagent calls: it is
the denominator all six rate targets were fitted against and the cross-source aggregation
weight, so moving it is a six-constant re-fit rather than a bug fix. What v12 adds beside it
is `volume.sidechain_tool_calls` — a diagnostic sibling nothing scores, so the delegated share
of the tool total is visible instead of implicit (66% of `tool_calls_total` on the corpus this
was measured against). `partial_terms` cannot express this: that fires only when an axis
DROPS a term, and the dilution silently lowered a term that stayed fully scored.

**Replay is NOT unaffected, and the reason is the field that CHANGED, not the one that was
added.** An earlier revision of this section argued replay safety from the added key — "a
payload captured before v12 carries no such key and projects it as 0, so replay is
unaffected". That is true of `volume.sidechain_tool_calls` and irrelevant: nothing scores it,
so its absence cannot move a number. The field that matters is
`behavior.actions_per_prompt`, which every pre-v12 payload DOES carry, on the mixed basis.
`gnomon/scoring/profiles.py::stats_from_scoring_block` copies the `behavior` block verbatim
and `compute_aq` stamps the LIVE `score_contract_id` on the result, so replaying a v11 payload
would score a frozen mixed-population ratio through the v12 Steering band and publish it as a
genuine `12:12:12` row — indistinguishable, under
`comparison_policy = same_score_contract_id_only`, from a real one, with a systematic
one-directional gap that reads as behaviour. It is not repairable downstream either: the
payload carries no sidechain breakdown to subtract, because that is precisely the key v12
added. So `replay()` refuses a payload whose `scoring_inputs_version` predates
`TOP_LEVEL_ACTIONS_INPUTS_VERSION` (12), raising `IncompatibleActionsPerPromptBasis` — a
third named boundary alongside the pre-dedup counter gate (v8) and the corpus-scale window
gate (v10), kept separate so a caller enumerating an archive can tell which one it hit. v12
payloads onwards replay normally.

**The 65/35 recency blend is removed in v11.** Up to v10, AQ was published as 65% recent
(rolling 30-day) + 35% full-window. That was written for a six-month window, where the two
components really did describe two horizons. At the v10 one-month window both components
ended at the same anchor, `full_window` was the calendar month (28-31 days) and the recent
component the trailing 30 days, so they covered 93.3% (a 28-day February) to 100% (any
30-day month) of the same days — 96.8% for a 31-day month, and a month of 30 days or fewer
sat entirely inside the recent bucket. The blend **no longer damped** one unusual month
against a longer baseline; it read one month twice. Measured on a real eight-source corpus
over a 31-day month, removing it moves the published AQ by 0.0 points (largest per-axis
movement 0.2).

It also removed a mixed-basis defect. The blend copied each axis's `signals` from its
highest-weight component (the 30-day bucket) while every corpus-level total stayed
full-window, so any consumer dividing one of those counts by a full-window denominator was
combining two spans. gnomon's own `--tools` table did that.

**Consumer impact.** `profile.aq` and each `profiles_by_source.by_source[*].aq` no longer
carry a `blend` block, and their axes no longer carry a `components` list.
`bucket_scoring_inputs` is no longer emitted at all, and `payload_features.recency_blend`
is `{"enabled": false}` with no `history_weight`. Every one of those was already optional
(a payload could always arrive with the blend disabled), so a reader that branches on
presence needs no change; one that assumes presence does. Payloads captured under v10 and
earlier still carry all of it and remain replayable — see "recompute-grade-payload" below.

The **scoring window and the evidence window are now two different spans.**
`context.window_months` reports the scoring window (1) — it is what the evolution chart
labels a point with, and it must never report the wider one. `noticed_stats_monthly` is
shaped over a trailing six-month read of the same transcripts by a second, corpus-only
accumulator that scores nothing, so mirdash's per-calendar-month self-heal (one
`buildMetricMonthlyStats` row per entry, deduped per `monthKey` keeping the greatest
`anchorMonthKey`) keeps working: a later upload can still correct an earlier month. Six is
bounded by `cleanupPeriodDays = 180`, the retention gnomon itself offers — reading further
back would re-state months from whatever survived retention and, carrying the newest anchor,
would win the dedupe and degrade a more complete stored row.

`context.window_months` is written by `gnomon/output/summary.py::build_summary`, which
derives it from the `--since`/`--until` bounds the run actually covered — never from the
uploader's `--window=N`, which a locally invoked paxel never sees. Whole calendar months
give an integer (the shape every monthly upload requests, so the derived value always
equals the requested one); anything else — an unbounded local run, a half-bounded run, a
`--last=30d` rolling window — gives `null`, meaning "this corpus has no statable month
count". The upload path only fills the field in when a payload does not carry it at all,
so the two writers can never disagree. `gnomon/scoring/replay.py` reads this declaration
and refuses to re-score anything that is not the live one-month window, `null` and absent
included: the window is a calibration constant, so a corpus of another (or unknown) scale
cannot be pooled into the same cohort.

Axes disclose **partial scoring**. `wsum` drops a term it cannot measure and renormalizes the
survivors; at a six-month window that was rare, at one month it is common (a rate below the
evidence floor, or a session-count floor such as `eligible_change_sessions < 5`). An axis
scored on fewer than all of its terms now carries `partial_terms: {scored, total,
weight_scored}` as a sibling of `signals` — absent means fully measured, mirroring
`not_applicable` on the pillar. It is a sibling and not a signal on purpose: `signals` is
consumed as `Record<string, number>` and its lowest entry is rendered as the axis
bottleneck, so a fractional weight share in there would read as a phantom bottleneck. The
score is unchanged by the disclosure.

`build_summary()` uploads:

- `context.total_prompts`
- `context.client_version`
- `churn.active_hours`
- `churn.actions_per_prompt`
- `noticed_stats_monthly`
- `scoring_inputs_version`
- `scoring_inputs_by_source`
- `profiles_by_source`
- `source_usage`
- `source_usage_monthly`
- `bucket_scoring_inputs` — recency-blend (`recent_30d`) scoring-input metadata + corpus
  block. **No longer emitted since v11**, which removed the blend; payloads captured under
  v10 and earlier carry it and `replay()` still reads it (see "recompute-grade-payload"
  below).
- `payload_features` — always emitted; an additive marker naming which of the above block(s)
  this payload carries and why any are absent (`omitted[].reason`), so a reader can tell
  "older client, capability never existed" apart from "budget-trimmed" apart from
  "this runtime does not blend" (`bucket_scoring_inputs` absent entirely with
  `omitted[].reason == "recency_blend_removed"`, distinct from a pre-v11 payload's
  `bucket_scoring_inputs.by_source` trimmed while `bucket_scoring_inputs.corpus` still
  ships). `recency_blend` is `{"enabled": false}` since v11 — an explicit declaration, not
  an absent key, so "does not blend" stays distinguishable from "older client". Its
  pre-v11 `history_weight` sibling is gone with the blend. A `build_summary()` call that
  never went through local.py's real computation (e.g. a hand-built stats dict) omits
  `recency_blend` entirely rather than asserting a guessed state.

  No `scoring_inputs_corpus` block ships, for any source count (scope relaxation:
  approximate multi-source recompute is acceptable, so the merged-corpus block that bought
  only EXACT multi-source recompute was dropped entirely -- see "recompute-grade-payload"
  below).

Mirdash reads `actions_per_prompt` from `churn`, with legacy fallback to `context.actions_per_prompt`.

### Recompute-grade-payload: replaying `profile.aq` from the payload alone

`gnomon/scoring/replay.py::replay(payload)` reconstructs `profile.aq` (and, with limits
below, `profiles_by_source`) from an uploaded summary payload alone, with zero access to
local transcripts — this is the entry point a future recompute job (re-scoring uploaded
rows under a new metric definition) should call. It is composition-only: no scoring
formula is reimplemented, and it raises `ReplayError` rather than guessing whenever the
payload lacks data the original run genuinely depended on.

**Which payloads can be replayed: a changed FORMULA yes, a changed COUNTER no.** Re-scoring
an old payload under a new metric definition is the point, so a payload stamped with an
older `score_contract_id` / `aq_version` / `gstack_version` replays normally and
deliberately gets today's formula. `scoring_inputs_version` is the exception: it versions
what the stored counters MEAN, and nothing in the payload allows re-deriving them (there are
no transcripts in it). A payload from before the v8 skill-counting dedup carries PRE-dedup
skill counters — 4.0x larger pooled, 25.8x on Claude — which today's post-dedup targets
would saturate on arithmetic alone, so `replay()` raises `IncompatibleScoringInputs` (both a
`ReplayError` and an `IncompatibleScoreContract`) for any `scoring_inputs_version` outside
`[SKILL_DEDUP_INPUTS_VERSION, SCORING_INPUTS_VERSION]`, including a payload that declares
none. A recompute job walking stored rows should catch it and skip that row.

**Exactness is NOT uniform across payload shapes** — `replay()`'s return value carries an
`aq_exactness` field so a caller can tell which regime it got:

- **Single-source payloads are EXACT** (`aq_exactness == "exact"`): the source's own window
  block IS the corpus block (there is only one source, nothing was pooled away), so
  `replay()` reproduces `payload["profile"]["aq"]` bit-for-bit, including the 65/35 recency
  blend of a pre-v11 payload whose `bucket_scoring_inputs` carries one. `profiles_by_source` is exact too for
  single-source payloads, for the same reason: the source's own
  `bucket_scoring_inputs.corpus` window block IS that one source's per-source bucket block,
  so `replay()` synthesizes the per-source breakdown from it even though
  `bucket_scoring_inputs.by_source` was always trimmed from the shipped payload.
- **Multi-source payloads are APPROXIMATE, but blended when possible.** No
  `scoring_inputs_corpus` merged-corpus block ships for any source count — an earlier
  revision shipped one so multi-source replay could be exact too, but it cost ~487 KB on
  real 8-source data (see "Upload payload budget" below) and bought only exactness, so the
  requirement was relaxed to accept an approximate multi-source recompute. `replay()`
  instead composes the tool-volume-weighted mean of each source's own scored AQ — the same
  aggregation `gnomon.scoring.aggregate.score_by_source` already implements — and then
  blends that base value (65/35) against the merged `bucket_scoring_inputs.corpus` block,
  which pre-v11 payloads ship unconditionally. Two distinct
  exactness values distinguish whether that blend actually fired, since silently mixing an
  unblended base value with the canonical 65/35 window semantics reproduces the exact
  divergence this contract exists to prevent:
    - `aq_exactness == "approximate_weighted_mean"`: the base value WAS blended against the
      merged-corpus recency bucket. Measured on a real 8-source corpus: replayed
      `aq_0_100` 93 vs canonical `profile.aq.aq_0_100` 91 — an error of ~2 points, not the
      ~11-point gap an earlier, unblended revision of this module produced on the same
      corpus.
    - `aq_exactness == "approximate_weighted_mean_unblended"`: no bucket data was available
      to blend at all — a v11 payload (no blend was ever computed, so this is the exact
      right answer rather than an approximation of window semantics), or a pre-v11 payload
      whose shipped corpus bucket carried zero sessions that window. For a pre-v11 payload
      every source stayed 100% full-window and wider divergence from canonical should be
      expected.
  Neither approximate value is expected to equal `payload["profile"]["aq"]` (the
  merged-corpus canonical value, where distinct counts stay unions rather than per-source
  means; see `aggregate.py`'s module docstring for the aggregation-rule difference) or
  `payload["profiles_by_source"]["aggregate"]["aq_diagnostic"]` once a blend has fired for
  the corpus (that field is computed from the full, untrimmed per-source bucket breakdown,
  which a shipped payload never carries).
- **`profiles_by_source` has its own, independent coverage limit, but only for multi-source
  payloads**: `bucket_scoring_inputs.by_source` (the per-source recency-blend breakdown) is
  trimmed from every shipped payload today (see the payload-budget section below), so for a
  multi-source payload where a recency blend genuinely fired for a corpus, `replay()` cannot
  reconstruct the per-source blended profile from the payload alone. In that case it returns
  `profiles_by_source: None` and `profiles_by_source_status:
  "not_replayable_by_source_bucket_trimmed"` instead of a silently wrong (unblended) dict.
  When no blend fired, the payload is single-source (always exact, see above), or a future
  payload does carry `bucket_scoring_inputs.by_source`, `profiles_by_source_status` is
  `"exact"`.
- **Raises** for: a payload predating this capability (`payload_features` absent), an empty
  `scoring_inputs_by_source`, a scoring-input block that resolves to no known source id
  (a foreign-payload guard — see `replay.py`'s `_require_known_source_identity`), and
  (either path) a recency bucket shipped without complete metadata or a non-positive
  configured weight. Multi-source replay never raises on a model-less source — the
  weighted-mean aggregation already treats a missing per-source capability as N/A, not a
  defect, unlike the retired exact-reconstruction path.

### Upload payload budget

`gnomon/upload/mirdash.py::_INGEST_MAX_BYTES` (900 KB, mirroring mirdash's Convex
per-document ingest limit) is checked before every POST; an over-budget payload raises
`PayloadTooLarge` rather than being silently truncated or dropped. See that constant's own
docstring for the full numbers. Summary:

- Real 8-source measurement, baseline (pre-`persist-recompute-grade-inputs`, everything
  except `bucket_scoring_inputs`/`payload_features`): 824,398 bytes, ratio **0.8945** — fits.
- Real 8-source measurement, with this capability's two blocks (`scoring_inputs_corpus`
  never shipped): 839,496 bytes, ratio **0.9109** — fits. Measured before v11 removed
  `bucket_scoring_inputs`, so a current payload is that number minus the recency-bucket
  block; the budget assertions still model the heavier pre-v11 shape, since those payloads
  can still be re-sent.
- **KNOWN RISK, documented and tracked, NOT a blocker for this change**: the real baseline
  is already at ~89% of the cap for a heavy 8-source, multi-month user — a PRE-EXISTING
  condition that predates this capability and is not meaningfully worsened by it (+1.6
  percentage points on real data). A fully synthetic worst-case fixture (every documented
  per-source/per-month list cap hit simultaneously across all 8 sources — see
  `tests/test_payload_budget.py`) shows the pre-existing `scoring_inputs_by_source` +
  `profiles_by_source` fields can alone exceed the cap in an extreme, never-observed
  scenario, unrelated to this capability's own blocks. Closing that gap is the deferred
  mirdash structural split (denormalized scoring-inputs table) — a real follow-up, but not
  something this change caused or can fix alone. `tests/test_payload_budget.py` gates on
  this capability's own bounded contribution (absolute size and marginal delta), not on the
  payload's total size, for exactly this reason.

### Three time scales in the payload

- `scoring_inputs_by_source[*].window` — **window** (one calendar month by default,
  `--window=N` months) raw scoring input per source.
  These feed the per-source profiles and model-routing eligibility; the corpus AQ's rate
  terms do NOT read them, since the per-tool-call denominator is the merged
  `volume.tool_calls_total`.
- `noticed_stats_monthly` — **per calendar month** evidence, one entry per month with its own `git_churn`, tokens, errors, etc.
- `scoring_inputs_by_source[*].monthly` — **per source per calendar month** raw scoring inputs.
- `profiles_by_source` / `profile` / AQ — **window** (the requested scoring
  window, one calendar month by default), scored once and unblended since v11;
  gstack/archetype/steering are scoped to the same inputs. Up to v10 this was a
  65/35 blend against a trailing 30-day bucket — see "Uploaded summary contract"
  above for why that was removed.
- **One canonical combined AQ**: `profile.aq`, scored from the merged corpus.
  `profiles_by_source.by_source[*].aq` are per-source readings. The aggregate's
  weighted mean of per-source scores is published as
  `profiles_by_source.aggregate.aq_diagnostic` (with `canonical_aq: "profile.aq"`)
  and must not be displayed as a combined score: distinct counts are unions, so
  blending per-source scores under-counts breadth of tooling (7 MCP servers across
  three tools really is 7). Two combined numbers used to ship in the same payload.
- `source_usage` — **window** usage share by source.
- `source_usage_monthly` — **per calendar month** usage share by source.

Per-month session counts can sum above the window's unique session count when a session crosses a month boundary (accepted).

## Execution target

Current formula:

```text
execution = 10 × (0.6 × out_pct + 0.4 × deleg_pct)
out_rate  = tool_churn_edit_write / max(active_hours, 0.1)
out_pct   = clamp(out_rate / TARGET)
```

Current `TARGET = 1000` tool-authored lines/hr. Treat as provisional calibration point.
