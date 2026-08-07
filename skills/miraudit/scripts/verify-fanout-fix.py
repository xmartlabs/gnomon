"""Injection-based falsification of the Workflow fan-out fix (contract 15:15:15).

    python3 verify-fanout-fix.py <path-to-a-checkout-with-the-fix>

Feeds the REAL Accumulator with synthetic transcripts. Every case carries a control:
a case that MUST come out non-zero, so that a 0 means something.

REQUIRES a checkout at `90a2d85` or later (branch fix/workflow-fanout-undercredit).
The `../gnomon` clone tracks `main`, which does NOT have the fix.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus

from gnomon.cli.accumulator import Accumulator  # noqa: E402

try:
    from gnomon.taxonomy import parse_workflow_agent_dispatch  # noqa: F401
except ImportError:
    sys.exit(f"{REPO} does not have the fan-out fix (missing "
             "parse_workflow_agent_dispatch). Pass a checkout >= 90a2d85.")

IN = "2026-07-15T12:00:00.000Z"
OUT = "2025-01-15T12:00:00.000Z"
SINCE = datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc)
UNTIL = datetime.datetime(2026, 8, 7, tzinfo=datetime.timezone.utc)

PARENT = "46eb9eed-1238-4825-9f6d-c2bbd54ffe3a"
ROOT = "/Users/x/.claude/projects/-proj"


def wf_path(parent, run, agent):
    return f"{ROOT}/{parent}/subagents/workflows/wf_{run}/agent-{agent}.jsonl"


def sub_path(parent, agent):
    return f"{ROOT}/{parent}/subagents/agent-{agent}.jsonl"


def ev(name, sid, i, ts=IN, agent_id=None):
    e = {"type": "assistant", "sessionId": sid, "timestamp": ts,
         "isSidechain": False, "cwd": "/repo", "uuid": f"u{sid}{i}",
         "message": {"role": "assistant", "model": "claude-opus-5",
                     "content": [{"type": "tool_use", "id": f"t{sid}{i}",
                                  "name": name, "input": {"command": "ls"}}]}}
    if agent_id is not None:
        e["agentId"] = agent_id
    return e


def feed(files):
    """files = [(path, [event, ...]), ...] -> Accumulator."""
    a = Accumulator()
    for path, events in files:
        a.begin_file("claude", path)
        for e in events:
            a.observe(e, SINCE, UNTIL)
    return a


def show(label, a, expect_parent, expect_total=None):
    got = a.agents_per_session.get(expect_parent, 0)
    total = sum(a.agents_per_session.values())
    mark = "ok" if (expect_total is None or total == expect_total) else "??"
    print(f"  [{mark}] {label:<52} parent={got:<3} total={total:<3} "
          f"keys={sorted(a.agents_per_session)}")
    return got, total


print(f"repo: {REPO}\n")

print("1. attribution: credit goes to the parent SESSION, not the project")
a = feed([(wf_path(PARENT, "abc", "a1"),
           [ev("Bash", PARENT, 0, agent_id="a1")])])
show("1 workflow transcript", a, PARENT, 1)

print("\n2. real fan-out: N distinct transcripts = N dispatches")
a = feed([(wf_path(PARENT, "abc", f"a{i}"),
           [ev("Bash", PARENT, i, agent_id=f"a{i}") for _ in range(3)])
          for i in range(5)])
show("5 transcripts x 3 events each", a, PARENT, 5)

print("\n3. dedup: the same transcript read twice counts once")
a = feed([(wf_path(PARENT, "abc", "a1"), [ev("Bash", PARENT, 0, agent_id="a1")]),
          (wf_path(PARENT, "abc", "a1"), [ev("Bash", PARENT, 1, agent_id="a1")])])
show("same (parent, agentId) x2", a, PARENT, 1)

print("\n4. agentId fallback: without the field, uses the id from the filename")
a = feed([(wf_path(PARENT, "abc", "a1"), [ev("Bash", PARENT, 0)]),
          (wf_path(PARENT, "abc", "a1"), [ev("Bash", PARENT, 1, agent_id="a1")])])
show("one without agentId + one with the same id", a, PARENT, 1)

print("\n5. window: a whole run outside the window gets no credit")
a = feed([(wf_path(PARENT, "abc", "a1"),
           [ev("Bash", PARENT, 0, ts=OUT, agent_id="a1")])])
show("transcript outside window", a, PARENT, 0)
a = feed([(wf_path(PARENT, "abc", "a1"),
           [ev("Bash", PARENT, 0, ts=OUT, agent_id="a1"),
            ev("Bash", PARENT, 1, ts=IN, agent_id="a1")])])
show("CONTROL: same run with one event inside window", a, PARENT, 1)

print("\n6. no double counting with Agent/Task")
a = feed([(sub_path(PARENT, "a1"), [ev("Bash", PARENT, 0, agent_id="a1")])])
show("Agent sidechain (no /workflows/wf_*/)", a, PARENT, 0)
a = feed([(f"{ROOT}/{PARENT}.jsonl", [ev("Agent", PARENT, 0)])])
show("CONTROL: one top-level Agent call", a, PARENT, 1)
a = feed([(f"{ROOT}/{PARENT}.jsonl", [ev("Workflow", PARENT, 0)])])
show("CONTROL: top-level Workflow call (no longer credits)", a, PARENT, 0)

print("\n7. delegation preserved: Workflow-only still counts as delegating")
a = feed([(f"{ROOT}/{PARENT}.jsonl", [ev("Workflow", PARENT, 0)]),
          (wf_path(PARENT, "abc", "a1"), [ev("Bash", PARENT, 1, agent_id="a1")])])
show("Workflow + its dispatched transcript", a, PARENT, 1)
