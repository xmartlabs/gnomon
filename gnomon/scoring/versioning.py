# v13 — `o_harn` taxonomy: drop-instead-of-floor for unmeasured delegation, and
# `o_quality` uses wsum for per-term drop-and-renormalize. Until v13 a corpus that never
# observed delegation scored `o_harn = 0.6` (20% of Orchestration quality), identical to a
# corpus that measured low diversity. The five-case taxonomy discriminates: no_tool_activity
# and absent key → drop; dispatched with max >= 1 → scored as before; dispatched but roles
# unregistered → drop; genuinely measured zero → 0.0. fanout_median `None` is also
# distinguished from `0` (the `or 0` coercion is removed). HARNESS_TEAM_SESSION_TYPES (3)
# and HARNESS_BELOW_TEAM_CREDIT (0.6) are REUBICATIONS — values identical to the inline
# literals, registered under the fingerprint so a re-fit cannot hide in a refactor.
#
# v12 — `actions_per_prompt` counts TOP-LEVEL actions only; the delegated share is published
# beside the total. Until v12 the ratio divided `tool_use_total` (which counts sidechain
# tool calls) by `prompts_count` (which explicitly excludes sidechain user turns), so the two
# sides described two different populations by CONSTRUCTION, not by workload. Three changes
# ship together because they are one semantic move:
#   inputs: `behavior.actions_per_prompt` keeps its name, type and span but changes what it
#           COUNTS — the numerator loses subagent tool calls, in the corpus, per-source and
#           monthly projections alike. On the development corpus that is 22.7 -> ~7 (claude)
#           and 25.3 -> ~15 (all sources), which is not a drift a reader could attribute to
#           behaviour, so it is exactly what COMPARISON_POLICY = same_score_contract_id_only
#           has to see. One field is ADDED: `volume.sidechain_tool_calls`, a diagnostic
#           sibling of `tool_calls_total` that nothing scores and that makes the dilution
#           visible (it was 66.0% of tool_calls_total for 2026-07 on that corpus). It is
#           absent-safe by construction, so pre-v12 payloads still replay.
#           `volume.tool_calls_total` is DELIBERATELY unchanged and stays
#           sidechain-inclusive: it is the denominator all six rate targets were fitted
#           against and the cross-source aggregation weight in aggregate.py, so moving it is
#           a six-constant re-fit rather than a bug fix.
#   aq:     the formula is untouched and no calibration VALUE moves. What moves is the
#           population the Steering-leverage band judges, so the band stops being three
#           inline literals and becomes STEERING_LEVERAGE_BAND_MIN / _BAND_MAX /
#           _DECAY_SPAN, registered under the calibration fingerprint — the reason
#           12:12:12's digest differs from 11:11:11's (gnomon/scoring/calibration.py). The
#           axis was scoring the same behaviour twice in opposite directions: Orchestration
#           rewarded a delegation while Steering leverage read its 200 subagent calls as 200
#           unsteered actions and decayed toward zero. (An earlier revision of this note said
#           "measured on that corpus, the axis goes 0.868 -> 1.000". That was one corpus stated
#           as a population fact and it is false for 41 of the 48 measured users, who were
#           already inside the band; it is deleted rather than softened.) The band VALUES are
#           NOT re-fitted, and not because a re-fit was skipped: it was derived against the
#           48-user upload population and REJECTED, because the contraction is per-user
#           (projected share 0.00-0.97) while a band is two scalars, so the best available
#           re-fit still left 9 users worse (mean -0.66 AQ, worst -8.9). aq.py's PROVENANCE
#           block carries the sensitivity table and the measurement. It also deletes a
#           manufactured claim that the band had been fitted against the mixed population:
#           `git log -S` shows it entering in b65ad99 with no data at all.
#           The CONCLUSION of that rejection is the fourth registered calibration name,
#           STEERING_LEVERAGE_BAND_VALIDATED = False: a band that never fitted anything does
#           not get to grade a number, so v12 publishes `actions_per_prompt` and does not score
#           it. `lever = None`, the axis drops through build_pillar._live, and Efficiency
#           renormalizes onto Recovery -- the SAME mechanism as the unlabelling-source case
#           below, not a second one. `agentic.steering_leverage` carries the measured ratio and
#           a state saying which of the two absences applies. Cost over the same 48 users:
#           mean -0.88 AQ vs v11, uncorrelated with delegation (r = -0.16), and a mean +0.30 AQ
#           against grading the contracted ratio through the unfitted band. The flag flips only
#           when the first 12:12:12 cohort makes the per-user share measurable, as a contract
#           bump with a documented reason -- the `task_tool_calls` numerator asymmetry recorded
#           in aq.py's rate block waits on that same cohort.
#           A THIRD term ships beside the numerator, on the other side of the fraction:
#           `behavior.actions_per_prompt` now divides by `volume.total_instructions` (typed-
#           text turns PLUS bare slash commands) rather than by `volume.total_prompts`. A bare
#           `<command-name>` turn increments `command_invocations` and not `prompts_count`, so
#           its tool calls sat in the numerator with nothing in the denominator: 10 slash
#           commands driving 300 calls read `total_prompts = 0` -> app 0 -> lever 0.0, and a
#           mixed 2-typed/8-command corpus read 300/2 = 150 -> 0.0, both strictly worse than
#           the 200-subagent case above. `total_prompts` keeps its narrower meaning because
#           the prompt-length and politeness statistics are built from typed text.
#           And a trust flag: `behavior.sidechain_label_state`. claude, codex, cursor and
#           opencode stamp `isSidechain`; gemini, pi and antigravity do not. Only antigravity
#           also carries the `delegate` capability, so it can delegate and cannot label, and
#           its subagent calls stay in the top-level numerator -- the pre-v12 mixed ratio
#           wearing a v12 label. Where that is observed the Steering term is DROPPED and
#           Efficiency renormalizes (aq.py), rather than scoring 0.0 on a signal the adapter
#           cannot emit. gemini and pi need no case: without `delegate` they cannot dispatch.
#   replay: the floor NARROWS to TOP_LEVEL_ACTIONS_INPUTS_VERSION (12). `actions_per_prompt`
#           is a persisted RATIO that `stats_from_scoring_block` reads verbatim, so a v8-v11
#           payload replayed under v12 would have its frozen mixed-population ratio scored by
#           the v12 band and stamped 12:12:12 -- indistinguishable, under
#           COMPARISON_POLICY = same_score_contract_id_only, from a genuine v12 row. Not
#           repairable either: the payload carries no sidechain breakdown to subtract, that
#           being the key v12 adds. Same class of change as v10's corpus-scale gate, so it
#           follows that precedent with its own named constant and its own exception
#           (IncompatibleActionsPerPromptBasis).
#   pooling: gnomon/scoring/aggregate.py pooled this ratio with `wmean` weighted by
#           `tool_calls_total`. Value and weight were the same population before v12 and are
#           not now, so source A (10 instructions, 100 top-level, 0 sidechain) and source B
#           (10 instructions, 10 top-level, 990 sidechain) pooled to 1.8 against a true pooled
#           ratio of 5.5. The weight is now the ratio's own denominator, which makes the
#           pooled value exact rather than merely closer. Contained -- compute_aq never runs
#           on the synth block -- so the published AQ does not move; `steering_reading` and
#           the score_breakdown sub-percentages do.
#   gstack: unchanged logic; it moves with the pair for the same reason it did in v7-v11 —
#           aggregate._blend_aq raises on any mixed contract, so a partial bump would
#           publish two universes inside one PR.
# The subagent work is not lost by the numerator change: it is still measured by the
# Orchestration axis and by all six per-tool-call rate numerators (none of which is
# sidechain-gated), and its volume still travels in `tool_calls_total` and now explicitly in
# `sidechain_tool_calls`. Adding dispatches to the DENOMINATOR was rejected: a dispatch is
# one instruction, so 200 subagent calls over 1 dispatch would still read as 200 unsteered
# actions.
#
# v11 — The recency blend is gone; a published point is the month's own score, once.
# Until v11 `profile.aq` was `0.65 * recent_30d + 0.35 * full_window` (aggregate._blend_aq).
# v10 narrowed the scoring window to one calendar month and that made the pair degenerate:
# both components end at the same anchor, so they cover 93.3% (a 28-day February) to 100%
# (any 30-day month) of the same days — 96.8% for a 31-day month. The blend stopped damping
# one unusual month against a longer baseline and started averaging a month with itself.
# Three changes ship together because they are one semantic move:
#   inputs: no field is added, renamed or reshaped, and the SPAN each field covers is
#           unchanged from v10 (still one calendar month). What changes is that the payload
#           no longer carries a `bucket_scoring_inputs` block at all and
#           `payload_features.recency_blend.enabled` is a hard False — a v10 row was a
#           blended number and a v11 row is not, which is a scoring-semantics difference
#           COMPARISON_POLICY = same_score_contract_id_only has to see.
#   aq:     the formula is untouched; what moves is that its merged-corpus output is now
#           PUBLISHED verbatim instead of being overwritten by the blend. Measured on a real
#           8-source corpus over a 31-day month (the worst overlap case) the two agree:
#           aq_0_100 92 either way, largest per-axis movement 0.200, per-axis normalized
#           scores within 0.006 on all 12 axes. NO calibration TARGET moves. The blend
#           WEIGHTS do — `RECENT_WEIGHT` (0.65) ceases to exist — and they are registered
#           under the calibration fingerprint here for the first time, which is why
#           11:11:11's fingerprint differs from 10:10:10's (gnomon/scoring/calibration.py).
#   gstack: unchanged logic; it moves with the pair for the same reason it did in v7-v10 —
#           aggregate._blend_aq raises on any mixed contract, so a partial bump would
#           publish two universes inside one PR.
# This also fixed a live mixed-basis defect: `_blend_aq` copies each axis's `signals` from
# the highest-weight component (recent_30d), so anything dividing one of those counts by the
# full-window `volume.tool_calls_total` was mixing two spans. `--tools`
# (gnomon/cli/local.py::tools_diagnostic) did exactly that.
# The READING side stays: `_blend_aq`, `_blend_partial_terms`, `_blend_profiles` and
# HISTORY_WEIGHT are still exported because replay() must keep recomputing payloads
# captured before v11, and those carry blend blocks.
#
# v10 — One published point is scored on ONE calendar month. Until v10 the default window
# was a trailing SIX months (`_DEFAULT_WINDOW_MONTHS = 6`), so a month's score was mostly
# the five months before it: real behaviour change surfaced as slow drift and a step change
# read as an unexplained jump. Three changes ship together because they are one semantic
# move:
#   inputs: no field is added, renamed or reshaped. What changes is the SPAN each field
#           covers — a scored corpus is now one calendar month, so absolute counts,
#           session-count floors and rate denominators are all roughly a sixth of what the
#           same behaviour produced at v9. That makes a v9 row and a v10 row incomparable
#           even though they are byte-compatible, which is exactly what
#           COMPARISON_POLICY = same_score_contract_id_only is for.
#   aq:     the window moves into aq.py as DEFAULT_SCORING_WINDOW_MONTHS and under the
#           calibration fingerprint (it was score-affecting and unfingerprinted before), and
#           `wsum` now publishes `partial_terms` on an axis it could only score with some of
#           its terms. NO calibration target moves: the five absolute ceilings were measured
#           and left alone (.context/window-ceiling-measurement-2026-07-31.md), and
#           RATE_MIN_EXPECTED_AT_TARGET stays at 1.0 — the drops it causes at one month are
#           honest, what was missing was saying so.
#   gstack: unchanged logic; it moves with the pair for the same reason it did in v7-v9 —
#           aggregate._blend_aq raises on any mixed contract, so a partial bump would
#           publish two universes inside one PR.
# The evidence block is deliberately NOT narrowed with the score: mirdash self-heals its
# per-calendar-month series from `noticed_stats_monthly`, so gnomon keeps shaping that block
# over a trailing multi-month window from a second, corpus-only accumulator
# (gnomon/cli/local.py's MONTHLY_SELF_HEAL_MONTHS). Scoring window and evidence window are
# now two different things, and only the scoring one is published as
# `context.window_months`.
#
# v9 — The v8 dedup's calibration debt paid off. v8 made a Skill invocation count once per
# (session, skill) span, which is correct, but left SKILLS_TOTAL_PER_CALL_TARGET (0.25) and
# REVIEW_SKILLS_PER_CALL_TARGET (0.060) fitted against the PRE-dedup counter, so every
# post-v8 row scored heavy skill practice near zero. Two changes ship together because they
# are the same measurement:
#   inputs: `stack.skills_all` / `stack.skills_total` are unchanged in SHAPE, but the review
#           numerator derived from them moves: `_is_review_skill_name` now admits a
#           `verif`-LEADING tail (`verify-frontend`, `verify_changes`,
#           `verification-before-completion`) instead of only `verify` / `*-verify`. v8's
#           narrowing had dropped the prefix forms along with the false positive it targeted
#           (`email-verify-flow`), worth 2.2% of the pooled review numerator over 16 real
#           corpora and up to 59.5% for one user. The noun form was missed by v7 too, so
#           part of this is a new fix rather than a restoration.
#   aq:     SKILLS_TOTAL_PER_CALL_TARGET 0.25 -> 0.009 and REVIEW_SKILLS_PER_CALL_TARGET
#           0.060 -> 0.004, re-fitted/anchored on the post-dedup distribution (see the rate
#           rationale block at the top of aq.py for the sample, the projection model and its
#           uncertainty). The other four rate targets were re-measured and deliberately left
#           alone — the reasoning is written down there, because "the six move together" is
#           a denominator argument and the dedup only moved numerators.
#   gstack: unchanged logic; it moves with the pair for the same reason it did in v7 and v8
#           — aggregate._blend_aq raises on any mixed contract, so a partial bump would
#           publish two universes inside one PR.
# The matcher change and the re-fit MUST NOT be split: re-fitting the review target against
# a numerator that is still lossy would bake the matcher's gap into the calibration, and
# widening the matcher without the re-fit moves a published score with no contract move.
# gnomon/scoring/calibration.py registers 9:9:9's fingerprint; the 8:8:8 entry stays as the
# audit trail of what the pre-dedup calibration published.
#
# v8 — Honest AQ series: skill-counting dedup (a Skill invocation now counts once per
# invocation, not once per assistant/sidechain turn carrying attributionSkill -- a real
# corpus previously inflated e.g. judgment-day from 1 to 196) + the review-skill matcher's
# exact-tail "verify" fix + git_churn scoped to the corpus's observed span. All three
# component versions bump together and last, so no intermediate commit in the change
# publishes a payload whose score_contract_id claims v7 semantics while the counting
# logic underneath has already changed (aggregate._blend_aq raises on any mixed
# contract). Reverting the dedup fix alone (keeping the v8 stamp) is a harmless cohort
# split; reverting the version bump alone (keeping the dedup fix) is FORBIDDEN -- it
# would silently stamp new-behavior rows with the old contract. See
# tests/test_score_contract_atomicity.py, which asserts both facts in one test so a
# partial revert is caught mechanically.
#
# v7 — Per-tool-call rate denominators + one canonical combined AQ. All three bump together
# and last, so every intermediate commit in the change stays internally consistent:
# aggregate._blend_aq raises on any mixed contract, so bumping component-by-component would
# publish three different universes inside one PR.
#   inputs: `volume.tool_calls_total` becomes load-bearing for scoring — it is now the
#           denominator of every rate term, so a payload that OMITS it scores differently
#           (those terms drop to N/A and renormalize) rather than merely losing a diagnostic.
#           No field is added or renamed; what changed is which existing field is required.
#   aq:     the six rate terms score count-per-TOOL-CALL instead of count-per-SESSION, against
#           targets recalibrated into per-tool-call units. One session is not one unit of work
#           across tools: a batch of 2-minute one-shot CLI sessions acted as near-pure
#           denominator and collapsed the rate of a habit genuinely practised elsewhere.
#           Pooling numerator and denominator over the same unit is what makes this safe —
#           Sigma x / Sigma c is the tool-call-share-weighted mean of the per-source rates, so
#           the corpus rate can never land outside the range its sources span.
#   gstack: unchanged logic; it moves with the pair because the published payload now carries
#           exactly ONE combined AQ (`profile.aq`) and demotes the per-source score blend to
#           `profiles_by_source.aggregate.aq_diagnostic`.
# NOTE for whoever recalibrates next: there is NO per-source rate weighting and no
# capability-based exclusion from a rate denominator. An earlier draft of v7 weighted
# per-session rates by each source's tool volume; review rejected it because the resulting
# mean mixes units (tool_calls x things/session is not a quantity) and inverts. Do not
# reintroduce it — see the comment above `rate()` in aq.py for the measured counter-example.
SCORING_INPUTS_VERSION = 13
AQ_VERSION = 13
GSTACK_VERSION = 13
# The first SCORING_INPUTS_VERSION whose skill counters are DEDUPED: v8 (28d3bda) made a
# Skill invocation count once per (session, skill) span instead of once per assistant/
# sidechain turn carrying attributionSkill. That changed what the persisted counter MEANS,
# not just how it is scored -- measured on one full corpus, skills_total 17781 -> 4427
# (25.8x on Claude alone) and review_skills 4981 -> 597. Anything captured before it is a
# different quantity and cannot be re-scored against post-dedup targets; replay() refuses
# such a payload rather than publishing an over-saturated number (gnomon/scoring/replay.py).
SKILL_DEDUP_INPUTS_VERSION = 8
# The first SCORING_INPUTS_VERSION whose `behavior.actions_per_prompt` numerator is
# TOP-LEVEL-only: v12. Before it the numerator was `tool_use_total`, which counts sidechain
# tool calls, over a denominator that never did -- so the field is not merely scored
# differently across the boundary, it is a different QUANTITY.
#
# A second boundary constant rather than moving SKILL_DEDUP_INPUTS_VERSION: the two gate
# different things and a caller enumerating an archive needs to tell them apart. v8 is about
# persisted COUNTERS (`skills_total`, `review_skills`); this one is about a persisted RATIO,
# and unlike a counter it cannot even in principle be repaired downstream -- the payload
# carries no sidechain breakdown to subtract (`volume.sidechain_tool_calls` is the field v12
# ADDS, so no pre-v12 payload has it).
#
# Why this needs a gate at all, and why it is the same class of change v10's
# `_require_comparable_scoring_window` was written for: `profiles.py::
# stats_from_scoring_block` copies the `behavior` block verbatim and `compute_aq` stamps the
# LIVE `SCORE_CONTRACT_ID` on whatever it scored. So a v11 payload replayed under v12 has its
# frozen mixed-population ratio scored by the v12 Steering band and published as a genuine
# 12:12:12 row, which `COMPARISON_POLICY = same_score_contract_id_only` cannot distinguish
# from a real one. The gap between the two bases is systematic and large (measured on the
# development corpus, 22.7 -> ~7 on claude), so it reads as behaviour rather than as a
# definition change. See gnomon/scoring/replay.py::_require_comparable_actions_per_prompt.
TOP_LEVEL_ACTIONS_INPUTS_VERSION = 12
SCORE_CONTRACT_ID = f"{SCORING_INPUTS_VERSION}:{AQ_VERSION}:{GSTACK_VERSION}"
COMPARISON_POLICY = "same_score_contract_id_only"


class IncompatibleScoreContract(ValueError):
    pass
