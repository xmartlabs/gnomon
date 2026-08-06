"""Bind score-affecting calibration to append-only contract fingerprints.

Any calibration change requires a new contract ID and fingerprint entry. Never
rewrite an existing entry: it records the values published by that contract.
"""
import hashlib
import importlib

from gnomon.scoring import aq

# Score-affecting calibration. Order is irrelevant (the fingerprint sorts), but keep the
# grouping so a reviewer can see which axis each constant feeds.
CALIBRATION_CONSTANT_NAMES = (
    # scoring window: it determines the corpus all window-sensitive inputs score.
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
    # steering leverage and whether the term is currently applicable.
    "STEERING_LEVERAGE_BAND_MIN",
    "STEERING_LEVERAGE_BAND_MAX",
    "STEERING_LEVERAGE_DECAY_SPAN",
    # False withholds an unvalidated steering term. A later flip must bump the contract.
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
    # harness taxonomy (v13)
    "HARNESS_TEAM_SESSION_TYPES",
    "HARNESS_BELOW_TEAM_CREDIT",
)

# Numeric constants in aq.py that do NOT affect a score, with the reason. The drift test
# demands every numeric constant be in one list or the other, so an unclassified addition
# fails rather than slipping through as uncovered.
NON_CALIBRATION_CONSTANT_NAMES = ()

# Score-affecting calibration outside aq.py. Registered absence is fingerprinted,
# preserving compatibility for replayed payloads that use historical blend inputs.
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

    Registered absence is a distinct fingerprint value, so replay compatibility
    remains visible and accidental removal narrows neither the digest nor its coverage.
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
    # Append-only audit trail: each digest is the calibration published by its contract.
    "8:8:8": "38bf1d623bea1517",
    "9:9:9": "2e7638d58c2b26e4",
    "10:10:10": "7a2c444ff5c26f06",
    "11:11:11": "888bec08099b6fbc",
    "12:12:12": "43f4a19179acc3a0",
    "13:13:13": "94f38d0963b1b195",
    # v14 (H10 active_hours union + WU4 ORCHESTRATION_TOOLS taxonomy): neither change
    # touches a registered CALIBRATION_CONSTANT_NAMES value, so the digest is unchanged
    # from 13:13:13 -- see versioning.py's v14 note and design's calibration-blind-spot
    # risk (the fingerprint hashes constant VALUES, not derivation/taxonomy logic).
    "14:14:14": "94f38d0963b1b195",
    # v15 (Workflow fan-out under-credit fix): sources Workflow fan-out from real
    # dispatched-agent transcripts instead of the per-call tool_use increment. A real
    # score delta (fanout_median/Orchestration/Breadth/AQ move), but no registered
    # CALIBRATION_CONSTANT_NAMES value changed -- FANOUT_CEILING stays 5 and no rate
    # target/weight/denominator moved -- so the digest is unchanged from 13:13:13/14:14:14.
    "15:15:15": "94f38d0963b1b195",
}

# Contract IDs whose fingerprint is a DOCUMENTED, deliberate duplicate of the contract
# they immediately followed: the bump was score-affecting through a derivation/taxonomy
# change (H10 active_hours union, WU4 ORCHESTRATION_TOOLS gate), not a registered
# CALIBRATION_CONSTANT_NAMES value, so no constant moved and the digest is legitimately
# unchanged. test_calibration_contract.py's injectivity guard excludes exactly these IDs;
# any OTHER duplicate fingerprint remains the accidental-drift failure mode it exists to
# catch.
ZERO_CALIBRATION_DELTA_CONTRACT_IDS = frozenset({"14:14:14", "15:15:15"})
