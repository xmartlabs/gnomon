"""FIDELITY audit: each AQ axis against what actually happens in the corpus.

Proposes no changes. Only answers: does the number describe the practice?
30-day window, the same one as the report.
"""
import collections
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, require, load_stats  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus

# Every predicate comes from the tool being audited. An earlier version hand-rolled three of
# them -- a test-command regex, the MCP knowledge-write hints, and the write-tool set -- which
# is the invented-denominator mistake this skill exists to catch, committed inside the audit.
from gnomon.taxonomy import (WRITE_TOOLS as WRITES, bash_runs_tests,  # noqa: E402
                             classify_change_target, classify_mcp_subcategory,
                             is_mcp_knowledge_write)

# Private upstream, so it can be renamed without deprecation.
(_is_compounding_path,) = require(
    [("gnomon.taxonomy", "_is_compounding_path")],
    "It is private upstream; check whether it was renamed or made public.")

# Axis scores are READ from the report, never baked in. An earlier version hardcoded one
# person's values into the section headers, so the script asserted numbers it had not read
# and went stale the moment an axis moved.
_AXES = {}
for _pillar in (load_stats(args.stats).get("agentic") or {}).get("pillars") or []:
    for _ax in _pillar.get("axes") or []:
        _AXES[_ax.get("name")] = _ax


def axis(name, note=""):
    """'<name> <score>/<max>' from the report, or a marker when no report was given."""
    a = _AXES.get(name)
    if a is None:
        head = f"{name} (score not read: pass --stats)"
    else:
        head = f"{name} {a.get('score')}/{a.get('weight', a.get('base_weight'))}"
    return f"{head}{' ' + note if note else ''}"

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
            if dt not in WINDOW:
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

print(header(args, WINDOW))
print(f"sessions with activity in window: {len(events)}\n")


def is_knowledge_mcp(name):
    if not name.startswith("mcp__"):
        return False
    parts = name.split("__")
    if len(parts) < 3:
        return False
    return classify_mcp_subcategory(parts[1], "__".join(parts[2:])) == "knowledge"


# ============ A. Context Intelligence: is grounding judgment or boilerplate? ============
print("=" * 78)
print("A. " + axis("Context Intelligence", "- is grounding judgment or boilerplate?"))
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

# ============ C. Discipline: what the task-tool counter is made of ============
print()
print("=" * 78)
print("C. " + axis("Discipline", "- what the task-tool counter is made of"))
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
print("D. ToolSearch - one counter, two pillars: "
      + axis("Tool command (MCP + CLI)") + " and " + axis("Token economy"))
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
print("E. " + axis("Compounding", "- what it is made of"))
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
        elif n.startswith("mcp__"):
            parts = n.split("__")
            if len(parts) >= 3 and is_mcp_knowledge_write(parts[1], "__".join(parts[2:])):
                comp["memory MCP call"] += 1
for k, c in comp.most_common():
    print(f"    {c:>5}  {k}")
print("  most written files:")
for k, c in paths.most_common(6):
    print(f"    {c:>5}  {k}")

# ============ F. Verification: verdict right even if the mechanism is not? ============
print()
print("=" * 78)
print("F. " + axis("Verification", "- the mechanism is wrong, but the verdict?"))
print("=" * 78)
code_sess, tested_sess = set(), set()
for sid, evs in events.items():
    for _, n, i, _ in evs:
        if n in WRITES and classify_change_target(str(i.get("file_path") or "")) == "code":
            code_sess.add(sid)
        if n == "Bash" and bash_runs_tests(str(i.get("command", ""))):
            tested_sess.add(sid)
print(f"  sessions that edited code         : {len(code_sess)}")
print(f"  of those, ran tests               : {len(code_sess & tested_sess)}"
      f"  ({100*len(code_sess & tested_sess)//max(1,len(code_sess))}%)")
_v = _AXES.get("Verification")
if _v:
    _sc, _mx = _v.get("score"), _v.get("weight", _v.get("base_weight"))
    print(f"  the axis scores                   : {_sc}/{_mx} = "
          f"{100*float(_sc)/float(_mx):.0f}% of its range")
else:
    print("  the axis scores                   : not read (pass --stats)")
