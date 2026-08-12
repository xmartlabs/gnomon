"""Which axes has this run actually looked at, and which is it about to skip in silence.

Phase 1 owes a gap and a direction for every axis. Most axes have no script, so the
unscripted path is the normal path -- and nothing enumerated the axes, so "no script" and
"nobody looked" were indistinguishable from the outside. A hand-maintained list of the
uncovered ones drifted for exactly that reason: ad-hoc-checks.md named five axes and the
payload has six, because Model mix was never added to the prose.

    python3 axis-coverage.py --checkout <copy> --since --until --stats <stats.json> \
        [--output-dir <run dir>] [--scripts-dir <dir>]

TWO SOURCES, AND THEIR DIFFERENCE IS THE POINT. The payload says what was scored. The
checkout says what exists. An axis in the second and not the first is a dropped term -- the
Phase 2 shape that until now depended on somebody reading the scoring source by eye.
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

args, WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--output-dir": {"metavar": "PATH", "default": None,
                     "help": "the run's directory, where ad-hoc checks are written"},
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

# ---- who covers what --------------------------------------------------------------------
# Declared by a grepped comment rather than by importing: a check with a syntax error must
# still be visible as claiming its axis. Silence from a broken file would read as "no script
# exists", which is the one thing this script is here to distinguish.
COVERS_RX = re.compile(r'^#\s*miraudit-covers:\s*(.+?)\s*$', re.M)


def claims(pattern):
    out = {}
    for path in sorted(glob.glob(pattern)):
        with open(path) as fh:
            for name in COVERS_RX.findall(fh.read()):
                out.setdefault(name, []).append(os.path.basename(path))
    return out


committed = claims(os.path.join(args.scripts_dir, "*.py"))
adhoc = claims(os.path.join(args.output_dir, "*.py")) if args.output_dir else {}

unknown = sorted((set(committed) | set(adhoc)) - set(declared))

# ---- report ------------------------------------------------------------------------------
total_base = sum(a["base_weight"] or 0 for a in scored)
covered, uncovered = [], []
for a in scored:
    where = committed.get(a["name"], []) + adhoc.get(a["name"], [])
    (covered if where else uncovered).append((a, where))

print("\nCOVERED")
for a, where in sorted(covered, key=lambda x: -(x[0]["base_weight"] or 0)):
    print(f"  {a['name']:28} {a['base_weight']:>4}  {', '.join(where)}")

print("\nNOT COVERED")
if not uncovered:
    print("  none")
for a, _w in sorted(uncovered, key=lambda x: -(x[0]["base_weight"] or 0)):
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
for n in sorted(dropped):
    print(f"  {n:28} {declared[n]:>4}  in aq.py, ABSENT from the payload."
          " Its weight went somewhere.")
for a in renormalized:
    print(f"  {a['name']:28} {a['base_weight']:>4}  carries {a['weight']} after"
          " renormalization: it is absorbing a dropped sibling's weight.")

if unknown:
    print("\nCLAIMED BUT NOT AN AXIS")
    for n in unknown:
        print(f"  {n:28}        no axis by this name. A typo here reads as coverage.")

print(f"\n  {len(covered)}/{len(scored)} scored axes covered."
      f"  {sum(a['base_weight'] or 0 for a, _w in uncovered)}/{total_base} base points not.")

if uncovered:
    print("\n  Phase 1 owes each of these a gap and a direction. Where no script exists,")
    print("  references/ad-hoc-checks.md is the procedure: a runnable file in the run's")
    print("  output directory, the tool's own primitives, both numbers, and a control.")
    print("  Re-run with --output-dir once they are written and this goes green.")
    raise SystemExit(1)
