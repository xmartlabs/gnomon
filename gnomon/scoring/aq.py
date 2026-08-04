from gnomon.analysis.metrics import _review_skill_uses, _task_skill_uses
from gnomon.config import available_caps
# The planning-evidence helper lives in its own module precisely so BOTH scoring systems
# can share it: gstack imports from this module, so a gstack import here would cycle.
from gnomon.scoring.planning_evidence import _planning_skill_evidence
from gnomon.scoring.versioning import SCORE_CONTRACT_ID

# ---- The scoring window (v10) -------------------------------------------------------
# How many calendar months one published point is scored over. 1 = a month is scored on
# THAT month.
#
# Until v10 this was 6, so every published monthly point was a trailing six-month window
# and a month's score was dominated by the five months before it: a real behavioural
# change surfaced as a slow drift, and a step change read as an unexplained jump. The
# window ends at (and includes) the anchor month -- see `_anchor_window` in
# gnomon/upload/mirdash.py, which already produced exact calendar-month bounds for 1.
#
# It lives HERE, not in the upload module that reads it, because it is a calibration
# input and not a transport detail: it decides the corpus that the five absolute count
# ceilings below and the two session-count floors (MIN_ELIGIBLE_SESSIONS,
# ORCHESTRATION_FULL_CONFIDENCE_SESSIONS) are judged against. Being here puts it under
# gnomon/scoring/calibration.py's fingerprint, so it cannot move again without a contract
# bump -- which is exactly what it needs, because COMPARISON_POLICY is
# `same_score_contract_id_only` and a silent window change would pool 1-month rows with
# 6-month rows in one cohort. Before v10 it was score-affecting and unfingerprinted.
#
# Measured consequences of 6 -> 1, so a later reader does not have to rediscover them:
#   * the five absolute ceilings barely move -- a distinct-tool inventory is re-used every
#     month, not accumulated (see .context/window-ceiling-measurement-2026-07-31.md);
#   * the SESSION-COUNT floors are what actually bite. `eligible_change_sessions < 5`
#     fires for 3/17 six-month users but 31/81 month slices; `orchestratable_sessions < 5`
#     goes 0/10 users to 18/54 slices;
#   * the RATE evidence floor starts dropping terms for light users -- 0/16 six-month
#     corpora lose a rate term, against 18/75 month slices (compounding_writes 18,
#     review_skills 14, toolsearch 8, skills_total 6, task_calls 5, test_runs 2).
# None of those three is a reason to re-fit a constant: the drops are honest (see the rate
# evidence floor block below). What was NOT honest is that a term dropping left no trace
# in the payload, so an axis resting its whole weight on one surviving term looked exactly
# like a fully measured one. `wsum` now publishes `partial_terms` when that happens.
DEFAULT_SCORING_WINDOW_MONTHS = 1

PLANNING_TARGET = 0.50
# Planning-practice target: fraction of eligible top-level sessions that should carry a
# planning signal (plan mode OR a planning Skill). Read today by the GStack Planning axis;
# it lives here rather than in gstack because gstack already imports from this module, so
# this is the only side of that edge both scoring systems can share.
#
# 0.30 is anchored, not rounded: on a real corpus 374 of 1181 eligible top-level sessions
# (0.317) carried a substantive code change at all — doc/config/lockfile/test-only sessions
# are excluded from that count. So the target reads as "plan in about every session where
# you touch real code", and NOT planning the other two thirds is correct rather than a gap.
# The previous 0.40 predated any measurement. Recalibrate against a larger corpus if one
# becomes available; the guard test pins a band, not this exact value.
PLANNING_PRACTICE_TARGET = 0.30
CONTEXT_INTELLIGENCE_TARGET = 0.60

# ---- Per-tool-call rate targets ---------------------------------------------------
# Every rate term in compute_aq is `count / tool_calls_total` (see `rate`), so its target is
# a per-TOOL-CALL figure and had to be fitted on that basis — not divided out of the old
# per-session numbers by a calls-per-session constant, because that is not a constant: it
# spans 39 to 179 calls/session across the users measured below, and picking one would just
# hide the old session denominator inside a magic number.
#
# Sample: the 16 real corpora in the mirdash upload archive that still carry raw scoring
# inputs — each a full 6-month window pooled across every source that user runs, 15 of them
# anchored at 2026-07. Basis is the one the previous per-session targets documented: p40-50
# of the users who record the signal AT ALL (a source that cannot record it drops the term
# in `wsum`, so those zeros are structural, not weak practice). Each value is a round number
# inside its own [p40, p50] band; the band is quoted so a later recalibration can tell a
# population shift from a rounding choice. Six constants cover seven rate call sites —
# ToolSearch is scored on both Tool command and Token economy against the same target.
#
# ---- v9: the two SKILL numerators are re-fitted POST-dedup -------------------------
# Commit 28d3bda made a Skill invocation count once per (session, skill) span instead of
# once per attributed turn. That is correct, but it collapsed the numerator of the two
# skill rates while their targets stayed fitted against the PRE-dedup counter. Measured
# EXACTLY on one full 6-month corpus (114.6k tool calls, 1379 sessions, 8 sources), both
# sides of the dedup in a single pass:
#     skills_total   17781 -> 4427   (4.0x pooled; claude 25.8x, codex/cursor 1.00x)
#     review_skills   4981 ->  597   (8.3x pooled; claude 49.7x)
# The collapse is CLAUDE-ONLY: only Claude carries the per-turn `attributionSkill` span
# the dedup folds (13391 per-turn sites vs 4390 discrete ones). Codex/Cursor record skills
# at discrete sites, so their counts are identical on both sides.
#
# The 16 uploaded corpora are all PRE-dedup, so the post-dedup population had to be
# PROJECTED, not measured: for each slice, L = distinct skills (each ran >= 1 session) and
# U = sum_k min(n_k, sessions) bracket the truth, and theta = (P-L)/(U-L) = 0.083 is
# calibrated on the one corpus where P is known exactly. Bands below are that projection.
# Sensitivity is real and is the honest limit of this fit: theta 0.04 -> p50 .0074,
# theta 0.083 -> p50 .0098, theta 0.15 -> p50 .0133.
SKILLS_TOTAL_PER_CALL_TARGET = 0.009         # p40 .00865 / p50 .00981, n=16 — ~1 skill span per 110 calls
TOOLSEARCH_PER_CALL_TARGET = 0.0075          # p40 .00732 / p50 .00773, n=15 — ~7 per 1000 calls
TASK_CALLS_PER_CALL_TARGET = 0.011           # p40 .00817 / p50 .01475, n=13 — ~11 per 1000 calls
TEST_RUNS_PER_CALL_TARGET = 0.025            # p40 .02219 / p50 .02715, n=16 — 1 test run per 40 calls
REVIEW_SKILLS_PER_CALL_TARGET = 0.004        # p40 .00338 / p50 .00440, n=13 — ANCHORED, see below
COMPOUNDING_WRITES_PER_CALL_TARGET = 0.0018  # p40 .00170 / p50 .00207, n=16 — ~2 per 1000 calls
# REVIEW_SKILLS_PER_CALL_TARGET is ANCHORED, not fitted: the quoted band assumes review
# skills survive the dedup at the histogram-average rate, and they do not — they are the
# LONG-span ones (claude review survived at 2.01% vs 3.87% for all skills), so a
# review-specific projection puts p40/p50 at .00207/.00276 while the one exactly measured
# corpus reads .00832. 0.004 is the geometric middle of those two defensible readings and
# lands inside the proportional band. Treat .002-.008 as its uncertainty.
#
# WHY THE OTHER FOUR DID NOT MOVE (decision, not omission). The "recalibrate the six
# together" rule exists because they share the `tool_calls_total` denominator, so a shift
# in population tool-heaviness moves every band at once. The dedup moved two NUMERATORS and
# left the denominator untouched, so that coupling does not apply here. All four were
# re-measured on the same 16 corpora anyway: test_runs p40 .02479 / p50 .02726 and
# compounding p40 .00170 / p50 .00301 still contain their targets. toolsearch (p40 .00837 /
# p50 .01037) and task_calls (p40 .01352 / p50 .01519) have drifted ABOVE theirs by ~12%
# and ~23% — a genuine population shift from three extra months of uploads, unrelated to
# the dedup. Folding it in here would make the v9 delta unattributable; it needs its own
# contract bump and its own re-measurement.
#
# Still PROVISIONAL, and more so than v8's: n=16 is the entire population that has uploaded
# raw inputs, every one of them PRE-dedup and all from one company. The first upload cohort
# on contract 9:9:9 carries post-dedup counters directly — re-fit both skill targets from
# that measured distribution and delete the projection.
#
# ---- PENDING CALIBRATION DECISION (v12): task_calls is numerator-asymmetric -------
# This is a recorded decision, NOT a bug, and NOT something v12 changes. All six rates share
# the sidechain-INCLUSIVE `tool_calls_total` denominator on purpose (that is the population
# they were fitted on, and it is also the cross-source aggregation weight in
# gnomon/scoring/aggregate.py). Five of the six numerators are also recorded on sidechain
# turns, so numerator and denominator stay on the same population. `task_tool_calls` is the
# ONE that is not, and it is nearly TOTALLY asymmetric: subagent tool allowlists exclude the
# orchestrator-level task tools, so on the development corpus sidechain contributed
# `TaskCreate` 0 of 79 and `TaskUpdate` 1 of 133 — about 0.5% of the numerator — against a
# denominator that was 66.0% sidechain. The term therefore reads as roughly a third of the
# practice it measures, purely from where the tools are available.
#
# Deliberately NOT fixed here, and the options are not equivalent:
#   * re-fitting TASK_CALLS_PER_CALL_TARGET alone breaks the "the six move together" rule for
#     no measurement gain — the rule is a DENOMINATOR argument and the denominator is what is
#     wrong for this one term;
#   * giving task_calls a top-level-only denominator makes one rate incomparable with the
#     other five and with every rate row already uploaded;
#   * publishing a top-level tool total for ALL six is the defensible move, and it is a
#     six-constant re-fit against a cohort that does not exist yet.
# Decide it on the first cohort uploaded under 12:12:12, with all six re-measured at once.

# ---- Rate evidence floor (v9) ------------------------------------------------------
# `rate(x, t) = min(1, x / (tool_calls · t))` maxes out at x = tool_calls · t, so wherever
# that product falls to 1 a SINGLE occurrence saturates the term. That is the same failure
# mode `MIN_ELIGIBLE_SESSIONS` already fixes for the two session-share terms (see
# `planning_habit`: "one planning-skill invocation maxed the term forever"), and the v9
# re-fit above is what made it reachable rather than theoretical:
#     SKILLS_TOTAL_PER_CALL_TARGET  0.25  -> 0.009 : boundary tool_calls <=   4 -> <= 111
#     REVIEW_SKILLS_PER_CALL_TARGET 0.060 -> 0.004 : boundary tool_calls <=  16 -> <= 250
# 111 calls is a couple of sessions, and both terms feed a published axis (Skill fluency
# .30 of Breadth, Verification .5 of Craft).
#
# The floor is therefore expressed in the ONLY unit that cannot drift out from under a
# re-fit: the number of occurrences the target ITSELF implies at this denominator
# (tool_calls · target). A hardcoded tool-call count would reproduce the very bug under
# repair — it would silently stop covering any target later re-fitted downwards, exactly as
# the pre-dedup targets silently stopped matching the post-dedup numerator. Below the floor
# `rate` returns None, which `wsum` drops and renormalizes; the term is never scored on one
# event. Implied minimum denominators at the current six targets — tool_calls must EXCEED
# RATE_MIN_EXPECTED_AT_TARGET / target:
#     test_runs 40.0 · task_calls 90.9 · skills_total 111.1 · toolsearch 133.3 ·
#     review_skills 250.0 · compounding_writes 555.6 tool calls
# A measured ZERO below the floor is dropped for the same reason a saturated one is: at 200
# calls the review target implies 0.8 expected invocations, so observing none is consistent
# with on-target practice and scoring it 0 would be just as unfounded.
#
# 1.0 is the invariant boundary (below it one occurrence maxes the term) and is taken as the
# MINIMUM intervention rather than a round number above it. The population bounds it from
# the other side: across the 16 real 6-month corpora, the LIGHTEST user pools 2,036 tool
# calls over 17 sessions (119.8 calls/session), and its tightest product is
# 2036 · 0.0018 = 3.66 — so the data permits [1.0, 3.66) and every rate term of every real
# uploaded corpus stays scored either way. Anything at or above 3.66 would start dropping
# terms for a real user; anything above 1.0 also discards evidence from the small-but-real
# slices scored separately (per-source profiles, per-month evidence blocks), which is why the
# low end is the deliberate choice. Re-argue both bounds if the population changes.
RATE_MIN_EXPECTED_AT_TARGET = 1.0

# ---- Ordered-planning redesign (C1-C7) calibration placeholders ------------
# All five constants below are PROVISIONAL calibration placeholders (proposal C5):
# picked from qualitative guidance (Anthropic plan-mode guidance, Fowler's Design
# Stamina Hypothesis), NOT yet fit against a real corpus. Recalibrate all of them
# together once eligible/planned counts are available from production data —
# do not tune one in isolation, they interact (a lower CHURN_MIN admits more
# sessions as eligible, which shifts the denominator PLANNING_TARGET is judged
# against).
CHURN_MIN = 80              # net changed lines (C2): single-file eligibility via churn
WINDOW = 72 * 3600           # seconds (C4): cross-session plan-credit lookback window
PLAN_MIN_LINES = 8          # net lines (C6): minimum substantive plan-file size
PLAN_MIN_STEPS = 3          # distinct todo/task steps (C6): raised from 2 (anti-theater)
MIN_ELIGIBLE_SESSIONS = 5   # sessions (C7): below this, drop+renormalize (noise floor)

# ---- Orchestration v2 — frequency + quality compound -------------------------
ORCHESTRATABLE_CODE_FILES = 3    # code files written (stricter than eligible's 2)
ORCHESTRATABLE_SUBSTANTIVE = 20  # substantive tool calls (stricter than eligible's 10)
# PROVISIONAL: the current three-user sample is insufficient for recalibration.
ORCHESTRATION_FREQUENCY_TARGET = 0.78  # 78% of orchestratable sessions should delegate
ORCHESTRATION_FULL_CONFIDENCE_SESSIONS = 5

# ---- Absolute count ceilings -------------------------------------------------
# Named, not inline, because these five are the only sat() targets that read an ABSOLUTE
# cumulative count instead of a rate, so they are the ones a scoring-window change moves:
# `rate(x, t) = sat(x / tool_calls, t)` is window-invariant, a raw count is not. Naming them
# puts them under the calibration fingerprint (gnomon/scoring/calibration.py), so they cannot
# be re-fitted without a contract bump. Values are unchanged from the inline literals.
SUBAGENT_TYPES_DISTINCT_CEILING = 8
FANOUT_CEILING = 5  # span-of-control theory (Graicunas/Urwick) lands at 5-7
SKILLS_DISTINCT_CEILING = 40
MCP_SERVERS_DISTINCT_CEILING = 15
CLIS_DISTINCT_CEILING = 40

# ---- Steering leverage band (v12) --------------------------------------------
# The Efficiency/Steering-leverage curve over `behavior.actions_per_prompt`: below
# _BAND_MIN the score ramps linearly (too few actions per instruction is hand-holding, not
# leverage), inside [_BAND_MIN, _BAND_MAX] it is full, and above _BAND_MAX it decays
# linearly to zero over _DECAY_SPAN more actions (so the term reaches 0 at 60).
#
# Named here, VALUES UNCHANGED from the inline literals they replace, for the same reason
# DEFAULT_SCORING_WINDOW_MONTHS was named at v10 and the blend weights were registered at
# v11: what v12 changes is the POPULATION this band judges. Until v12
# `actions_per_prompt` divided the sidechain-INCLUSIVE tool total by the sidechain-EXCLUSIVE
# prompt count, so a band fitted as "actions you took per instruction you gave" was being
# applied to "every call anyone made, per instruction you gave" — one delegation of 200
# subagent calls scored 0.0 on this axis while the Orchestration axis rewarded it. A band
# whose meaning moves is calibration, so it belongs under the fingerprint
# (gnomon/scoring/calibration.py); leaving it as three literals would have made v12's digest
# identical to v11's, which is precisely the silent cohort merge that module exists to stop.
#
# ---- PROVENANCE: these three values were NEVER FITTED --------------------------------
# An earlier revision of this comment claimed the band "was fitted against the mixed
# population". That provenance was manufactured and is deleted rather than softened. What the
# history actually shows: `app / 5`, `app <= 20` and `/ 40` all enter in b65ad99 ("feat:
# rewrite compute_aq to 4-pillar AQ v2", 2026-06-09) with a one-line commit message and no
# data, sample or rationale of any kind; 2152713 only moves the monolith into the package.
# `git log -S` finds no fitting commit before or after either literal. docs/
# metrics-evaluation.md:41 says the same thing about the surrounding rubric in as many words
# ("rúbrica con pesos arbitrarios"). So the honest statement is: 5, 20 and 40 are judgement
# calls of unknown origin that have never been measured against a population.
#
# ---- Why v12 does NOT re-fit them, even though v12 is what makes them wrong -----------
# The v12 numerator change is a CONTRACTION, post = pre * (1 - sidechain_share). A contraction
# only helps above _BAND_MAX, is neutral inside the band, and HARMS anything it pushes below
# _BAND_MIN, where the score ramps linearly to zero. Measured on the 48 users in the mirdash
# upload archive whose latest row anchors at 2026-06 or later (pre-v12 `actions_per_prompt`
# from `churn.actions_per_prompt`): median 10.8, p25 8.0, p75 13.5, max 22.9. Only 4 sit above
# 20 where the fix helps at all, and their maximum gain is +0.07 lever (+0.7 AQ); 41 sit inside
# [5, 20] where it can only hurt. The defect being fixed needs app >= 60 to zero the term and
# nobody is within 37 of that.
#
# A re-fit was derived rather than assumed (.context/refit_steering_band.py). The per-user
# sidechain share is not in any stored payload -- `volume.sidechain_tool_calls` is the field
# v12 ADDS -- so it has to be PROJECTED as share ~= k * delegate_actions / tool_calls_total,
# with k = sidechain calls per dispatch measured on the local corpora
# (.context/measure_k.py, 116,356 tool calls / 1,608 dispatches over 2026-02..08).
# k is NOT a constant and that is the finding: claude 38.0 pooled (37.6-44.3 by month),
# codex 23.8 (21.3-27.9), cursor 18.0, pooled 32.1. Scaling the band by the population's
# median contraction factor gives:
#     k = 22 (codex end)      band [4, 15]   ->  4 better, 5 worse, 39 unchanged
#     k = 32 (pooled, CENTRAL) band [3, 13]  ->  3 better, 9 worse, 36 unchanged
#     k = 42 (claude end)     band [3, 11]   ->  3 better, 15 worse, 30 unchanged
# At the central k the best available band still leaves 9 users worse, mean -0.66 AQ, and four
# of them lose 6.5-8.9 AQ. So the re-fit reduces the damage and does not remove it, and 5/20/40
# are therefore left EXACTLY as they were: replacing unfitted values with differently unfitted
# values would move every published score for no gain in correctness.
#
# The reason no band can fix this is structural, not a matter of picking better numbers. The
# contraction is PER USER and its spread is enormous -- at central k the projected share runs
# from 0.00 to 0.97 across the population. A band is two scalars; rescaling it can re-centre
# the median user but cannot follow a per-user contraction. Worse, the projection is least
# trustworthy exactly where the harm is largest: the four worst-hit users are the ones whose
# projected share saturates, and their own counts cap k far below the corpus figure
# ((tool_calls - dispatches) / dispatches is 14 for one of them, against a claude k of 38), so
# their true loss swings from about -1 to about -9 AQ on a parameter nothing can pin down. They
# are also the heaviest delegators -- the users the fix was meant to help.
STEERING_LEVERAGE_BAND_MIN = 5
STEERING_LEVERAGE_BAND_MAX = 20
STEERING_LEVERAGE_DECAY_SPAN = 40

# ---- ...so the term is NOT SCORED until the band can be fitted -----------------------
# The three values above have never been fitted against a population (see PROVENANCE), and
# v12 changed the population they judge. Publishing a contracted number through a band that
# never fitted anything is what this codebase refuses to do everywhere else: `partial_terms`,
# the capability coverage flags, the pillar's `not_applicable` and `_fanout_median`'s
# deliberate `None` all encode "we could not measure this" instead of inventing a value. So
# does this flag. A uniform, explained absence beats an unexplainable -8.9 AQ for the heaviest
# delegators.
#
# When False, `compute_aq` sets `lever = None` and the axis drops through
# `build_pillar._live`, renormalizing Efficiency's remaining Recovery axis 50 -> 100. That is
# the SAME mechanism the non-labelling-source case uses, deliberately reused rather than
# duplicated; `agentic.steering_leverage.state` distinguishes the two reasons, and the measured
# `actions_per_prompt` keeps being published either way (the count is measured, only its
# scoring is not -- the `partial_terms` principle: the value stands, the interpretation is
# withheld).
#
# WHAT IT COSTS, measured on the same 48-user population and not estimated
# (.context/refit_steering_band.py, `withhold_report`). Efficiency has exactly two axes, so
# the effect is closed-form: d_AQ = 10 * (recovery - lever), bounded by the Recovery shortfall
# and zero for anyone Recovery already scores full.
#   * vs v11 as published: mean -0.88 AQ, median -0.66; 40 of 48 users move by <= 1 published
#     point and 19 do not move at all after rounding. Pearson r against delegation intensity
#     is -0.16, i.e. NOT concentrated on delegators -- which was the acceptance condition.
#   * vs v12 as it would otherwise ship (contracted numerator, unfitted band): mean +0.30 AQ,
#     and the four users that band hits hardest (-9.09, -8.70, -8.18, -7.77 AQ) come back to
#     +0.10, -1.22, -1.10 and -0.17. Removing that concentration is the whole point.
#   * the one -8.62 outlier is the user whose Recovery is 0.138, the lowest Efficiency in the
#     population. Withholding stops half a pillar of unvalidated credit from masking a
#     measured signal; the unfitted band cost them -4.66 anyway.
#
# WHAT REPLACES THIS, concretely. The first cohort uploaded under 12:12:12 carries
# `volume.sidechain_tool_calls`, so the per-user share stops being PROJECTED (share ~=
# k * delegate_actions / tool_calls_total, with k not a constant) and becomes MEASURED
# (sidechain_tool_calls / tool_calls_total). At that point the band is derived from that real
# distribution, the projection in `.context/refit_steering_band.py` is deleted, and this flag
# flips -- as a contract bump with a documented reason, next to the fitted values and the
# population they were fitted on.
#
# Flipping it back on WITHOUT a fitted band is the exact failure this flag exists to prevent.
# It is registered in `CALIBRATION_CONSTANT_NAMES`, so the flip cannot happen quietly: it
# moves the digest and turns `test_calibration_contract.py` red until a new contract ID and
# fingerprint entry are added.
STEERING_LEVERAGE_BAND_VALIDATED = False

_MODEL_TIERS = {
    "anthropic": (("opus", 3), ("sonnet", 2), ("haiku", 1)),
    "openai": (("pro", 4), ("mini", 2), ("nano", 1), ("gpt-", 3), ("codex", 3)),
}


def _model_tier(provider, model):
    low = str(model or "").lower()
    for needle, tier in _MODEL_TIERS.get(provider, ()):
        if needle in low:
            return tier
    return None


def score_linked_routing(pairs, state):
    if state != "measured":
        return {"state": state, "score": None,
                "successful_lower_tier_pairs": 0, "eligible_completed_substantive_pairs": 0,
                "excluded_reasons": {}}
    successful = eligible = 0
    excluded = {}
    for pair in pairs or []:
        if not pair.get("completed"):
            excluded["incomplete"] = excluded.get("incomplete", 0) + 1
            continue
        lead = _model_tier(pair.get("provider"), pair.get("lead_model"))
        child = _model_tier(pair.get("provider"), pair.get("child_model"))
        if lead is None or child is None:
            excluded["unknown_model"] = excluded.get("unknown_model", 0) + 1
            continue
        if not (pair.get("writes", 0) or pair.get("substantive_calls", 0) >= 5):
            excluded["not_substantive"] = excluded.get("not_substantive", 0) + 1
            continue
        eligible += 1
        successful += child < lead
    if excluded and not eligible:
        state = "unmeasured"
    rate = successful / eligible if eligible else 0.0
    return {"state": state, "score": min(1.0, rate / 0.40) if state == "measured" else None,
            "successful_lower_tier_pairs": successful,
            "eligible_completed_substantive_pairs": eligible, "excluded_reasons": excluded}


def _window_block(blocks):
    """A source's `window` scoring-input block, or None when the payload is unreadable.

    Foreign/legacy payloads reach scoring as plain JSON, so nothing guarantees the shape.
    Returning None (rather than trusting `.get`) keeps every caller fail-closed.
    """
    if not isinstance(blocks, dict):
        return None
    window = blocks.get("window")
    return window if isinstance(window, dict) else None


def _models_for_scoring(stats, fallback):
    """Pool model rows only from sources where model choice is scoreable."""
    by_source = stats.get("scoring_inputs_by_source")
    if not isinstance(by_source, dict) or not by_source:
        return fallback
    counts = {}
    for source, blocks in by_source.items():
        if "model" not in available_caps([source]):
            continue
        window = _window_block(blocks) or {}
        for model, turns in ((window.get("stack") or {}).get("models") or []):
            counts[model] = counts.get(model, 0) + turns
    return list(counts.items())


def compute_aq(stats):
    """Agentic Quotient v4 — 'how well you OPERATE AGENTS' (distinct from the gstack
    scorecard, which grades how you BUILD). Four pillars: Breadth (how much machinery),
    Craft (how well), Efficiency (leverage per intervention), Savvy (smart choices).
    MCP-vs-CLI and tool diversity stay descriptive (not graded).

    Capability-aware: a signal a source CANNOT record (skills/toolsearch on Cursor, etc.)
    is dropped and its weight renormalized away — not scored 0 — so non-Claude tools aren't
    penalized for what their backend never persists. With a full-capability corpus (Claude)
    every term stays and this is a no-op."""
    t, st, b = stats.get("tools", {}), stats.get("stack", {}), stats.get("behavior", {})
    caps = available_caps((stats.get("corpus", {}).get("sources") or {}).keys())
    has_skills = "skills" in caps
    has_toolsearch = "toolsearch" in caps

    def sat(x, target):
        return min(1.0, x / target) if target else 0.0

    # Rate score. An absolute cumulative count over the window penalizes low-volume users by
    # their exact volume deficit (a volume artifact — verified: identical behavior scored
    # 2.4x lower for a user with 2.4x less window), so score a RATE, not a count.
    #
    # The denominator is TOOL CALLS, not sessions. A session boundary is a UI artifact of
    # whichever tool produced it, and one session is not one unit of work across tools:
    # measured on a real three-source corpus, 397 Claude sessions carried 68.6% of the tool
    # calls and 91.1% of the active hours (~68 calls / ~37 min each) while 540 `codex exec`
    # one-shots carried 8.9% of the active hours (~18 calls / ~2.7 min each). Inside a
    # per-session rate the short ones act as near-pure denominator — Verification scored
    # 34.4/35 on the Claude slice alone, 4/35 on the codex slice alone and 22.9/35 merged,
    # for identical behavior.
    #
    # Pooling numerator and denominator over the SAME unit is what makes that safe rather
    # than merely different: Σx/Σc is exactly the tool-call-share-weighted mean of the
    # per-source rates, so the corpus rate can never land outside the range its sources
    # span, and no per-source reweighting is needed to get there. Weighting per-SESSION
    # rates by tool volume instead mixes units (tool_calls × things/session is not a
    # quantity) and inverts: 5 sessions / 2000 calls / 0 test runs beside 50 sessions / 500
    # calls / 75 test runs scored 0.10 that way against 0.45 pooled — a 78% drop for a
    # corpus where 50 of 55 sessions hit target. Targets are per tool call to match; see the
    # calibrated constants at module top.
    # `sessions` is still the right unit for the terms that count SESSIONS rather than work
    # inside them — the planning-evidence share, ordered-planning readiness and the Context
    # Intelligence coverage denominator all ask "in what fraction of your sessions did X
    # happen". The unit argument above is about RATES of activity, not about those.
    sessions = max((stats.get("volume", {}) or {}).get("total_sessions", 0), 1)
    _volume = stats.get("volume", {}) or {}
    tool_calls = _volume.get("tool_calls_total", 0)
    # Absent field vs measured zero. profiles.py setdefaults this to 0, so a legacy or
    # foreign payload that simply omits it is indistinguishable from an idle corpus unless we
    # look for the key itself. Scoring 0 there floors SIX terms across all four pillars at
    # once (measured: AQ 47 -> 33) and publishes it as if it were behaviour. Same fail-closed
    # rule Context Intelligence applies below: a missing field means backward-compat, so stay
    # N/A instead of scoring a phantom 0.
    _tool_calls_measured = "tool_calls_total" in _volume and isinstance(tool_calls, (int, float))

    def _rate_has_evidence(per_call_target):
        """Is the denominator big enough for THIS target to be evidence rather than noise?
        See RATE_MIN_EXPECTED_AT_TARGET: below the floor one occurrence maxes the term."""
        return tool_calls * per_call_target > RATE_MIN_EXPECTED_AT_TARGET

    def rate(x, per_call_target):
        # None -> wsum drops the term and renormalizes. 0.0 is reserved for a MEASURED zero:
        # real tool activity, none of this particular signal.
        if not _tool_calls_measured:
            return None
        # `> 0`, not truthiness: a corrupt negative denominator would otherwise flip the sign
        # and escape sat()'s [0,1] range (a normalized_score of -2.9 propagating into the
        # pillar and the AQ total). A measured zero denominator keeps its deliberate 0.0 —
        # the evidence floor below is about saturation, and nothing saturates a term that is
        # never divided.
        if tool_calls <= 0:
            return 0.0
        # Second reason to drop the term, alongside an absent denominator: the denominator is
        # real but too small for this target to mean anything (RATE_MIN_EXPECTED_AT_TARGET).
        if not _rate_has_evidence(per_call_target):
            return None
        return sat(x / tool_calls, per_call_target)

    def rate_facts(key, x, per_call_target):
        """The three numbers that explain a rate term, for the axis `signals`: the count, the
        per-tool-call rate it became, and the target it was scored against. The denominator
        is corpus-wide, so a term can fall while its own count rises — publishing only the
        count leaves that move unattributable. The rate is None whenever the term itself was
        NOT scored — no usable denominator, or one below this target's evidence floor — so a
        consumer can never read "300% of target" off a term the scorer refused. The count and
        the denominator stay published either way, which is what makes a dropped term
        explainable (`tool_calls` + target vs the floor)."""
        usable = _tool_calls_measured and tool_calls > 0 and _rate_has_evidence(per_call_target)
        return {key: x,
                f"{key}_per_call": round(x / tool_calls, 6) if usable else None,
                f"{key}_per_call_target": per_call_target}

    # axis name -> how much of that axis was actually scored. Populated by `wsum` and read
    # by build_pillar; see `partial_terms` there for why it is an axis sibling and not a
    # signal.
    partial_by_axis = {}

    def wsum(*terms, axis=None):
        """Weighted mean of (coef, value, required_cap) terms, dropping terms whose cap is
        unavailable and renormalizing the remaining coefficients to sum 1. Returns None when
        NO term is measurable (the whole axis is unsupported -> build_pillar drops it).

        `axis` names the axis so a PARTIAL result can be disclosed. A dropped term is
        renormalized away silently, which used to be invisible in the payload: Discipline
        scored on the task-tool rate alone at 100% weight was indistinguishable from
        Discipline scored on all three of its terms. That was tolerable while the window
        was six months and a drop was rare; under the one-month window it is the common
        case (see DEFAULT_SCORING_WINDOW_MONTHS for the measured rates). Recording WHICH
        FRACTION of the configured weight survived is the honest disclosure -- it does not
        change the number, it explains it."""
        live = [(c, v) for c, v, cap in terms
                if v is not None and (cap is None or cap in caps)]
        tot = sum(c for c, _ in live)
        if axis is not None and len(live) < len(terms):
            configured = sum(c for c, _, _ in terms)
            partial_by_axis[axis] = {
                "scored": len(live),
                "total": len(terms),
                "weight_scored": round(tot / configured, 4) if configured else 0.0,
            }
        return sum(c * v for c, v in live) / tot if tot else None

    skills = st.get("skills_all") or st.get("top_skills", [])

    def skill_uses(needles):
        return sum(n for k, n in skills if any(nd in str(k).lower() for nd in needles))

    def has_skill(needles):
        return any(any(nd in str(k).lower() for nd in needles) for k, _ in skills)

    # ---- Pillar 1: Breadth (unchanged axes) ----
    fanout = b.get("fanout_median") or 0  # None (unmeasured) treated as 0 for AQ
    # Harness use = a SINGLE session coordinating a team of >=3 distinct subagent roles
    # (behavioral), not a subagent/skill NAMED "harness"/"trisel" (opaque), and not window-wide
    # role variety (subagent_types_distinct would credit 3 roles fired one-per-session, which
    # never coordinated a team). max_session_subagent_types is the per-session distinct-role
    # peak — name-/content-agnostic, so it works in the cross-source aggregate.
    o_harn = 1.0 if st.get("max_session_subagent_types", 0) >= 3 else 0.6
    # Orchestration v2: observed frequency (share of orchestratable sessions that
    # delegated), normalized target score, and coordination quality (subagent
    # diversity, fan-out, harness use). Frequency earns its full 30% weight
    # progressively over the first five eligible sessions.
    o_quality = (0.40 * sat(st.get("subagent_types_distinct", 0),
                            SUBAGENT_TYPES_DISTINCT_CEILING)
               + 0.40 * sat(fanout, FANOUT_CEILING)
               + 0.20 * o_harn)
    _o_orchestratable = b.get("orchestratable_sessions") or 0
    _o_delegated = b.get("delegated_orchestratable_sessions") or 0
    o_frequency = (_o_delegated / _o_orchestratable) if _o_orchestratable else None
    o_frequency_score = (sat(o_frequency, ORCHESTRATION_FREQUENCY_TARGET)
                         if o_frequency is not None else None)
    o_frequency_confidence = min(
        _o_orchestratable / ORCHESTRATION_FULL_CONFIDENCE_SESSIONS, 1.0)
    o_frequency_weight = 0.30 * o_frequency_confidence
    orchestration = ((1.0 - o_frequency_weight) * o_quality
                     + o_frequency_weight * o_frequency_score
                     if o_frequency_score is not None else o_quality)
    # skills_total -> per-tool-call rate; skills_distinct stays (diversity, correctly absolute).
    # Via wsum, not raw arithmetic: `rate` returns None when there is no usable tool-call
    # denominator, and wsum is what drops such a term and renormalizes the rest. Multiplying
    # by a coefficient directly would raise a TypeError instead.
    skill_fluency = wsum(
        (.40, sat(st.get("skills_distinct", 0), SKILLS_DISTINCT_CEILING), None),
        (.30, rate(st.get("skills_total", 0), SKILLS_TOTAL_PER_CALL_TARGET), None),
        (.30, 1.0 if has_skill(["subagent-driven", "brainstorm", "writing-plans",
                                "cerberus", "systematic-debugging"]) else 0.6, None),
        axis="Skill fluency")
    # mcp_servers/clis are distinct-counts (kept absolute); toolsearch -> per-tool-call rate.
    # toolsearch term drops out (renormalized) when no present source can record it
    tool_command = wsum((.40, sat(t.get("mcp_servers_distinct", 0),
                                  MCP_SERVERS_DISTINCT_CEILING), None),
                        (.40, sat(t.get("clis_distinct", 0), CLIS_DISTINCT_CEILING), None),
                        (.20, rate(t.get("toolsearch_calls", 0), TOOLSEARCH_PER_CALL_TARGET),
                         "toolsearch"),
                        axis="Tool command (MCP + CLI)")
    # task-tool -> per-tool-call rate; TaskCreate/Update + SDD sdd-tasks skill invocations
    # both count as structured task planning. plan-skill term needs the Skill capability.
    task_calls = t.get("task_tool_calls", 0) + _task_skill_uses(skills)
    ordered_state = b.get("ordered_facts_state")
    eligible = b.get("eligible_change_sessions", 0) or 0
    # C7 — significance floor: below MIN_ELIGIBLE_SESSIONS the ratio is noise
    # (e.g. 40% over 2 sessions), so drop the term (None -> renormalized)
    # rather than score it. Placeholder constant, see aq.py's MIN_ELIGIBLE_SESSIONS.
    ordered_planning = (None if ordered_state != "measured"
                        or eligible < MIN_ELIGIBLE_SESSIONS
                        else sat(b.get("planned_eligible_sessions", 0) / eligible,
                                 PLANNING_TARGET))
    # Planning HABIT, not planning-tool awareness. This was a binary has_skill() check, so
    # one planning-skill invocation in a thousand sessions maxed the term forever and AQ
    # could not tell that apart from planning in a third of your sessions. It now reads the
    # same qualified share the GStack Planning practice term reads — routed through the
    # shared evidence helper rather than the raw field so both systems inherit the identical
    # fail-closed validation and legacy fallback, and produce bit-identical numbers.
    _plan_practice = _planning_skill_evidence(b, max(sessions, 1))
    _plan_eligible = _plan_practice["eligible_sessions"] or 0
    # Same significance floor as ordered_planning above: 1-of-2 sessions is a 0.5 share and
    # would max the term on noise, so drop it (None -> renormalized) instead of scoring it.
    planning_habit = (
        None if _plan_practice["share"] is None or _plan_eligible < MIN_ELIGIBLE_SESSIONS
        else sat(_plan_practice["share"], PLANNING_PRACTICE_TARGET))
    discipline = wsum((.40, rate(task_calls, TASK_CALLS_PER_CALL_TARGET), "tasktool"),
                      # The legacy path derives the share from plan_sessions over ALL
                      # sessions, which only a Skill-capable source populates. The qualified
                      # path is earnable by plan mode OR a skill signal, hence the broader
                      # planning_signal cap — which a measured planning scope does NOT imply
                      # (opencode has authoritative identity but emits neither signal).
                      (.40, planning_habit,
                       "skills" if _plan_practice["legacy"] else "planning_signal"),
                      (.20, ordered_planning, None),
                      axis="Discipline")
    breadth_axes = [
        # Orchestration needs subagent delegation; a source that can't fan out by design
        # (Gemini/Pi/opencode) drops this axis (renormalized) instead of scoring ~0.
        ("Orchestration", 33, orchestration, {"subagent_types": st.get("subagent_types_distinct", 0),
         "fanout_median": fanout, "o_harn": o_harn,
         "frequency": round(o_frequency, 3) if o_frequency is not None else None,
         "frequency_score": (round(o_frequency_score, 3)
                             if o_frequency_score is not None else None),
         "frequency_confidence": round(o_frequency_confidence, 3),
         "frequency_weight": round(o_frequency_weight, 3),
         "coordination_quality": round(o_quality, 3),
         "orchestratable_sessions": _o_orchestratable,
         "delegated_orchestratable_sessions": _o_delegated},
         "delegate"),
        ("Skill fluency", 22, skill_fluency, {
            "skills_distinct": st.get("skills_distinct", 0), "tool_calls": tool_calls,
            **rate_facts("skills_total", st.get("skills_total", 0),
                         SKILLS_TOTAL_PER_CALL_TARGET)}, "skills"),
        ("Tool command (MCP + CLI)", 28, tool_command, {
            "mcp_servers": t.get("mcp_servers_distinct", 0),
            "clis": t.get("clis_distinct", 0), "tool_calls": tool_calls,
            **rate_facts("toolsearch", t.get("toolsearch_calls", 0),
                         TOOLSEARCH_PER_CALL_TARGET)}),
        # Surface the planning inputs, not just the task-tool count: the axis now moves with
        # planning FREQUENCY, and a score with no visible driver is not actionable.
        ("Discipline", 17, discipline, {
            "tool_calls": tool_calls,
            **rate_facts("task_tool_calls", task_calls, TASK_CALLS_PER_CALL_TARGET),
            "planning_practice_share": (
                round(_plan_practice["share"], 4)
                if _plan_practice["share"] is not None else None),
            "planning_practice_target": PLANNING_PRACTICE_TARGET,
            "planning_practice_eligible_sessions": _plan_practice["eligible_sessions"],
        }),
    ]

    # ---- Pillar 2: Craft ----
    review_n = _review_skill_uses(skills)
    # review-skill term needs observable skill data (first-class Skill tool OR SKILL.md reads /
    # injected skills on Cursor). Skill fluency / Discipline still require `skills` only.
    # test runs + review skills -> per-tool-call rates
    verification = wsum((.5, rate(b.get("shell_test_runs", 0), TEST_RUNS_PER_CALL_TARGET), None),
                        (.5, rate(review_n, REVIEW_SKILLS_PER_CALL_TARGET), "skill_reads"),
                        axis="Verification")
    grounding = sat(b.get("planning_ratio_explore_to_doing", 0), 1.0)
    # Context Intelligence: PURE per-session grounding COVERAGE, not knowledge-MCP call/
    # server volume (the old `<50 calls` gate was gameable by auto-fired knowledge-MCP
    # calls with zero relationship to authored output). A session is "grounded" when a
    # knowledge-MCP call (accumulator.py's per-session state machine) precedes a later
    # Edit/Write/MultiEdit/NotebookEdit in that SAME session. coverage = grounded/total.
    # MONOTONIC per-session coverage score — NO floor. More grounding never lowers the
    # axis, and a real measured zero (has tool activity, 0 grounded sessions) is scored 0,
    # NOT dropped. TARGET is PROVISIONAL (recalibrate from prod p40-50). The axis is N/A
    # ONLY when the source genuinely can't measure grounding: no_tool_activity (can't
    # reconstruct ordered per-session tool sequences) OR the grounding field is absent
    # (legacy/external block predating the accumulator, which always sets the field —
    # a missing field means backward-compat, so stay N/A instead of scoring a phantom 0).
    _v5_ordered = "ordered_facts_state" in b
    grounded = (b.get("evidence_eligible_sessions") if _v5_ordered
                else t.get("mcp_grounded_sessions"))
    ci_denom = (b.get("eligible_change_sessions") if _v5_ordered
                else t.get("mcp_write_sessions", sessions))
    coverage = (grounded / ci_denom) if grounded is not None and ci_denom else None
    context_intel = (None if ((_v5_ordered and ordered_state != "measured")
                              or b.get("no_tool_activity") or grounded is None or not ci_denom)
                     else sat(coverage, CONTEXT_INTELLIGENCE_TARGET))
    # compounding writes -> per-tool-call rate (rewards the habit, not raw volume)
    compounding = wsum((.6, rate(st.get("compounding_writes", 0),
                                 COMPOUNDING_WRITES_PER_CALL_TARGET), None),
                       (.4, (1.0 if has_skill(["retro", "writing-plans", "brainstorm"]) else 0.6), "skill_reads"),
                       axis="Compounding")
    _review_skills_applicable = "skill_reads" in caps
    verification_signals = {
        "tool_calls": tool_calls,
        **rate_facts("test_runs", b.get("shell_test_runs", 0), TEST_RUNS_PER_CALL_TARGET)}
    if _review_skills_applicable:
        verification_signals.update(
            rate_facts("review_skills", review_n, REVIEW_SKILLS_PER_CALL_TARGET))
    else:
        verification_signals["review_skills_applicable"] = False
    craft_axes = [
        ("Verification", 35, verification, verification_signals),
        ("Grounding", 25, grounding, {"planning_ratio": b.get("planning_ratio_explore_to_doing", 0)}),
        ("Context Intelligence", 20, context_intel,
         {"grounded_sessions": grounded, "write_sessions": ci_denom,
          "total_sessions": sessions,
          "coverage": round(coverage, 3) if coverage is not None else None,
          "target_coverage": CONTEXT_INTELLIGENCE_TARGET,
          "grounded_session_rule": "knowledge-MCP call OR explore-class project/data/design MCP call before a later Edit/Write/MultiEdit/NotebookEdit in the same session",
          "score_formula": (f"coverage = evidence_eligible_sessions / eligible_change_sessions; score = min(1, coverage / {CONTEXT_INTELLIGENCE_TARGET:.2f})"
                            if _v5_ordered else
                            f"coverage = grounded_sessions / write_sessions; score = min(1, coverage / {CONTEXT_INTELLIGENCE_TARGET:.2f})")}),
        ("Compounding", 20, compounding, {
            "tool_calls": tool_calls,
            **rate_facts("compounding_writes", st.get("compounding_writes", 0),
                         COMPOUNDING_WRITES_PER_CALL_TARGET)}),
    ]

    # ---- Pillar 3: Efficiency ----
    # `actions_per_prompt` is TOP-LEVEL calls per top-level prompt as of v12 (see the band
    # constants above and gnomon/cli/accumulator.py) — before that the numerator included
    # subagent calls while the denominator excluded subagent turns, so this band was applied
    # to a mixed population.
    app = b.get("actions_per_prompt", 0)
    # A source that can delegate but cannot label a call as delegated leaves its subagent
    # calls in the top-level numerator, so `app` there is the PRE-v12 mixed ratio wearing a
    # v12 label -- and nothing else in the payload distinguishes the two meanings. Steering is
    # UNMEASURED in that case, not zero, so the term is dropped: `lever = None` makes
    # `build_pillar._live` renormalize Efficiency's remaining axis weights back to 100 instead
    # of halving the pillar on a signal the adapter cannot emit. Same treatment
    # `linked_model_routing_state` already gets, for the same reason.
    #
    # Only `antigravity` triggers this today (`delegate` capability, `invoke_subagent ->
    # Agent`, no `isSidechain`); gemini and pi cannot delegate at all, so nothing of theirs is
    # ever mislabelled. See gnomon/config.py::sidechain_label_scope, and the accumulator's
    # `unlabelled_delegate_dispatches` for why the verdict follows OBSERVED delegation rather
    # than capability -- a corpus that never dispatched has an exact ratio and stays scored.
    #
    # The band itself is not fitted either (STEERING_LEVERAGE_BAND_VALIDATED above), so the
    # term is withheld for EVERY source, not just the unlabelling ones. Same `lever = None`
    # mechanism, and the two reasons are reported apart in `steering_leverage.state` below:
    # they are different facts with different lifetimes. The adapter verdict is checked FIRST
    # because it is the one that OUTLIVES the band being fitted -- reporting it keeps the state
    # stable for antigravity across the flag flip, and a reader who sees
    # `withheld_unvalidated_band` knows their own source is fine.
    if b.get("sidechain_label_state", "measured") != "measured":
        steering_state, lever = "unmeasured_sidechain_labels", None
    elif not STEERING_LEVERAGE_BAND_VALIDATED:
        steering_state, lever = "withheld_unvalidated_band", None
    elif app <= 0:
        steering_state, lever = "scored", 0.0
    elif app < STEERING_LEVERAGE_BAND_MIN:
        steering_state, lever = "scored", app / STEERING_LEVERAGE_BAND_MIN
    elif app <= STEERING_LEVERAGE_BAND_MAX:
        steering_state, lever = "scored", 1.0
    else:
        steering_state = "scored"
        lever = max(0.0, 1 - (app - STEERING_LEVERAGE_BAND_MAX)
                    / STEERING_LEVERAGE_DECAY_SPAN)
    # API-error hygiene is scored as a RATE (per 100 tool calls), not an absolute count:
    # an absolute threshold penalizes volume and is window-size dependent. Target 2/100 =
    # full penalty (healthy env < 0.5/100; retry-storm / broken setup > 2/100).
    api_per_100 = 100 * b.get("api_errors_retries", 0) / tool_calls if tool_calls else 0
    recovery = .85 * sat(b.get("error_recovery_ratio") or 0, 1.0) + .15 * (1 - sat(api_per_100, 2.0))
    eff_axes = [
        ("Steering leverage", 50, lever, {"actions_per_prompt": app}),
        ("Recovery", 50, recovery, {"recovery_ratio": b.get("error_recovery_ratio") or 0,
         "api_retries": b.get("api_errors_retries", 0), "api_per_100_tools": round(api_per_100, 3)}),
    ]

    # ---- Pillar 4: Savvy ----
    # Provider-agnostic: works across Claude / OpenAI-Codex / Gemini / etc. "Model mix"
    # rewards using more than one model and routing work off your single default model
    # (match model to task) — no hard-coded model names or tiers.
    models = _models_for_scoring(stats, st.get("models", []))
    total_turns = sum(n for _, n in models)
    top_turns = max((n for _, n in models), default=0)
    offload_share = (1 - top_turns / total_turns) if total_turns else 0
    routing = score_linked_routing(b.get("linked_model_pairs", []), b.get("linked_model_routing_state", "unsupported"))
    model_mix = (.35 * sat(len(models), 3) + .35 * sat(offload_share, 0.30)
                 + .30 * routing["score"] if routing["score"] is not None
                 else .5 * sat(len(models), 3) + .5 * sat(offload_share, 0.30))
    cli_calls, mcp_calls = t.get("cli_calls", 0), t.get("mcp_calls", 0)
    cli_share = cli_calls / (cli_calls + mcp_calls) if (cli_calls + mcp_calls) else 0
    # toolsearch term drops out (renormalized) when unsupported, leaving CLI-share
    token_economy = wsum((.5, rate(t.get("toolsearch_calls", 0), TOOLSEARCH_PER_CALL_TARGET),
                          "toolsearch"),
                         (.5, sat(cli_share, 0.70), None),
                         axis="Token economy")
    savvy_axes = [
        # Model mix needs a real per-turn model id; a source that masks it (Antigravity IDE)
        # drops this axis (renormalized) instead of scoring 0.
        ("Model mix", 50, model_mix, {"distinct_models": len(models), "offload_share": round(offload_share, 2),
         "routing": routing},
         "model"),
        ("Token economy", 50, token_economy, {
            "tool_calls": tool_calls, "cli_share": round(cli_share, 2),
            **rate_facts("toolsearch", t.get("toolsearch_calls", 0),
                         TOOLSEARCH_PER_CALL_TARGET)}),
    ]

    def build_pillar(name, weight, axes):
        # An axis may carry a 5th element: a required capability. If no present source can
        # record it, drop the axis and renormalize the remaining axis weights back to 100 so
        # the pillar isn't dragged down by an unmeasurable signal. Full-capability corpora
        # (Claude) keep every axis -> scale == 1.0 -> no-op.
        def _live(a):
            if a[2] is None:                               # wsum found no measurable term
                return False
            if len(a) < 5 or a[4] is None:
                return True
            # Skill fluency is observable via first-class Skill tool or read/inject paths.
            if a[0] == "Skill fluency" and a[4] == "skills":
                return "skills" in caps or "skill_reads" in caps
            return a[4] in caps
        live = [a for a in axes if _live(a)]
        wlive = sum(a[1] for a in live) or 1
        scale = 100.0 / wlive
        effective_weights = [round(a[1] * scale) for a in live]
        if effective_weights:
            effective_weights[-1] += 100 - sum(effective_weights)
        # `partial_terms` is present ONLY when the axis was scored on fewer than all of its
        # terms -- absence means fully measured, mirroring the pillar's `not_applicable`
        # (also absent when nothing dropped). It is an axis SIBLING rather than an entry in
        # `signals` on purpose: mirdash reads `signals` as Record<string, number> and shows
        # the LOWEST value as the axis bottleneck (`pickDrivingSignal` in
        # apps/web/lib/aq-report.ts), so a fractional weight share in there would be
        # rendered as a phantom bottleneck on nearly every partial axis. As a sibling it
        # falls outside `parseAxis`'s {name, weight, score, signals} whitelist and is simply
        # ignored by consumers that have not opted in.
        out = [{"name": a[0], "base_weight": a[1], "weight": effective_weight,
                # Binary64 guarantees 15 portable significant decimal digits. Canonicalize
                # only the exported diagnostic; keep scoring on the unrounded value below.
                "normalized_score": float(format(a[2], ".15g")),
                "score": round(effective_weight * a[2], 1),
                "signals": a[3],
                **({"partial_terms": partial_by_axis[a[0]]}
                   if a[0] in partial_by_axis else {})}
               for a, effective_weight in zip(live, effective_weights)]
        pillar = {"name": name, "weight": weight, "score": round(sum(x["score"] for x in out), 1), "axes": out}
        dropped = [a[0] for a in axes if a not in live]
        if dropped:
            pillar["not_applicable"] = dropped
        return pillar

    pillars = [build_pillar("Breadth", 30, breadth_axes), build_pillar("Craft", 35, craft_axes),
               build_pillar("Efficiency", 20, eff_axes), build_pillar("Savvy", 15, savvy_axes)]
    total = round(sum(p["weight"] / 100 * p["score"] for p in pillars))
    # ONE honest level vocabulary, driven by AQ (the score that actually separates level).
    # No flattery at the floor: a low score reads low. Also drives the profile archetype.
    tier = ("Elite" if total >= 88 else "Advanced" if total >= 75 else "Proficient" if total >= 60
            else "Adequate" if total >= 45 else "Apprentice" if total >= 25 else "Novice")
    return {
        "aq_0_100": total, "tier": tier, "pillars": pillars,
        "score_contract_id": SCORE_CONTRACT_ID,
        # `actions_per_prompt` is MEASURED even when the term built from it is not scored, so
        # the number keeps being published — the `partial_terms` principle: the value stands,
        # the interpretation is withheld. It cannot ride in the axis's `signals` when the axis
        # is dropped, so it sits here beside the other ungraded readings (`mcp_vs_cli`,
        # `tool_diversity`). `state` is the *_state convention (`ordered_facts_state`,
        # `linked_model_routing_state`, `sidechain_label_state`) applied to the OUTPUT rather
        # than the input: "scored", or which of the two absences applies.
        "steering_leverage": {"state": steering_state, "actions_per_prompt": app},
        "mcp_vs_cli": {"cli_calls": cli_calls, "cli_distinct": t.get("clis_distinct", 0),
                       "mcp_calls": mcp_calls, "mcp_distinct": t.get("mcp_servers_distinct", 0),
                       "ratio": round(cli_calls / mcp_calls, 1) if mcp_calls else None},
        "tool_diversity": {"distinct": t.get("tool_diversity", 0), "entropy": t.get("tool_entropy_normalized", 0)},
    }
