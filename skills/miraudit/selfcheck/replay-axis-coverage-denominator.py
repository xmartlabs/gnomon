"""axis-coverage.py's denominator: the axes aq.py DECLARES, not the ones the payload scored.

This was the largest hole the skill had, and it was invisible for the same reason all of them
are invisible: the denominator came from the thing being measured. An axis withheld upstream
never reaches the payload, so it could never appear as uncovered, and the manifest printed
`11/11 covered, 0/350 base points not` while Steering leverage -- base weight 50, tied for the
heaviest axis in the tool -- had no check at all. It appeared under DROPPED OR RENORMALIZED,
which reads as a footnote.

Driven as a subprocess against a SYNTHETIC checkout and a synthetic payload, so the numbers are
small enough to assert exactly. A fixture whose expected answer is "12" is worth more here than
the real corpus, where the answer moves whenever upstream does.
"""
import json
import os
import subprocess
import sys
import harness

NEEDS = ()

# Three axes declared; the payload scores two. The third is the shape of a withheld axis.
AQ_SOURCE = '''
def compute_aq(b, st, tools):
    craft = [
        ("Alpha", 30, alpha, {}),
        ("Beta", 20, beta, {}),
    ]
    efficiency = [
        ("Gamma", 50, gamma, {}),
    ]
'''


def _checkout(root):
    path = os.path.join(root, "checkout")
    scoring = os.path.join(path, "gnomon", "scoring")
    os.makedirs(scoring)
    with open(os.path.join(scoring, "aq.py"), "w") as fh:
        fh.write(AQ_SOURCE)
    return path


def _stats(root, scored):
    path = os.path.join(root, "stats.json")
    with open(path, "w") as fh:
        json.dump({"agentic": {"pillars": [{"name": "Craft", "axes": scored}]}}, fh)
    return path


def _tagging_scripts(root, axes):
    """A scripts dir whose files claim `axes`, so the fixture can separate covered from not.

    Without this every axis came out uncovered and the shortfall was the whole declared total,
    which satisfied a 'the withheld axis is short' assertion for the wrong reason.
    """
    path = os.path.join(root, "scripts")
    os.makedirs(path, exist_ok=True)
    for i, axis in enumerate(axes):
        with open(os.path.join(path, "verify-fixture-%d.py" % i), "w") as fh:
            fh.write("# miraudit-covers: %s\n" % axis)
    return path


def _run(root, scored, tags=("Alpha", "Beta")):
    empty = os.path.join(root, "empty-corpus")
    os.makedirs(empty, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, "axis-coverage.py"),
         "--checkout", _checkout(root), "--corpus", empty,
         "--since", "2026-07-13", "--until", "2026-08-12",
         "--scripts-dir", _tagging_scripts(root, tags),
         "--stats", _stats(root, scored)],
        capture_output=True, text=True, timeout=120)
    return proc.stdout + proc.stderr


def _two_scored():
    return [{"name": "Alpha", "base_weight": 30, "weight": 30, "normalized_score": 1.0},
            {"name": "Beta", "base_weight": 20, "weight": 20, "normalized_score": 1.0}]


def check_the_denominator_counts_declared_axes_not_scored_ones(t):
    with harness.tmpdir() as d:
        out = _run(d, _two_scored())
        t.contains(out, "/3 DECLARED axes",
                   "the denominator is the three axes aq.py declares")
        t.absent(out, "/2 scored axes",
                 "and not the two the payload happened to score")


def check_the_withheld_axis_counts_as_uncovered(t):
    # The point of the whole change. Gamma is declared, withheld, and claimed by nothing, so
    # it is uncovered -- not a footnote about weight redistribution.
    with harness.tmpdir() as d:
        out = _run(d, _two_scored())
        head, _, tail = out.partition("NOT COVERED")
        t.equal(bool(tail), True, "there is a NOT COVERED section")
        t.contains(tail.split("DROPPED")[0], "Gamma",
                   "the withheld axis is listed as uncovered")
        t.contains(out, "50/100 base points not",
                   "and its weight counts against the declared total, not the scored one")


def check_a_withheld_axis_is_named_as_withheld(t):
    # Uncovered and withheld are different facts and the report owes both: nobody can write a
    # check for an axis by reading a line that only says "uncovered".
    with harness.tmpdir() as d:
        out = _run(d, _two_scored())
        t.contains(out, "withheld upstream and never reaches the payload",
                   "the report says WHY it never appeared before")
        t.contains(out, "Gamma", "and names it")


def check_a_fully_scored_payload_reports_no_shortfall(t):
    # CONTROL. Without it every assertion above is satisfied by a script that always claims a
    # missing axis. Score all three and the shortfall must go to zero.
    with harness.tmpdir() as d:
        out = _run(d, _two_scored() + [
            {"name": "Gamma", "base_weight": 50, "weight": 50, "normalized_score": 1.0}],
            tags=("Alpha", "Beta", "Gamma"))
        t.contains(out, "0/100 base points not",
                   "CONTROL: nothing withheld means nothing short")
        t.absent(out, "withheld upstream and never",
                 "and no withheld line is printed")
