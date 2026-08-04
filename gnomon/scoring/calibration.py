"""Binds the calibration constants to the score contract ID mechanically.

`COMPARISON_POLICY` is `same_score_contract_id_only`, so the contract ID is the only thing
that keeps two rows from being compared. That makes re-fitting a target WITHOUT bumping the
contract a silent cohort merge: mirdash charts a delta between a pre-fit row and a post-fit
row believing both were scored the same way. Nothing caught that before this module --
`tests/test_score_contract_atomicity.py` only asserts the contract left "7:7:7".

The rule this module enforces: **any calibration constant that moves requires a new contract
ID and a new fingerprint entry.** Never edit an existing entry to make the suite green; that
is the exact failure being prevented.

Bumping procedure:
  1. change the constant(s) in `gnomon/scoring/aq.py` (or one of the out-of-module
     constants registered in `BLEND_CALIBRATION_CONSTANT_NAMES`)
  2. bump the three versions in `gnomon/scoring/versioning.py`
  3. run `python3 -c "from gnomon.scoring.calibration import calibration_fingerprint as f; print(f())"`
  4. add `"<new contract id>": "<printed fingerprint>"` to CALIBRATION_FINGERPRINTS,
     leaving the older entries untouched as the audit trail
  5. regenerate the golden with `python3 tests/gen_scoring_vectors.py`

KNOWN GAP: apart from the explicitly registered out-of-module constants below, only
module-level named constants in `aq.py` are covered. A handful of sat() targets are still
inline literals in expressions (`sat(len(models), 3)`, `sat(offload_share, 0.30)`,
`sat(cli_share, 0.70)`, and the `1.0` identity targets). They are NOT fingerprinted -- name
them here first if a change needs to touch them. The Steering-leverage band used to be in
that list and is the worked example of the rule: v12 needed to touch what it judges, so it
was named in aq.py and registered below before the change shipped.
"""
import hashlib
import importlib

from gnomon.scoring import aq

# Score-affecting calibration. Order is irrelevant (the fingerprint sorts), but keep the
# grouping so a reviewer can see which axis each constant feeds.
CALIBRATION_CONSTANT_NAMES = (
    # the scoring window itself -- it decides the corpus every ceiling and floor below is
    # judged against, so a silent change to it is the same cohort merge this module exists
    # to prevent. It was score-affecting and unfingerprinted until v10.
    "DEFAULT_SCORING_WINDOW_MONTHS",
    # rate targets -- the six that share the tool_calls_total denominator
    "SKILLS_TOTAL_PER_CALL_TARGET",
    "TOOLSEARCH_PER_CALL_TARGET",
    "TASK_CALLS_PER_CALL_TARGET",
    "TEST_RUNS_PER_CALL_TARGET",
    "REVIEW_SKILLS_PER_CALL_TARGET",
    "COMPOUNDING_WRITES_PER_CALL_TARGET",
    # the evidence floor those six are scored through (occurrences implied by the target)
    "RATE_MIN_EXPECTED_AT_TARGET",
    # absolute count ceilings -- the window-sensitive ones
    "SUBAGENT_TYPES_DISTINCT_CEILING",
    "FANOUT_CEILING",
    "SKILLS_DISTINCT_CEILING",
    "MCP_SERVERS_DISTINCT_CEILING",
    "CLIS_DISTINCT_CEILING",
    # steering leverage -- the band Efficiency reads `actions_per_prompt` through. Registered
    # at v12, when that field stopped counting subagent calls in its numerator: the band's
    # VALUES do not move, the population they judge does, and a band applied to a different
    # population is a different calibration.
    "STEERING_LEVERAGE_BAND_MIN",
    "STEERING_LEVERAGE_BAND_MAX",
    "STEERING_LEVERAGE_DECAY_SPAN",
    # ...and whether that band has been fitted against a population at all. It has not (the
    # PROVENANCE block in aq.py), so it is False and the term is WITHHELD rather than scored
    # through it. This is the most score-affecting constant in the group -- it decides whether
    # the term exists -- and registering it is what makes flipping it back on impossible to do
    # quietly: the flip moves the digest and demands a new contract ID, which is exactly the
    # failure it guards against. A bool registers cleanly here: the sensitivity test patches
    # `False + 1` = 1, whose repr differs, so the fingerprint moves.
    "STEERING_LEVERAGE_BAND_VALIDATED",
    # planning / context intelligence
    "PLANNING_TARGET",
    "PLANNING_PRACTICE_TARGET",
    "CONTEXT_INTELLIGENCE_TARGET",
    "CHURN_MIN",
    "WINDOW",
    "PLAN_MIN_LINES",
    "PLAN_MIN_STEPS",
    "MIN_ELIGIBLE_SESSIONS",
    # orchestration
    "ORCHESTRATABLE_CODE_FILES",
    "ORCHESTRATABLE_SUBSTANTIVE",
    "ORCHESTRATION_FREQUENCY_TARGET",
    "ORCHESTRATION_FULL_CONFIDENCE_SESSIONS",
)

# Numeric constants in aq.py that do NOT affect a score, with the reason. The drift test
# demands every numeric constant be in one list or the other, so an unclassified addition
# fails rather than slipping through as uncovered.
NON_CALIBRATION_CONSTANT_NAMES = ()

# Score-affecting calibration that does NOT live in aq.py, as (name, module path). The
# recency-blend weights are the whole of it: until v11 they multiplied the PUBLISHED corpus
# AQ (`0.65 * recent_30d + 0.35 * full_window`) while sitting in `aggregate.py`, outside
# this module's aq.py-only reach -- the same hole `DEFAULT_SCORING_WINDOW_MONTHS` had until
# v10, and the same silent cohort merge this module exists to prevent.
#
# `RECENT_WEIGHT` is registered even though v11 DELETED it, and that is the point: the
# fingerprint records a registered constant's absence as a distinct value (see
# `_registered_value`), so the multiplier disappearing is exactly as visible as it moving
# would have been. `HISTORY_WEIGHT` survives because replay() applies it when reconstructing
# a pre-v11 payload's blend; registering it keeps that surviving weight pinned too.
BLEND_CALIBRATION_CONSTANT_NAMES = (
    ("RECENT_WEIGHT", "gnomon.scoring.aggregate"),
    ("HISTORY_WEIGHT", "gnomon.scoring.aggregate"),
)

# What the fingerprint hashes in place of a registered constant that does not exist. A
# sentinel object rather than a value any constant could legitimately hold, so "deleted"
# can never collide with "set to None"/"set to 0".
_ABSENT = "<absent>"


def _registered_value(module, name):
    """The repr the fingerprint hashes for one registered constant, or `_ABSENT`.

    Absence is a VALUE here, not an error: v11 removes `RECENT_WEIGHT` and the contract
    move has to be visible in the digest. It also means an accidental deletion of a
    registered constant turns `test_fingerprint_matches_the_one_registered_for_this_contract`
    red instead of silently narrowing what the fingerprint covers.
    """
    sentinel = object()
    value = getattr(module, name, sentinel)
    return _ABSENT if value is sentinel else repr(value)


def calibration_fingerprint():
    """Stable 16-hex-char digest of every registered calibration constant's VALUE.

    Read through `getattr` at call time, not captured at import, so the fingerprint tracks
    the live modules (which is also what makes the per-constant sensitivity tests
    possible). `repr` rather than `str` so 0.25 and "0.25" cannot collide.

    Out-of-module constants are namespaced by their module path, so `aggregate.RECENT_WEIGHT`
    can never collide with a same-named constant added to aq.py later.
    """
    lines = [f"{name}={getattr(aq, name)!r}"
             for name in sorted(CALIBRATION_CONSTANT_NAMES)]
    lines += [
        f"{module_path}.{name}={_registered_value(importlib.import_module(module_path), name)}"
        for name, module_path in sorted(BLEND_CALIBRATION_CONSTANT_NAMES)
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


# contract ID -> the calibration it published. Append-only.
CALIBRATION_FINGERPRINTS = {
    # v8 (skill-dedup + exact-tail review matcher + scoped git_churn). The targets here are
    # the ones fitted against the PRE-dedup counters -- the known-misaligned pair
    # (SKILLS_TOTAL_PER_CALL_TARGET, REVIEW_SKILLS_PER_CALL_TARGET) is registered as-is so
    # the re-fit shows up as a contract move rather than as an in-place edit.
    "8:8:8": "38bf1d623bea1517",
    # v9 (post-dedup re-fit of the two skill rate targets + `verif`-leading review matcher
    # + the rate evidence floor the re-fit made necessary).
    # SKILLS_TOTAL_PER_CALL_TARGET 0.25 -> 0.009 and REVIEW_SKILLS_PER_CALL_TARGET
    # 0.060 -> 0.004, plus the NEW constant RATE_MIN_EXPECTED_AT_TARGET = 1.0: dropping a
    # rate whose denominator is so small that one occurrence would max the term (the re-fit
    # moved that boundary into reach — see aq.py's rate evidence floor block). The floor is
    # part of the SAME unpublished v9: this entry has never been committed to a released
    # payload, so its hash is being AUTHORED here, not edited after publication. The 8:8:8
    # entry above is untouched. Nothing else in CALIBRATION_CONSTANT_NAMES moved; the other
    # four rate targets were re-measured on the same population and deliberately left in
    # place (the reasoning is in aq.py's rate rationale block, so a later reader does not
    # read this as an oversight).
    "9:9:9": "2e7638d58c2b26e4",
    # v10 (one-month scoring window). The ONLY constant that moves is the new
    # DEFAULT_SCORING_WINDOW_MONTHS 6 -> 1, registered above because it was score-affecting
    # and outside the fingerprint until now: it sets the corpus every absolute ceiling and
    # both session-count floors are judged against, so 1-month rows and 6-month rows must
    # not pool under one contract ID. No TARGET is re-fitted -- the five ceilings were
    # measured under a 1-month window and deliberately left alone
    # (.context/window-ceiling-measurement-2026-07-31.md), and RATE_MIN_EXPECTED_AT_TARGET
    # stays 1.0 for the reason its own block in aq.py gives: the low end is the deliberate
    # choice precisely so small-but-real slices keep their evidence, and under a 1-month
    # window every published slice IS a small slice, which strengthens that argument rather
    # than weakening it. The 8:8:8 and 9:9:9 entries above are untouched.
    "10:10:10": "7a2c444ff5c26f06",
    # v11 (the recency blend is removed). No TARGET in aq.py moves -- checked first, and
    # had that been the whole story the digest would have equalled 10:10:10's and
    # `test_no_two_contracts_share_a_fingerprint` would have failed. That failure would
    # have been informative rather than obstructive: it means something score-affecting was
    # outside the registry. What was outside it is the blend itself, so v11 registers the
    # two weights (BLEND_CALIBRATION_CONSTANT_NAMES above) instead of working around the
    # test. `RECENT_WEIGHT` = 0.65 no longer exists and hashes as absent; `HISTORY_WEIGHT`
    # stays 0.35 for replay of pre-v11 payloads. Adding the two names is itself part of the
    # move, exactly as adding DEFAULT_SCORING_WINDOW_MONTHS was at v10 -- older entries are
    # never recomputed against a newer registry, they record what their contract published
    # under the registry of its day. The 8:8:8, 9:9:9 and 10:10:10 entries are untouched.
    "11:11:11": "888bec08099b6fbc",
    # v12 (`actions_per_prompt` counts top-level actions only; `sidechain_tool_calls` is
    # published beside `tool_calls_total`). No calibration VALUE moves -- checked FIRST, and
    # the counterfactual was measured rather than assumed: with the Steering-leverage band
    # left as three inline literals this digest computes to 888bec08099b6fbc, byte-identical
    # to 11:11:11's, and `test_no_two_contracts_share_a_fingerprint` fails. That failure is
    # informative, exactly as it was at v11: it means the score-affecting thing is outside the
    # registry. Here it is the POPULATION the band judges -- the numerator of
    # `actions_per_prompt` stops counting subagent tool calls and its denominator gains bare
    # slash commands, so a band applied to "actions per instruction" now covers a different
    # quantity on both sides. A band whose meaning moves is calibration, so v12 names
    # STEERING_LEVERAGE_BAND_MIN / _BAND_MAX / _DECAY_SPAN in aq.py (values UNCHANGED from the
    # literals) and registers them above, rather than working around the test. Adding the names
    # is itself part of the move, as it was for DEFAULT_SCORING_WINDOW_MONTHS at v10 and the
    # blend weights at v11 -- older entries are never recomputed against a newer registry, they
    # record what their contract published under the registry of its day. The 8:8:8, 9:9:9,
    # 10:10:10 and 11:11:11 entries are untouched.
    #
    # The values staying put is a DECISION with a measurement behind it, not a deferral: a
    # re-fit was derived against the 48-user upload population and rejected because no pair of
    # thresholds tracks a per-user contraction whose projected spread is 0.00-0.97. See the
    # PROVENANCE block in aq.py for the sensitivity table, and for the correction of an earlier
    # claim that these three had ever been fitted at all.
    #
    # The conclusion drawn from that measurement is the FOURTH registered name in the group,
    # STEERING_LEVERAGE_BAND_VALIDATED = False: since no band can be fitted until the per-user
    # sidechain share is measured rather than projected, v12 does not score the term at all. It
    # is registered rather than left as a plain module flag for the same reason the band itself
    # was named -- it is the single most score-affecting value in the block, and its eventual
    # flip to True must cost a contract bump instead of being a one-character edit. Adding the
    # name is part of the move, as it was for DEFAULT_SCORING_WINDOW_MONTHS at v10, the blend
    # weights at v11 and the band at v12.
    #
    # This entry has never been committed, so its hash is authored in place rather than
    # migrated. The 8:8:8, 9:9:9, 10:10:10 and 11:11:11 entries stay byte-identical.
    "12:12:12": "43f4a19179acc3a0",
}
