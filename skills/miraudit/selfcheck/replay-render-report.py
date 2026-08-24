"""render-report.py: the renderer, and the --check that proves a report matches its source.

--check is the only thing standing between a payload and a report that quietly describes an
earlier version of the same run. Nothing tested it.

The strongest checks here are the two that separate a real re-render from a cheap stand-in:
a same-length edit must be caught, and a field the renderer does not read must NOT be. A
hash of the source file passes the first and fails the second.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import harness

NEEDS = ()

rr = harness.load("render-report.py")
gate = harness.load("emit-gate.py")


def _load_path(path, name):
    """Like harness.load(), but for a file that is not sitting in scripts/ -- used to run the
    pre-patch-then-gate render-report.py fetched from HEAD, beside a throwaway copy of it."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_root():
    return os.path.dirname(os.path.dirname(harness.SKILL))


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


# ---- patch-then-gate: reconciling run_cost from run-checks.py/run-arms.py --emit files ----
# render-report.py used to gate a file it never wrote and never read `run_cost` back in --
# so nothing gated ever inspected what a later patch would add. These prove the reversal: the
# patched value reaches disk only through the SAME gate as everything else, a genuine
# violation elsewhere in the payload still refuses (and leaves `src` provably untouched), and
# --check's contract of zero side effects survives the reversal unchanged.


def _write_checks_emit(run_dir, battery_seconds, adhoc_count):
    checks_dir = os.path.join(run_dir, "checks")
    os.makedirs(checks_dir, exist_ok=True)
    with open(os.path.join(checks_dir, "run-checks-emit.json"), "w") as fh:
        json.dump({"battery": {"count": 3, "seconds": battery_seconds},
                   "adhoc": {"count": adhoc_count, "seconds": 0}}, fh)


def check_a_stale_run_cost_is_patched_from_the_emit_file_on_disk_and_in_check_mode(t):
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()],
                              run_cost={"checks": {"unit": "seconds", "value": 999.0}})
        src, dst = _pair(d, doc)
        _write_checks_emit(d, battery_seconds=42.5, adhoc_count=2)

        code, _out = _main(["render-report.py", src, dst])
        t.equal(code, 0, "a clean payload with a fresh --emit file still renders")

        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["checks"], {"unit": "seconds", "value": 42.5},
                "the stale value on disk is replaced by the --emit file's, not merged or kept")
        t.equal(on_disk["run_cost"]["adhoc_checks"], {"unit": "count", "value": 2},
                "adhoc_checks is filled the same pass, from the same file's adhoc.count")

        check_code, _check_out = _main(["render-report.py", "--check", src, dst])
        t.equal(check_code, 0,
                "and --check on the now-patched pair agrees the .md still matches its JSON")


def check_no_emit_files_leaves_checks_arms_adhoc_untouched_but_still_adds_gate_retries(t):
    # `_patch_run_cost` itself is still a true no-op here: absent --emit output, it must not
    # add checks/arms/adhoc_checks that were not there. gate_retries is a SEPARATE mechanism
    # (see check_gate_retries_is_zero_on_a_first_try_pass below) and it always fires on a real
    # invocation, which is why `run_cost` as a whole is no longer absent the way it used to be
    # before gate_retries existed -- that was this check's old assertion, and it is exactly
    # the behaviour this feature was built to change.
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        t.equal("run_cost" in doc, False, "vacuity guard: this fixture starts without run_cost")
        src, dst = _pair(d, doc)
        code, _out = _main(["render-report.py", src, dst])
        t.equal(code, 0, "CONTROL: the payload still renders")
        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(set(on_disk.get("run_cost", {})), {"gate_retries"},
                "no --emit files next to the run means checks/arms/adhoc_checks/wall/phases "
                "are never added, and the only key present is the one gate_retries itself "
                "always writes")


def check_a_genuine_gate_violation_is_still_refused_with_a_valid_emit_file_present(t):
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        doc["tool"]["ref"] = "deadbeef0"                       # will not match the real pin
        t.equal(bool(gate.check(doc, doc_path=None, flags_dir=d)), True,
                "CONTROL: this tool.ref fails the gate on its own, before any run_cost patch")
        src, dst = _pair(d, doc)
        _write_checks_emit(d, battery_seconds=12.3, adhoc_count=0)
        before = open(src, "rb").read()
        dst_before = open(dst, "rb").read()

        code, out = _main(["render-report.py", src, dst])
        t.equal(code, 1,
                "a genuine gate violation is still refused with a valid --emit file present")
        t.contains(out, "the gate refused this file", "and says so the way it always did")

        after = open(src, "rb").read()
        t.equal(after, before,
                "src is byte-for-byte unmutated by the failed attempt -- the patch never "
                "reaches src unless the gate, run on the patched content, agrees")
        t.equal(os.path.exists(src + ".partial"), False,
                "and the temp file the patch was gated through does not survive a refusal")
        t.equal(open(dst, "rb").read(), dst_before,
                "a refused run leaves whatever report was already there untouched")


def check_the_gate_target_is_the_patched_content_not_the_stale_original(t):
    """The point of gating AFTER the patch: a payload whose ONLY violation was in run_cost's
    own shape (the bare-number form emit-gate.py now refuses) must pass once --emit files
    replace it with the valid {"unit", "value"} shape -- which only happens if the subprocess
    is actually gating the patched temp file and not the stale `src`."""
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()], run_cost={"checks": 13})
        t.equal(bool(gate.check(doc, doc_path=None, flags_dir=d)), True,
                "CONTROL: the bare-number run_cost.checks fails the gate by itself")
        src, dst = _pair(d, doc)
        _write_checks_emit(d, battery_seconds=7.0, adhoc_count=0)

        code, _out = _main(["render-report.py", src, dst])
        t.equal(code, 0,
                "the patch replaces the violating field before gating, so this now passes -- "
                "proof the gate ran against the patched content, not the stale original")
        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["checks"], {"unit": "seconds", "value": 7.0},
                "and the promoted src carries the patched value")


def check_check_mode_does_not_patch_even_with_an_emit_file_present(t):
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()],
                              run_cost={"checks": {"unit": "seconds", "value": 999.0}})
        src, dst = _pair(d, doc)
        _write_checks_emit(d, battery_seconds=42.5, adhoc_count=2)
        before = open(src, "rb").read()

        code, _out = _main(["render-report.py", "--check", src, dst])

        after = open(src, "rb").read()
        t.equal(before, after,
                "--check leaves src untouched even though a valid --emit file sits right "
                "there -- its contract is comparing the report to its source, not patching it")
        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["checks"], {"unit": "seconds", "value": 999.0},
                "the stale value survives --check, because --check never reads --emit files")
        t.equal(code, 0,
                "and it still answers correctly: the .md was rendered from the stale doc, "
                "which is exactly what is still on disk")


def check_check_mode_is_unaffected_by_the_patch_then_gate_reversal(t):
    """Runs the PRE-reversal render-report.py, fetched from HEAD, and the current one against
    the same fixture -- proof by execution, not by reading the checking branch and asserting
    it looks untouched. Skips gracefully (a note, not a failure) if git is unavailable, which
    it is not expected to be here but a replay in this tier must never hard-fail on tooling
    outside the skill.
    """
    with harness.tmpdir() as d:
        proc = subprocess.run(
            ["git", "show", "HEAD:skills/miraudit/scripts/render-report.py"],
            cwd=_repo_root(), capture_output=True, text=True, timeout=20)
        if proc.returncode != 0 or not proc.stdout.strip():
            t.note("git show HEAD:...render-report.py failed; skipping the before/after "
                   "comparison rather than failing on missing tooling")
            return
        original_path = os.path.join(d, "render-report-original.py")
        with open(original_path, "w") as fh:
            fh.write(proc.stdout)
        shutil.copy2(os.path.join(harness.SCRIPTS, "emit-gate.py"),
                    os.path.join(d, "emit-gate.py"))
        original = _load_path(original_path, "miraudit_rr_original")

        run_dir = os.path.join(d, "run")
        os.makedirs(run_dir, exist_ok=True)
        doc = harness.payload(findings=[harness.finding()])
        src = os.path.join(run_dir, "miraudit-probe.json")
        dst = os.path.join(run_dir, "miraudit-probe.md")
        with open(src, "w") as fh:
            json.dump(doc, fh, indent=2)
        with open(dst, "w") as fh:
            fh.write(rr.render(doc))
        _write_checks_emit(run_dir, battery_seconds=55.0, adhoc_count=1)

        def run_check(module):
            buf = io.StringIO()
            with harness.quiet():
                with contextlib.redirect_stdout(buf):
                    code = module.main(["render-report.py", "--check", src, dst])
            return code, buf.getvalue()

        before_code, before_text = run_check(original)
        mid_bytes = open(src, "rb").read()
        after_code, after_text = run_check(rr)
        after_bytes = open(src, "rb").read()

        t.equal(before_code, after_code,
                "--check returns the same code before and after the reversal")
        t.equal(mid_bytes, after_bytes,
                "and src is untouched by --check either way, even with a valid --emit file "
                "sitting beside it -- the reversal did not teach --check to patch anything")


# ---- run_cost.gate_retries: how many times the REAL submission gate failed for THIS run ----
# The only place a real submission attempt happens is the `gate = subprocess.run(...)` call
# inside main() itself, so the log has to live here rather than inside emit-gate.py -- a
# standalone diagnostic run of that file (confirmed in a saved transcript, invoked twice on
# purpose from two working directories to compare behaviour) must never be mistaken for one.


def check_gate_retries_is_zero_on_a_first_try_pass(t):
    """CONTROL: zero is a real measurement (first-try success), not the same thing as the
    field being absent."""
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        src, dst = _pair(d, doc)
        code, _out = _main(["render-report.py", src, dst])
        t.equal(code, 0, "CONTROL: this payload passes the gate on the first try")
        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["gate_retries"], {"unit": "count", "value": 0},
                "no prior fails on record, patched in before this attempt's own outcome was "
                "known")


def check_gate_retries_persists_across_invocations_after_a_real_failure(t):
    """Proves the count is read from the log BEFORE the attempt's own result, by forcing a
    genuine gate failure first and then a second, successful invocation against the SAME src
    path -- the second attempt's gate_retries has to already reflect the first attempt's
    failure, which only the log (not this attempt's own outcome) can supply."""
    with harness.tmpdir() as d:
        src = os.path.join(d, "run.json")
        dst = os.path.join(d, "run.md")
        with open(src, "w") as fh:
            json.dump(harness.skeleton(), fh, indent=2)          # every bucket empty: fails
        code1, _out1 = _main(["render-report.py", src, dst])
        t.equal(code1, 1, "CONTROL: the first attempt genuinely fails the gate")

        good = harness.payload(findings=[harness.finding()])
        with open(src, "w") as fh:
            json.dump(good, fh, indent=2)
        code2, _out2 = _main(["render-report.py", src, dst])
        t.equal(code2, 0, "the second attempt, against the same src path, passes")

        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["gate_retries"], {"unit": "count", "value": 1},
                "the one real failure already on record, read before this attempt's own pass")


def check_standalone_emit_gate_runs_do_not_touch_the_log(t):
    """The single most important correctness property here: emit-gate.py gets invoked
    directly all the time for diagnosis, and none of that is a submission. Only main()'s own
    subprocess.run() call may write this log."""
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        src, dst = _pair(d, doc)
        log_path = rr._gate_log_path(src)
        t.equal(os.path.exists(log_path), False,
                "no log yet -- nothing has gone through render-report.py")

        for _ in range(3):
            subprocess.run(
                [sys.executable, os.path.join(harness.SCRIPTS, "emit-gate.py"), src],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t.equal(os.path.exists(log_path), False,
                "three standalone emit-gate.py runs against the same file wrote no log at all")

        code, _out = _main(["render-report.py", src, dst])
        t.equal(code, 0, "the real submission through render-report.py still passes")
        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["gate_retries"], {"unit": "count", "value": 0},
                "unaffected by the three standalone diagnostic runs that preceded it")


def check_check_mode_never_touches_the_gate_log(t):
    """--check's contract is zero side effects, proven by bytes and mtime rather than assumed
    -- both before any log exists, and again once a real run has created one."""
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        src, dst = _pair(d, doc)
        log_path = rr._gate_log_path(src)
        t.equal(os.path.exists(log_path), False, "CONTROL: no log before any --check call")

        code, _out = _main(["render-report.py", "--check", src, dst])
        t.equal(code, 0, "CONTROL: the check itself succeeds")
        t.equal(os.path.exists(log_path), False,
                "--check never creates the gate log -- it has no submission to record")

        _main(["render-report.py", src, dst])
        t.equal(os.path.exists(log_path), True, "a real run does create the log")
        before_bytes = open(log_path, "rb").read()
        before_mtime = os.path.getmtime(log_path)

        _main(["render-report.py", "--check", src, dst])
        t.equal(open(log_path, "rb").read(), before_bytes,
                "and --check does not modify an existing log's bytes")
        t.equal(os.path.getmtime(log_path), before_mtime,
                "or its mtime")

        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["gate_retries"], {"unit": "count", "value": 0},
                "and --check never re-patches gate_retries into src")


def check_a_corrupted_gate_log_degrades_to_null_not_a_crash(t):
    """A hand-truncated or corrupted log is a real edge case -- a crash mid-append, a person
    editing the file by hand -- and it must not read as zero (a false first-try-pass claim)
    and must not take render-report.py down with it."""
    with harness.tmpdir() as d:
        doc = harness.payload(findings=[harness.finding()])
        src, dst = _pair(d, doc)
        log_path = rr._gate_log_path(src)
        with open(log_path, "w") as fh:
            fh.write("not json, not even close\n{garbage")

        code, _out = _main(["render-report.py", src, dst])
        t.equal(code, 0, "a corrupted log does not crash the render")
        with open(src) as fh:
            on_disk = json.load(fh)
        t.equal(on_disk["run_cost"]["gate_retries"], None,
                "degrades to null rather than a fabricated 0 or a crash")
