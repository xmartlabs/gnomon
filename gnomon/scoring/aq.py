from gnomon.analysis.metrics import _review_skill_uses
from gnomon.config import available_caps
# The planning-evidence helper lives in its own module precisely so BOTH scoring systems
# can share it: gstack imports from this module, so a gstack import here would cycle.
from gnomon.scoring.planning_evidence import _planning_skill_evidence
from gnomon.scoring.versioning import SCORE_CONTRACT_ID

# ---- Scoring window ---------------------------------------------------------------
# Each published score covers one calendar month ending at the selected anchor.
# The window is calibration input: changing it changes the scored corpus and must
# be fingerprinted with the contract.
DEFAULT_SCORING_WINDOW_MONTHS = 1

PLANNING_TARGET = 0.50
# Planning-practice is the share of eligible top-level sessions with plan-mode
# or planning-skill evidence. It lives here because both AQ and GStack use it.
PLANNING_PRACTICE_TARGET = 0.30
# PROVISIONAL -- recalibrate from a production p40-50, which this value has never been
# fitted against (the note was previously buried beside the axis; it belongs next to the
# number). Issue #72 measured five corpora at 0.984-1.000 coverage, i.e. every one of them
# saturated a target set at 0.60, which is consistent with 0.60 being too low but does NOT
# establish it: five self-selected corpora cannot show where the real population mass sits.
# Moving this value is a registered calibration change (see calibration.py's
# CALIBRATION_CONSTANT_NAMES) and needs a new contract ID and fingerprint.
CONTEXT_INTELLIGENCE_TARGET = 0.60

# ---- Per-tool-call rate targets ---------------------------------------------------
# Rate terms use `count / tool_calls_total`. Targets are calibration inputs and
# are evaluated against observable source capabilities; unavailable signals drop
# rather than scoring zero.
#
# v17 removed TWO of these targets. TEST_RUNS_PER_CALL_TARGET was removed because the
# Verification test-run half switched from a per-call DENSITY (shell_test_runs /
# tool_calls, confounded by delegation inflating the denominator) to a per-SESSION
# COVERAGE fraction scored with NO fitted target (sat(coverage, 1.0)). TASK_CALLS_
# PER_CALL_TARGET was removed because the Discipline task-tool term saturated for virtually
# everyone (~3.2x target) and was dropped as non-discriminating todo-tool ceremony.
SKILLS_TOTAL_PER_CALL_TARGET = 0.009
REVIEW_SKILLS_PER_CALL_TARGET = 0.004
COMPOUNDING_WRITES_PER_CALL_TARGET = 0.0018

# ---- Rate evidence floor ------------------------------------------------------------
# A term needs at least one expected occurrence at its target. Below this floor,
# `rate` returns None so `wsum` drops and renormalizes the term instead of treating
# a single event or absence as conclusive evidence.
RATE_MIN_EXPECTED_AT_TARGET = 1.0

# ---- Ordered-planning calibration -------------------------------------------------
# These constants define eligibility and ordered-plan evidence. Recalibrate them
# together because each changes the population used by the others.
CHURN_MIN = 80              # net changed lines (C2): single-file eligibility via churn
WINDOW = 72 * 3600           # seconds (C4): cross-session plan-credit lookback window
PLAN_MIN_LINES = 8          # net lines (C6): minimum substantive plan-file size
PLAN_MIN_STEPS = 3          # distinct todo/task steps (C6): raised from 2 (anti-theater)
MIN_ELIGIBLE_SESSIONS = 5   # sessions (C7): below this, drop+renormalize (noise floor)

# ---- Orchestration v2 — frequency + quality compound -------------------------
ORCHESTRATABLE_CODE_FILES = 3    # code files written (stricter than eligible's 2)
ORCHESTRATABLE_SUBSTANTIVE = 20  # substantive tool calls (stricter than eligible's 10)
# Provisional target; any recalibration requires a contract update.
ORCHESTRATION_FREQUENCY_TARGET = 0.78  # share of orchestratable sessions that delegate
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

# ---- Harness taxonomy constants (v13) ----------------------------------------
# Names for existing values. They are registered under the calibration fingerprint
# so an equivalent refactor cannot hide a score-affecting change.
HARNESS_TEAM_SESSION_TYPES = 3
HARNESS_BELOW_TEAM_CREDIT = 0.6

# ---- Steering leverage --------------------------------------------------------
# The band operates on top-level actions per human instruction. It is registered
# because changing either its values or its applicability changes scoring.
STEERING_LEVERAGE_BAND_MIN = 5
STEERING_LEVERAGE_BAND_MAX = 20
STEERING_LEVERAGE_DECAY_SPAN = 40

# The steering band is not validated. Keep publishing the measured ratio, but
# withhold its score until a fitted replacement ships under a new contract.
# The flag is fingerprinted, so re-enabling the term cannot happen silently.
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

    Capability-aware: a signal a source CANNOT record (skills on Cursor, etc.)
    is dropped and its weight renormalized away — not scored 0 — so non-Claude tools aren't
    penalized for what their backend never persists. With a full-capability corpus (Claude)
    every term stays and this is a no-op."""
    t, st, b = stats.get("tools", {}), stats.get("stack", {}), stats.get("behavior", {})
    caps = available_caps((stats.get("corpus", {}).get("sources") or {}).keys())
    has_skills = "skills" in caps

    def sat(x, target):
        return min(1.0, x / target) if target else 0.0

    # Rate score. Absolute cumulative counts are window-size dependent, so score a
    # rate instead of penalizing low-volume users for the size of their window.
    #
    # Rate terms use `tool_calls_total`, pooling numerator and denominator over the same
    # unit. Terms that measure session coverage continue to use sessions.
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
    # ---- fanout: None (unmeasured) is DISTINCT from 0 (measured zero) --------
    # Until v13 `or 0` coerced both to 0, hiding a legitimate measured zero.
    _fanout_raw = b.get("fanout_median")
    fanout = _fanout_raw if _fanout_raw is not None else None

    # ---- o_harn taxonomy (v13) -----------------------------------------------
    # Five cases, in order of discriminating evidence:
    _max_types = st.get("max_session_subagent_types")
    _agent_calls = t.get("agent_calls")
    _types_distinct = st.get("subagent_types_distinct", 0)
    _no_tool = b.get("no_tool_activity", False)
    if _no_tool:
        o_harn = None  # no tool activity at all -> drop
    elif _max_types is None:
        o_harn = None  # absent key ≠ measured zero -> drop
    elif _max_types >= 1:
        o_harn = 1.0 if _max_types >= HARNESS_TEAM_SESSION_TYPES else HARNESS_BELOW_TEAM_CREDIT
    elif _agent_calls is None or _agent_calls > 0 or _types_distinct > 0:
        o_harn = None  # dispatched but roles not registered -> drop
    else:
        o_harn = 0.0  # genuinely measured zero delegation

    # Orchestration v2: observed frequency (share of orchestratable sessions that
    # delegated), normalized target score, and coordination quality (subagent
    # diversity, fan-out, harness use). Frequency earns its full 30% weight
    # progressively over the first five eligible sessions.
    o_quality = wsum(
        (0.40, sat(_types_distinct, SUBAGENT_TYPES_DISTINCT_CEILING), None),
        (0.40, sat(fanout, FANOUT_CEILING) if fanout is not None else None, None),
        (0.20, o_harn, None),
        axis="Orchestration")
    _o_orchestratable = b.get("orchestratable_sessions") or 0
    _o_delegated = b.get("delegated_orchestratable_sessions") or 0
    o_frequency = (_o_delegated / _o_orchestratable) if _o_orchestratable else None
    o_frequency_score = (sat(o_frequency, ORCHESTRATION_FREQUENCY_TARGET)
                         if o_frequency is not None else None)
    o_frequency_confidence = min(
        _o_orchestratable / ORCHESTRATION_FULL_CONFIDENCE_SESSIONS, 1.0)
    o_frequency_weight = 0.30 * o_frequency_confidence
    orchestration = (
        ((1.0 - o_frequency_weight) * o_quality
         + o_frequency_weight * o_frequency_score)
        if o_quality is not None and o_frequency_score is not None
        else o_quality if o_quality is not None
        else o_frequency_score if o_frequency_score is not None
        else None)
    # skills_total -> per-tool-call rate; skills_distinct stays (diversity, correctly absolute).
    # Via wsum, not raw arithmetic: `rate` returns None when there is no usable tool-call
    # denominator, and wsum is what drops such a term and renormalizes the rest. Multiplying
    # by a coefficient directly would raise a TypeError instead.
    _process_skills_matched = has_skill(["subagent-driven", "brainstorm", "writing-plans",
                                         "cerberus", "systematic-debugging"])
    skill_fluency = wsum(
        (.40, sat(st.get("skills_distinct", 0), SKILLS_DISTINCT_CEILING), None),
        (.30, rate(st.get("skills_total", 0), SKILLS_TOTAL_PER_CALL_TARGET), None),
        (.30, 1.0 if _process_skills_matched else 0.6, None),
        axis="Skill fluency")
    # mcp_servers/clis are distinct-counts (kept absolute). The toolsearch rate term was
    # removed (v17): it was ~94% select:-prefixed deterministic tool-loading the deferred-tool
    # harness forces, and its deliberate remainder is too sparse to calibrate as a rate.
    # wsum renormalizes the two surviving terms to .5/.5. toolsearch_calls stays a published
    # diagnostic (see the Tool command facts dict below) but is no longer scored.
    tool_command = wsum((.40, sat(t.get("mcp_servers_distinct", 0),
                                  MCP_SERVERS_DISTINCT_CEILING), None),
                        (.40, sat(t.get("clis_distinct", 0), CLIS_DISTINCT_CEILING), None),
                        axis="Tool command (MCP + CLI)")
    # plan-skill term needs the Skill capability. (v17 dropped the task-tool rate term:
    # TaskCreate/Update + task-skill uses ran at ~3.2x target, so rate()'s sat() pinned it
    # at 1.0 for virtually everyone -- todo-tool ceremony that did not discriminate and
    # rewarded TaskUpdate spam. task_tool_calls stays a published diagnostic, not scored.)
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
    # v17 dropped the (.40, task-tool rate) term; wsum renormalizes the two survivors
    # (planning_habit .40 + ordered_planning .20) to .667 / .333.
    discipline = wsum(  # The legacy path derives the share from plan_sessions over ALL
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
         "fanout_median": fanout,
         "o_harn": o_harn,
         "frequency": round(o_frequency, 3) if o_frequency is not None else None,
         "frequency_score": (round(o_frequency_score, 3)
                             if o_frequency_score is not None else None),
         "frequency_confidence": round(o_frequency_confidence, 3),
         "frequency_weight": round(o_frequency_weight, 3),
         "coordination_quality": round(o_quality, 3) if o_quality is not None else None,
         "orchestratable_sessions": _o_orchestratable,
         "delegated_orchestratable_sessions": _o_delegated},
         "delegate"),
        ("Skill fluency", 22, skill_fluency, {
            "skills_distinct": st.get("skills_distinct", 0), "tool_calls": tool_calls,
            **rate_facts("skills_total", st.get("skills_total", 0),
                         SKILLS_TOTAL_PER_CALL_TARGET),
            "process_skills_matched": _process_skills_matched}, "skills"),
        ("Tool command (MCP + CLI)", 28, tool_command, {
            "mcp_servers": t.get("mcp_servers_distinct", 0),
            "clis": t.get("clis_distinct", 0), "tool_calls": tool_calls,
            # Non-scored diagnostic: the raw ToolSearch count stays visible (the accumulator
            # still emits it) without the *_per_call / *_per_call_target rate disclosure that
            # would imply it is scored.
            "toolsearch_calls": t.get("toolsearch_calls", 0)}),
        # Surface the planning inputs: the axis now moves with planning FREQUENCY and
        # ordered planning only, and a score with no visible driver is not actionable. The
        # raw task_tool_calls count stays a published diagnostic (v17 dropped its scored
        # rate term) without the *_per_call / *_per_call_target disclosure that implies it
        # is scored -- mirroring how toolsearch_calls is republished on Tool command.
        ("Discipline", 17, discipline, {
            "tool_calls": tool_calls,
            "task_tool_calls": t.get("task_tool_calls", 0),
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
    #
    # v17 — the test half is per-SESSION COVERAGE, not per-call density. The old
    # shell_test_runs / tool_calls density was confounded by delegation (sidechain tool calls
    # inflate the denominator), so it did not measure whether the developer verified their
    # changes. coverage = (eligible change-sessions that also ran a shell test) /
    # eligible_change_sessions, scored as a PURE FRACTION with NO fitted target (sat(_, 1.0),
    # exactly like Grounding) so it needs no calibration band. It is N/A (None -> wsum
    # renormalizes onto review_skills) when ordered facts are not measured -- the same
    # fail-closed guard Context Intelligence applies on ordered_facts_state and
    # eligible_change_sessions. review skills stays a per-tool-call rate.
    #
    # ABSENT vs MEASURED ZERO. `inputs.py` no longer defaults a missing key to 0 (it
    # projects absence as None), so a legacy/foreign payload that never measured coverage
    # reads None here -- distinct from a genuine measured zero (the field present, value
    # 0). Coercing both to 0 (the old `.get(..., 0) or 0`) fabricated a 0.0 coverage for a
    # v17 payload that had `ordered_facts_state == "measured"` and a real
    # `eligible_change_sessions`, both of which predate the v17 coverage numerator. `is
    # None`, not falsiness, is the test: a present 0 must still score 0.0 coverage.
    _test_covered = b.get("test_covered_change_sessions")
    _test_covered_measured = _test_covered is not None
    # F9 — a malformed/replayed block can carry covered > eligible (the
    # numerator and denominator are computed from different sources on a
    # replay/legacy path, unlike the accumulator's own aggregate_ordered
    # where covered <= eligible by construction). Clamp the numerator to the
    # denominator BEFORE dividing so the published ratio can never exceed
    # 1.0 for accepted input; sat(_, 1.0) below already clamps the SCORED
    # term, this clamp is only about the raw diagnostic.
    # OBS 2 — a malformed/replayed block can ALSO carry a NEGATIVE covered
    # count. `min(_, eligible)` alone only bounds the numerator from above, so
    # also floor it at 0 here — otherwise the ratio (and, since sat(x, 1.0) =
    # min(1.0, x/target) does not bound from below either, the SCORED term
    # too) goes negative and unfairly lowers Verification.
    _test_covered_clamped = (max(0, min(_test_covered, eligible))
                             if _test_covered_measured and eligible else _test_covered)
    _verif_coverage = (_test_covered_clamped / eligible
                       if _test_covered_measured and eligible else None)
    # F8 — same C7 significance floor as ordered_planning/planning_habit below:
    # a coverage ratio over fewer than MIN_ELIGIBLE_SESSIONS eligible sessions
    # is noise (e.g. 100% over 1 session), so drop the term (None ->
    # renormalized onto review_skills) instead of scoring it.
    verification_coverage = (None if (ordered_state != "measured" or not eligible
                                      or not _test_covered_measured
                                      or eligible < MIN_ELIGIBLE_SESSIONS)
                             # OBS 2 — belt-and-suspenders: the numerator clamp above
                             # already guarantees _verif_coverage is in [0, 1] here, but
                             # clamp both bounds explicitly so the SCORED term can never
                             # go negative even if the numerator clamp is bypassed.
                             else max(0.0, min(1.0, _verif_coverage)))
    verification = wsum((.5, verification_coverage, None),
                        (.5, rate(review_n, REVIEW_SKILLS_PER_CALL_TARGET), "skill_reads"),
                        axis="Verification")
    # Grounding is a PURE FRACTION with no fitted target: parity (one explore-or-reason
    # action per doing action) is full marks, and the ratio is saturated there because
    # exploring MORE than you build is not a further virtue to reward.
    #
    # KNOWN LIMITATION (issue #72, five corpora): observed ratios spanned 0.974-1.469 and
    # every corpus scored at or within half a point of this ceiling, so above 1.0 the term
    # carries no information and does not separate people IN THAT RANGE. Whether it
    # discriminates below parity is unmeasured. Raising the ceiling would be a genuine
    # recalibration -- it needs a production distribution, not a re-read of the formula --
    # so the target stays 1.0 and the limitation is published instead of quietly carried.
    grounding = sat(b.get("planning_ratio_explore_to_doing", 0), 1.0)
    # Context Intelligence: PURE per-session grounding COVERAGE, not knowledge-MCP call/
    # server volume (the old `<50 calls` gate was gameable by auto-fired knowledge-MCP
    # calls with zero relationship to authored output). A session is "grounded" when a
    # knowledge-MCP call (accumulator.py's per-session state machine) precedes a later
    # Edit/Write/MultiEdit/NotebookEdit in that SAME session. coverage = grounded/total.
    # F8 — per-session coverage score WITH an evidence floor (this deliberately reverses
    # the earlier "MONOTONIC ... NO floor" design): more grounding never lowers the axis,
    # and a real measured zero (has tool activity, 0 grounded sessions) is still scored 0,
    # NOT dropped -- but a ratio over fewer than MIN_ELIGIBLE_SESSIONS eligible sessions
    # (e.g. 1/1 = 100% grounded) is not a defensible coverage measurement, so it is dropped
    # (None -> renormalized) instead, mirroring the same C7 floor Verification coverage
    # and ordered_planning/planning_habit apply. TARGET is PROVISIONAL (recalibrate from
    # prod p40-50). The axis is ALSO N/A when the source genuinely can't measure grounding:
    # no_tool_activity (can't reconstruct ordered per-session tool sequences) OR the
    # grounding field is absent (legacy/external block predating the accumulator, which
    # always sets the field — a missing field means backward-compat, so stay N/A instead
    # of scoring a phantom 0).
    _v5_ordered = "ordered_facts_state" in b
    grounded = (b.get("evidence_eligible_sessions") if _v5_ordered
                else t.get("mcp_grounded_sessions"))
    ci_denom = (b.get("eligible_change_sessions") if _v5_ordered
                else t.get("mcp_write_sessions", sessions))
    coverage = (grounded / ci_denom) if grounded is not None and ci_denom else None
    context_intel = (None if ((_v5_ordered and (
                                  ordered_state != "measured"
                                  or (ci_denom is not None and ci_denom < MIN_ELIGIBLE_SESSIONS)))
                              or b.get("no_tool_activity") or grounded is None or not ci_denom)
                     else sat(coverage, CONTEXT_INTELLIGENCE_TARGET))
    # compounding writes -> per-tool-call rate (rewards the habit, not raw volume)
    _compounding_skills_matched = has_skill(["retro", "writing-plans", "brainstorm"])
    compounding = wsum((.6, rate(st.get("compounding_writes", 0),
                                 COMPOUNDING_WRITES_PER_CALL_TARGET), None),
                       (.4, (1.0 if _compounding_skills_matched else 0.6), "skill_reads"),
                       axis="Compounding")
    _review_skills_applicable = "skill_reads" in caps
    # v17 — disclose per-session COVERAGE (numerator / denominator / ratio) in place of the
    # dropped test-run density rate_facts. coverage is None whenever the term was NOT scored
    # (ordered facts unmeasured or no eligible change-sessions), so a consumer never reads a
    # ratio off a term the scorer refused. The raw shell_test_runs count stays a published
    # diagnostic (still emitted, still fed to gstack/insights) without the *_per_call rate.
    verification_signals = {
        "tool_calls": tool_calls,
        "shell_test_runs": b.get("shell_test_runs", 0),
        "test_covered_change_sessions": _test_covered,
        "eligible_change_sessions": eligible,
        # None whenever the coverage term was NOT scored (ordered facts unmeasured or no
        # eligible change-sessions), so a consumer never reads a ratio off a refused term.
        # F9/OBS2 — max(0.0, min(_, 1.0)) belt-and-suspenders clamp on BOTH bounds: the
        # numerator is already clamped to [0, eligible] above, but a malformed/replayed
        # block (covered outside [0, eligible] from a source other than the
        # accumulator's own aggregate_ordered) must never publish a ratio outside [0, 1]
        # — the SCORED term already clamps the same way.
        "test_coverage": (round(max(0.0, min(_verif_coverage, 1.0)), 4)
                          if verification_coverage is not None else None),
    }
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
                         COMPOUNDING_WRITES_PER_CALL_TARGET),
            "compounding_skills_matched": _compounding_skills_matched}),
    ]

    # ---- Pillar 3: Efficiency ----
    # A corpus with observed delegation but no sidechain labels cannot provide a
    # trustworthy top-level numerator. Drop that term rather than score it as zero.
    # Otherwise withhold it until the registered steering band is validated.
    app = b.get("actions_per_prompt", 0)
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
    model_mix = wsum(
        (0.35, sat(len(models), 3), None),
        (0.35, sat(offload_share, 0.30), None),
        (0.30, routing["score"], None),
        axis="Model mix",
    )
    cli_calls, mcp_calls = t.get("cli_calls", 0), t.get("mcp_calls", 0)
    cli_share = cli_calls / (cli_calls + mcp_calls) if (cli_calls + mcp_calls) else 0
    # The toolsearch rate term was removed (v17, see Tool command above); wsum renormalizes
    # the single surviving cli_share term to full weight, so Token economy is now CLI-share.
    token_economy = wsum((.5, sat(cli_share, 0.70), None),
                         axis="Token economy")
    savvy_axes = [
        # Model mix needs a real per-turn model id; a source that masks it (Antigravity IDE)
        # drops this axis (renormalized) instead of scoring 0.
        ("Model mix", 50, model_mix, {"distinct_models": len(models), "offload_share": round(offload_share, 2),
         "routing": routing},
         "model"),
        ("Token economy", 50, token_economy, {
            "tool_calls": tool_calls, "cli_share": round(cli_share, 2)}),
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
