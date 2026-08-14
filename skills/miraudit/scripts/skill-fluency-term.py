"""Skill fluency's third term: recovered by algebra, and checked against the diagnostic.

    python3 skill-fluency-term.py --checkout <copy> --since --until \
        --stats <stats.json> --comparison <file.json> [--comparison <file.json> ...]

# miraudit-covers: Skill fluency

Graduated from adhoc-skill-fluency.py because a second run needed the same measurement on a
different input: comparison-2 payloads carry per-axis `signals` and `normalized_score`, which
is exactly what the algebra needs, so the same recovery now runs on anybody's corpus.

30% of the axis is `1.0 if has_skill([...]) else 0.6`, a SUBSTRING match against five
hard-coded names. `has_skill` is a closure inside compute_aq and cannot be imported, so
nothing here reimplements it: the term is recovered by algebra on gnomon's own published
normalized_score.

It used to appear in no `signals` field, which was the finding. gnomon now publishes
`process_skills_matched` as a diagnostic that scores nothing, so on a current payload this
file has a different job: the algebra and the diagnostic are two independent routes to the
same bit, and it reports when they disagree. On an older payload, or any corpus collected
before the diagnostic existed, the recovery is still the only route and still runs.

Saying "the term is published nowhere" past that fix would be a fixture outliving its
subject, which is what step 4 of the refresh procedure is about.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats, require  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--comparison": {"action": "append", "default": [], "metavar": "PATH",
                     "help": "a comparison-2 payload; repeatable"},
})

(CEIL, TARGET, MCP_CEIL, CLI_CEIL) = require(
    [("gnomon.scoring.aq", "SKILLS_DISTINCT_CEILING"),
     ("gnomon.scoring.aq", "SKILLS_TOTAL_PER_CALL_TARGET"),
     ("gnomon.scoring.aq", "MCP_SERVERS_DISTINCT_CEILING"),
     ("gnomon.scoring.aq", "CLIS_DISTINCT_CEILING")],
    "The ceilings this scores against are gone.")

W = (0.40, 0.30, 0.30)
BRANCHES = {1.0: "a name matched", 0.6: "no name matched"}
crosscheck_failed = []
print(header(args, WINDOW))


def sat(x, t):
    return min(1.0, x / t) if t else 0.0


def recover(label, axes):
    sf = axes.get("Skill fluency")
    if not sf or not sf.get("signals"):
        print(f"  {label:10} no per-axis signals — a comparison-1 file cannot answer this")
        return None
    s = sf["signals"]
    t1 = sat(s["skills_distinct"], CEIL)
    t2 = sat(s["skills_total_per_call"], s["skills_total_per_call_target"])
    norm = sf["normalized_score"]
    x = (norm * sum(W) - W[0] * t1 - W[1] * t2) / W[2]
    hit = [v for v in BRANCHES if abs(x - v) < 0.005]
    verdict = BRANCHES[hit[0]] if hit else "INCONSISTENT, do not report"
    # gnomon now publishes the branch as a diagnostic that scores nothing. Where a payload
    # carries it, the algebra stops being a recovery and becomes a check ON that diagnostic:
    # two independent routes to the same bit.
    published = s.get("process_skills_matched")
    if published is not None and hit:
        agrees = bool(published) == (hit[0] == 1.0)
        verdict += f"; published {published!r}, {'agrees' if agrees else 'DISAGREES'}"
        if not agrees:
            crosscheck_failed.append(label)
    print(f"  {label:10} distinct {s['skills_distinct']:>4}/{CEIL}  rate {t2:.3f}"
          f"  norm {norm:.4f}  ->  term3 {x:.4f}  ({verdict})")
    return hit[0] if hit else None


def axes_of(payload):
    if "axes" in payload:
        return {a["name"]: a for a in payload["axes"]}
    return {a["name"]: a for p in payload["agentic"]["pillars"] for a in p["axes"]}


print("SKILL FLUENCY — the undisclosed 30% term, recovered per corpus")
found = [recover("ours", axes_of(load_stats(args.stats)))]
for path in args.comparison:
    with open(os.path.expanduser(path)) as fh:
        payload = json.load(fh)
    # The stem minus the shared prefix, because every file starts "comparison-" and a blind
    # truncation labelled all of them "comparison" -- an output nobody could read a corpus off.
    stem = os.path.splitext(os.path.basename(path))[0]
    found.append(recover(stem.replace("comparison-", "") or stem, axes_of(payload)))

known = [v for v in found if v is not None]
print(f"\n  {len(known)} corpora resolved; branches seen: {sorted(set(known))}")
if known and set(known) == {1.0}:
    print("  Every corpus measured is on the 1.0 branch, so on this evidence the term is a")
    print("  constant that lifts everyone equally rather than one that costs anyone points.")
if crosscheck_failed:
    print(f"\n  CROSS-CHECK FAILED on {', '.join(crosscheck_failed)}: the algebra and the")
    print("  published diagnostic disagree about the same bit. One of them is wrong and this")
    print("  script cannot say which.")

# CONTROL: the same algebra on an axis whose terms are all disclosed must reproduce exactly.
ours = axes_of(load_stats(args.stats))
tc = ours["Tool command (MCP + CLI)"]
pred = (0.40 * sat(tc["signals"]["mcp_servers"], MCP_CEIL)
        + 0.40 * sat(tc["signals"]["clis"], CLI_CEIL)) / 0.80
agree = abs(pred - tc["normalized_score"]) < 1e-6
print(f"\n  CONTROL  Tool command, every term disclosed: predicted {pred:.6f} vs published"
      f" {tc['normalized_score']:.6f}  -> {'agree' if agree else 'DISAGREE'}")
print("  NOT CHECKED: whether a corpus using none of the five names exists. Every corpus")
print("  here is a Claude Code user, and the needles are Claude Code skill names.")
if not agree:
    raise SystemExit(1)
