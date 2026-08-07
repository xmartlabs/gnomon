"""The compounding fix (contract 16:16:16) credits the filesystem PER CALL and
memory via MCP ONCE PER SESSION. Measures the asymmetry with the real Accumulator.

    python3 verify-compounding-symmetry.py <path-to-a-checkout-with-the-fix>

REQUIRES a checkout at `e7f85bc` or later (branch fix/workflow-fanout-undercredit).
The `../gnomon` clone tracks `main`, which does NOT have the fix.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, CUT = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus

from gnomon.cli.accumulator import Accumulator  # noqa: E402

try:
    from gnomon.taxonomy import is_mcp_knowledge_write  # noqa: F401
except ImportError:
    sys.exit(f"{REPO} does not have the compounding fix (missing "
             "is_mcp_knowledge_write). Pass a checkout >= e7f85bc.")

TS = "2026-07-15T12:00:00.000Z"
SINCE = datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc)
UNTIL = datetime.datetime(2026, 8, 7, tzinfo=datetime.timezone.utc)
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
cases = [
    ("N writes to CLAUDE.md (distinct content)",
     [("Write", {"file_path": "/repo/CLAUDE.md", "content": f"regla {i}"})
      for i in range(N)]),
    ("N writes to distinct CLAUDE.md (BE/FE/root/...)",
     [("Write", {"file_path": f"/repo/{i}/CLAUDE.md", "content": "x"})
      for i in range(N)]),
    ("N mem0 add_memory (DISTINCT learnings)",
     [("mcp__mem0__add_memory",
       {"messages": f"aprendizaje distinto numero {i}", "user_id": "fede"})
      for i in range(N)]),
    ("N mem0 update_memory (distinct memory_id)",
     [("mcp__mem0__update_memory", {"memory_id": f"m{i}", "text": "x"})
      for i in range(N)]),
    ("N mem0 update_memory (SAME memory_id)",
     [("mcp__mem0__update_memory", {"memory_id": "m0", "text": f"v{i}"})
      for i in range(N)]),
    ("CONTROL: N mem0 search_memories (read)",
     [("mcp__mem0__search_memories", {"query": f"q{i}"}) for i in range(N)]),
    ("CONTROL: N mem0 delete_memory",
     [("mcp__mem0__delete_memory", {"memory_id": f"m{i}"}) for i in range(N)]),
]

print(f"repo: {REPO}\nN = {N} calls per case, all in ONE session\n")
print(f"{'case':<52}{'credits':>9}")
print("-" * 61)
for label, events in cases:
    print(f"{label:<52}{run(events):>9}")

print("\nSame number of persistence acts, different backend:")
print(f"  {N} file writes          -> {run(cases[0][1])} credits")
print(f"  {N} distinct add_memory  -> {run(cases[2][1])} credits")
