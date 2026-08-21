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
import datetime
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

# ---- how long the run actually took, from the artifacts rather than from memory ----------
# A cold run's self-reported clock came in inflated 2.3x BOTH times it was checked against
# reality (it said 45 minutes; the runs took 19.4 and 19.9). The payload had nowhere to put
# the real figure, so the correction lived in a markdown file and could not stop a third one.
#
# mtimes are the only source here that does not have an opinion. The exclusion is not
# optional: anchor/ holds a copy of the checkout, whose files carry the date `git archive`
# stamped on them -- one run's raw directory span read 47 hours because of it.
# `checkout` is the live name and `anchor` is the old one, kept because saved runs still use
# it. Both hold a `git archive` extraction whose files carry the COMMIT's date, and one raw
# directory span read 47 hours because of it -- excluding only `anchor` against the current
# layout read NINE DAYS.
#
# The exclusion and the root below have to move together. Widening the walk to the run root
# without this list is exactly how the 47-hour number came back, and narrowing the root to
# dodge it is how the span became structurally zero.
EXCLUDE_FROM_SPAN = ("checkout", "anchor", ".git", "__pycache__")


def run_span(root):
    """(earliest, latest, seconds) over the run's own artifacts, or None when there are
    fewer than two to span."""
    stamps = []
    for here, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_FROM_SPAN]
        for name in files:
            try:
                stamps.append(os.path.getmtime(os.path.join(here, name)))
            except OSError:
                continue
    if len(stamps) < 2:
        return None
    lo, hi = min(stamps), max(stamps)
    return {
        "started": datetime.datetime.fromtimestamp(lo, datetime.timezone.utc)
                   .isoformat(timespec="seconds"),
        "ended": datetime.datetime.fromtimestamp(hi, datetime.timezone.utc)
                 .isoformat(timespec="seconds"),
        "seconds": int(round(hi - lo)),
        "derived_from": "mtimes of the output directory, excluding " +
                        "/".join(EXCLUDE_FROM_SPAN) +
                        ". NOT a self-report: an agent's own clock has been wrong by 2.3x.",
    }


# The directory the PAYLOAD lands in, which is the run directory by definition. This used to
# be `dirname(--stats)`, and under anchor.py's layout that is `report/` -- five files written
# inside one second. Every run_cost.wall it produced read `started == ended, seconds: 0`, for
# runs whose artifacts really spanned minutes. A cold run had to compute its own by hand and
# said so in the field's `derived_from`, which is the only reason it was caught.
# Computed below, once `out` is resolved: the span's root is the directory the payload lands
# in, and that is not known until the destination is.
_span = None

skeleton = {
    "schema_version": "1",
    # `ref` is the PIN and `measured_ref` is what the pipeline actually ran against. They are
    # separate fields because they answer different questions and used to answer one: with
    # only `ref`, emit-gate compared the pin against the pin.
    "tool": {"name": "xl-ai-insights", "ref": ref, "contract": contract,
             "measured_ref": anchored.get("measured_ref")},
    "corpus": {
        "tool_calls": tool_calls,
        "sessions": sessions,
        "sidechain_share": round(sidechain / tool_calls, 4) if tool_calls else None,
        "window": f"{args.since} -> {args.until} (fixed)",
        "sources": sources or ["unstated: the payload carries no per-source block"],
    },
    "anchor": {"published": anchored.get("published"), "reproduced": reproduced,
               "ok": anchored.get("ok"), "note": ""},
    # What the audit itself cost, in units rather than in prose. `process_friction[].cost`
    # is the only other place cost appears and it holds strings like "four re-runs", which
    # cannot be compared between two runs.
    "run_cost": {
        "wall": _span,
        "checks": None,      # fill from run-checks.py's "wall clock Ns" line
        "arms": None,        # fill from run-arms.py's, when an A/B ran
        "adhoc_checks": None,
    },
    "axes": [],
    "findings": [],
    "not_raised": [],
    "reported": [],
    "dismissed": [],
    "process_friction": [],
}

out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.stats or ".")),
                               f"miraudit-{args.until}.json")
_run_dir = os.path.dirname(os.path.abspath(out))
_span = run_span(_run_dir) if os.path.isdir(_run_dir) else None
skeleton["run_cost"]["wall"] = _span

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
print("\n  The other buckets need these beyond an id, and nothing used to say so. A cold run\n"
      "  paid a refused render plus a grep through emit-gate.py to find out:\n")
for _bucket, _keys in (("reported[]", _gate.REPORTED_KEYS),
                       ("dismissed[]", _gate.DISMISSED_KEYS),
                       ("process_friction[]", _gate.FRICTION_KEYS)):
    print(f"    {_bucket:32} {', '.join(_keys)}")
print("\n  process_friction is the one the gate does not enforce: those three are what\n"
      "  render-report.py reads, so an entry missing them renders blank rather than being\n"
      "  refused, which is worse.")
print("\n  Said here for the same reason as the rows above. A run added its first\n"
      "  not_raised entry, learned these existed by being refused at the gate, and paid a\n"
      "  render cycle for it.")
print("\n  NOT CHECKED: whether the window you passed is the one the report used. This "
      "reads\n  the anchored run you point it at and cannot tell a right window from a "
      "wrong one.")
