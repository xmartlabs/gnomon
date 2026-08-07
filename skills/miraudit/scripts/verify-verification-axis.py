"""Finding: the Verification axis rewards testing LESS.

    python3 verify-verification-axis.py [path-to-the-gnomon-clone]

Defaults to the sibling clone (../gnomon). Two synthetic users with the SAME number of
code changes (10). A verifies all 10; B verifies 2. A does more non-test work.
The axis scores B above A.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus

from gnomon.cli.accumulator import Accumulator  # noqa: E402
from gnomon.scoring.aq import TEST_RUNS_PER_CALL_TARGET as TARGET  # noqa: E402

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
for label, changes, tested, other in [("A  tests 10/10", 10, 10, 200),
                                      ("B  tests  2/10", 10, 2, 10)]:
    st, tc, r = run(changes, tested, other)
    print(f"{label:<18}{100 * tested // changes:>10}%{st:>7}{tc:>12}{r:>8.3f}")

print("\nA verifies 100% of its changes and scores 0.198")
print("B verifies  20% of its changes and scores 0.714")
