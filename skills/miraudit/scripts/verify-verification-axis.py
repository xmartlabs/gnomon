"""Finding: the Verification axis rewards testing LESS.

    python3 verify-verification-axis.py [path-to-the-gnomon-clone]

Defaults to the sibling clone (../gnomon). Two synthetic users with the SAME number of
code changes (10). A verifies all 10; B verifies 2. A does more non-test work.
The axis scores B above A.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, require  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus

from gnomon.cli.accumulator import Accumulator  # noqa: E402

(TARGET,) = require(
    [("gnomon.scoring.aq", "TEST_RUNS_PER_CALL_TARGET")],
    "This fixture demonstrates the DENSITY term. A checkout without it has replaced that "
    "term, and the fixture has nothing to say about it -- refusing to run beats printing a "
    "conclusion about an axis that no longer works this way.")

TS = "2026-07-15T12:00:00.000Z"


def ev(name, inp, sid, i):
    return {"type": "assistant", "sessionId": sid, "timestamp": TS,
            "isSidechain": False, "cwd": "/repo", "uuid": f"u{sid}{i}",
            "message": {"role": "assistant", "model": "claude-opus-5",
                        "content": [{"type": "tool_use", "id": f"t{sid}{i}",
                                     "name": name, "input": inp}]}}


def run(changes, tested, other_work):
    """`changes` code changes, one per session; the first `tested` ones carry a test."""
    a = Accumulator()
    a.begin_file("claude", "/tmp/x.jsonl")
    k = 0
    for s in range(changes):
        sid = f"s{s}"
        a.observe(ev("Edit", {"file_path": "/repo/src/a.ts",
                              "old_string": "a", "new_string": "b"}, sid, k), None, None)
        k += 1
        if s < tested:
            a.observe(ev("Bash", {"command": "npx vitest run"}, sid, k), None, None)
            k += 1
        for _ in range(other_work):
            a.observe(ev("Bash", {"command": "grep -r foo ."}, sid, k), None, None)
            k += 1
    return a.shell_test_runs, a.tool_use_total, min(
        1.0, (a.shell_test_runs / a.tool_use_total) / TARGET)


print(f"repo: {REPO}\n")
print(f"{'user':<18}{'coverage':>11}{'tests':>7}{'tool_calls':>12}{'rate':>8}")
print("-" * 56)
rates = {}
for label, changes, tested, other in [("A  tests 10/10", 10, 10, 200),
                                      ("B  tests  2/10", 10, 2, 10)]:
    st, tc, r = run(changes, tested, other)
    rates[label[0]] = (100 * tested // changes, r)
    print(f"{label:<18}{100 * tested // changes:>10}%{st:>7}{tc:>12}{r:>8.3f}")

# Printed from the computed rates, and the verdict is conditional on them. An earlier version
# asserted "scores 0.198" / "scores 0.714" as literals, so a checkout that fixed the axis would
# still have printed the finding as though it held.
print()
for who in ("A", "B"):
    cov, r = rates[who]
    print(f"{who} verifies {cov:>3}% of its changes and scores {r:.3f}")

if rates["B"][1] > rates["A"][1]:
    print("\nThe axis scores B above A: verifying MORE lowers the score.")
else:
    print("\nThis checkout does NOT reproduce the inversion. The finding does not hold here.")
