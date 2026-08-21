"""render-report.py: the renderer, and the --check that proves a report matches its source.

--check is the only thing standing between a payload and a report that quietly describes an
earlier version of the same run. Nothing tested it.

The strongest checks here are the two that separate a real re-render from a cheap stand-in:
a same-length edit must be caught, and a field the renderer does not read must NOT be. A
hash of the source file passes the first and fails the second.
"""
import contextlib
import io
import json
import os
import harness

NEEDS = ()

rr = harness.load("render-report.py")
gate = harness.load("emit-gate.py")


def _pair(root, doc, rendered=None):
    src = os.path.join(root, "miraudit-probe.json")
    dst = os.path.join(root, "miraudit-probe.md")
    with open(src, "w") as fh:
        json.dump(doc, fh, indent=2)
    with open(dst, "w") as fh:
        fh.write(rr.render(doc) if rendered is None else rendered)
    return src, dst


def _main(argv):
    """Run main() capturing BOTH python-level prints and the gate subprocess's fd-1 output.

    The redirect alone is not enough: render-report shells out to emit-gate.py, and a child
    process writes past sys.stdout straight into the runner's report.
    """
    buf = io.StringIO()
    with harness.quiet():
        with contextlib.redirect_stdout(buf):
            code = rr.main(argv)
    return code, buf.getvalue()


def check_render_is_deterministic(t):
    doc = harness.payload(findings=[harness.finding()])
    t.equal(rr.render(doc), rr.render(doc), "the same doc renders identically twice")
    t.equal(rr.render(json.loads(json.dumps(doc))), rr.render(doc),
            "and a round-trip through JSON does not change the output -- the whole premise "
            "of comparing a rendered report against a re-render")


def check_check_mode_detects_a_same_length_edit(t):
    with harness.tmpdir() as d:
        doc = harness.payload(dismissed=[{"id": "D1", "killed_by": "aaaaaaaaaa"}])
        src, dst = _pair(d, doc)
        code, _out = _main(["render-report.py", "--check", src, dst])
        t.equal(code, 0, "CONTROL: a freshly rendered pair matches")
        # Same length, same section count: nothing but an actual re-render tells them apart.
        doc["dismissed"][0]["killed_by"] = "bbbbbbbbbb"
        with open(src, "w") as fh:
            json.dump(doc, fh, indent=2)
        code, out = _main(["render-report.py", "--check", src, dst])
        t.equal(code, 1, "a content-only edit of identical length is caught")
        t.contains(out, "DOES NOT match", "and says so in words, not just an exit code")


def check_check_mode_ignores_a_field_the_renderer_does_not_read(t):
    """The gut-proof half: it compares RENDERED OUTPUT, not the source's bytes.

    A "cheap optimisation" that hashed the JSON would pass the same-length check above and
    fail here. That distinction is the difference between "the report is stale" and "the file
    was touched".
    """
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        src, dst = _pair(d, doc)
        doc["a_field_nothing_renders"] = ["some", "value"]
        with open(src, "w") as fh:
            json.dump(doc, fh, indent=2)
        code, _out = _main(["render-report.py", "--check", src, dst])
        t.equal(code, 0, "a field the renderer never reads does not make the report stale")


def check_check_mode_deliberately_does_not_gate(t):
    # render-report.py:210-212 argues for this in prose: a payload that fails the gate is
    # exactly when you most want to know whether its report matches. Gating first would
    # refuse to answer.
    with harness.tmpdir() as d:
        doc = harness.skeleton()                      # fails the gate
        src, dst = _pair(d, doc)
        t.equal(bool(gate.check(doc, doc_path=None, flags_dir=d)), True,
                "CONTROL: this payload really does fail the gate")
        code, _out = _main(["render-report.py", "--check", src, dst])
        t.equal(code, 0, "and --check still answers its own question about it")


def check_the_gate_refusal_writes_nothing(t):
    with harness.tmpdir() as d:
        src = os.path.join(d, "bad.json")
        dst = os.path.join(d, "bad.md")
        with open(src, "w") as fh:
            json.dump(harness.skeleton(), fh)
        code, out = _main(["render-report.py", src, dst])
        t.equal(code, 1, "a gate-refused payload renders nothing")
        t.equal(os.path.exists(dst), False, "and leaves no report behind")
        t.contains(out, "nothing was written", "and says so")


def check_the_gate_refusal_leaves_a_stale_report_untouched(t):
    """Catches a refactor that opens dst for writing before gating, which truncates the
    previous report on its way to refusing."""
    with harness.tmpdir() as d:
        src = os.path.join(d, "bad.json")
        dst = os.path.join(d, "bad.md")
        with open(src, "w") as fh:
            json.dump(harness.skeleton(), fh)
        with open(dst, "w") as fh:
            fh.write("the previous, valid report")
        _main(["render-report.py", src, dst])
        t.equal(open(dst).read(), "the previous, valid report",
                "the earlier report survives a refusal intact")


def check_a_clean_payload_renders(t):
    # CONTROL for the two refusals above: without it, "writes nothing" could mean "never
    # writes anything".
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        src = os.path.join(d, "ok.json")
        dst = os.path.join(d, "ok.md")
        with open(src, "w") as fh:
            json.dump(doc, fh)
        # No monkeypatch of gate.pinned_ref here, deliberately: main() runs emit-gate as a
        # SUBPROCESS, so patching the imported module would look load-bearing and do nothing.
        # This payload's tool.ref is blank, which the gate records as a note rather than a
        # violation, so it passes on its own merits.
        code, _out = _main(["render-report.py", src, dst])
        t.equal(code, 0, "CONTROL: a clean payload renders")
        t.equal(os.path.exists(dst) and open(dst).read() == rr.render(doc), True,
                "and what lands on disk is exactly render(doc)")


def check_the_default_output_path_is_the_json_with_md(t):
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        src = os.path.join(d, "run.json")
        with open(src, "w") as fh:
            json.dump(doc, fh)
        _main(["render-report.py", src])
        t.equal(os.path.exists(os.path.join(d, "run.md")), True,
                "omitting dst writes alongside the source with a .md suffix")


def check_an_unreadable_source_returns_two(t):
    with harness.tmpdir() as d:
        missing = os.path.join(d, "nope.json")
        t.equal(_main(["render-report.py", "--check", missing, missing + ".md"])[0], 2,
                "--check on a missing pair is 2, distinct from a mismatch")
        t.equal(_main(["render-report.py", missing])[0] in (1, 2), True,
                "and rendering a missing source does not pretend to succeed")


def check_empty_findings_with_empty_dismissed_says_so(t):
    # The renderer's first untrue sentence lived in this branch.
    both_empty = rr.render(harness.payload(dismissed=[]))
    with_dismissed = rr.render(harness.payload())
    t.contains(both_empty, "no filtering on display",
               "nothing found AND nothing dismissed is stated plainly")
    t.absent(with_dismissed, "no filtering on display",
             "but a populated dismissed list is filtering, and must not claim otherwise")


def check_files_and_lines_render_outside_the_fingerprint(t):
    """The ORDER is the claim: corpus size is not part of the fingerprint, and printing it
    above the fingerprint line would say the opposite. An index comparison, not a substring
    test -- moving the two appends back inside the block leaves every substring intact.
    """
    corpus = dict(harness.payload()["corpus"])
    corpus.update({"files": 3663, "lines": 262456})
    text = rr.render(harness.payload(corpus=corpus))
    t.contains(text, "outside the fingerprint", "the disclaimer is rendered")
    where_sources = text.find("Sources scored")
    where_size = text.find("outside the fingerprint")
    t.equal(where_sources != -1 and where_size > where_sources, True,
            "and it comes AFTER the fingerprint lines, never before them")
