"""The three synthetic-fixture checks: do they still run with no corpus, and do their
controls still fire?

Not a re-test of gnomon -- a test that OUR wiring is right. These build their events in
memory and never open a transcript, but _common.parse() required the corpus anyway, which is
what kept them out of any offline tier. This file is the regression guard for that change.

They need a gnomon checkout because they import Accumulator, and stubbing it would test the
stub. So: no corpus, no network, no tokens, one read-only directory.
"""
import os
import subprocess
import sys
import harness

NEEDS = ("checkout",)

FIXTURE_CHECKS = ("verify-fanout-fix.py", "verify-compounding-symmetry.py",
                  "verify-routing-orphan-gate.py")
NO_CORPUS = "/definitely/not/a/corpus"


def _run(t, name, extra=()):
    proc = subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, name),
         "--checkout", t.checkout, "--corpus", NO_CORPUS, "--until", "2026-08-12", *extra],
        capture_output=True, text=True, timeout=120)
    return proc


def check_the_three_run_with_no_corpus(t):
    for name in FIXTURE_CHECKS:
        proc = _run(t, name)
        t.equal(proc.returncode, 0,
                "%s runs against a corpus path that does not exist" % name)
        t.absent(proc.stdout + proc.stderr, "corpus not found",
                 "%s does not refuse an input it never reads" % name)


def check_a_corpus_reading_check_still_requires_it(t):
    # CONTROL, and the load-bearing half. Without it, "they run with no corpus" could mean
    # the requirement was dropped for all 28 scripts instead of for the three that earn it.
    proc = _run(t, "fidelity-audit.py")
    t.equal(proc.returncode != 0, True,
            "CONTROL: a check that DOES walk the corpus still refuses a missing one")
    t.contains(proc.stdout + proc.stderr, "corpus not found",
               "and says so, rather than measuring nothing")


def check_the_fixture_controls_still_fire(t):
    """Their controls are what make their numbers mean anything, so a checkout where a
    control moved must not be reported as a pass."""
    proc = _run(t, "verify-fanout-fix.py")
    t.contains(proc.stdout, "CONTROL", "verify-fanout-fix prints its controls")
    t.absent(proc.stdout, "[??]", "and none of its cases came out unexpected")

    proc = _run(t, "verify-compounding-symmetry.py")
    t.contains(proc.stdout, "CONTROL", "verify-compounding-symmetry prints its controls")
    t.absent(proc.stdout, "[??]",
             "and every case matched the credit count written beside it -- these were "
             "printed and never compared until this run")

    proc = _run(t, "verify-routing-orphan-gate.py")
    t.contains(proc.stdout, "control", "verify-routing-orphan-gate names its control case")


def check_the_window_flags_are_honoured_not_just_accepted(t):
    """verify-fanout-fix records that an earlier version parsed the window flags and ignored
    them. Nothing detects a relapse, so: two different windows must produce two different
    banners."""
    a = _run(t, "verify-fanout-fix.py").stdout
    b = subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, "verify-fanout-fix.py"),
         "--checkout", t.checkout, "--corpus", NO_CORPUS, "--until", "2026-06-30"],
        capture_output=True, text=True, timeout=120).stdout
    line_a = next((l for l in a.splitlines() if l.startswith("window:")), "")
    line_b = next((l for l in b.splitlines() if l.startswith("window:")), "")
    t.equal(bool(line_a) and bool(line_b), True, "both runs print a window banner")
    t.equal(line_a != line_b, True,
            "and a different --until produces a different one, so the flag is read")
