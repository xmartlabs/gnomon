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


# ---- run_cost.phases: one measured phase, one residual -----------------------------------
# anchor.py times its own shell-out to the external scoring pipeline (Phase 0) and writes it
# into anchor.json as `pipeline_seconds`. That is the ONLY phase boundary with a real
# timestamp on either side. Everything from there to the final payload write (Phases 1-5:
# checks, structural shapes, refutation, emit, send) has no artifact to mark a boundary in
# between -- render-report.py overwrites the same payload file on every synthesis pass, so
# the file's own mtime span between "skeleton created" and "final write" collapses to zero by
# construction, not because synthesis took no time. `4_synthesis` is therefore `wall.seconds
# minus 0_anchor`, a subtraction against the one real span (`wall`) and the one real
# measurement (`0_anchor`) -- never derived from mtimes, and never a fabricated 0 or a
# negative number when an input is missing.
def run_cost_phases(wall, pipeline_seconds):
    anchor = pipeline_seconds if isinstance(pipeline_seconds, (int, float)) \
        and not isinstance(pipeline_seconds, bool) else None
    wall_seconds = wall.get("seconds") if wall else None
    synthesis = None
    if anchor is not None and isinstance(wall_seconds, (int, float)):
        synthesis = round(wall_seconds - anchor, 1)
    return {"0_anchor": anchor, "4_synthesis": synthesis}


def run_span(root, label="the output directory"):
    """(earliest, latest, seconds) over ONE root's own artifacts, or None when there are
    fewer than two to span. `label` names that root in `derived_from` -- when
    `_combine_spans` below falls back to a single side (the other root had nothing to span),
    the returned dict is this function's unmodified output, so it has to name the right root
    itself rather than default to "the output directory" when it is actually the anchor-work
    root that produced the only surviving span."""
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
        "derived_from": f"mtimes of {label}, excluding " +
                        "/".join(EXCLUDE_FROM_SPAN) +
                        ". NOT a self-report: an agent's own clock has been wrong by 2.3x.",
    }


# A 2026-08-24 cold run pointed anchor.py's own work directory at a dispatched agent's session
# scratchpad while --out pointed the payload at a separate miraudit-runs/ directory -- exactly
# how this project's own CLAUDE.md ("Metodo para el A/B") already stages a fresh checkout copy
# apart from where a run's artifacts are meant to land. run_span(_run_dir) alone never walks
# the scratchpad at all, so anchor.json's mtime (15:04:44) was structurally invisible to a span
# that only ever saw the payload directory's earliest file (15:07:17, 153 seconds later). With
# `4_synthesis = wall.seconds - 0_anchor` that produced `-34.0`, a structurally impossible
# number that shipped into the rendered report undetected. _combine_spans unions the two roots
# so the earlier of the two directories' earliest files always anchors `started`.
def _combine_spans(a, b):
    if a is None:
        return b
    if b is None:
        return a
    lo = min(datetime.datetime.fromisoformat(a["started"]).timestamp(),
             datetime.datetime.fromisoformat(b["started"]).timestamp())
    hi = max(datetime.datetime.fromisoformat(a["ended"]).timestamp(),
             datetime.datetime.fromisoformat(b["ended"]).timestamp())
    return {
        "started": datetime.datetime.fromtimestamp(lo, datetime.timezone.utc)
                   .isoformat(timespec="seconds"),
        "ended": datetime.datetime.fromtimestamp(hi, datetime.timezone.utc)
                 .isoformat(timespec="seconds"),
        "seconds": int(round(hi - lo)),
        "derived_from": "mtimes of TWO directories -- the output directory and the "
                        "anchor-work root named by --stats -- excluding " +
                        "/".join(EXCLUDE_FROM_SPAN) +
                        " in each. NOT a self-report: an agent's own clock has been wrong by "
                        "2.3x.",
    }


# The directory the PAYLOAD lands in, which is the run directory by definition. This used to
# be `dirname(--stats)`, and under anchor.py's layout that is `report/` -- five files written
# inside one second. Every run_cost.wall it produced read `started == ended, seconds: 0`, for
# runs whose artifacts really spanned minutes. A cold run had to compute its own by hand and
# said so in the field's `derived_from`, which is the only reason it was caught.
# Computed below, once `out` is resolved: the span's root is the directory the payload lands
# in, and that is not known until the destination is. Since 2026-08-24 it is a union with a
# second root, dirname(--stats), for the run where that is a different directory -- see
# _combine_spans above.
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
        # One measured phase and one residual, see run_cost_phases() above. Filled below,
        # once `wall` (the residual's other input) is itself final.
        "phases": {"0_anchor": anchored.get("pipeline_seconds"), "4_synthesis": None},
        # {"unit": "seconds"|"count", "value": N}, or None if not measured. A bare number used
        # to go here, and two saved runs wrote the same field with two different meanings under
        # it: 13 as a COUNT of checks, 101.3 as SECONDS of wall clock. emit-gate.py now refuses
        # the bare form.
        "checks": None,      # fill from run-checks.py's "wall clock Ns" line: {"unit": "seconds", "value": N}
        "arms": None,        # fill from run-arms.py's, when an A/B ran: {"unit": "seconds", "value": N}
        "adhoc_checks": None,  # a count of ad-hoc checks written this run: {"unit": "count", "value": N}
    },
    "axes": [],
    "findings": [],
    "not_raised": [],
    # Two saved cold runs each failed emit-gate.py once here, both times by guessing a field
    # name instead of reading output-schema.md's worked example: "status"/"note" where the
    # schema wants "state"/"confirmed_by", and a cost_units.unit outside its closed
    # vocabulary. The shapes below are that worked example, not invented.
    "reported": [],         # one entry: {"id": ..., "confirmed_by": "...", "state": "..."}
    "dismissed": [],        # one entry: {"id": ..., "killed_by": "..."}
    "process_friction": [],  # one entry: {"phase": "...", "what": "...", "cost": "...",
                             #             "cost_units": {"unit": "runs"|"renders"|"minutes"
                             #                            |"seconds"|"none", "value": N}}
}

out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.stats or ".")),
                               f"miraudit-{args.until}.json")
_run_dir = os.path.dirname(os.path.abspath(out))
_span_run = run_span(_run_dir) if os.path.isdir(_run_dir) else None

# The second root: dirname(--stats), the SAME directory anchor.json is read from above. When
# --out is left to default, this equals _run_dir by construction and the union below is a
# no-op -- every run before 2026-08-24 took that path. Only spanned when it is a real,
# existing directory distinct from _run_dir, so a run with no --stats at all (or one that
# lands beside the payload, the common case) never gets a phantom second span.
_span_stats = None
if args.stats:
    _stats_dir = os.path.dirname(os.path.abspath(args.stats))
    if os.path.isdir(_stats_dir) and os.path.abspath(_stats_dir) != os.path.abspath(_run_dir):
        _span_stats = run_span(_stats_dir, label="the anchor-work root (--stats's directory)")

_span = _combine_spans(_span_run, _span_stats)
skeleton["run_cost"]["wall"] = _span
skeleton["run_cost"]["phases"] = run_cost_phases(_span, anchored.get("pipeline_seconds"))

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
