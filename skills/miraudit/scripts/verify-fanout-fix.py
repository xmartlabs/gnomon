"""Injection-based falsification of the Workflow fan-out fix (contract 15:15:15).

    python3 verify-fanout-fix.py <path-to-a-checkout-with-the-fix>

Feeds the REAL Accumulator with synthetic transcripts. Every case carries a control:
a case that MUST come out non-zero, so that a 0 means something.

Needs a checkout that has the fix. That is enforced at runtime by an import guard, not by
the reader: if the symbol is missing the script exits and says so. Do not restate here which
branches or clones carry it — the fix has since landed on `main`, an earlier version of this
docstring said it had not, and a cold run nearly skipped this fixture on that basis.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

# needs_corpus=False: this check builds its events in memory and never opens a
# transcript. It still ACCEPTS --corpus so run-checks.py's shared argv works, it
# just stops refusing to run over an input it does not read -- which is what kept
# it out of any offline tier and off a machine with no ~/.claude at all.
args, WINDOW = parse(__doc__.strip().splitlines()[0], needs_corpus=False)
REPO = args.checkout

from gnomon.cli.accumulator import Accumulator  # noqa: E402

try:
    from gnomon.taxonomy import parse_workflow_agent_dispatch  # noqa: F401
except ImportError:
    sys.exit(f"{REPO} does not have the fan-out fix (missing "
             "parse_workflow_agent_dispatch). Pass a checkout >= 90a2d85.")

# The events are synthetic, but the window fed to the Accumulator is the one from --days /
# --until, and the in/out timestamps are derived from it. An earlier version parsed those
# flags and then ignored them, using its own fixed SINCE/UNTIL: the script announced it
# honoured the report's window and did not.
SINCE, UNTIL = WINDOW.start, WINDOW.end
IN = (SINCE + (UNTIL - SINCE) / 2).strftime("%Y-%m-%dT%H:%M:%S.000Z")
OUT = (SINCE - datetime.timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

# Synthetic identifiers. This fixture never reads the real corpus, so nothing here should
# resemble anyone's actual session id or path.
PARENT = "00000000-0000-4000-8000-000000000001"
FAKE_ROOT = "/synthetic/projects/-proj"


def wf_path(parent, run, agent):
    return f"{FAKE_ROOT}/{parent}/subagents/workflows/wf_{run}/agent-{agent}.jsonl"


def sub_path(parent, agent):
    return f"{FAKE_ROOT}/{parent}/subagents/agent-{agent}.jsonl"


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


FAILED = []


def show(label, a, expect_parent, expect_total=None):
    got = a.agents_per_session.get(expect_parent, 0)
    total = sum(a.agents_per_session.values())
    good = expect_total is None or total == expect_total
    if not good:
        FAILED.append(label)
    print(f"  [{'ok' if good else '??'}] {label:<52} parent={got:<3} total={total:<3} "
          f"keys={sorted(a.agents_per_session)}")
    return got, total


print(header(args, WINDOW))

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
a = feed([(f"{FAKE_ROOT}/{PARENT}.jsonl", [ev("Agent", PARENT, 0)])])
show("CONTROL: one top-level Agent call", a, PARENT, 1)
a = feed([(f"{FAKE_ROOT}/{PARENT}.jsonl", [ev("Workflow", PARENT, 0)])])
show("CONTROL: top-level Workflow call (no longer credits)", a, PARENT, 0)

print("\n7. delegation preserved: Workflow-only still counts as delegating")
a = feed([(f"{FAKE_ROOT}/{PARENT}.jsonl", [ev("Workflow", PARENT, 0)]),
          (wf_path(PARENT, "abc", "a1"), [ev("Bash", PARENT, 1, agent_id="a1")])])
show("Workflow + its dispatched transcript", a, PARENT, 1)

# Exit non-zero when a case misbehaves. Printing "[??]" and returning 0 means anyone running
# these in a batch reads the exit codes and concludes everything passed.
if FAILED:
    print(f"\n  {len(FAILED)} case(s) did not behave as written; the first is {FAILED[0]!r}.")
    print("  Every conclusion above is unsafe: the fixture is describing something other")
    print("  than what its labels claim.")
    raise SystemExit(1)
# miraudit-covers: Orchestration
