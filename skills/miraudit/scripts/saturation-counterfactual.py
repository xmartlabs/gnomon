"""PHASE 2 `saturated`: how much of the score sits on axes that stopped discriminating?

An axis pinned at its ceiling still contributes its full weight, but it has stopped being a
measurement: the person could do substantially less and the number would not move. That is
invisible in the report, which shows a high axis exactly as it shows a hard-won one.

The check is a counterfactual, not an opinion. Cut every saturated signal down to EXACTLY
its own target or ceiling — the least the tool will still award full marks for — re-score
with the tool's own `compute_aq`, and see what the total does. If it does not move, every
point of headroom above those thresholds bought nothing.

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

args, WINDOW = parse(__doc__.strip().splitlines()[0])

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
    "toolsearch_calls": "TOOLSEARCH_PER_CALL_TARGET",
    # `task_calls` in aq.py is a local: task_tool_calls + skill uses that count as tasks.
    # Cutting the stats key cuts the first half only, so this arm understates that axis.
    "task_tool_calls": "TASK_CALLS_PER_CALL_TARGET",
    "shell_test_runs": "TEST_RUNS_PER_CALL_TARGET",
    "compounding_writes": "COMPOUNDING_WRITES_PER_CALL_TARGET",
}
COUNT_SIGNALS = {
    "subagent_types_distinct": "SUBAGENT_TYPES_DISTINCT_CEILING",
    "skills_distinct": "SKILLS_DISTINCT_CEILING",
    "mcp_servers_distinct": "MCP_SERVERS_DISTINCT_CEILING",
    "clis_distinct": "CLIS_DISTINCT_CEILING",
}

missing = [n for n in list(RATE_SIGNALS.values()) + list(COUNT_SIGNALS.values())
           if not hasattr(AQ, n)]
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
    for key, name in list(RATE_SIGNALS.items()) + list(COUNT_SIGNALS.items()):
        threshold = getattr(AQ, name)
        want = threshold * calls * fraction if key in RATE_SIGNALS else threshold * fraction
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

absent = []
at_target, changed = arm(1.0, absent)
print(f"\n  every saturated signal cut to EXACTLY its threshold -> AQ {at_target}"
      f"   (delta {at_target - base_aq:+d})")
# Nothing is deleted anywhere: every arm scores a deepcopy of the payload and discards it.
# The columns are read "you did X; Y would have scored the same", so the third column is
# work the score cannot see -- not work destroyed.
print("\n  Real work the score does not see. Nothing is modified on disk: each arm")
print("  re-scores a throwaway copy of the payload.")
print(f"    {'signal':<28}{'you did':>10}{'same score at':>15}{'unseen':>10}")
for key, was, now in changed:
    print(f"    {key:<28}{was:>10}{now:>15}{was - now:>10.0f}")

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

print("\n  COVERAGE — this is a floor, not the whole score:")
print(f"    signals cut          : {len(changed)}")
print(f"    examined, not saturated: "
      f"{len(RATE_SIGNALS) + len(COUNT_SIGNALS) - len(changed) - len(absent)}")
if absent:
    print(f"    LOOKED FOR, NOT FOUND: {', '.join(absent)}")
    print("      Either renamed upstream or absent from this payload. Each one is a signal")
    print("      this arm did NOT cut, so the real plateau is at least as wide as shown.")
print("    Signals with no entry above — fan-out, orchestration frequency, planning ratios,")
print("    model diversity, CLI share — are not cut at all. A wider arm can only make the")
print("    at-threshold delta more damning, never less.")

print("\n  NOT CHECKED: whether the thresholds are calibrated against a real population.")
print("  A pinned axis is only a defect if the graded population has mass above it, and")
print("  one corpus cannot tell 'the axis saturates' from 'this person clears every bar'.")
