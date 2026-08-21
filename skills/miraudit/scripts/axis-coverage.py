"""Which axes has this run actually looked at, and which is it about to skip in silence.

Phase 1 owes a gap and a direction for every axis. Most axes have no script, so the
unscripted path is the normal path -- and nothing enumerated the axes, so "no script" and
"nobody looked" were indistinguishable from the outside. A hand-maintained list of the
uncovered ones drifted for exactly that reason: ad-hoc-checks.md named five axes and the
payload has six, because Model mix was never added to the prose.

    python3 axis-coverage.py --checkout <copy> --since --until --stats <stats.json> \
        [--run <miraudit-<date>.json>] [--output-dir <run dir>] [--scripts-dir <dir>]

TWO SOURCES, AND THEIR DIFFERENCE IS THE POINT. The payload says what was scored. The
checkout says what exists. An axis in the second and not the first is a dropped term -- the
Phase 2 shape that until now depended on somebody reading the scoring source by eye.

A TAG IS NOT A MEASUREMENT, which is what `--run` exists to separate. `# miraudit-covers:`
says a script CLAIMS an axis. It does not say the script ran, that it exited 0, or that
anybody wrote down a gap and a direction. This file reported the first as if it were the
third until a run whose verdict read "11 of 11" turned out to have recorded six, with two
axes never appearing in any run's `axes` block at all. With `--run` the tag goes back to
being discovery and the run's own JSON is the proof.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats, claims  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

args, WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--run": {"metavar": "PATH", "default": None,
              "help": "the run's miraudit-<date>.json; binds coverage to what was recorded"},
    # `--out-dir` is what run-checks.py and every other script call it. This was the only
    # `--output-dir` in the skill, and anchor.py's copy-paste template matches neither, which
    # cost a cold run one refused invocation. Both are accepted; the old name stays because
    # ad-hoc-checks.md and saved run logs use it.
    "--out-dir": {"metavar": "PATH", "default": None, "dest": "output_dir",
                  "help": "same as --output-dir, and the name the rest of the skill uses"},
    "--output-dir": {"metavar": "PATH", "default": None,
                     "help": "the run's directory, where ad-hoc checks are written"},
    "--terms": {"metavar": "PATH", "default": None,
                "help": "axis-terms.py --emit output; downgrades an axis whose published "
                        "score cannot be rebuilt from its own terms"},
    "--scripts-dir": {"metavar": "PATH", "default": HERE,
                      "help": "where the committed checks live"},
})
stats = load_stats(args.stats)
if not stats:
    sys.exit("error: --stats is required; this reads an anchored run's payload.")

print(header(args, WINDOW))

# ---- what was scored --------------------------------------------------------------------
scored = []
for pillar in (stats.get("agentic") or {}).get("pillars") or []:
    for a in pillar.get("axes") or []:
        scored.append({
            "name": a.get("name"),
            "pillar": pillar.get("name"),
            "base_weight": a.get("base_weight"),
            "weight": a.get("weight"),
            "normalized": a.get("normalized_score"),
        })
by_name = {a["name"]: a for a in scored}

# ---- what exists ------------------------------------------------------------------------
# A source parse, because an axis withheld upstream never reaches the payload and so cannot
# be discovered from it -- which is the whole reason this half exists. Fragile on purpose
# and checked below: if the parse misses an axis the payload contains, the parse is wrong
# and this script says so instead of reporting a smaller world than the real one.
AXIS_RX = re.compile(r'^\s*\("([A-Z][^"]*)",\s*(\d+),', re.M)
aq_path = os.path.join(args.checkout, "gnomon", "scoring", "aq.py")
if not os.path.exists(aq_path):
    sys.exit(f"error: no {aq_path}. The scoring module moved; this parse is anchored to it.")
with open(aq_path) as fh:
    declared = {name: int(w) for name, w in AXIS_RX.findall(fh.read())}

missed = [n for n in by_name if n not in declared]
if missed:
    print("  PARSE FAILED: the payload scored axes this file could not find in aq.py:")
    for n in missed:
        print(f"    {n}")
    print("  The axis-tuple shape changed. Fix the pattern before trusting any line below;")
    print("  a coverage report that cannot see an axis reports it as covered by omission.")
    raise SystemExit(1)

# The check above catches a MISS -- an axis the pattern failed to find. It cannot catch a
# MISREAD: if the tuple grows a field before the weight, group 2 silently becomes something
# else and every line below is confidently wrong. The payload publishes the same number, so
# ask it. This is the only guard on the shape the parse depends on.
mismatched = [(n, declared[n], by_name[n]["base_weight"]) for n in sorted(by_name)
              if n in declared and by_name[n]["base_weight"] is not None
              and declared[n] != by_name[n]["base_weight"]]
if mismatched:
    print("  PARSE MISREAD: the weight parsed from aq.py disagrees with the payload's:")
    for n, got, want in mismatched:
        print(f"    {n:28} aq.py says {got}, the payload says {want}")
    print("  The tuple shape moved. Group 2 of AXIS_RX is no longer the base weight.")
    raise SystemExit(1)

# ---- who covers what --------------------------------------------------------------------
# `claims` lives in _common.py because run-checks.py builds its work list from the same tag,
# and two greps for one tag drift.
committed = claims(os.path.join(args.scripts_dir, "*.py"))
adhoc = claims(os.path.join(args.output_dir, "*.py")) if args.output_dir else {}

unknown = sorted((set(committed) | set(adhoc)) - set(declared))

# ---- what the run actually recorded ------------------------------------------------------
# The bar is Phase 1's own: a gap AND a direction, plus the control every check owes. An
# entry missing either is worse than no entry, because it looks like evidence in the report.
# Maps name -> list of what is missing; [] means complete, absent means no entry at all.
recorded = {}
if args.run:
    with open(os.path.expanduser(args.run)) as fh:
        run_payload = json.load(fh)
    for entry in run_payload.get("axes") or []:
        ev = entry.get("evidence")
        ev = ev if isinstance(ev, dict) else {}
        recorded[entry.get("name")] = [
            field for field, value in (("direction", entry.get("direction")),
                                       ("evidence.control", ev.get("control")))
            if not value]
    stale = sorted(n for n in recorded if n not in by_name)
    if stale:
        print("\n  RECORDED BUT NOT A SCORED AXIS (the run predates this payload, or renamed):")
        for n in stale:
            print(f"    {n}")

# ---- report ------------------------------------------------------------------------------
# The denominator is what aq.py DECLARES, not what the payload scored. It was the scored set,
# and that hid the largest hole in the skill: an axis withheld upstream never reaches the
# payload, so it could never appear as uncovered, and the manifest printed `11/11 covered,
# 0/350 base points not` while Steering leverage -- base weight 50, tied heaviest -- had no
# check at all and no way to acquire one that this report would notice. It showed up under
# DROPPED OR RENORMALIZED, which reads as a footnote rather than as a gap.
#
# Not having a check IS being uncovered, whatever upstream does with the axis afterwards. This
# is the same correction as the gate's ref rule and contract-probe's case count: a denominator
# drawn from the thing being measured cannot show what the thing is missing.
total_base = sum(declared.values())
withheld = [{"name": n, "base_weight": declared[n], "weight": None,
             "pillar": "withheld upstream, not in the payload"}
            for n in declared if n not in by_name]


def heaviest(rows):
    return sorted(rows, key=lambda r: -(r[0]["base_weight"] or 0))


measured, declared_only, uncovered = [], [], []
for a in scored + withheld:
    where = committed.get(a["name"], []) + adhoc.get(a["name"], [])
    gaps = recorded.get(a["name"])          # [] complete, [...] incomplete, None no entry
    if gaps == []:
        measured.append((a, where, gaps))
    elif where or gaps:
        declared_only.append((a, where, gaps))
    else:
        uncovered.append((a, where, gaps))

print("\nMEASURED" if args.run else "\nCOVERED")
if args.run and not measured:
    print("  none")
for a, where, _g in heaviest(measured if args.run else declared_only):
    print(f"  {a['name']:28} {a['base_weight']:>4}  {', '.join(where) or 'no script tags it'}")

if args.run:
    print("\nDECLARED, WITHOUT A RECORDED MEASUREMENT")
    if not declared_only:
        print("  none")
    for a, where, gaps in heaviest(declared_only):
        why = (f"the run's entry is missing {', '.join(gaps)}" if gaps
               else "no entry in the run at all")
        print(f"  {a['name']:28} {a['base_weight']:>4}  {why}")
        print(f"  {'':28}       tagged by {', '.join(where) or 'nothing'}")

print("\nNOT COVERED")
if not uncovered:
    print("  none")
for a, _w, _g in heaviest(uncovered):
    share = (a["base_weight"] or 0) / total_base if total_base else 0
    print(f"  {a['name']:28} {a['base_weight']:>4}  {share:5.1%} of scored weight"
          f"   ({a['pillar']})")

# ---- the dropped-term detector -----------------------------------------------------------
print("\nDROPPED OR RENORMALIZED")
dropped = [n for n in declared if n not in by_name]
renormalized = [a for a in scored
                if a["weight"] is not None and a["base_weight"] is not None
                and a["weight"] != a["base_weight"]]
if not dropped and not renormalized:
    print("  none")
def disclosed_elsewhere(name, blob):
    """Where, if anywhere, the payload still mentions an axis it did not score.

    'ABSENT from the payload' is what this line used to say, and it sent a cold run
    hunting for a missing key that was right there: Steering leverage is withheld
    upstream and the payload carries both `agentic.steering_leverage` and the pillar's
    `not_applicable` list. It was absent from the SCORED AXES, which is a different
    claim and the one worth making -- the interesting question is whether anything a
    person reads says so.
    """
    needle = name.lower().replace(" ", "_")
    hits = []

    def walk(o, path):
        if len(hits) >= 3:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if needle in k.lower():
                    hits.append(f"{path}/{k}")
                walk(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                if isinstance(v, str) and v.lower() == name.lower():
                    hits.append(f"{path}[{i}]")
                walk(v, f"{path}[{i}]")

    walk(blob, "")
    return hits


for n in sorted(dropped):
    where = disclosed_elsewhere(n, stats)
    print(f"  {n:28} {declared[n]:>4}  in aq.py, not among the SCORED AXES."
          " Its weight went somewhere.")
    if where:
        print(f"  {'':28}       the payload does disclose it at {', '.join(where)} —"
              " so the question is whether report.md or profile.html says anything.")
    else:
        print(f"  {'':28}       and nothing in the payload mentions it at all.")
for a in renormalized:
    print(f"  {a['name']:28} {a['base_weight']:>4}  carries {a['weight']} after"
          " renormalization: it is absorbing a dropped sibling's weight.")

if unknown:
    print("\nCLAIMED BUT NOT AN AXIS")
    for n in unknown:
        print(f"  {n:28}        no axis by this name. A typo here reads as coverage.")

# ---- what the term decomposer said about the same axes -------------------------------------
# Two instruments, one question, and until now nobody put their answers next to each other. An
# axis reads COVERED here because a script tags it, and NOT DECOMPOSABLE there because the
# published score cannot be rebuilt from its own terms. Both sentences were true at once for
# Model mix and Orchestration, printed in two different reports, and the contradiction had to
# be noticed by a person reading both.
opaque = []
if args.terms:
    with open(os.path.expanduser(args.terms)) as fh:
        _verdicts = (json.load(fh) or {}).get("verdicts") or {}
    opaque = sorted((n, v) for n, v in _verdicts.items() if v == "NOT DECOMPOSABLE")
    if opaque:
        print("\nCOVERED BUT NOT REBUILDABLE")
        print("  A script claims these, and axis-terms.py cannot rebuild the published score")
        print("  from the terms. A tag over an opaque axis is the thinnest coverage there is.")
        for n, v in opaque:
            who = ", ".join(committed.get(n, []) + adhoc.get(n, [])) or "no script tags it"
            print(f"  {n:28} {declared.get(n, 0):>4}  {v}   ({who})")

blocked = uncovered + (declared_only if args.run else [])
short = sum(a["base_weight"] or 0 for a, _w, _g in blocked)
done = len(measured) if args.run else len(declared_only)
print(f"\n  {done}/{len(declared)} DECLARED axes {'measured' if args.run else 'covered'}."
      f"  {short}/{total_base} base points not.")
if withheld:
    verb = "is" if len(withheld) == 1 else "are"
    reach = "reaches" if len(withheld) == 1 else "reach"
    print(f"  {len(withheld)} of those {verb} withheld upstream and never {reach} the payload: "
          f"{', '.join(a['name'] for a in withheld)}.")
    print("  Counted here anyway. A withheld axis with no check is uncovered twice over, and")
    print("  the scored denominator could not say so.")
if opaque:
    print(f"  {len(opaque)} of the covered axes cannot be rebuilt from their own terms.")
elif not args.terms:
    print("  NOT COMPARED: pass --terms <axis-terms --emit output> to find axes that are")
    print("  covered by a tag while their published score cannot be rebuilt from its parts.")
if not args.run:
    print("  A tag is all this mode can see. Pass --run <miraudit-<date>.json> to require")
    print("  that the run actually recorded a gap, a direction and a control for each.")

if blocked:
    print("\n  Phase 1 owes each of these a gap and a direction. Where no script exists,")
    print("  references/ad-hoc-checks.md is the procedure: a runnable file in the run's")
    print("  output directory, the tool's own primitives, both numbers, and a control.")
    print("  Re-run with --output-dir once they are written and this goes green.")
    raise SystemExit(1)
