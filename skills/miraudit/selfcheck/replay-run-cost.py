"""new-run.py's run_cost.wall: the run's real duration, derived instead of self-reported.

A cold run's self-reported clock came in inflated 2.3x BOTH times anyone checked it -- it
said 45 minutes for runs that took 19.4 and 19.9. The payload had nowhere to put the real
figure, so the correction lived in a markdown file and could not prevent a third one.

new-run.py walks the corpus at import, so this drives it as a subprocess. That is also the
honest level: the defect this guards against is a directory-walk exclusion, not a function.
"""
import json
import os
import subprocess
import sys
import time
import harness

NEEDS = ("checkout",)

REAL_SECONDS = 900


def _run_dir(root, anchor_age_days=3):
    """A run directory whose artifacts span REAL_SECONDS, plus the checkout/ trap.

    `checkout/` holds a `git archive` extraction, and those files carry the COMMIT's date --
    one real run's raw span read 47 HOURS because of it, and against the current layout a walk
    excluding only the old `anchor/` name read NINE DAYS. The fixture plants the trap on
    purpose: a span that includes it cannot come out right.
    """
    # anchor.py's REAL layout: the pipeline's output goes to <work>/report/ and the checkout
    # copy to <work>/checkout/. This fixture used to drop stats.json in the run root, which is
    # a shape no run produces -- and that is why these checks were green against a span that
    # was structurally ZERO. new-run.py derived the span from dirname(--stats), which under the
    # real layout is `report/`: five files written inside one second. A fixture shaped
    # differently from the artifact cannot see a defect that is about the shape.
    os.makedirs(os.path.join(root, "checkout"), exist_ok=True)
    os.makedirs(os.path.join(root, "report"), exist_ok=True)
    base = time.time() - REAL_SECONDS
    for name, when in (("report/stats.json", base), ("report.md", base + REAL_SECONDS)):
        path = os.path.join(root, name)
        with open(path, "w") as fh:
            fh.write("{}" if name.endswith(".json") else "x")
        os.utime(path, (when, when))
    trap = os.path.join(root, "checkout", "archived.py")
    with open(trap, "w") as fh:
        fh.write("x")
    old = base - anchor_age_days * 86400
    os.utime(trap, (old, old))
    return root


def _emit(t, root):
    """Drive new-run.py against an EMPTY corpus.

    It walks the corpus for the fingerprint, and pointing it at the real one made each of
    these checks take eight seconds and depend on whose machine it ran on. An empty
    directory satisfies needs_corpus (the requirement is that it exists), produces a zero
    fingerprint, and leaves run_cost -- the thing under test -- untouched.
    """
    out = os.path.join(root, "miraudit-probe.json")
    empty_corpus = os.path.join(os.path.dirname(root.rstrip("/")), "empty-corpus")
    os.makedirs(empty_corpus, exist_ok=True)
    subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, "new-run.py"),
         "--checkout", t.checkout, "--corpus", empty_corpus,
         "--stats", os.path.join(root, "report", "stats.json"),
         "--since", "2026-07-13", "--until", "2026-08-12", "--out", out],
        capture_output=True, text=True, timeout=300)
    if not os.path.exists(out):
        t.failures.append("new-run.py wrote no payload at all")
        return None
    return json.load(open(out))


def check_the_payload_has_a_slot_for_what_the_run_cost(t):
    with harness.tmpdir() as d:
        doc = _emit(t, _run_dir(d))
        if doc is None:
            return
        t.equal("run_cost" in doc, True, "the skeleton carries run_cost")
        t.equal(sorted(doc["run_cost"]), ["adhoc_checks", "arms", "checks", "wall"],
                "with a slot for each mechanism's own counter, not just a total")


def check_the_duration_is_derived_not_reported(t):
    with harness.tmpdir() as d:
        doc = _emit(t, _run_dir(d))
        if doc is None:
            return
        wall = (doc.get("run_cost") or {}).get("wall")
        t.equal(bool(wall), True, "a run with artifacts gets a wall block")
        if wall:
            t.equal(abs(wall["seconds"] - REAL_SECONDS) <= 2, True,
                    "and it equals the real span (%ss), got %ss"
                    % (REAL_SECONDS, wall.get("seconds")))
            t.contains(wall.get("derived_from", ""), "mtimes",
                       "and says where it came from, so nobody reads it as a self-report")


def check_the_anchor_copy_does_not_inflate_the_span(t):
    """The trap, isolated. Without the exclusion this reads three days instead of fifteen
    minutes -- and the number would still print, which is how the 47-hour span happened.
    """
    with harness.tmpdir() as d:
        doc = _emit(t, _run_dir(d, anchor_age_days=3))
        if doc is None:
            return
        wall = (doc.get("run_cost") or {}).get("wall") or {}
        t.equal(wall.get("seconds", 0) < 86400, True,
                "a checkout copy stamped three days ago does not become the run's duration")


def check_a_run_with_nothing_to_span_says_none(t):
    # One artifact cannot span anything. Reporting 0 seconds would be a measurement; None is
    # the honest answer, and the field being present-but-null is what makes it visible.
    with harness.tmpdir() as d:
        os.makedirs(os.path.join(d, "report"), exist_ok=True)
        with open(os.path.join(d, "report", "stats.json"), "w") as fh:
            fh.write("{}")
        doc = _emit(t, d)
        if doc is None:
            return
        t.equal((doc.get("run_cost") or {}).get("wall"), None,
                "a single artifact yields null, not a fabricated zero")
