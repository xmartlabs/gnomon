"""FIDELITY audit: each AQ axis against what actually happens in the corpus.

Proposes no changes. Only answers: does the number describe the practice?
30-day window, the same one as the report.
"""
import collections
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, CUT = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus
from gnomon.taxonomy import (classify_mcp_subcategory, _is_compounding_path,  # noqa: E402
                             classify_change_target)

WRITES = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# --- per-session state, in order ---
events = collections.defaultdict(list)   # sid -> [(order, name, input, is_error)]

for p in sorted(glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True)):
    try:
        f = open(p)
    except OSError:
        continue
    with f:
        for line in f:
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ts, sid = e.get("timestamp"), e.get("sessionId")
            if not ts or not sid:
                continue
            try:
                dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt < CUT:
                continue
            c = (e.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    events[sid].append((dt, b.get("name", ""), b.get("input") or {}, None))
                elif b.get("type") == "tool_result":
                    events[sid].append((dt, "__result__", {}, bool(b.get("is_error"))))

for sid in events:
    events[sid].sort(key=lambda x: x[0])

print(f"repo: {REPO}\nwindow: last 30 days, {len(events)} sessions with activity\n")


def is_knowledge_mcp(name):
    if not name.startswith("mcp__"):
        return False
    parts = name.split("__")
    if len(parts) < 3:
        return False
    return classify_mcp_subcategory(parts[1], "__".join(parts[2:])) == "knowledge"


# ============ A. Context Intelligence: is grounding judgment or boilerplate? ============
print("=" * 78)
print("A. Context Intelligence 20/20 (coverage = 1.00, 50/50 sessions 'grounded')")
print("=" * 78)
pos_hist = collections.Counter()
first_tool = collections.Counter()
grounded = 0
for sid, evs in events.items():
    calls = [(n, i) for _, n, i, _ in evs if n != "__result__"]
    if not any(n in WRITES for n, _ in calls):
        continue
    k_idx = next((j for j, (n, _) in enumerate(calls) if is_knowledge_mcp(n)), None)
    if k_idx is None:
        continue
    if any(n in WRITES for n, _ in calls[k_idx + 1:]):
        grounded += 1
        pos_hist[min(k_idx + 1, 11)] += 1
        first_tool[calls[k_idx][0]] += 1
print(f"  sessions with a write that ended up grounded: {grounded}")
print("  position of the call that set it up (1 = very first tool call of the session):")
for pos in sorted(pos_hist):
    lbl = f"{pos}" if pos <= 10 else ">10"
    bar = "#" * pos_hist[pos]
    print(f"    position {lbl:>3}: {pos_hist[pos]:>3}  {bar}")
early = sum(v for k, v in pos_hist.items() if k <= 3)
print(f"  -> {early}/{grounded} ({100*early//max(1,grounded)}%) were set up within the "
      f"first 3 tool calls")
print("  which tool set it up:")
for n, c in first_tool.most_common(5):
    print(f"    {c:>3}  {n}")

# ============ B. Recovery: owned by tmp-and-recovery.py ============
# Deliberately NOT measured here. An earlier version of this section counted only the
# tool call IMMEDIATELY after an error and reported a 0.465 "real recovery" ratio. That
# was a bad operationalization, not a finding: after an error you usually read a file
# before retrying. tmp-and-recovery.py pairs tool_use with its tool_result and looks for
# a later SUCCESSFUL retry of the same tool, which gives 0.90 against the 0.967 reported.
# One question, one owner. See references/refutation.md, example flattering-operationalization.
# ============ C. Discipline: 1474 'Task' calls ============
print()
print("=" * 78)
print("C. Discipline 16.5/17 (task_tool_calls = 1474, 3.2x over target)")
print("=" * 78)
task_names = collections.Counter()
for sid, evs in events.items():
    for _, n, _, _ in evs:
        if n.startswith("Task") or n in ("TodoWrite", "TodoRead"):
            task_names[n] += 1
for n, c in task_names.most_common():
    print(f"    {c:>5}  {n}")

# ============ D. ToolSearch: choice or harness requirement? ============
print()
print("=" * 78)
print("D. ToolSearch = 543 (feeds Tool command AND Token economy, two pillars)")
print("=" * 78)
ts_kind = collections.Counter()
for sid, evs in events.items():
    for _, n, i, _ in evs:
        if n == "ToolSearch":
            q = str(i.get("query", ""))
            ts_kind["select: (forced load of a deferred tool)"
                    if q.startswith("select:") else "keyword search"] += 1
for k, c in ts_kind.most_common():
    print(f"    {c:>5}  {k}")

# ============ E. Compounding: what it is made of ============
print()
print("=" * 78)
print("E. Compounding 20/20 (compounding_writes = 206)")
print("=" * 78)
comp = collections.Counter()
paths = collections.Counter()
for sid, evs in events.items():
    for _, n, i, _ in evs:
        if n in WRITES:
            fp = str(i.get("file_path") or i.get("notebook_path") or "")
            if fp and _is_compounding_path(fp):
                comp["file write"] += 1
                paths[fp.rsplit("/", 1)[-1]] += 1
        elif n.startswith("mcp__") and is_knowledge_mcp(n):
            leaf = n.split("__", 2)[-1].lower()
            if any(h in leaf for h in ("add", "update", "create", "save", "store")):
                comp["memory MCP call"] += 1
for k, c in comp.most_common():
    print(f"    {c:>5}  {k}")
print("  most written files:")
for k, c in paths.most_common(6):
    print(f"    {c:>5}  {k}")

# ============ F. Verification: verdict right even if the mechanism is not? ============
print()
print("=" * 78)
print("F. Verification 20.1/35 - the mechanism is wrong, but the verdict?")
print("=" * 78)
code_sess, tested_sess = set(), set()
for sid, evs in events.items():
    for _, n, i, _ in evs:
        if n in WRITES and classify_change_target(str(i.get("file_path") or "")) == "code":
            code_sess.add(sid)
        if n == "Bash" and re.search(
                r'\b(npm (run )?test|npx vitest|yarn test|pytest|vitest run)',
                str(i.get("command", ""))):
            tested_sess.add(sid)
print(f"  sessions that edited code         : {len(code_sess)}")
print(f"  of those, ran tests               : {len(code_sess & tested_sess)}"
      f"  ({100*len(code_sess & tested_sess)//max(1,len(code_sess))}%)")
print(f"  the axis scores                    : 20.1/35 = {100*20.1/35:.0f}% of the axis")
