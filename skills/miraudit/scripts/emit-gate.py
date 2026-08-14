"""Refuses to let a run emit a finding that did not survive Phase 3.

    python3 emit-gate.py <miraudit-<date>.json> [--flags-dir <run>/checks]

Phase 3 says "Nothing is reported until it survives every row" and Phase 1 says the
per-axis scripts emit "candidates for Phase 3, never findings". Both were prose, in a
file the auditor had open, and a cold run promoted a candidate to findings[] anyway --
one whose own evidence said the fixture was the whole result while the payload pointed
at a different cause. Nothing chirped. It was caught by a person asking "is that
verified?", which is exactly the check that must not depend on someone remembering.

So the table becomes data. A finding carries `refuted`, with one entry per row and a
verdict in {pass, fail, n/a}. A `fail` means it did not survive, and a finding that did
not survive does not belong in findings[] -- it belongs in dismissed[] with the fact
that killed it. The gate cannot judge whether a note is honest; it can insist that the
row was answered at all, which is where the failure actually happened.

Exit codes: 0 clean, 1 violations found, 2 the file could not be read.
"""
import json
import os
import subprocess
import sys

# Keyed to the Phase 3 table in SKILL.md. Order is the table's order.
ROWS = {
    "window_or_corpus": "Does the window or corpus explain it, rather than the code?",
    "denominator_theirs": "Is the denominator theirs, or one you invented?",
    "fairest_operationalization": "Is the operationalization the fairest, or the flattering one?",
    "already_conceded": "Have you already conceded the opposite?",
    "paths_and_refs_exist": "Do the paths and refs you checked still exist?",
    "control_present": "Without the control, does the zero prove anything?",
    "tooling_reshaped_evidence": "Did your own tooling reshape the evidence first?",
    "one_condition_neutralized": "Several conditions can cause this. Does neutralizing ONE leave it unchanged?",
}
VERDICTS = {"pass", "fail", "n/a"}
SHAPES = {"dropped-term", "saturated", "contaminated-denominator",
          "signal-not-attributable-to-person", "signal-reused"}
DIRECTIONS = {"overestimates", "underestimates", "faithful"}
CONFIDENCE = {"fact", "hypothesis"}
BOUNDS = {"upper", "lower"}


FLAGS = {"grounding-diverged.json": "Grounding"}

HERE = os.path.dirname(os.path.abspath(__file__))


def pinned_ref():
    """The ref the ```pin block names, or None when it cannot be resolved.

    Asks pin-consistency.py rather than parsing known-state.md again. That file's own comment
    says why: a second copy of the parser is the same mistake it exists to remove, one level
    down. None is returned, not raised -- a gate that cannot find the pin should say so and
    keep checking everything else, the way it already handles a missing SKILL.md.
    """
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "pin-consistency.py"),
                            "--field", "ref"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    ref = r.stdout.strip()
    return ref if r.returncode == 0 and ref else None


def find_flags(doc_path, explicit=None):
    """Return (directory searched, {flag file: axis}) for the flags checks leave behind.

    A check that says "nothing below this line is usable" is telling the run something, and
    until now it told nobody: the message went to stdout and no gate read it. Making it a
    file is right and the path is where it goes wrong. The first version of this wrote the
    flag beside `--stats` and looked for it beside the run JSON, which in a real run are
    `anchored-payload/` and the run root, so it never fired once. Two conventions is the
    same as none, and it fails open, which is the worst direction for a gate to fail in.

    So: one order, stated, and the caller is told which directory answered.

    The order WALKS UP, and that is not tidiness. Fixing the two conventions left a second way
    to miss: `new-run.py` defaults the run JSON beside `--stats`, which is the anchored
    payload's directory, while `run-checks.py` leaves flags in the run root's `checks/`. Follow
    both defaults and the gate searched `anchor/report/checks`, found no directory, and passed
    a Grounding finding with a real flag two levels above it. A cold run found that, and it is
    the same fail-open this function was written to remove, arriving through a sibling's
    default path instead of through this one.
    """
    if explicit:
        roots = [os.path.abspath(os.path.expanduser(explicit))]
    else:
        base = os.path.dirname(os.path.abspath(doc_path)) if doc_path else os.getcwd()
        roots, node = [], base
        for _ in range(4):
            roots.append(os.path.join(node, "checks"))
            parent = os.path.dirname(node)
            if parent == node:
                break
            node = parent
        roots.append(base)
    for root in roots:
        found = {name: axis for name, axis in FLAGS.items()
                 if os.path.exists(os.path.join(root, name))}
        if found:
            return root, found
    existing = [r for r in roots if os.path.isdir(r)]
    return (existing[0] if existing else roots[-1]), {}


def check(doc, doc_path=None, flags_dir=None, notes=None):
    """Return the list of violations. `notes` is an optional list the caller passes in to
    collect the things this could NOT check, which is not the same as a pass and has to be
    printed rather than swallowed. Optional so that importing this module keeps working."""
    bad = []
    if notes is None:
        notes = []

    def fail(where, msg):
        bad.append(f"{where}: {msg}")

    searched, flagged = find_flags(doc_path, flags_dir)

    anchor = doc.get("anchor") or {}
    if anchor.get("ok") is False and doc.get("findings"):
        fail("anchor", "ok is false and findings[] is not empty. Phase 0 is a gate: if the "
                       "base run does not reproduce the published number, every finding is "
                       "unsafe to read and none should be emitted.")
    # A null anchor is the common case, not an oversight: most runs have no published figure
    # at the pinned contract to compare against, and second-corpus.md says a null is usable
    # for composition and shape while only a false disqualifies. Demanding `true` would stop
    # every run this skill can currently produce, and stop contributors entirely. What was
    # missing is not the pass, it is the reason -- so the reason is what this requires.
    elif anchor.get("ok") is not True and doc.get("findings"):
        if not (anchor.get("note") or "").strip():
            fail("anchor", f"ok is {anchor.get('ok')!r} and findings[] is not empty, with no "
                           "`note` saying why. A run that never compared against a published "
                           "number can still be worth emitting, and the reader has to be told "
                           "which it was. Write what was gated and what was not.")

    # Which ref the run measured is the frame for every number under it, so this is NOT gated
    # on findings[] the way the anchor rules above are: a run against the wrong checkout has
    # the wrong axes and the wrong dismissals too, and those are what an empty-findings run
    # publishes. The case: a run pointed the pipeline at the working checkout instead of a
    # copy of the pin, read a contract four commits ahead, gated everything on that, and said
    # so in `anchor.note` -- so "there is a note" would have passed it. Naming the ref is the
    # bar because a deliberate run at another ref can clear it in four words, and an accident
    # cannot clear it at all.
    tool_ref = ((doc.get("tool") or {}).get("ref") or "").strip()
    pin = pinned_ref()
    if pin is None:
        notes.append("the ```pin block could not be read, so `tool.ref` was not compared "
                     "against it. Everything else still ran.")
    elif not tool_ref:
        notes.append("the payload carries no `tool.ref`, so there was nothing to compare "
                     "against the pin.")
    elif not (tool_ref.startswith(pin) or pin.startswith(tool_ref)):
        note = (anchor.get("note") or "")
        if tool_ref not in note:
            fail("tool.ref", f"the run measured {tool_ref} and the pin is {pin}, and "
                             f"`anchor.note` does not name {tool_ref}. Either it measured a "
                             "checkout it did not mean to, or it re-pinned on purpose; the "
                             "file reads the same either way. If it was on purpose, say so in "
                             "the note and name the ref. If it was not, the axes and the "
                             "dismissals below are about a different version of the tool.")

    for i, f in enumerate(doc.get("findings", [])):
        w = f"findings[{i}] {f.get('id', '<no id>')}"
        if f.get("shape") not in SHAPES:
            fail(w, f"shape {f.get('shape')!r} is not one of the five Phase 2 keys")
        if f.get("direction") not in DIRECTIONS:
            fail(w, f"direction {f.get('direction')!r} is not one of {sorted(DIRECTIONS)}")
        if f.get("confidence") not in CONFIDENCE:
            fail(w, f"confidence {f.get('confidence')!r} is not 'fact' or 'hypothesis'. "
                    "A sentence of prose here is how a run hedges instead of deciding.")
        mag = f.get("magnitude") or {}
        if mag and mag.get("bound") is not None and mag.get("bound") not in BOUNDS:
            fail(w, f"magnitude.bound {mag.get('bound')!r} is not 'upper', 'lower' or absent")
        ev = f.get("evidence") or {}
        for k in ("command", "control", "output"):
            if not (ev.get(k) or "").strip():
                fail(w, f"evidence.{k} is empty. Report only findings carrying a "
                        "reproducible command and a control that passed.")
        if not f.get("not_checked"):
            fail(w, "not_checked is empty. A finding that claims complete coverage "
                    "without naming its blind spots is the failure mode to avoid.")
        # Optional here on purpose: this gate governs the audit artifact, and a run that
        # raises something for its own records does not owe anyone a closing condition.
        # render-issue.py requires it, because the message that goes out does.
        if "what_would_close_it" in f and not (f["what_would_close_it"] or "").strip():
            fail(w, "what_would_close_it is present but empty. Either write the observation "
                    "that would settle it either way, or leave the field out.")

        for flag, axis in flagged.items():
            if any(axis in a for a in f.get("axes") or []):
                fail(w, f"{flag} is in {searched}, so the check covering {axis} reported that "
                        "its own re-derivation disagrees with the tool's published figure. A "
                        "finding about that axis rests on a number this run could not "
                        "reproduce.")

        ref = f.get("refuted")
        if not isinstance(ref, dict):
            fail(w, "no `refuted` block. Phase 3 is not optional and not prose: answer "
                    f"all {len(ROWS)} rows with a verdict in {sorted(VERDICTS)}.")
            continue
        for key, question in ROWS.items():
            row = ref.get(key)
            if not isinstance(row, dict) or "verdict" not in row:
                fail(w, f"refuted.{key} unanswered — {question}")
                continue
            v = row.get("verdict")
            if v not in VERDICTS:
                fail(w, f"refuted.{key} verdict {v!r} is not one of {sorted(VERDICTS)}")
            elif v == "fail":
                fail(w, f"refuted.{key} is 'fail', so this did not survive Phase 3 and "
                        "does not belong in findings[]. Move it to dismissed[] with the "
                        f"fact that killed it. Row: {question}")
            if not (row.get("note") or "").strip():
                fail(w, f"refuted.{key} has no note. The verdict without the fact behind "
                        "it is the same unchecked claim in a smaller box.")

    # not_raised carries the same proof burden as findings -- it is a CONFIRMED finding
    # somebody chose not to send. Only the two judgement fields are extra.
    for i, f in enumerate(doc.get("not_raised", [])):
        w = f"not_raised[{i}] {f.get('id', '<no id>')}"
        for k in ("why_not", "reconsider_if"):
            if not (f.get(k) or "").strip():
                fail(w, f"{k} is empty. Without it this list is a graveyard the next run "
                        "re-derives from scratch, which is what the state exists to avoid.")
        ref = f.get("refuted")
        if not isinstance(ref, dict):
            fail(w, "no `refuted` block. Deciding not to send something is not a reason to "
                    "skip proving it: a finding nobody proved has not earned the right to "
                    "be remembered as true.")
        else:
            for key, question in ROWS.items():
                row = ref.get(key)
                if not isinstance(row, dict) or row.get("verdict") not in VERDICTS:
                    fail(w, f"refuted.{key} unanswered or invalid — {question}")

    for i, d in enumerate(doc.get("dismissed", [])):
        if not (d.get("killed_by") or "").strip():
            fail(f"dismissed[{i}] {d.get('id', '<no id>')}",
                 "killed_by is empty. Record the fact that killed it, not the verdict, "
                 "so nobody reopens it next month.")

    for i, r in enumerate(doc.get("reported", [])):
        for k in ("confirmed_by", "state"):
            if not (r.get(k) or "").strip():
                fail(f"reported[{i}] {r.get('id', '<no id>')}", f"{k} is empty")

    return bad


def main(argv):
    flags_dir = None
    argv = list(argv)
    if "--flags-dir" in argv:
        i = argv.index("--flags-dir")
        try:
            flags_dir = argv[i + 1]
        except IndexError:
            sys.exit("error: --flags-dir needs a path")
        del argv[i:i + 2]
    if len(argv) != 2:
        sys.exit(__doc__)
    path = argv[1]
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read {path}: {exc}")
        return 2

    notes = []
    bad = check(doc, doc_path=path, flags_dir=flags_dir, notes=notes)
    searched, flagged = find_flags(path, flags_dir)
    print(f"emit gate: {os.path.basename(path)}")
    print(f"  findings {len(doc.get('findings', []))}  "
          f"not_raised {len(doc.get('not_raised', []))}  "
          f"dismissed {len(doc.get('dismissed', []))}  "
          f"reported {len(doc.get('reported', []))}")
    # Said out loud because the alternative is failing open in silence: no flag file and no
    # directory reads exactly like a clean run, and a gate that cannot tell "nothing was
    # wrong" from "nobody looked" is not a gate.
    print(f"  check flags: {', '.join(flagged) if flagged else 'none'} "
          f"(looked in {searched}{'' if os.path.isdir(searched) else ', which does not exist'})")
    for n in notes:
        print(f"  note: {n}")
    if not bad:
        print("  clean. Every finding answered all eight Phase 3 rows.")
        print("  NOT CHECKED: whether the notes are true. This gate reads structure, not "
              "honesty -- it cannot tell a real refutation from a plausible sentence.")
        return 0
    print(f"\n  {len(bad)} violation(s) — nothing should be rendered from this file:\n")
    for b in bad:
        print(f"  - {b}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
