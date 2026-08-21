"""contract-probe.py: how many predicates EXIST, not how many cases were written.

The probe printed `18/18 behaviours unchanged` and that figure was read -- in `anchor.py`'s
payload, in `known-state.md`, in the second-corpus write-ups -- as coverage of the predicate
surface. It never was. It counted its own case list against itself, so it read complete no
matter how much of `gnomon.taxonomy` had nothing pointed at it, and five public predicates that
reach a score had no case at all.

Same shape as the gate comparing the pin against the pin, and as axis-coverage taking its
denominator from the payload it was auditing. The denominator has to come from outside.

Needs a checkout because the probe imports gnomon.taxonomy for real -- which is the point: a
denominator derived from a stub would be the same defect wearing a different hat.
"""
import os
import re
import shutil
import subprocess
import sys
import harness

NEEDS = ("checkout",)


def _probe(t, extra=()):
    proc = subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, "contract-probe.py"),
         "--checkout", t.checkout, "--since", "2026-07-13", "--until", "2026-08-12", *extra],
        capture_output=True, text=True, timeout=180)
    return proc.stdout + proc.stderr, proc.returncode


def _fig(text, needle):
    for line in text.splitlines():
        if needle in line:
            m = re.search(r"(\d+)/(\d+)", line)
            if m:
                return int(m.group(1)), int(m.group(2))
    return None


def check_the_predicate_count_is_reported_at_all(t):
    text, code = _probe(t)
    t.equal(code, 0, "the probe passes against the pinned checkout")
    t.equal(_fig(text, "public predicates in gnomon.taxonomy") is not None, True,
            "the probe reports predicates covered out of predicates that exist")


def check_the_two_denominators_are_independent(t):
    # The load-bearing assertion. If the predicate count were derived from the case list it
    # would move with it and be the same self-referential number in new clothes. These count
    # different things and must be able to disagree.
    text, _ = _probe(t)
    cases = _fig(text, "behaviours unchanged")
    preds = _fig(text, "public predicates in gnomon.taxonomy")
    if not (cases and preds):
        t.failures.append("one of the two figures is missing")
        return
    t.equal(cases[1] != preds[1], True,
            "the case total and the predicate total are different numbers "
            f"(cases {cases[1]}, predicates {preds[1]})")


def check_the_predicate_total_matches_the_module(t):
    # Derived means derived: count the public functions in the real module and require the
    # probe's denominator to equal it. A hand-typed total would pass every other check here.
    text, _ = _probe(t)
    preds = _fig(text, "public predicates in gnomon.taxonomy")
    sys.path.insert(0, t.checkout)
    try:
        import inspect
        from gnomon import taxonomy as tax
        real = [n for n, f in inspect.getmembers(tax, inspect.isfunction)
                if not n.startswith("_") and getattr(f, "__module__", "") == tax.__name__]
    finally:
        sys.path.remove(t.checkout)
    t.equal(preds[1], len(real),
            "the denominator equals the module's public predicate count")


def check_every_predicate_has_a_case_right_now(t):
    # Not a permanent invariant -- it is a statement about today, and the day it goes red is
    # the day somebody added a predicate. That is the notification this file exists to give.
    text, _ = _probe(t)
    preds = _fig(text, "public predicates in gnomon.taxonomy")
    t.equal(preds[0], preds[1],
            "every public predicate has at least one case (if this is red, taxonomy grew)")
    t.absent(text, "NO CASE AT ALL", "so nothing is listed as unprobed")


def check_deleting_a_case_lowers_the_count_and_names_the_predicate(t):
    """The derivation itself, exercised on a COPY.

    Every assertion above passes against a probe that simply declares all predicates probed,
    because today the honest answer is also "all of them" -- an injection proved it: replacing
    the derivation with `list(_public)` turned nothing red. A count that is right by accident
    is the self-referential denominator again, one level in.

    So: remove a case from a copy of the shipped file and require the number to follow. The
    shipped tree is never touched, same discipline as the A/B arms.
    """
    with harness.tmpdir() as d:
        copy_dir = os.path.join(d, "scripts")
        shutil.copytree(harness.SCRIPTS, copy_dir,
                        ignore=shutil.ignore_patterns("__pycache__"))
        target = os.path.join(copy_dir, "contract-probe.py")
        with open(target) as fh:
            body = fh.read()
        start = body.index('    ("a knowledge command is knowledge"')
        end = body.index('    ("a write tool classifies as produce"')
        t.equal(start < end, True, "the two cases to remove were found in the source")
        with open(target, "w") as fh:
            fh.write(body[:start] + body[end:])

        proc = subprocess.run(
            [sys.executable, target, "--checkout", t.checkout,
             "--since", "2026-07-13", "--until", "2026-08-12"],
            capture_output=True, text=True, timeout=180)
        text = proc.stdout + proc.stderr
        preds = _fig(text, "public predicates in gnomon.taxonomy")
        t.equal(preds[0], preds[1] - 1,
                "removing the only cases for one predicate drops the numerator by exactly one")
        t.contains(text, "NO CASE AT ALL", "and the gap is announced")
        t.contains(text, "bash_runs_knowledge", "naming the predicate that lost its cases")
        cases = _fig(text, "behaviours unchanged")
        t.equal(cases[0], cases[1],
                "CONTROL: the behaviour count is still whole, so the two are not one number")
