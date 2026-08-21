"""unmeasured-surface.py: how much CAN go unmeasured, against what one run disclosed.

Two dropped terms were found here by hand, one at a time, each costing an investigation --
the routing third of Model mix and the ordered-facts term behind Context Intelligence. The
third would have cost another, because nothing enumerated the rest.

The denominator is the scoring source, not the payload, for the third time in this skill: a
run can only disclose what it dropped, never what it never had the chance to.

Needs a checkout: the enumeration parses the real scoring module, and a stub would be the
same self-referential denominator wearing a different hat.
"""
import json
import os
import re
import subprocess
import sys
import harness

NEEDS = ("checkout",)


def _run(t, payload, root):
    stats = os.path.join(root, "stats.json")
    with open(stats, "w") as fh:
        json.dump(payload, fh)
    empty = os.path.join(root, "empty-corpus")
    os.makedirs(empty, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, "unmeasured-surface.py"),
         "--checkout", t.checkout, "--corpus", empty,
         "--since", "2026-07-13", "--until", "2026-08-12", "--stats", stats],
        capture_output=True, text=True, timeout=180)
    return proc.stdout + proc.stderr, proc.returncode


def _count(text, label):
    """The number on `label`'s line, read as a FIELD.

    Asserting the exact run of spaces coupled this file to a format string, which is the same
    mistake that put six repo-bucketing cases in the red when a column was widened.
    """
    for line in text.splitlines():
        if label in line:
            m = re.search(r"(\d+)", line.split(label, 1)[1])
            if m:
                return int(m.group(1))
    return None


def _payload(**over):
    body = {"agentic": {"pillars": [{"name": "Efficiency", "not_applicable": [], "axes": [
        {"name": "Recovery", "base_weight": 50, "weight": 50}]}]}}
    if over.get("dropped"):
        body["agentic"]["pillars"][0]["not_applicable"] = list(over["dropped"])
    if over.get("partial"):
        body["agentic"]["pillars"][0]["axes"][0]["partial_terms"] = over["partial"]
    if over.get("renormalized"):
        body["agentic"]["pillars"][0]["axes"][0]["weight"] = over["renormalized"]
    return body


def check_the_four_mechanisms_are_counted_from_the_source(t):
    with harness.tmpdir() as d:
        out, code = _run(t, _payload(), d)
        t.equal(code, 0, "the enumeration runs clean against the pinned checkout")
        for label in ("wsum drops a term", "an axis is dropped",
                      "a weight is scaled", "the pooled score collapses"):
            t.contains(out, label, f"mechanism `{label}` is counted")


def check_the_capacity_is_larger_than_what_one_run_discloses(t):
    # The whole argument in one assertion. If these two numbers were the same the script would
    # be reporting the payload back to itself, which is what everything before it did.
    with harness.tmpdir() as d:
        out, _ = _run(t, _payload(dropped=["Ghost"]), d)
        source_half = out.split("WHAT THIS RUN DISCLOSED")[0]
        counts = [int(tok) for tok in source_half.split() if tok.isdigit()]
        t.equal(bool(counts) and max(counts) > 1, True,
                "the source can drop things in more places than a run discloses "
                f"(largest count found: {max(counts) if counts else 0})")


def check_a_dropped_axis_is_reported_with_its_pillar(t):
    with harness.tmpdir() as d:
        out, _ = _run(t, _payload(dropped=["Ghost"]), d)
        t.equal(_count(out, "axes dropped entirely"), 1, "the drop is counted")
        t.contains(out, "Ghost left Efficiency",
                   "and named with the pillar whose weight it left behind")


def check_a_partial_term_and_a_renormalized_axis_are_distinguished(t):
    # They disclose through different fields and mean different things: one axis lost a term,
    # another gained a sibling's weight. Collapsing them would hide which happened.
    with harness.tmpdir() as d:
        out, _ = _run(t, _payload(partial={"scored": 1, "total": 2, "weight_scored": 0.5},
                                  renormalized=100), d)
        t.contains(out, "1/2 terms scored", "the partial term reports its ratio")
        t.contains(out, "declares 50 and carries 100",
                   "and the renormalized axis reports both weights")


def check_a_clean_payload_reports_nothing_dropped(t):
    # CONTROL. Every assertion above is satisfied by a script that always claims a drop, and
    # a report that always says something is wrong stops being read.
    with harness.tmpdir() as d:
        out, code = _run(t, _payload(), d)
        t.equal(code, 0, "CONTROL: a payload with no drops still exits 0")
        t.equal(_count(out, "axes dropped entirely"), 0,
                "and reports zero rather than inventing one")
        t.equal(_count(out, "axes with a dropped term"), 0, "for terms too")


def check_the_parse_refuses_a_credible_looking_zero(t):
    # The vacuity guard, exercised. A regex that stops matching reports a small world instead
    # of an error, and a small world reads as "not much can go wrong" -- which is the reading
    # this whole file exists to deny. Run it against a checkout whose scoring module is empty.
    with harness.tmpdir() as d:
        fake = os.path.join(d, "fake")
        os.makedirs(os.path.join(fake, "gnomon", "scoring"))
        for name in ("aq.py", "planning_evidence.py", "aggregate.py"):
            open(os.path.join(fake, "gnomon", "scoring", name), "w").close()
        os.makedirs(os.path.join(fake, "gnomon"), exist_ok=True)
        stats = os.path.join(d, "s.json")
        with open(stats, "w") as fh:
            json.dump(_payload(), fh)
        empty = os.path.join(d, "empty")
        os.makedirs(empty, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, os.path.join(harness.SCRIPTS, "unmeasured-surface.py"),
             "--checkout", fake, "--corpus", empty,
             "--since", "2026-07-13", "--until", "2026-08-12", "--stats", stats],
            capture_output=True, text=True, timeout=180)
        t.equal(proc.returncode, 1,
                "an empty scoring module is a parse failure, not an answer of zero")
        t.contains(proc.stdout + proc.stderr, "not a credible answer",
                   "and it says why rather than printing zeros")
