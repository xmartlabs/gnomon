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
  1. change the constant(s) in `gnomon/scoring/aq.py`
  2. bump the three versions in `gnomon/scoring/versioning.py`
  3. run `python3 -c "from gnomon.scoring.calibration import calibration_fingerprint as f; print(f())"`
  4. add `"<new contract id>": "<printed fingerprint>"` to CALIBRATION_FINGERPRINTS,
     leaving the older entries untouched as the audit trail
  5. regenerate the golden with `python3 tests/gen_scoring_vectors.py`

KNOWN GAP: only module-level named constants in `aq.py` are covered. A handful of sat()
targets are still inline literals in expressions (`sat(len(models), 3)`,
`sat(offload_share, 0.30)`, `sat(cli_share, 0.70)`, and the `1.0` identity targets). They are
NOT fingerprinted -- name them here first if a change needs to touch them.
"""
import hashlib

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


def calibration_fingerprint():
    """Stable 16-hex-char digest of every registered calibration constant's VALUE.

    Read through `getattr` at call time, not captured at import, so the fingerprint tracks
    the live module (which is also what makes the per-constant sensitivity test possible).
    `repr` rather than `str` so 0.25 and "0.25" cannot collide.
    """
    payload = "\n".join(
        f"{name}={getattr(aq, name)!r}" for name in sorted(CALIBRATION_CONSTANT_NAMES))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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
}
