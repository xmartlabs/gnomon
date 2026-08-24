"""run-checks.py's wiring guards, exercised from outside the runner.

Both guards live at module level in run-checks.py, so until now the only thing checking them
was the runner itself -- which cannot fail BY NAME in this suite, and which reports its own
wiring problems in the same table as a real check failure. Those are different problems with
different fixes, and only one of them is about gnomon.

The runner cannot be imported: it calls parse() at import and then walks a corpus. So this
copies the scripts directory, breaks the wiring IN THE COPY, and runs that. The shipped tree
is never mutated, which is the same discipline the A/B arms follow -- patch a throwaway,
never the reference.

Deliberately not re-derived here: the orphan set itself. Recomputing "which scripts are
accounted for" in this file would be a second implementation of the rule, and the second
implementation is what the rule exists to prevent. What is asserted is that the shipped
derivation NAMES a planted orphan and STOPS naming it once the orphan is accounted for.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import harness

NEEDS = ()

ORPHAN = "verify-planted-orphan.py"


def _copy_scripts(root):
    """A faithful enough copy of the skill: the scripts, plus the markdown that calls them.

    The procedure files are not optional here. The runner scans them because run-arms.py is
    invoked by the model from ad-hoc-checks.md and by NO script -- scanning code alone
    reports a live driver as dead. A copy without them would make every such driver look
    like an orphan, and this file would be measuring its own incomplete fixture.
    """
    dst = os.path.join(root, "scripts")
    shutil.copytree(harness.SCRIPTS, dst,
                    ignore=shutil.ignore_patterns("__pycache__"))
    skill = os.path.dirname(harness.SCRIPTS)
    os.makedirs(os.path.join(root, "references"), exist_ok=True)
    for pattern in ("*.md", os.path.join("references", "*.md")):
        for src in glob.glob(os.path.join(skill, pattern)):
            shutil.copy2(src, os.path.join(root, os.path.relpath(src, skill)))
    return dst


def _run(scripts, root, checkout, extra=()):
    """Drive the COPY's run-checks.py against an empty corpus."""
    return _run_into(scripts, root, checkout, os.path.join(root, "out"), extra)


def _run_into(scripts, root, checkout, out_dir, extra=()):
    """Like `_run`, but the caller names --out-dir. Two invocations in one check (a control
    run and a --only run) need separate directories, or comparing their .out files proves
    nothing -- the second run's files would just sit beside the first's."""
    empty = os.path.join(root, "empty-corpus")
    os.makedirs(empty, exist_ok=True)
    return subprocess.run(
        [sys.executable, os.path.join(scripts, "run-checks.py"),
         "--checkout", checkout, "--corpus", empty,
         "--since", "2026-07-13", "--until", "2026-08-12",
         "--out-dir", out_dir, "--jobs", "8", "--timeout", "30"]
        + list(extra),
        capture_output=True, text=True, timeout=300)


def check_a_check_that_ran_at_half_scope_says_so(t):
    # verification-reality.py runs either way and exits 0 either way, but without --repo it
    # skips the file-level pairing of test to subject. Exit 0 therefore meant two different
    # things and the batch printed nothing to separate them -- the runner announces what it
    # SKIPPED and said nothing about what it narrowed.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc = _run(_copy_scripts(d), d, ck)
        t.contains(proc.stdout + proc.stderr, "HALF SCOPE",
                   "the batch says a check ran narrower than it can")
        t.contains(proc.stdout + proc.stderr, "--repo",
                   "and names the flag that would widen it")


def check_the_half_scope_line_is_absent_when_the_flag_is_given(t):
    # CONTROL. A line that prints unconditionally is noise, and noise in a summary is how the
    # real warnings stop being read. This is the same bar the orphan detector had to clear.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc = _run(_copy_scripts(d), d, ck, extra=["--repo", d])
        t.absent(proc.stdout + proc.stderr, "HALF SCOPE",
                 "CONTROL: with --repo given, the batch does not claim half scope")


def check_a_renamed_check_is_reported_as_wiring_not_as_failure(t):
    # The failure this replaces: a rename slipped through, the subprocess failed, its
    # traceback landed in the .out file, and the table reported it as a check that FAILED.
    # The guard has to fire BEFORE anything runs, because a wiring error that arrives as a
    # red check sends somebody reading gnomon's scoring code for an hour.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        victim = os.path.join(scripts, "verify-repo-bucketing.py")
        t.equal(os.path.exists(victim), True,
                "the file ALWAYS names is there to begin with")
        os.rename(victim, os.path.join(scripts, "verify-repo-bucketing-RENAMED.py"))
        proc = _run(scripts, d, ck)
        t.equal(proc.returncode != 0, True, "the runner refuses to start")
        both = proc.stdout + proc.stderr
        t.contains(both, "verify-repo-bucketing.py", "naming the file that went missing")
        t.contains(both, "Fix the wiring, not the check",
                   "and saying which kind of problem this is")
        t.equal(os.path.isdir(os.path.join(d, "out")), False,
                "and it stops before writing any check output at all")


def check_the_unbroken_wiring_starts(t):
    # CONTROL. A runner that refused unconditionally would satisfy every assertion above.
    # The checks themselves fail here -- the corpus is empty and the checkout is a stub --
    # and that is fine: what is asserted is that the run got PAST the wiring guard, which
    # the out/ directory proves because the guard exits before it is created.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        proc = _run(scripts, d, ck)
        both = proc.stdout + proc.stderr
        t.absent(both, "Fix the wiring, not the check",
                 "CONTROL: intact wiring is not reported as broken")
        t.equal(os.path.isdir(os.path.join(d, "out")), True,
                "and the batch reaches the point of writing its output")


def check_the_machine_readable_handoffs_are_wired(t):
    """Two checks write output another check reads, and neither was ever asked to.

    axis-terms' verdicts are what let axis-coverage see an axis covered by a tag whose score
    nobody can rebuild -- a contradiction that lived in two separate reports. saturation's
    `above_threshold` is the single implementation of "this signal is below its target".

    Read by AST out of `per_script_args`, with a vacuity guard. The batch cannot be imported --
    it calls parse() at module level -- and driving it against an empty corpus proves nothing
    here: the checks die before writing anything, so their absence would look identical to a
    flag that was never passed. The first version of this check asserted on the files and went
    red against wiring that was correct.
    """
    import ast
    src = open(os.path.join(harness.SCRIPTS, "run-checks.py"), encoding="utf-8").read()
    fn = next((n for n in ast.walk(ast.parse(src))
               if isinstance(n, ast.FunctionDef) and n.name == "per_script_args"), None)
    t.equal(fn is not None, True,
            "vacuity guard: per_script_args was found in the shipped runner")
    if fn is None:
        return
    body = ast.dump(fn)
    for script, dest in (("axis-terms.py", "axis-terms.json"),
                         ("saturation-counterfactual.py", "saturation.json")):
        t.contains(body, script, f"{script} has a branch of its own")
        t.contains(body, dest, f"and that branch names {dest}")
    t.equal(body.count("'--emit'"), 2,
            "both handoffs pass --emit, and nothing else quietly acquired one")


def check_an_exclusion_that_removes_nothing_says_so(t):
    # EXCLUDED only does something while the named file actually claims an axis. The shipped
    # entry stopped claiming one at some point and nothing noticed, while the comment above it
    # went on asserting that it did -- a guard that reads live and subtracts nothing.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        proc = _run(_copy_scripts(d), d, ck)
        t.contains(proc.stdout + proc.stderr, "INERT EXCLUSION",
                   "an exclusion that removes nothing is reported")
        t.contains(proc.stdout + proc.stderr, "axis-coverage.py",
                   "and names which entry went inert")


def check_a_live_exclusion_is_not_reported_as_inert(t):
    # CONTROL, and the one that matters: give the excluded file a real line-anchored tag and the
    # exclusion starts doing work, so the line must disappear. Without this the check passes just
    # as well against a runner that prints the warning unconditionally.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        target = os.path.join(scripts, "axis-coverage.py")
        with open(target) as fh:
            body = fh.read()
        with open(target, "w") as fh:
            fh.write("# miraudit-covers: Verification\n" + body)
        proc = _run(scripts, d, ck)
        t.absent(proc.stdout + proc.stderr, "INERT EXCLUSION",
                 "CONTROL: an exclusion that removes something is not called inert")


def check_a_check_nobody_calls_is_named_as_an_orphan(t):
    # A script with no tag and no ALWAYS entry runs NOWHERE, and nothing else reports it:
    # axis-coverage.py names uncovered AXES, never uncovered scripts. That is how a check
    # gets written, committed, and executed zero times.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        with open(os.path.join(scripts, ORPHAN), "w") as fh:
            fh.write("# a check with no covers tag, named by nothing\n")
        proc = _run(scripts, d, ck)
        t.contains(proc.stdout + proc.stderr, ORPHAN,
                   "the planted orphan is named")
        t.contains(proc.stdout + proc.stderr, "ORPHANS",
                   "under the heading that says what to do about it")


def check_an_accounted_for_check_stops_being_an_orphan(t):
    # CONTROL for the orphan detector, and the one that matters: a detector that names every
    # script would pass the check above while being noise nobody reads. The plant is
    # identical except that one procedure file now invokes it by name, which is exactly how
    # run-arms.py is accounted for -- it is called from ad-hoc-checks.md and by no script.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        with open(os.path.join(scripts, ORPHAN), "w") as fh:
            fh.write("# a check with no covers tag, invoked from a procedure file\n")
        skill = os.path.dirname(scripts)
        with open(os.path.join(skill, "references", "ad-hoc-checks.md"), "a") as fh:
            fh.write(f"\n\nRun `python3 scripts/{ORPHAN}` when the window looks wrong.\n")
        proc = _run(scripts, d, ck)
        t.absent(proc.stdout + proc.stderr, ORPHAN,
                 "CONTROL: a script a procedure file calls is not an orphan")


def check_emit_writes_a_well_formed_breakdown(t):
    # The shape follows axis-terms.py --emit: a JSON file a sibling script reads, not a
    # person comparing two printed lines by eye.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        emit_path = os.path.join(d, "run-checks-emit.json")
        _run(scripts, d, ck, extra=["--emit", emit_path])
        t.equal(os.path.exists(emit_path), True, "the --emit file is written")
        with open(emit_path) as fh:
            emitted = json.load(fh)
        for key in ("wall", "serial", "battery", "adhoc", "checks"):
            t.equal(key in emitted, True, "the emit doc carries %r" % key)
        t.equal(emitted["adhoc"]["count"], 0, "no --also was given, so nothing is adhoc")
        t.equal(emitted["battery"]["count"] + emitted["adhoc"]["count"],
                len(emitted["checks"]), "battery and adhoc partition the checks list")
        names = {c["name"] for c in emitted["checks"]}
        out_names = {os.path.splitext(f)[0] + ".py"
                    for f in os.listdir(os.path.join(d, "out")) if f.endswith(".out")}
        t.equal(names, out_names,
                "the breakdown names exactly the checks that actually wrote a .out")


def check_emit_splits_battery_from_adhoc_when_both_ran_together(t):
    # --emit alone, WITHOUT --only, is the case the two checks above never exercise: battery
    # and ad-hoc checks running side by side in the one pool, and the breakdown having to
    # tell them apart correctly rather than just reporting an empty adhoc bucket because
    # nothing ad-hoc was passed at all.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        adhoc = os.path.join(d, "my-adhoc-check.py")
        with open(adhoc, "w") as fh:
            fh.write("print('hello from the adhoc check')\n")
        emit_path = os.path.join(d, "run-checks-emit.json")
        _run(scripts, d, ck, extra=["--also", adhoc, "--emit", emit_path])
        with open(emit_path) as fh:
            emitted = json.load(fh)
        entry = next(c for c in emitted["checks"] if c["name"] == "my-adhoc-check.py")
        t.equal(entry["adhoc"], True, "the --also entry is flagged adhoc in the breakdown")
        t.equal(emitted["adhoc"]["count"], 1, "and counted in the adhoc bucket")
        battery_names = {c["name"] for c in emitted["checks"] if c["name"] != "my-adhoc-check.py"}
        t.equal(all(not c["adhoc"] for c in emitted["checks"] if c["name"] in battery_names),
                True, "while every battery check stays flagged battery, not adhoc")
        t.equal(emitted["battery"]["count"], len(battery_names),
                "so battery.count reflects only the non---also checks")


def check_only_restricts_execution_with_a_control(t):
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        _run_into(scripts, d, ck, os.path.join(d, "out-full"))
        _run_into(scripts, d, ck, os.path.join(d, "out-only"),
                 extra=["--only", "unmeasured-surface.py"])
        full_outs = os.listdir(os.path.join(d, "out-full"))
        only_outs = os.listdir(os.path.join(d, "out-only"))
        t.equal(len(full_outs) > 1, True,
                "CONTROL: a run without --only writes more than one .out file")
        t.equal(only_outs, ["unmeasured-surface.out"],
                "--only restricts this run to exactly the named check")
        t.equal(len(only_outs) < len(full_outs), True,
                "and it is strictly fewer subprocess calls than the full battery")


def check_only_composes_with_also_to_skip_the_battery(t):
    # The measured waste this exists to fix: one saved run's --also cost ~194s of re-running
    # twelve checks that had not changed. --only <adhoc basename> is how a second pass avoids
    # paying that twice.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        adhoc = os.path.join(d, "my-adhoc-check.py")
        with open(adhoc, "w") as fh:
            fh.write("print('hello from the adhoc check')\n")
        out_dir = os.path.join(d, "out-adhoc")
        proc = _run_into(scripts, d, ck, out_dir,
                         extra=["--also", adhoc, "--only", "my-adhoc-check.py"])
        outs = os.listdir(out_dir)
        t.equal(outs, ["my-adhoc-check.out"],
                "--also plus --only on its own basename runs JUST the ad-hoc check")
        t.absent(proc.stdout + proc.stderr, "unmeasured-surface.py",
                 "and none of the battery's own checks are named as having run")


def check_an_unknown_only_name_errors_before_writing_anything(t):
    # Same shape as the renamed-ALWAYS-entry guard above: a wiring mistake refuses to start
    # rather than silently running a shorter list than the one asked for.
    with harness.tmpdir() as d, harness.fake_checkout() as ck:
        scripts = _copy_scripts(d)
        out_dir = os.path.join(d, "out-bad-only")
        proc = _run_into(scripts, d, ck, out_dir, extra=["--only", "does-not-exist.py"])
        t.equal(proc.returncode != 0, True, "an unknown --only name refuses to start")
        t.contains(proc.stdout + proc.stderr, "does-not-exist.py",
                   "naming the check that was not found")
        t.equal(os.path.isdir(out_dir), False,
                "and it stops before writing any check output at all")
