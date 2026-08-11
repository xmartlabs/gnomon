"""PHASE 2 `saturated`: how much of the score sits on axes that stopped discriminating?

An axis pinned at its ceiling still contributes its full weight, but it has stopped being a
measurement: the person could do substantially less and the number would not move. That is
invisible in the report, which shows a high axis exactly as it shows a hard-won one.

The check is a counterfactual, not an opinion. Cut every saturated signal down to EXACTLY
its own target or ceiling — the least the tool will still award full marks for — re-score
with the tool's own `compute_aq`, and see what the total does. If it does not move, every
point of headroom above those thresholds bought nothing.

Thresholds are IMPORTED where they are named constants. Where the threshold is an inline
literal there is nothing to import, and restating it would make this check disagree with the
tool the moment anyone recalibrates — the exact defect this script reports. Those saturation
points are DISCOVERED by bisection instead: lower the signal until the axis scores move, with
the tool's own scoring as the oracle. The run validates that method before trusting it, by
bisecting a threshold it could have imported and checking the two agree.

    python3 saturation-counterfactual.py --checkout <copy> --since ... --until ... --stats ...

Needs `--stats` from an anchored run: it re-scores that payload rather than the corpus.

CONTROLS ARE THE POINT. A counterfactual that does not move the number is indistinguishable
from a broken one, so this also scores arms at a fraction of target. Those MUST move. If they
do not, the mutation is not landing and the headline zero means nothing.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats, require, find_all  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0],
                     {"--emit": {"metavar": "PATH", "default": None,
                                 "help": "also write the result as JSON, for a caller that "
                                         "needs the numbers rather than the reading"}})

# Every threshold is imported. Restating one here would make this check disagree with the
# tool it is auditing the moment anyone recalibrates, which is the mistake it exists to find.
(compute_aq, RATE_TARGETS, CEILINGS) = require(
    [("gnomon.scoring.aq", "compute_aq")], "This checkout has no compute_aq.")[0], {}, {}

import gnomon.scoring.aq as AQ  # noqa: E402

# stats key -> threshold NAME in aq.py. The names are imported; only the pairing lives here,
# and the pairing is verified below rather than trusted: setting a signal to exactly its
# threshold must put that term at full marks.
RATE_SIGNALS = {
    "skills_total": "SKILLS_TOTAL_PER_CALL_TARGET",
    "compounding_writes": "COMPOUNDING_WRITES_PER_CALL_TARGET",
}
COUNT_SIGNALS = {
    "subagent_types_distinct": "SUBAGENT_TYPES_DISTINCT_CEILING",
    "skills_distinct": "SKILLS_DISTINCT_CEILING",
    "mcp_servers_distinct": "MCP_SERVERS_DISTINCT_CEILING",
    "clis_distinct": "CLIS_DISTINCT_CEILING",
    "fanout_median": "FANOUT_CEILING",
}
# numerator -> (denominator, threshold NAME). Terms scored as a share of a population
# rather than per tool call. Cutting one means cutting its numerator to the share the
# threshold still pays full marks for, so the denominator has to be read per arm.
SHARE_SIGNALS = {
    "delegated_orchestratable_sessions": ("orchestratable_sessions",
                                          "ORCHESTRATION_FREQUENCY_TARGET"),
    "evidence_eligible_sessions": ("eligible_change_sessions",
                                   "CONTEXT_INTELLIGENCE_TARGET"),
    "planned_eligible_sessions": ("eligible_change_sessions", "PLANNING_TARGET"),
    "planning_skill_sessions": ("planning_skill_eligible_sessions",
                                "PLANNING_PRACTICE_TARGET"),
}
# Terms whose threshold is an inline literal in aq.py rather than a named constant, so there
# is nothing to import. Restating the literal here is out of the question: that is exactly
# the mistake this script exists to find. Instead the saturation point is DISCOVERED by
# bisection against the tool's own scoring function -- lower the signal until the axis
# scores move. Nothing is restated, and the discovered point tracks any recalibration for
# free. `payload key -> (axis, the derived signal it drives)`.
BISECT_SIGNALS = {
    "cli_calls": ("Token economy", "cli_share"),
    "planning_ratio_explore_to_doing": ("Grounding", "planning_ratio"),
    "test_covered_change_sessions": ("Verification", "test_coverage"),
}
# Still uncuttable, for a different reason: their input is a LIST, so there is no scalar to
# bisect. Printed with the coverage floor rather than left silent, because an axis missing
# from the arm makes the result look better covered than it is.
NOT_CUTTABLE = [
    ("offload_share", "Model mix", "derived from a per-model turn-count list"),
    ("distinct_models", "Model mix", "sat(len(models), 3): cutting means truncating a list"),
    ("review_skills", "Verification", "derived from the skills list by _review_skill_uses"),
]

missing = [n for n in list(RATE_SIGNALS.values()) + list(COUNT_SIGNALS.values())
           + [t for _, t in SHARE_SIGNALS.values()] if not hasattr(AQ, n)]
if missing:
    sys.exit(f"error: this checkout has no {', '.join(missing)}. The thresholds were renamed "
             "or removed; re-pair them before trusting this check.")

stats = load_stats(args.stats)
if not stats:
    sys.exit("error: --stats is required. This check re-scores an anchored run's payload.")

base = compute_aq(stats)
base_aq = base.get("aq_0_100")


def set_everywhere(payload, key, value):
    """Set every occurrence of `key`. Returns how many were written.

    Signals are repeated across per-source and per-month blocks, and scoring reads more than
    one of them. Setting only the first would produce an arm that looks mutated and is not.
    """
    written = 0
    if isinstance(payload, dict):
        for name in list(payload):
            if name == key and isinstance(payload[name], (int, float)):
                payload[name] = value
                written += 1
            else:
                written += set_everywhere(payload[name], key, value)
    elif isinstance(payload, list):
        for item in payload:
            written += set_everywhere(item, key, value)
    return written


def calls_in(payload):
    """The tool-call denominator the rate terms are scored against."""
    seen = {v for p, v in find_all(payload, "tool_calls")
            if "/signals/" in p and isinstance(v, int)}
    return seen.pop() if len(seen) == 1 else None


def fingerprint(scored):
    """Every axis score, rounded. The bisection's objective.

    NOT the AQ: that is an integer, so a term can lose a third of its value without the
    headline moving, and a bisection against it would report a saturation point far below
    the real one. The axis vector moves as soon as any term does.
    """
    return tuple(round(float(a.get("score") or 0), 6)
                 for p in scored.get("pillars") or []
                 for a in p.get("axes") or [])


BASE_FP = fingerprint(base)


def score_at(key, value):
    mutated = copy.deepcopy(stats)
    if not set_everywhere(mutated, key, value):
        return None
    return fingerprint(compute_aq(mutated))


def discover_saturation(key, current):
    """The lowest value of `key` that still scores exactly what the real payload scores.

    Bisection, not arithmetic: the threshold is never restated here, it is found by asking
    the tool's own scoring function where the axis starts to move. Assumes the term is
    monotonic in the signal, which every sat()/rate() term is, and checks the assumption
    before trusting the search -- if setting the signal to zero changes nothing, the signal
    does not drive any scored term and there is nothing to discover.
    """
    if score_at(key, 0) == BASE_FP:
        return None
    lo, hi = 0.0, float(current)          # fp(lo) != BASE_FP, fp(hi) == BASE_FP
    for _ in range(48):
        mid = (lo + hi) / 2
        if score_at(key, mid) == BASE_FP:
            hi = mid
        else:
            lo = mid
    return hi


def arm(fraction, absent=None):
    """Score a copy with every saturated signal set to `fraction` of its threshold.

    `absent` collects signals this script looked for and did not find. A name that no longer
    matches the payload would otherwise be skipped in silence, quietly shrinking the
    counterfactual and making the result look stronger than its coverage.
    """
    mutated = copy.deepcopy(stats)
    calls = calls_in(mutated)
    if not calls:
        sys.exit("error: could not read the tool-call denominator from stats.json.")
    changes = []
    pairs = (list(RATE_SIGNALS.items()) + list(COUNT_SIGNALS.items())
             + [(k, t) for k, (_, t) in SHARE_SIGNALS.items()]
             + [(k, None) for k in BISECT_SIGNALS])
    for key, name in pairs:
        if name is None:
            # Discovered by bisection, not imported. `DISCOVERED` is filled in once, before
            # any arm runs, so every arm cuts to the same point.
            want = DISCOVERED.get(key)
            if want is None:
                if absent is not None:
                    absent.append(f"{key} (no scored effect)")
                continue
            want = want * fraction
            current = next((v for _, v in find_all(mutated, key)
                            if isinstance(v, (int, float))), None)
            if current is None or current <= want:
                continue
            if set_everywhere(mutated, key, want):
                changes.append((key, current, round(want, 1)))
            continue
        threshold = getattr(AQ, name)
        if key in RATE_SIGNALS:
            want = threshold * calls * fraction
        elif key in COUNT_SIGNALS:
            want = threshold * fraction
        else:
            # A share's ceiling is threshold * its own population, not a fixed count. Read
            # the denominator from the payload: hardcoding it would silently misscale the
            # cut on any other corpus, which is the whole point of this arm.
            denom_key = SHARE_SIGNALS[key][0]
            denom = next((v for _, v in find_all(mutated, denom_key)
                          if isinstance(v, (int, float)) and v), None)
            if denom is None:
                if absent is not None:
                    absent.append(f"{key} (no {denom_key})")
                continue
            want = threshold * denom * fraction
        current = next((v for _, v in find_all(mutated, key) if isinstance(v, (int, float))),
                       None)
        if current is None:
            if absent is not None:
                absent.append(key)
            continue
        if current <= want:
            continue                      # not saturated: leave it alone
        if set_everywhere(mutated, key, want):
            changes.append((key, current, round(want, 1)))
    return compute_aq(mutated).get("aq_0_100"), changes


print(header(args, WINDOW))
print("=" * 78)
print("SATURATION COUNTERFACTUAL")
print("=" * 78)
print(f"  baseline AQ {base_aq}  ({base.get('tier')}, contract {base.get('score_contract_id')})")

# ---- discover the thresholds that cannot be imported, and validate the method first ----
_calls = calls_in(stats)
print("\n  METHOD CHECK — bisection against a threshold that CAN be imported. If the two")
print("  columns disagree, the discovered points below are not trustworthy either:")
_method_ok = True
for _key, _name in RATE_SIGNALS.items():
    _known = getattr(AQ, _name) * _calls
    _cur = next((v for _, v in find_all(stats, _key) if isinstance(v, (int, float))), None)
    if _cur is None or _cur <= _known:
        print(f"    {_key:<28}not saturated, nothing to discover")
        continue
    _found = discover_saturation(_key, _cur)
    _agree = _found is not None and abs(_found - _known) <= max(1.0, _known * 0.02)
    _method_ok = _method_ok and _agree
    print(f"    {_key:<28}imported {_known:>10.1f}   discovered {_found:>10.1f}"
          f"   {'agree' if _agree else 'DISAGREE'}")

DISCOVERED = {}
for _key in BISECT_SIGNALS:
    _cur = next((v for _, v in find_all(stats, _key) if isinstance(v, (int, float))), None)
    DISCOVERED[_key] = discover_saturation(_key, _cur) if _cur is not None else None

print("\n  DISCOVERED saturation points (no importable threshold; found by bisection):")
for _key, (_axis, _derived) in BISECT_SIGNALS.items():
    _cur = next((v for _, v in find_all(stats, _key) if isinstance(v, (int, float))), None)
    _pt = DISCOVERED.get(_key)
    if _cur is None:
        print(f"    {_key:<32}{_axis:<18}absent from this payload")
    elif _pt is None:
        print(f"    {_key:<32}{_axis:<18}no scored effect, not cut")
    else:
        print(f"    {_key:<32}{_axis:<18}you did {_cur:<10.1f}same score at {_pt:.1f}"
              f"   (drives {_derived})")

absent = []
at_target, changed = arm(1.0, absent)
print(f"\n  every saturated signal cut to EXACTLY its threshold -> AQ {at_target}"
      f"   (delta {at_target - base_aq:+d})")
# Nothing is deleted anywhere: every arm scores a deepcopy of the payload and discards it.
# The columns are read "you did X; Y would have scored the same", so the third column is
# work the score cannot see -- not work destroyed.
print("\n  Real work the score does not see. Nothing is modified on disk: each arm")
print("  re-scores a throwaway copy of the payload.")
def num(v):
    """Counts read as counts, ratios keep their decimals, neither goes scientific.

    `.0f` printed a headroom of 0.13 as "0", which reads as "not saturated" -- the opposite
    of what the row says. `.4g` fixed that and turned 38558 into 3.856e+04.
    """
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.4g}"


print(f"    {'signal':<34}{'you did':>12}{'same score at':>15}{'unseen':>12}")
for key, was, now in changed:
    print(f"    {key:<34}{num(was):>12}{num(now):>15}{num(was - now):>12}")

print("\n  CONTROLS — these must move, or the mutation is not landing:")
ok = True
for fraction in (0.50, 0.25):
    score, _ = arm(fraction)
    moved = score != base_aq
    ok = ok and moved
    print(f"    at {int(fraction * 100):>3}% of threshold -> AQ {score:<4}"
          f" {'ok, moved' if moved else 'DID NOT MOVE'}")

print()
if not ok:
    print("  The controls did not move. Treat the headline as a BROKEN FIXTURE, not a")
    print("  finding: nothing here shows the mutation reached the scorer.")
elif at_target == base_aq:
    print("  Controls move, the at-threshold arm does not. Every point of headroom above")
    print("  those thresholds bought nothing: the axes are describing a ceiling, not the")
    print("  person. Report as `saturated`, direction `underestimates`, magnitude = the")
    print("  weight sitting on the pinned axes.")
else:
    print("  The at-threshold arm moved. The headroom is doing work on this corpus, and")
    print("  there is no saturation finding to report.")

if not _method_ok:
    print("\n  THE METHOD CHECK FAILED. Bisection did not recover a threshold the script")
    print("  could read directly, so treat every discovered point above as unverified.")

print("\n  COVERAGE — this is a floor, not the whole score:")
examined = (len(RATE_SIGNALS) + len(COUNT_SIGNALS) + len(SHARE_SIGNALS)
            + len(BISECT_SIGNALS))
print(f"    signals cut          : {len(changed)}")
print(f"    examined, not saturated: {examined - len(changed) - len(absent)}")
if absent:
    print(f"    LOOKED FOR, NOT FOUND: {', '.join(absent)}")
    print("      Either renamed upstream or absent from this payload. Each one is a signal")
    print("      this arm did NOT cut, so the real plateau is at least as wide as shown.")
print("\n    SATURATED BUT NOT CUT — no importable threshold to cut to. Restating the")
print("    literal would drift from the tool the moment anyone recalibrates:")
for sig, axis, why in NOT_CUTTABLE:
    print(f"      {sig:<32}{axis:<22}{why}")
print("    A wider arm can only make the at-threshold delta more damning, never less.")

print("\n  NOT CHECKED: whether the thresholds are calibrated against a real population.")
print("  A pinned axis is only a defect if the graded population has mass above it, and")
print("  one corpus cannot tell 'the axis saturates' from 'this person clears every bar'.")

# Two ways this run's headline is not trustworthy, and both were prose-only until now: a
# control that did not move, and a bisection that could not recover a threshold it could
# have read. Anyone running the checks in a batch reads exit codes, not paragraphs.
# A machine-readable copy of what the prose above says, for callers that need the result
# rather than the reading. Parsing the printed tables would be the `truncated-evidence`
# mistake with extra steps: a display exists to be read by people and reshapes data on the
# way. Written before the exit below so a broken arm still leaves its evidence behind.
if args.emit:
    import json
    with open(os.path.expanduser(args.emit), "w") as _fh:
        json.dump({
            "base_aq": base_aq,
            "at_threshold_aq": at_target,
            "delta": at_target - base_aq,
            "signals_cut": [{"signal": k, "you_did": w, "same_score_at": n}
                            for k, w, n in changed],
            "examined": examined,
            "looked_for_not_found": absent,
            "not_cuttable": [s for s, _a, _w in NOT_CUTTABLE],
            "controls": {f"{int(f * 100)}pct": arm(f)[0] for f in (0.50, 0.25)},
            "controls_moved": ok,
            "method_check_passed": _method_ok,
        }, _fh, indent=2)
    print(f"\n  wrote {args.emit}")

if not ok or not _method_ok:
    raise SystemExit(1)
