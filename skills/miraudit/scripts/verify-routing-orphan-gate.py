"""PHASE 2 `dropped-term`: does one unreferenced child transcript discard the whole routing term?

    python3 verify-routing-orphan-gate.py --checkout <copy> --since ... --until ... --stats ...

Feeds the real `Accumulator` synthetic events in memory. Nothing is read from the corpus and
nothing is written to disk, so this answers the question a real corpus cannot: whether the
routing term reaches `measured` at all when no fan-out and no background dispatch are present.

The corpus this was written against could not supply that control. It holds 98 events before
the first `Workflow` call and the first `async_launched` result, which is not enough to score.

CASE A IS THE CONTROL AND IT MUST COME OUT `measured`. Without it, an `unmeasured` in the
other cases proves nothing: it could just as well mean the fixture never built a valid pair.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, require  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])

(Accumulator,) = require(
    [("gnomon.cli.accumulator", "Accumulator")], "This checkout has no Accumulator.")

TS = "2026-07-15T12:00:00.000Z"


def assistant(sid, uuid, blocks, model="claude-opus-5", sidechain=False, agent_id=None):
    ev = {"type": "assistant", "sessionId": sid, "timestamp": TS, "uuid": uuid,
          "isSidechain": sidechain, "cwd": "/repo",
          "message": {"role": "assistant", "model": model, "content": blocks}}
    if agent_id:
        ev["agentId"] = agent_id
    return ev


def dispatch(sid, tool_use_id, uuid, name="Agent"):
    return assistant(sid, uuid, [{"type": "tool_use", "id": tool_use_id,
                                  "name": name, "input": {"prompt": "go"}}])


def result(sid, tool_use_id, uuid, agent_id, status, child_model="claude-haiku-4-5"):
    return {"type": "user", "sessionId": sid, "timestamp": TS, "uuid": uuid,
            "isSidechain": False, "cwd": "/repo",
            "sourceToolAssistantUUID": "a1",
            "toolUseResult": {"agentId": agent_id, "status": status,
                              "resolvedModel": child_model,
                              "toolStats": {"editFileCount": 2}},
            "message": {"role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": tool_use_id,
                                     "content": "done"}]}}


def child_work(agent_id, sid, n=6, model="claude-haiku-4-5"):
    """A dispatched agent's own transcript: sidechain events carrying its agentId."""
    out = []
    for i in range(n):
        out.append(assistant(sid, f"c{agent_id}{i}",
                             [{"type": "tool_use", "id": f"t{agent_id}{i}",
                               "name": "Read", "input": {"file_path": "/repo/a.ts"}}],
                             model=model, sidechain=True, agent_id=agent_id))
    return out


def run(events):
    acc = Accumulator()
    acc.begin_file("claude", "/tmp/x.jsonl")
    for ev in events:
        acc.observe(ev, None, None)
    pairs, state = acc._routing_snapshot()
    return state, len(pairs)


BASE = ([dispatch("s1", "T1", "a1")]
        + child_work("X", "s1")
        + [result("s1", "T1", "r1", "X", "completed")])

CASES = [
    ("A  control: one Agent call, one child, completed", BASE, "measured"),
    ("B  + one unreferenced child (a Workflow-dispatched agent)",
     BASE + child_work("Y", "s1"), "unmeasured"),
    ("C  the same call, dispatched in background",
     [dispatch("s1", "T1", "a1")] + child_work("X", "s1")
     + [result("s1", "T1", "r1", "X", "async_launched")], "unmeasured"),
]

print(header(args, WINDOW))
print("=" * 78)
print("ROUTING ORPHAN GATE — one unreferenced child vs the whole term")
print("=" * 78)

ok = True
for label, events, expected in CASES:
    state, n = run(events)
    good = state == expected
    ok = ok and good
    print(f"  {label:<58}{state:<12}pairs={n:<4}"
          f"{'ok' if good else 'MISMATCH, expected ' + expected}")

print()
if not ok:
    print("  A case did not behave as written. Treat every conclusion here as unsafe: the")
    print("  fixture is describing something other than what its labels claim.")
else:
    print("  Case A reaches `measured`, so the fixture does build a scorable pair and an")
    print("  `unmeasured` elsewhere is a real result rather than an empty fixture.")
    print("  Case B differs from A by ONE sidechain transcript that no attempt references.")
    print("  That single transcript discards the routing term for the entire corpus, and")
    print("  `score_linked_routing` returns before examining the pair that case A scored.")
    print("  Case C shows background dispatch does the same through `lifecycle_known`.")

print("\n  NOT CHECKED: whether a real corpus with neither fan-out nor background dispatch")
print("  reaches `measured`. This is a synthetic fixture; it shows the gate's behaviour,")
print("  not how often the condition arises in anyone's actual transcripts.")

# Prose on stdout is not a channel a batch run reads. Exit non-zero so the return code
# stops agreeing with a broken fixture.
if not ok:
    raise SystemExit(1)
