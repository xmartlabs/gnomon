"""The compounding fix (contract 16:16:16) credits the filesystem PER CALL and
memory via MCP ONCE PER SESSION. Measures the asymmetry with the real Accumulator.

    python3 verify-compounding-symmetry.py <path-to-a-checkout-with-the-fix>

Needs a checkout that has the fix. That is enforced at runtime by an import guard, not by
the reader: if the symbol is missing the script exits and says so. Do not restate here which
branches or clones carry it — the fix has since landed on `main`, an earlier version of this
docstring said it had not, and a cold run nearly skipped this fixture on that basis.

Note that "credits the right calls" is not "counts them correctly": this measures symmetry
between backends, and the filesystem/MCP counters undercount independently of it.
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
    from gnomon.taxonomy import is_mcp_knowledge_write  # noqa: F401
except ImportError:
    sys.exit(f"{REPO} does not have the compounding fix (missing "
             "is_mcp_knowledge_write). Pass a checkout >= e7f85bc.")

# The events are synthetic, but the window comes from --days / --until and the timestamp is
# derived from it. An earlier version parsed those flags and then ignored them.
SINCE, UNTIL = WINDOW.start, WINDOW.end
TS = (SINCE + (UNTIL - SINCE) / 2).strftime("%Y-%m-%dT%H:%M:%S.000Z")
SID = "s1"


def ev(name, inp, i):
    return {"type": "assistant", "sessionId": SID, "timestamp": TS,
            "isSidechain": False, "cwd": "/repo", "uuid": f"u{i}",
            "message": {"role": "assistant", "model": "claude-opus-5",
                        "content": [{"type": "tool_use", "id": f"t{i}",
                                     "name": name, "input": inp}]}}


def run(events):
    a = Accumulator()
    a.begin_file("claude", "/U/.claude/projects/-p/s1.jsonl")
    for i, (name, inp) in enumerate(events):
        a.observe(ev(name, inp, i), SINCE, UNTIL)
    return a.compounding_counter


N = 10
# Each case carries the credit count it MUST produce. They were prose until now: the two
# rows labelled CONTROL were printed and never compared against anything, so a checkout
# where is_mcp_knowledge_write started crediting a read would have printed a wrong table
# and exited 0. A control nobody asserts on is decoration.
cases = [
    ("N writes to CLAUDE.md (distinct content)", N,
     [("Write", {"file_path": "/repo/CLAUDE.md", "content": f"regla {i}"})
      for i in range(N)]),
    ("N writes to distinct CLAUDE.md (BE/FE/root/...)", N,
     [("Write", {"file_path": f"/repo/{i}/CLAUDE.md", "content": "x"})
      for i in range(N)]),
    # THE ASYMMETRY. N distinct learnings collapse to one credit because persist_id falls
    # back to the f"{server}:{tool}" bucket when the call carries no id of its own.
    ("N mem0 add_memory (DISTINCT learnings)", 1,
     [("mcp__mem0__add_memory",
       {"messages": f"distinct learning number {i}", "user_id": "u1"})
      for i in range(N)]),
    ("N mem0 update_memory (distinct memory_id)", N,
     [("mcp__mem0__update_memory", {"memory_id": f"m{i}", "text": "x"})
      for i in range(N)]),
    ("N mem0 update_memory (SAME memory_id)", 1,
     [("mcp__mem0__update_memory", {"memory_id": "m0", "text": f"v{i}"})
      for i in range(N)]),
    # The two controls, and they are the reason the numbers above mean anything: if reads
    # and deletes also scored, "10 vs 1" would say nothing about knowledge writes.
    ("CONTROL: N mem0 search_memories (read)", 0,
     [("mcp__mem0__search_memories", {"query": f"q{i}"}) for i in range(N)]),
    ("CONTROL: N mem0 delete_memory", 0,
     [("mcp__mem0__delete_memory", {"memory_id": f"m{i}"}) for i in range(N)]),
]

print(header(args, WINDOW))
print(f"N = {N} calls per case, all in ONE session, timestamped inside that window\n")
print(f"{'case':<52}{'credits':>9}{'want':>7}  ")
print("-" * 70)
FAILED = []
for label, want, events in cases:
    got = run(events)
    if got != want:
        FAILED.append(f"{label}: {got} credits, expected {want}")
    print(f"{label:<52}{got:>9}{want:>7}  {'[ok]' if got == want else '[??]'}")

print("\nSame number of persistence acts, different backend:")
print(f"  {N} file writes          -> {run(cases[0][2])} credits")
print(f"  {N} distinct add_memory  -> {run(cases[2][2])} credits")

if FAILED:
    print(f"\n  {len(FAILED)} case(s) did not behave as written; the first is {FAILED[0]!r}.")
    print("  Either the checkout changed how it credits knowledge writes, or this table is "
          "stale.\n  Read the accumulator before editing the numbers here.")
    raise SystemExit(1)
# miraudit-covers: Compounding
