"""Recovery: today any tool call after an error counts. How many errors were followed
by a SUCCESSFUL RETRY of the same tool in the same session.

A first section here measured how much of the 'edited code' denominator was harness
scratchpad. It is DELETED, not moved: at c6401cc classify_change_target short-circuits
every path matching _EPHEMERAL_PATH_RX to "other" (taxonomy.py:274-295), and eligibility
only admits file_class == "code" (accumulator.py:2200-2206), so a scratchpad write can no
longer reach the denominator at all. The section still printed a bucket, because its own
TMP_ANY regex dropped the `scratchpad/` requirement their predicate carries -- so what it
labelled "ONLY ephemeral scratchpad <- should not count" was /tmp and /var/folders paths
that are not scratchpads and that the tool counts on purpose. Wrong population, wrong
label, confident output.
"""
import collections
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
REPO, ROOT = args.checkout, args.corpus

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
            if dt not in WINDOW:
                continue
            c = (e.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    order += 1
                    uses[b.get("id")] = (sid, order, b.get("name", ""))
                elif b.get("type") == "tool_result":
                    u = uses.get(b.get("tool_use_id"))
                    if u:
                        by_sess[u[0]].append((u[1], u[2], not b.get("is_error")))

print(header(args, WINDOW))

print("=" * 80)
print("Recovery: 'I recovered' vs 'I did something else'")
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
# miraudit-covers: Recovery
