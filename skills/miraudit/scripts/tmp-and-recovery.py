"""Two questions: how much of the denominator is /tmp scratchpad, and what Recovery means.

1) Of the sessions the tool counts as 'edited code', how many qualify ONLY through
   writes to the ephemeral scratchpad the harness itself assigns
   (/private/tmp/claude-*/<project>/<session-uuid>/scratchpad/).

2) Recovery: today any tool call after an error counts. How many errors were followed
   by a SUCCESSFUL RETRY of the same tool in the same session.
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
from gnomon.taxonomy import classify_change_target  # noqa: E402

WRITES = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SCRATCH = re.compile(r'^/private/tmp/claude-\d+/[^/]+/[0-9a-f-]{36}/scratchpad/')
TMP_ANY = re.compile(r'^(/private)?/tmp/|^/var/folders/')

sess_files = collections.defaultdict(lambda: {"scratch": set(), "real": set()})
uses = {}                                     # tool_use_id -> (sid, order, name)
fails = []                                    # (sid, order, name)
by_sess = collections.defaultdict(list)       # sid -> [(order, name, ok)]
order = 0

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
                    order += 1
                    name, inp = b.get("name", ""), (b.get("input") or {})
                    uses[b.get("id")] = (sid, order, name)
                    fp = str(inp.get("file_path") or inp.get("notebook_path") or "")
                    if name in WRITES and fp and classify_change_target(fp) == "code":
                        tgt = "scratch" if (SCRATCH.match(fp) or TMP_ANY.match(fp)) else "real"
                        sess_files[sid][tgt].add(fp)
                elif b.get("type") == "tool_result":
                    u = uses.get(b.get("tool_use_id"))
                    if u:
                        by_sess[u[0]].append((u[1], u[2], not b.get("is_error")))

print(header(args, CUT))

# ---------- 1. scratchpad ----------
print("=" * 80)
print("1. How much of the 'sessions that edited code' denominator is /tmp scratchpad")
print("=" * 80)
coding = {s: v for s, v in sess_files.items() if v["scratch"] or v["real"]}
only_scratch = [s for s, v in coding.items() if v["scratch"] and not v["real"]]
mixed = [s for s, v in coding.items() if v["scratch"] and v["real"]]
only_real = [s for s, v in coding.items() if v["real"] and not v["scratch"]]
print(f"  sessions with any code write            : {len(coding)}")
print(f"    ONLY ephemeral scratchpad             : {len(only_scratch):>3}"
      f"  <- should not count")
print(f"    mixed (scratchpad + real code)        : {len(mixed):>3}")
print(f"    real code only                        : {len(only_real):>3}")
nfiles_s = sum(len(v["scratch"]) for v in coding.values())
nfiles_r = sum(len(v["real"]) for v in coding.values())
print(f"  distinct code files: {nfiles_s} in scratchpad, {nfiles_r} real")
# C2 approx: >=2 distinct code files
c2_con = sum(1 for v in coding.values() if len(v["scratch"] | v["real"]) >= 2)
c2_sin = sum(1 for v in coding.values() if len(v["real"]) >= 2)
print(f"\n  C2-eligible (>=2 distinct code files):")
print(f"    counting scratchpad : {c2_con}")
print(f"    excluding it        : {c2_sin}   (difference: {c2_con - c2_sin})")

# ---------- 2. recovery ----------
print()
print("=" * 80)
print("2. Recovery: 'I recovered' vs 'I did something else'")
print("=" * 80)
tot = retried_ok = retried_fail = other_only = nothing = 0
for sid, evs in by_sess.items():
    evs.sort()
    for i, (o, name, ok) in enumerate(evs):
        if ok:
            continue
        tot += 1
        later = evs[i + 1:]
        if not later:
            nothing += 1
        elif any(n == name and k for _, n, k in later):
            retried_ok += 1
        elif any(n == name for _, n, _ in later):
            retried_fail += 1
        else:
            other_only += 1
print(f"  tool calls that failed: {tot}")
print(f"    followed by a SUCCESSFUL retry of the same tool  : {retried_ok:>5}"
      f"  ({100*retried_ok//max(1,tot)}%)")
print(f"    retried the same tool, still failing             : {retried_fail:>5}"
      f"  ({100*retried_fail//max(1,tot)}%)")
print(f"    never retried that tool, but did other calls     : {other_only:>5}"
      f"  ({100*other_only//max(1,tot)}%)")
print(f"    NO tool call at all afterwards                   : {nothing:>5}"
      f"  ({100*nothing//max(1,tot)}%)")
print(f"\n  ratio under today's definition (any tool call)  : "
      f"{(tot-nothing)/max(1,tot):.3f}")
print(f"  ratio requiring a successful same-tool retry    : "
      f"{retried_ok/max(1,tot):.3f}")
print("\n  (the second is a LOWER BOUND: changing approach is also recovering)")
