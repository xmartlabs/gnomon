"""Write the file a second corpus is asked for. No prose, no judgement, no agent.

A full audit needs judgement and cannot be asked of a volunteer. The CROSS-CORPUS
COMPARISON does not: every field it reads is a number some script already produces. Until
this existed the JSON was hand-written from the checks' printed output, which made the ask
"run these and have an agent write a file" -- an expectation rather than an instruction.

    python3 emit-comparison.py --checkout <copy> --since --until --stats <stats.json> \
        --out <path> [--saturation <sat.json>] [--published <N>]

Everything here is aggregate. No transcripts, no file contents, no paths, no repository or
project names: the profile signature below is deliberately counts and shares, so that
describing what somebody works on never requires naming it.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (parse, load_stats, dig, find_key, require,  # noqa: E402
                     iter_tool_uses, iter_events)

args, WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--out": {"metavar": "PATH", "default": None, "help": "where to write the payload"},
    "--saturation": {"metavar": "PATH", "default": None,
                     "help": "saturation-counterfactual.py --emit output, folded in"},
    "--published": {"metavar": "N", "default": None,
                    "help": "the number the report shows, so anchor.ok can be set"},
})
if not args.out:
    sys.exit("error: --out is required. A run that writes nothing has produced nothing.")
stats = load_stats(args.stats)
if not stats:
    sys.exit("error: --stats is required; this reads an anchored run's payload.")

(classify_tool,) = require(
    [("gnomon.taxonomy", "classify_tool")],
    "The tool categories moved, so the profile signature would describe buckets that no "
    "longer exist.")

# ---- corpus fingerprint and profile signature -------------------------------------------
# The signature answers "are these two corpora the same kind of work?" without anyone having
# to describe their job. People describe work in incomparable ways, and "backend engineer"
# does not say whether two people share a codebase.
tools = collections.Counter()
cats = collections.Counter()
sessions = set()
roots = set()
sidechain = 0
total = 0

for use in iter_tool_uses(args.corpus, WINDOW):
    total += 1
    tools[use.name] += 1
    cats[classify_tool(use.name)] += 1
    if use.sid:
        sessions.add(use.sid)
    if use.sidechain:
        sidechain += 1
    cwd = use.event.get("cwd")
    if cwd:
        # The COUNT of distinct project roots, never the roots themselves.
        roots.add(cwd)

thinking = 0
for _path, event, _when in iter_events(args.corpus, WINDOW, contains='"thinking"'):
    content = (event.get("message") or {}).get("content")
    if isinstance(content, list):
        thinking += sum(1 for b in content
                        if isinstance(b, dict) and b.get("type") == "thinking")

doing = cats["produce"] + cats["execute"] + cats["delegate"]
top = tools.most_common(10)

axes = [{"name": a.get("name"), "score": a.get("score")}
        for p in (stats.get("agentic") or {}).get("pillars") or []
        for a in p.get("axes") or []]

published = int(args.published) if args.published else None
reproduced = find_key(stats, "aq_0_100")

payload = {
    "schema_version": "comparison-1",
    "generated_by": "miraudit/scripts/emit-comparison.py",
    "tool": {
        "ref": None,
        "contract": find_key(stats, "score_contract_id"),
    },
    "anchor": {
        "published": published,
        "reproduced": reproduced,
        # Unknown is not the same as true. Without --published nobody checked, and a
        # comparison that treats an unchecked run as anchored is worse than one that skips it.
        "ok": (published == reproduced) if published is not None else None,
    },
    "corpus": {
        # A SNAPSHOT, not a property of the window. Measured on this corpus: the same fixed
        # window read 42,664 tool calls in the morning and 42,874 hours later, because two
        # transcripts gained events timestamped inside the window after the fact -- resumed
        # sessions keep writing under their original dates. A fixed window fixes which days
        # are counted, not which files exist to be counted.
        #
        # So the anchored `stats.json` and this walk are two snapshots taken at different
        # moments, and running the checks long after the anchor compares a live corpus
        # against a frozen payload. Keep the gap small; when comparing two machines, read
        # these as approximate context and the axis scores as the comparable part.
        "measured_at": "this run; see the note in emit-comparison.py",
        "tool_calls": total,
        "sessions": len(sessions),
        "sidechain_share": round(sidechain / total, 4) if total else None,
        "window": {"since": args.since, "until": args.until, "days": args.days},
        "sources_scored": sorted((stats.get("scoring_inputs_by_source") or {}).keys()),
    },
    "profile": {
        "distinct_project_roots": len(roots),
        "tool_mix_top10": [{"tool": n, "share": round(c / total, 4)} for n, c in top]
        if total else [],
        "category_share": {k: round(v / total, 4) for k, v in sorted(cats.items())}
        if total else {},
        "explore_to_doing": round((cats["explore"] + thinking) / doing, 3) if doing else None,
        "explore_to_doing_without_thinking": round(cats["explore"] / doing, 3) if doing else None,
    },
    "axes": axes,
    "grounding": {
        "explore_actions": dig(stats, "behavior", "explore_actions"),
        "thinking_blocks": dig(stats, "volume", "thinking_blocks"),
        "planning_ratio": dig(stats, "behavior", "planning_ratio_explore_to_doing"),
    },
    "not_checked": [
        "whether two corpora with matching signatures are the same codebase; the signature "
        "describes the shape of the work, not where it happens",
        "whether the thresholds are calibrated against the graded population; people who "
        "agree to run an audit are not a random sample of it",
    ],
}

think_total = payload["grounding"]["thinking_blocks"]
explore_total = payload["grounding"]["explore_actions"]
if think_total and explore_total:
    payload["grounding"]["thinking_share"] = round(think_total / explore_total, 4)

if args.saturation:
    with open(os.path.expanduser(args.saturation)) as fh:
        payload["saturation"] = json.load(fh)

out = os.path.expanduser(args.out)
with open(out, "w") as fh:
    json.dump(payload, fh, indent=2)

print(f"wrote {out}")
print(f"  contract       {payload['tool']['contract']}")
print(f"  anchor.ok      {payload['anchor']['ok']}"
      f"{'   (no --published passed, so nothing was checked)' if published is None else ''}")
print(f"  corpus         {total:,} tool calls, {len(sessions)} sessions,"
      f" {len(roots)} project roots")
print(f"  axes           {len(axes)} scored")
print(f"  saturation     {'folded in' if args.saturation else 'not included, pass --saturation'}")
print("\nThis file carries counts and shares only. Read it before sending it.")
