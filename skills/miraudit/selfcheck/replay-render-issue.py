"""render-issue.py: what the reporter will and will not draft.

It used to demand `axes`, which meant it could only express a finding about an AXIS. A defect
in a published stat that feeds no axis had nowhere to go, and the only way to send one was to
write a false axis name -- which is both a wrong claim and a change of verdict, since the
gate's flag rule keys on axis names.
"""
import contextlib
import io
import json
import os
import harness

NEEDS = ()

ri = harness.load("render-issue.py")


def _draft(root, finding):
    src = os.path.join(root, "run.json")
    dst = os.path.join(root, "issue.md")
    doc = harness.payload(findings=[finding])
    with open(src, "w") as fh:
        json.dump(doc, fh)
    buf = io.StringIO()
    with harness.quiet():
        with contextlib.redirect_stdout(buf):
            ri.main([src, dst])
    text = open(dst).read() if os.path.exists(dst) else None
    return buf.getvalue(), text


def _finding(**over):
    f = harness.finding(
        not_checked=["a named blind spot"],
        what_would_close_it="the observation that would settle it either way")
    f.update(over)
    return f


def check_a_finding_with_axes_drafts(t):
    with harness.tmpdir() as d:
        out, text = _draft(d, _finding(axes=["Verification"]))
        t.equal(text is not None, True, "CONTROL: the axis case still drafts")
        if text:
            t.contains(text, "Axes: Verification", "and the header names the axes")


def check_a_finding_with_only_a_surface_drafts(t):
    with harness.tmpdir() as d:
        f = _finding(axes=[], surface='stats["token_usage"]')
        out, text = _draft(d, f)
        t.equal(text is not None, True, "a surface-only finding is draftable")
        if text:
            t.contains(text, 'Surface: stats["token_usage"]', "the header names the surface")
            t.contains(text, "feeds no axis", "and says plainly that no axis is involved")
            t.absent(text, "Axes:", "without inventing an axis line")


def check_a_finding_naming_neither_is_refused(t):
    with harness.tmpdir() as d:
        f = _finding(axes=[])
        f.pop("surface", None)
        out, text = _draft(d, f)
        t.equal(text, None, "nothing is written when the finding names neither")
        t.contains(out, "axes-or-surface", "and the refusal says which requirement failed")


def check_the_refusal_writes_nothing_over_an_earlier_draft(t):
    # Same shape as render-report's gate refusal: a refusal that truncates the previous
    # draft on its way to refusing is worse than no refusal.
    with harness.tmpdir() as d:
        dst = os.path.join(d, "issue.md")
        with open(dst, "w") as fh:
            fh.write("the previous draft")
        src = os.path.join(d, "run.json")
        f = _finding(axes=[])
        f.pop("surface", None)
        with open(src, "w") as fh:
            json.dump(harness.payload(findings=[f]), fh)
        with harness.quiet():
            with contextlib.redirect_stdout(io.StringIO()):
                ri.main([src, dst])
        t.equal(open(dst).read(), "the previous draft",
                "an earlier draft survives a refusal intact")


def check_the_unfilled_markers_are_counted_not_hidden(t):
    with harness.tmpdir() as d:
        out, text = _draft(d, _finding(axes=["Verification"]))
        t.contains(out, "marker(s) left to fill",
                   "the draft states how many holes it still has")
        if text:
            t.contains(text, "UNFILLED",
                       "and the holes are findable in the file by that word")


def _anchored(root, **anchor):
    src = os.path.join(root, "run.json")
    dst = os.path.join(root, "issue.md")
    doc = harness.payload(findings=[_finding(axes=["Verification"])])
    doc["anchor"] = anchor
    with open(src, "w") as fh:
        json.dump(doc, fh)
    with harness.quiet():
        with contextlib.redirect_stdout(io.StringIO()):
            ri.main([src, dst])
    return open(dst).read()


def check_no_python_literal_reaches_the_issue_body(t):
    # The draft is pasted into a public issue, so a language primitive that renders as a word
    # is the worst kind of defect: it reads as prose and nobody re-reads prose. `None` got
    # there by interpolating an absent field into a sentence that assumed it was present.
    #
    # The assertion is on the WORD, not on the sentence that produced it, because the next
    # field to go missing will produce a different sentence.
    with harness.tmpdir() as d:
        text = _anchored(d, published=None, reproduced=None, ok=None, note="ran --local")
        t.absent(text, "None", "no bare `None` is published into the body")
        t.contains(text, "did not reproduce a headline number",
                   "the absent number is stated as absence, not interpolated")


def check_a_reproduced_number_is_still_reported(t):
    # CONTROL for the check above. Suppressing the sentence entirely would also pass an
    # absent-`None` assertion while losing the number, so the number has to be demanded here.
    with harness.tmpdir() as d:
        text = _anchored(d, published=None, reproduced=91, ok=None, note="ran --local")
        t.contains(text, "reproduced 91 locally",
                   "CONTROL: a run that did reproduce a number still says which")
        t.absent(text, "None", "and it does so without leaking a literal either")


def check_the_unanchored_warning_survives_both_ways(t):
    # Both branches must keep the disclosure, which is the reason the paragraph exists at
    # all: a reader who reaches the third number and only then learns nothing was anchored
    # has been misled by everything above it.
    with harness.tmpdir() as d:
        for repro in (None, 91):
            text = _anchored(d, published=None, reproduced=repro, ok=None, note="")
            t.contains(text, "`anchor.ok` is `null`",
                       f"the unanchored state is stated up front (reproduced={repro})")
