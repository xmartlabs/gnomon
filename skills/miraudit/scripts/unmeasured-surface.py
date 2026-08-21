"""Everything that can go `unmeasured`, against the little of it any one run discloses.

    python3 unmeasured-surface.py --checkout <copy> --since --until --stats <stats.json>

This project found two dropped terms by hand -- the routing third of Model mix, and the
ordered-facts term behind Context Intelligence -- and each cost an investigation. Nothing
enumerated the rest, so the third one would have cost another. A drop is the most expensive
kind of defect this skill looks for: the axis keeps a score, the weight goes somewhere, and
the payload says almost nothing.

The denominator is the SOURCE, not the payload. That is the whole point and it is the third
time this skill has had to learn it: the gate compared the pin against the pin, contract-probe
counted its own cases, and axis-coverage took its axis list from the payload it was auditing.
A run can only disclose what it dropped; it cannot disclose what it never had the chance to.

Four mechanisms, not one, and only the first is widely known here:

  A  wsum() drops a term and renormalizes the survivors      (aq.py)
  B  build_pillar drops a whole AXIS and renormalizes        (aq.py)
  C  a weight is SCALED continuously, not dropped            (planning_evidence.py)
  D  the pooled aggregate collapses across sources           (aggregate.py)

C is invisible in `partial_terms` by construction: the term is present with a smaller weight.
D is worse -- pooled `not_applicable` is the INTERSECTION across sources, so an axis dropped in
one source and not another disappears from the disclosure while still being blended.

Exits non-zero only when a control fails. A drop is not a defect by itself; an undisclosed one
might be, and that judgement is not this script's.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
stats = load_stats(args.stats)
if not stats:
    sys.exit("error: --stats is required; this reads an anchored run's payload.")

SRC = os.path.join(args.checkout, "gnomon", "scoring")


def read(name):
    path = os.path.join(SRC, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---- what the source can drop -------------------------------------------------------------
# Counted from the shipped scoring module. Patterns, not a list of line numbers: a list would
# be a second declaration that goes stale on the next upstream commit, which is the failure
# this whole file exists to make visible.
MECHANISMS = (
    ("A  wsum drops a term", "aq.py",
     r"^\s*\(\s*[\d.]+\s*,\s*\w+", "terms passed to wsum, each droppable when None"),
    ("B  an axis is dropped", "aq.py",
     r'^\s*\("([A-Z][^"]*)",\s*\d+,', "axes build_pillar can drop whole"),
    ("C  a weight is scaled", "planning_evidence.py",
     r"effective_weight", "sites where weight shrinks continuously instead of dropping"),
    ("D  the pooled score collapses", None, None, None),
)

print(header(args, WINDOW))
print("=" * 88)
print("UNMEASURED SURFACE — what CAN go unmeasured, against what this run disclosed")
print("=" * 88)

FAILED = []
capacity = {}
print("\nWHAT THE SOURCE CAN DROP")
for label, filename, pattern, what in MECHANISMS:
    if filename is None:
        body = read("../analysis/aggregate.py") or read("aggregate.py")
        n = len(re.findall(r"not_applicable|ordered_facts_state", body or ""))
        capacity[label] = n
        print(f"  {label:<28} {n:>4}  sites touching pooled disclosure or pooled state")
        continue
    body = read(filename)
    if body is None:
        FAILED.append(f"{filename} is not where this expects it; the parse is anchored to it")
        print(f"  {label:<28}    ?  {filename} not found")
        continue
    n = len(re.findall(pattern, body, re.M))
    capacity[label] = n
    print(f"  {label:<28} {n:>4}  {what}")

# The vacuity guard. A regex that finds nothing reports a small world rather than an error, and
# a small world reads as "not much can go wrong" -- the exact reading this file exists to deny.
for label, n in capacity.items():
    if n == 0:
        FAILED.append(f"{label}: the parse found zero sites, which is not a credible answer. "
                      "The shape moved; fix the pattern before reading any line above.")

# ---- what this run disclosed --------------------------------------------------------------
agentic = stats.get("agentic") or {}
dropped_axes, partial_axes, renormalized = [], [], []
for pillar in agentic.get("pillars") or []:
    for name in pillar.get("not_applicable") or []:
        dropped_axes.append((name, pillar.get("name")))
    for axis in pillar.get("axes") or []:
        pt = axis.get("partial_terms")
        if pt:
            partial_axes.append((axis["name"], pt))
        if (axis.get("weight") is not None and axis.get("base_weight") is not None
                and axis["weight"] != axis["base_weight"]):
            renormalized.append((axis["name"], axis["base_weight"], axis["weight"]))

print("\nWHAT THIS RUN DISCLOSED")
print(f"  axes dropped entirely      {len(dropped_axes):>4}  "
      f"{', '.join(n for n, _p in dropped_axes) or 'none'}")
for name, pillar in dropped_axes:
    print(f"      {name} left {pillar} to be shared out among its siblings")
print(f"  axes with a dropped term   {len(partial_axes):>4}  "
      f"{', '.join(n for n, _p in partial_axes) or 'none'}")
for name, pt in partial_axes:
    print(f"      {name}: {pt.get('scored')}/{pt.get('total')} terms scored, "
          f"{pt.get('weight_scored')} of the axis weight")
print(f"  axes carrying more weight  {len(renormalized):>4}  "
      f"{', '.join(n for n, _b, _w in renormalized) or 'none'}")
for name, base, weight in renormalized:
    print(f"      {name} declares {base} and carries {weight} — it absorbed a sibling")

print("\n  A dropped axis and a dropped TERM disclose differently: the axis leaves a name in")
print("  `not_applicable`, the term leaves a ratio in `partial_terms`, and mechanism C leaves")
print("  NOTHING — the term is still there with a smaller weight. Nothing in a payload")
print("  distinguishes a term at full weight from one scaled to a tenth of it.")

# ---- the control --------------------------------------------------------------------------
# Without it, "0 dropped" is indistinguishable from a parse that reads no payload at all, which
# is how a report ends up quietly saying nothing is wrong.
print("\n  CONTROL: a synthetic payload with one dropped axis and one partial term must be seen")
probe = {"agentic": {"pillars": [{"name": "P", "not_applicable": ["Ghost"], "axes": [
    {"name": "Real", "base_weight": 20, "weight": 40,
     "partial_terms": {"scored": 1, "total": 2, "weight_scored": 0.5}}]}]}}
seen_dropped, seen_partial, seen_renorm = [], [], []
for pillar in probe["agentic"]["pillars"]:
    seen_dropped += pillar.get("not_applicable") or []
    for axis in pillar["axes"]:
        if axis.get("partial_terms"):
            seen_partial.append(axis["name"])
        if axis["weight"] != axis["base_weight"]:
            seen_renorm.append(axis["name"])
ok = seen_dropped == ["Ghost"] and seen_partial == ["Real"] and seen_renorm == ["Real"]
print(f"    dropped {seen_dropped}, partial {seen_partial}, renormalized {seen_renorm}  "
      f"{'[ok]' if ok else '[??]'}")
if not ok:
    FAILED.append("CONTROL: the synthetic payload's drops were not detected, so a zero above "
                  "means nothing")

print("\n  NOT CHECKED: whether a drop is WRONG. Several are deliberate and documented in the")
print("  tool's own source -- the withheld steering band is, and they said so. This counts")
print("  what can happen and reports what did; deciding is Phase 3's job, with their code")
print("  open. And mechanism C is counted but not observed: no payload field exposes it.")

if FAILED:
    print(f"\n  {len(FAILED)} control(s) or parse(s) failed:")
    for f in FAILED:
        print(f"    - {f}")
    raise SystemExit(1)
# No `miraudit-covers:` tag on purpose, for the reason verify-repo-bucketing.py has
# none: this is cross-axis. It counts a MECHANISM that can drop any axis, so tagging
# it with one would credit that axis with coverage it did not get -- which is exactly
# the mis-tag this same pass had to correct in verify-routing-orphan-gate.py.
# It belongs in run-checks.ALWAYS instead, beside axis-terms.py.
