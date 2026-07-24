"""Planning-practice scoring evidence: the one place that validates and derives the
counted / eligible / unmeasured triple into a share, a coverage and an effective weight.

Lives in its own module because BOTH consumers need it and they sit on opposite sides of
an import edge: ``gstack`` already imports from ``aq``, so ``aq`` cannot import from
``gstack`` without a cycle. ``gstack`` re-exports these names for backwards compatibility.

Field-name note: the serialized ``planning_skill_*`` keys are historical. Since plan-mode
tools also feed the numerator, they mean "planning practice", not "planning Skill". The
names are the wire contract with the mirdash dashboard and are deliberately not renamed.
"""

import math

_PLANNING_SKILL_BASE_WEIGHT = 0.25
_PLANNING_SKILL_NEW_FIELDS = {
    "planning_skill_sessions",
    "planning_skill_eligible_sessions",
    "planning_skill_unmeasured_sessions",
    "planning_skill_session_scope_state",
    "planning_skill_session_share",
    "planning_skill_session_coverage",
}
_PLANNING_SKILL_SELECTORS = _PLANNING_SKILL_NEW_FIELDS - {"planning_skill_sessions"}


def _nonnegative_integral_count(value):
    """Return an integer count, or ``None`` for malformed telemetry."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        return None
    return int(value) if value >= 0 else None


def _unmeasured_planning_evidence():
    return {
        "planning_sessions": None,
        "eligible_sessions": None,
        "unmeasured_sessions": None,
        "state": "unmeasured",
        "share": None,
        "coverage": None,
        "legacy": False,
        "base_weight": _PLANNING_SKILL_BASE_WEIGHT,
        "effective_weight": 0.0,
    }


def _planning_skill_evidence(behavior, legacy_sessions):
    """Validate and derive the one Planning practice scoring evidence shape."""
    if not any(field in behavior for field in _PLANNING_SKILL_SELECTORS):
        denominator = _nonnegative_integral_count(legacy_sessions)
        numerator = _nonnegative_integral_count(behavior.get(
            "planning_skill_sessions", behavior.get("plan_sessions", 0)))
        if numerator is None or denominator is None:
            return _unmeasured_planning_evidence()
        share = numerator / denominator if denominator and numerator <= denominator else None
        return {
            "planning_sessions": numerator,
            "eligible_sessions": denominator,
            "unmeasured_sessions": None,
            "state": "legacy",
            "share": share,
            "coverage": 1.0 if share is not None else None,
            "legacy": True,
            "base_weight": _PLANNING_SKILL_BASE_WEIGHT,
            "effective_weight": (
                _PLANNING_SKILL_BASE_WEIGHT if share is not None else 0.0),
        }

    if not _PLANNING_SKILL_NEW_FIELDS <= set(behavior):
        return _unmeasured_planning_evidence()
    numerator = _nonnegative_integral_count(behavior["planning_skill_sessions"])
    denominator = _nonnegative_integral_count(
        behavior["planning_skill_eligible_sessions"])
    unmeasured = _nonnegative_integral_count(
        behavior["planning_skill_unmeasured_sessions"])
    if (numerator is None or denominator is None or unmeasured is None
            or numerator > denominator):
        return _unmeasured_planning_evidence()

    expected_state = (
        "measured" if denominator > 0 and unmeasured == 0
        else "partial" if denominator > 0 and unmeasured > 0
        else "unmeasured")
    if behavior["planning_skill_session_scope_state"] != expected_state:
        return _unmeasured_planning_evidence()
    if expected_state == "unmeasured":
        if (behavior["planning_skill_session_share"] is not None
                or behavior["planning_skill_session_coverage"] is not None):
            return _unmeasured_planning_evidence()
        return {
            **_unmeasured_planning_evidence(),
            "planning_sessions": numerator,
            "eligible_sessions": denominator,
            "unmeasured_sessions": unmeasured,
        }

    share = numerator / denominator
    coverage = denominator / (denominator + unmeasured)
    raw_share = behavior["planning_skill_session_share"]
    raw_coverage = behavior["planning_skill_session_coverage"]
    if (isinstance(raw_share, bool) or not isinstance(raw_share, (int, float))
            or not math.isfinite(raw_share)
            or not math.isclose(raw_share, share, rel_tol=1e-6, abs_tol=1e-6)
            or isinstance(raw_coverage, bool)
            or not isinstance(raw_coverage, (int, float))
            or not math.isfinite(raw_coverage)
            or not math.isclose(
                raw_coverage, coverage, rel_tol=1e-6, abs_tol=1e-6)):
        return _unmeasured_planning_evidence()
    return {
        "planning_sessions": numerator,
        "eligible_sessions": denominator,
        "unmeasured_sessions": unmeasured,
        "state": expected_state,
        "share": share,
        "coverage": coverage,
        "legacy": False,
        "base_weight": _PLANNING_SKILL_BASE_WEIGHT,
        "effective_weight": _PLANNING_SKILL_BASE_WEIGHT * coverage,
    }


def _planning_skill_share(behavior, legacy_sessions):
    """Compatibility test hook; production scoring uses the full evidence helper."""
    evidence = _planning_skill_evidence(behavior, legacy_sessions)
    return evidence["share"], evidence["state"], evidence["legacy"]
