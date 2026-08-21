"""The two instruments that answered the same question and never compared answers.

`axis-coverage.py` counts axes; `axis-terms.py` counts the terms inside them. On the same run
Model mix and Orchestration come out COVERED in the first and NOT DECOMPOSABLE in the second --
a script tags the axis while nobody can rebuild its published score from its own parts. Both
sentences were printed, in two different reports, and the contradiction had to be noticed by a
person reading both. Eighty-three base points sat under it.

Offline: the join is a JSON handoff, so it needs neither corpus nor checkout to exercise. The
verdicts themselves are produced elsewhere and checked elsewhere.
"""
import json
import os
import subprocess
import sys
import harness

NEEDS = ()

AQ_SOURCE = '''
def compute_aq(b, st, tools):
    craft = [
        ("Alpha", 30, alpha, {}),
        ("Beta", 20, beta, {}),
    ]
'''


def _fixture(root, verdicts=None, tags=("Alpha", "Beta")):
    scoring = os.path.join(root, "checkout", "gnomon", "scoring")
    os.makedirs(scoring, exist_ok=True)
    with open(os.path.join(scoring, "aq.py"), "w") as fh:
        fh.write(AQ_SOURCE)
    scripts = os.path.join(root, "scripts")
    os.makedirs(scripts, exist_ok=True)
    for i, axis in enumerate(tags):
        with open(os.path.join(scripts, "verify-fixture-%d.py" % i), "w") as fh:
            fh.write("# miraudit-covers: %s\n" % axis)
    stats = os.path.join(root, "stats.json")
    with open(stats, "w") as fh:
        json.dump({"agentic": {"pillars": [{"name": "Craft", "axes": [
            {"name": "Alpha", "base_weight": 30, "weight": 30, "normalized_score": 1.0},
            {"name": "Beta", "base_weight": 20, "weight": 20, "normalized_score": 1.0}]}]}}, fh)
    empty = os.path.join(root, "empty-corpus")
    os.makedirs(empty, exist_ok=True)
    cmd = [sys.executable, os.path.join(harness.SCRIPTS, "axis-coverage.py"),
           "--checkout", os.path.join(root, "checkout"), "--corpus", empty,
           "--since", "2026-07-13", "--until", "2026-08-12",
           "--scripts-dir", scripts, "--stats", stats]
    if verdicts is not None:
        terms = os.path.join(root, "terms.json")
        with open(terms, "w") as fh:
            json.dump({"verdicts": verdicts}, fh)
        cmd += ["--terms", terms]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return proc.stdout + proc.stderr


def check_a_covered_but_opaque_axis_is_called_out(t):
    with harness.tmpdir() as d:
        out = _fixture(d, {"Alpha": "NOT DECOMPOSABLE", "Beta": "REPRODUCED"})
        t.contains(out, "COVERED BUT NOT REBUILDABLE",
                   "the contradiction gets its own section")
        t.contains(out, "Alpha", "naming the axis a tag covers and nobody can rebuild")
        t.contains(out, "1 of the covered axes cannot be rebuilt",
                   "and the summary carries the count")


def check_the_script_that_tags_it_is_named(t):
    # A line that says an axis is opaque without saying who claims it sends the reader back to
    # a grep. The whole value of the join is arriving at one place with both halves.
    with harness.tmpdir() as d:
        out = _fixture(d, {"Alpha": "NOT DECOMPOSABLE"})
        section = out.split("COVERED BUT NOT REBUILDABLE")[1].split("\n\n")[0]
        t.contains(section, "verify-fixture-0.py",
                   "the section names the script whose tag is doing the covering")


def check_rebuildable_axes_are_not_called_out(t):
    # CONTROL. Every assertion above passes against a report that lists every axis, and a
    # section that names everything is the orphan detector that names every script.
    with harness.tmpdir() as d:
        out = _fixture(d, {"Alpha": "REPRODUCED", "Beta": "ONE UNKNOWN"})
        t.absent(out, "COVERED BUT NOT REBUILDABLE",
                 "CONTROL: nothing opaque means no section")
        t.absent(out, "cannot be rebuilt from their own terms",
                 "and no count either")


def check_the_absence_of_the_join_is_announced(t):
    # Without --terms the comparison silently does not happen, and a report that omits a
    # comparison reads exactly like one where the comparison came out clean. Same reason
    # run-checks announces a check that ran at half scope.
    with harness.tmpdir() as d:
        out = _fixture(d, verdicts=None)
        t.contains(out, "NOT COMPARED",
                   "a run without the verdicts says the comparison did not happen")
        t.contains(out, "--terms", "and names the flag that would make it happen")
