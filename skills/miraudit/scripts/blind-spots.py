"""What this run did not touch, compared against the holes earlier runs already declared.

    python3 blind-spots.py --run <miraudit-<date>.json> [--saturation <saturation.json>]
                           [--checkout <copy>] [--update <runs dir>]

There is NO browse mode, and that is the design rather than an omission. You cannot ask this
what the known blind spots are; you can only ask what your FINISHED payload missed. A cold run
that reads a list of holes before measuring stops measuring and starts confirming -- it happened
here, with `known-state.md`, and the run said so itself: reading it during Phase 0 anchored the
investigation before a single number existed.

The registry carries KEYS ONLY. No `what`, no `why`, not one sentence. An agent that sees
`Compounding/other-backend/add_memory` learns that somebody once wondered about a backend, and
cannot learn a hypothesis, a magnitude or a direction from it. That is what makes the rule above
structural instead of a matter of anybody's discipline, and it is checked: a registry entry
carrying prose is a violation.

Identity is DERIVED, never typed. A blind spot's key is `<anchor>/<kind>/<term>`, where the
anchor comes from where the entry sits in the payload -- the axis it hangs off, or a finding's
surface. Across the saved runs one hole carries sixteen wordings and one finding carries five
different hand-typed ids; nothing that keys on prose or on `id` could ever have counted them.

Exit 1 only for a reopening condition this run's own corpus already meets. Everything else is a
printed line. A run that discovers a NEW hole is never failed for it: failing that would punish
exactly the run that found something, and would turn the registry into guidance by the back door.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import require  # noqa: E402
from importlib.machinery import SourceFileLoader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
_gate = SourceFileLoader("emit_gate_bs", os.path.join(HERE, "emit-gate.py")).load_module()

REGISTRY = os.path.join(os.path.dirname(HERE), "references", "blind-spots.json")

# The only keys an entry may carry. `why`, `what`, `note` and friends are rejected on purpose:
# this is the check that stops the anchoring hazard creeping back one helpful sentence at a time.
ENTRY_KEYS = {"id", "anchor", "kind", "term", "runs", "first_seen", "last_seen", "reopens_when"}
NOISE_CAP = 3


def load_registry(path=REGISTRY):
    if not os.path.exists(path):
        return [], [f"no registry at {path}; nothing to compare against"]
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    entries = doc.get("entries") or []
    bad = []
    for i, e in enumerate(entries):
        extra = sorted(set(e) - ENTRY_KEYS)
        if extra:
            bad.append(f"entries[{i}] carries {extra}, which is prose or provenance the "
                       "registry must not hold. Keys only -- a sentence here is a hypothesis "
                       "a cold run can adopt before measuring anything.")
        if e.get("kind") and e["kind"] not in _gate.BLIND_SPOT_KINDS:
            bad.append(f"entries[{i}] kind {e.get('kind')!r} is outside the vocabulary "
                       f"{sorted(_gate.BLIND_SPOT_KINDS)}")
    return entries, bad


def key_of(anchor, kind, term):
    return "/".join(x for x in (anchor, kind, term) if x)


def keys_in(doc):
    """Every (key, anchor) this payload declares, derived from position and `kind`.

    A bare string stays legal forever: 29 payloads on disk are bare strings and the shipped
    example run would otherwise fail its own gate. Those are unkeyed and counted as such, in
    ONE summary line rather than one line each.
    """
    keyed, unkeyed = set(), 0

    def walk(entries, anchor):
        nonlocal unkeyed
        for nc in entries or []:
            if isinstance(nc, dict) and nc.get("kind"):
                keyed.add(key_of(anchor, nc.get("kind"), nc.get("term")))
            else:
                unkeyed += 1

    for axis in doc.get("axes") or []:
        walk(axis.get("not_checked"), axis.get("name"))
    for bucket in ("findings", "not_raised", "reported"):
        for f in doc.get(bucket) or []:
            anchor = (f.get("axes") or [None])[0] or f.get("surface")
            walk(f.get("not_checked"), anchor)
    return keyed, unkeyed


def met_conditions(entries, doc, saturation, checkout):
    """Reopening conditions this run's own corpus already satisfies.

    The highest-value half and the least obvious. Several recorded conditions reduce to `a
    corpus arrives whose signals sit BELOW one of the pinned thresholds`, which is decidable
    from artifacts the run already produced -- and on the corpus this was written against it
    was true five times over while sixteen runs re-declared the same hole as still open.

    The run's own `reconsider_if` prose is never parsed. The predicate hangs off the key.
    """
    met, unevaluable, notes = [], [], []
    # require() imports out of the CHECKOUT, and this script does not go through parse(), which
    # is what normally puts it on the path. Without this the constant read as "gone from aq.py"
    # -- a rename report on a checkout where nothing had been renamed, which is the wrong-fire
    # this whole predicate has to avoid.
    if checkout and checkout not in sys.path:
        sys.path.insert(0, os.path.expanduser(checkout))
    below = {}
    if saturation:
        for row in (saturation.get("signals_cut") or []):
            if "above_threshold" in row:
                below[row.get("signal") or row.get("name")] = not row["above_threshold"]
    for e in entries:
        cond = e.get("reopens_when")
        if not cond:
            continue
        kind = cond.get("kind")
        if kind == "signal_below_threshold":
            sig = cond.get("signal")
            if sig not in below:
                unevaluable.append((e["id"], f"saturation.json carries no row for {sig}"))
                continue
            if below[sig]:
                met.append((e["id"], f"{sig} is below its threshold "
                                     f"({cond.get('threshold')}) on this corpus"))
        elif kind == "constant_equals":
            if not checkout:
                unevaluable.append((e["id"], "no --checkout, so the constant was not read"))
                continue
            name = cond.get("constant")
            try:
                (value,) = require([("gnomon.scoring.aq", name)],
                                   f"{name} is gone from aq.py")
            except SystemExit:
                # A rename must ERROR, never answer wrongly -- but it degrades to a note, not
                # a gate failure, because the run did nothing wrong and the cheapest escape
                # from a wrong failure is editing the registry, which would make this a thing
                # runs edit to go green.
                notes.append(f"{e['id']}: {name} is not in aq.py any more, so its reopening "
                             "condition could not be evaluated. Re-read the registry row.")
                continue
            if value == cond.get("value"):
                met.append((e["id"], f"{name} is {value!r}, which is the value the row "
                                     "names as reopening it"))
        else:
            unevaluable.append((e["id"], f"predicate kind {kind!r} is not implemented"))
    return met, unevaluable, notes


def report(doc, saturation=None, checkout=None, path=REGISTRY):
    """Returns (violations, lines). Only a met reopening condition is a violation."""
    entries, bad = load_registry(path)
    lines, violations = [], list(bad)
    if not entries:
        return violations, lines

    keyed, unkeyed = keys_in(doc)
    known = {e["id"]: e for e in entries}
    new = sorted(keyed - set(known))
    touched = {a.get("name") for a in doc.get("axes") or []}

    met, unevaluable, notes = met_conditions(entries, doc, saturation, checkout)
    for ident, why in met:
        violations.append(
            f"blind-spots: {ident} names a reopening condition this run's own corpus meets "
            f"-- {why}. The payload contradicts itself: it carries the observation the entry "
            "said would reopen it. Raise it, or rewrite why it stays closed.")

    # (a) an axis touched with none of its known holes recorded. Note, not failure: a run that
    # re-measured the axis and satisfied itself may stop declaring; forcing re-declaration
    # produces copy-paste, which is how 228 clusters happened in the first place.
    silent = sorted({e["anchor"] for e in entries
                     if (e.get("runs") or 0) >= 3 and e["anchor"] in touched
                     and not any(k.startswith(e["anchor"] + "/") for k in keyed)})
    for anchor in silent[:NOISE_CAP]:
        lines.append(f"  {anchor}: measured here, and none of its recorded holes were "
                     "declared. Re-measuring past one is fine; not saying so is not.")

    # (c) declared many times and still with no predicate that could close it. Goes silent for
    # good the moment somebody writes one, which is the only kind of rule that stays read.
    stuck = sorted((e for e in entries
                    if (e.get("runs") or 0) >= 10 and not e.get("reopens_when")),
                   key=lambda e: -(e.get("runs") or 0))
    for e in stuck[:NOISE_CAP]:
        lines.append(
            f"  {e['id']}: declared in {e['runs']} runs and still has no `reopens_when`. "
            "Writing one is a change to references/blind-spots.json — the SKILL, not this run "
            "— so it is not something this audit can close. Say so and move on, or open the "
            "file.")

    lines += [f"  {n}" for n in notes]
    lines.append(
        f"  blind spots: {len(keyed & set(known))} keyed, {unkeyed} unkeyed, "
        f"{len(new)} new{' (' + ', '.join(new[:2]) + ')' if new else ''}; "
        f"{len(met)} reopen conditions met "
        f"({len([e for e in entries if e.get('reopens_when')]) - len(unevaluable)} evaluated, "
        f"{len(unevaluable)} not evaluable).")
    # Naming them, not counting them. A signal saturation-counterfactual does not emit cannot
    # be judged here, and the answer is to widen that ONE implementation of "below its
    # threshold" rather than to write a second one in this file -- which is how the two halves
    # of every other pair in this skill drifted apart.
    for ident, why in unevaluable[:NOISE_CAP]:
        lines.append(f"  NOT EVALUABLE {ident}: {why}")
    return violations, lines


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    def flag(name):
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else None
        return None

    run = flag("--run")
    if not run:
        sys.exit(__doc__.strip().splitlines()[0] + "\n\n"
                 "error: --run is required. There is no browse mode on purpose: this answers "
                 "what your finished payload missed, and cannot be asked what the holes are.")
    with open(os.path.expanduser(run)) as fh:
        doc = json.load(fh)
    sat = None
    if flag("--saturation") and os.path.exists(os.path.expanduser(flag("--saturation"))):
        with open(os.path.expanduser(flag("--saturation"))) as fh:
            sat = json.load(fh)
    violations, lines = report(doc, sat, flag("--checkout"))
    for line in lines:
        print(line)
    for v in violations:
        print(f"  VIOLATION {v}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
