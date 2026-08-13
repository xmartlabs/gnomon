"""Refuses to let a run emit a finding that did not survive Phase 3.

    python3 emit-gate.py <miraudit-<date>.json>

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


def check(doc):
    bad = []

    def fail(where, msg):
        bad.append(f"{where}: {msg}")

    anchor = doc.get("anchor") or {}
    if anchor.get("ok") is False and doc.get("findings"):
        fail("anchor", "ok is false and findings[] is not empty. Phase 0 is a gate: if the "
                       "base run does not reproduce the published number, every finding is "
                       "unsafe to read and none should be emitted.")

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
    if len(argv) != 2:
        sys.exit(__doc__)
    path = argv[1]
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read {path}: {exc}")
        return 2

    bad = check(doc)
    print(f"emit gate: {os.path.basename(path)}")
    print(f"  findings {len(doc.get('findings', []))}  "
          f"not_raised {len(doc.get('not_raised', []))}  "
          f"dismissed {len(doc.get('dismissed', []))}  "
          f"reported {len(doc.get('reported', []))}")
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
