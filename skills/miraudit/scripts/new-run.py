"""Writes the skeleton of a run's JSON, prefilled from the anchored run.

    python3 new-run.py --checkout <copy> --since YYYY-MM-DD --until YYYY-MM-DD \\
        --stats <stats.json> [--out <path>]

Phase 4 used to start from a blank file. Two of the structural mistakes this skill now gates
against were made there: a candidate that had failed a refutation row went into findings[],
and a sentence of prose went into `confidence`, which the schema defines as two words.
emit-gate.py catches both, and catches them after they are written. A skeleton removes the
class instead of detecting it.

It also stops the numbers being retyped. `tool`, `anchor` and `corpus` are read from the
anchored run rather than copied by hand from a check's output, which is mechanical work that
fails silently when it fails.

The eight refutation rows come from emit-gate.ROWS by import, not by copy, so a row added
there arrives here without anyone remembering to. JSON carries no comments, so the questions
themselves cannot sit in the file without looking like answers: they are printed instead, at
the moment somebody is about to answer them.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, iter_tool_uses, load_stats, find_key  # noqa: E402
from importlib.machinery import SourceFileLoader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# Hyphenated filename, so a plain import will not reach it.
_gate = SourceFileLoader("emit_gate", os.path.join(HERE, "emit-gate.py")).load_module()

args, WINDOW = parse(__doc__.strip().splitlines()[0],
                     extra={"--out": {"default": None,
                                      "help": "where the skeleton goes (default: "
                                              "miraudit-<until>.json beside the stats)"}})

# Counted with the shared primitive rather than a fourth copy of the walk. Its own docstring
# says it counts identically to fingerprint.py on purpose; the verification for this script
# compares the two rather than trusting that.
tool_calls = sidechain = 0
sessions = set()
for use in iter_tool_uses(args.corpus, WINDOW):
    tool_calls += 1
    if use.event.get("isSidechain"):
        sidechain += 1
    if use.sid:
        sessions.add(use.sid)
sessions = len(sessions)

stats = load_stats(args.stats)

# Which sources were SCORED is the payload's answer, not the transcripts'. This read
# `event["source"]` for a while, a key no Claude Code transcript carries: the set came out
# empty every time and the `["claude"]` fallback was the only branch that ever ran. It wrote
# `["claude"]` on a window whose payload said claude and codex, and this is the field the
# cross-machine protocol leans on hardest.
sources = sorted((stats.get("scoring_inputs_by_source") or {})) if stats else []

# Phase 0 already resolved all of this. Reading it back beats deriving it again: `git
# rev-parse` returns nothing on a `git archive` tree, which has no .git, and the empty string
# became `tool.ref: null` with nothing saying so.
anchored = {}
if args.stats:
    side = os.path.join(os.path.dirname(os.path.abspath(args.stats)), "anchor.json")
    if os.path.exists(side):
        with open(side) as fh:
            anchored = json.load(fh)

ref = anchored.get("ref") or subprocess.run(
    ["git", "-C", args.checkout, "rev-parse", "--short", "HEAD"],
    capture_output=True, text=True).stdout.strip() or None
contract = find_key(stats, "score_contract_id") if stats else None
reproduced = find_key(stats, "aq_0_100") if stats else None

skeleton = {
    "schema_version": "1",
    "tool": {"name": "xl-ai-insights", "ref": ref, "contract": contract},
    "corpus": {
        "tool_calls": tool_calls,
        "sessions": sessions,
        "sidechain_share": round(sidechain / tool_calls, 4) if tool_calls else None,
        "window": f"{args.since} -> {args.until} (fixed)",
        "sources": sources or ["unstated: the payload carries no per-source block"],
    },
    "anchor": {"published": anchored.get("published"), "reproduced": reproduced,
               "ok": anchored.get("ok"), "note": ""},
    "axes": [],
    "findings": [],
    "not_raised": [],
    "reported": [],
    "dismissed": [],
    "process_friction": [],
}

out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.stats or ".")),
                               f"miraudit-{args.until}.json")
if os.path.exists(out):
    sys.exit(f"error: {out} exists. The earlier run is evidence and comparing two runs of "
             "one day is sometimes the point, so this will not overwrite it. Pass --out.")

with open(out, "w") as fh:
    json.dump(skeleton, fh, indent=2)
    fh.write("\n")

print(f"new-run: wrote {out}")
print(f"  tool      ref {ref}  contract {contract}"
      f"{'  (from the anchored run)' if anchored.get('ref') else ''}")
print(f"  anchor    reproduced {reproduced}, ok {skeleton['anchor']['ok']!r}")
if skeleton["anchor"]["ok"] is not True:
    print("            `note` is empty and emit-gate.py will refuse this file once it "
          "carries a\n            finding. Say what was gated and what was not.")
print(f"  corpus    {tool_calls:,} tool calls, {sessions} sessions, "
      f"sidechain {skeleton['corpus']['sidechain_share']}, "
      f"sources {', '.join(skeleton['corpus']['sources'])}")
print("\n  Every finding you add needs a `refuted` block answering all eight rows. They are\n"
      "  printed here because JSON cannot hold them without them looking like answers:\n")
for key, question in _gate.ROWS.items():
    print(f"    {key:32} {question}")
print("\n  A verdict is pass, fail or n/a, and each carries the fact behind it. A row that\n"
      "  reads `fail` means the finding did not survive, and what did not survive belongs\n"
      "  in dismissed[] with the fact that killed it, not in findings[].")
print("\n  An entry in not_raised[] carries that same `refuted` block, because it is a\n"
      "  CONFIRMED finding somebody chose not to send, plus these two:\n")
for key in _gate.NOT_RAISED_KEYS:
    print(f"    {key:32} {'why it was not sent' if key == 'why_not' else 'what would reopen it'}")
print("\n  Said here for the same reason as the rows above. A run added its first\n"
      "  not_raised entry, learned these existed by being refused at the gate, and paid a\n"
      "  render cycle for it.")
print("\n  NOT CHECKED: whether the window you passed is the one the report used. This "
      "reads\n  the anchored run you point it at and cannot tell a right window from a "
      "wrong one.")
