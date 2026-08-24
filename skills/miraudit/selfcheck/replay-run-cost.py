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


def _emit(t, root, stats=None):
    """Drive new-run.py against an EMPTY corpus.

    It walks the corpus for the fingerprint, and pointing it at the real one made each of
    these checks take eight seconds and depend on whose machine it ran on. An empty
    directory satisfies needs_corpus (the requirement is that it exists), produces a zero
    fingerprint, and leaves run_cost -- the thing under test -- untouched.
    """
    out = os.path.join(root, "miraudit-probe.json")
    stats = stats or os.path.join(root, "report", "stats.json")
    empty_corpus = os.path.join(os.path.dirname(root.rstrip("/")), "empty-corpus")
    os.makedirs(empty_corpus, exist_ok=True)
    subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, "new-run.py"),
         "--checkout", t.checkout, "--corpus", empty_corpus,
         "--stats", stats,
         "--since", "2026-07-13", "--until", "2026-08-12", "--out", out],
        capture_output=True, text=True, timeout=300)
    if not os.path.exists(out):
        t.failures.append("new-run.py wrote no payload at all")
        return None
    return json.load(open(out))


def _write_anchor(stats_dir, pipeline_seconds):
    """anchor.json, in the exact directory new-run.py resolves it from: `dirname(--stats)`.

    Omitting `pipeline_seconds` (pass None) writes the file WITHOUT the key, modelling an
    anchor.json written by anchor.py before this field existed -- a different case from no
    anchor.json at all, and the one that is easy to get wrong by defaulting to 0.
    """
    os.makedirs(stats_dir, exist_ok=True)
    body = {"ref": "abc1234", "measured_ref": "abc1234"}
    if pipeline_seconds is not None:
        body["pipeline_seconds"] = pipeline_seconds
    with open(os.path.join(stats_dir, "anchor.json"), "w") as fh:
        json.dump(body, fh)


def check_the_payload_has_a_slot_for_what_the_run_cost(t):
    with harness.tmpdir() as d:
        doc = _emit(t, _run_dir(d))
        if doc is None:
            return
        t.equal("run_cost" in doc, True, "the skeleton carries run_cost")
        t.equal(sorted(doc["run_cost"]), ["adhoc_checks", "arms", "checks", "phases", "wall"],
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


# ---- run_cost.phases --------------------------------------------------------------------
# anchor.py is the only large script in this skill with no internal timing. Two real cold
# runs measured the orchestrating session at 767s/1163s while run_cost.wall (mtimes of the
# output directory) only covered 578s/933s of that -- the gap was Phase 0 (anchor.py's
# shell-out to the external scoring pipeline), invisible end to end. `0_anchor` is anchor.py's
# own timer, read out of anchor.json; `4_synthesis` is the one honest way to get the rest,
# `wall.seconds - 0_anchor`, and it is a residual and says so, not a second measurement.

def check_phase_0_anchor_is_read_from_anchor_json(t):
    with harness.tmpdir() as d:
        run_root = _run_dir(d)
        _write_anchor(os.path.join(run_root, "report"), pipeline_seconds=240)
        doc = _emit(t, run_root)
        if doc is None:
            return
        phases = (doc.get("run_cost") or {}).get("phases") or {}
        t.equal(phases.get("0_anchor"), 240,
                "0_anchor is anchor.py's own pipeline_seconds, not re-derived from mtimes")


def check_phase_0_anchor_is_null_without_an_anchor_json(t):
    # CONTROL side of the field: most saved runs predate anchor.json entirely, and this is
    # the shape every one of those files has -- there is no anchor.json at dirname(stats) at
    # all, as opposed to one present but missing the key (the check below).
    with harness.tmpdir() as d:
        doc = _emit(t, _run_dir(d))
        if doc is None:
            return
        phases = (doc.get("run_cost") or {}).get("phases") or {}
        t.equal(phases.get("0_anchor"), None,
                "no anchor.json at all yields null, not a fabricated zero")


def check_phase_0_anchor_is_null_with_an_old_shaped_anchor_json(t):
    # The other absence: anchor.json exists (a run made with a pre-timing anchor.py) but
    # carries no pipeline_seconds key. `.get()` on the loaded dict returns None either way,
    # but this is the shape a real old saved run actually has, so it is worth its own check.
    with harness.tmpdir() as d:
        run_root = _run_dir(d)
        _write_anchor(os.path.join(run_root, "report"), pipeline_seconds=None)
        doc = _emit(t, run_root)
        if doc is None:
            return
        phases = (doc.get("run_cost") or {}).get("phases") or {}
        t.equal(phases.get("0_anchor"), None,
                "an anchor.json written before this field existed yields null too")
        t.equal(phases.get("4_synthesis"), None,
                "and with no 0_anchor to subtract, the residual is null as well -- not "
                "wall.seconds unchanged, which would silently claim Phase 0 took no time")


def check_phase_4_synthesis_is_the_wall_minus_anchor(t):
    """CONTROL: with a known wall (~REAL_SECONDS, the fixture's nominal span) and a known
    0_anchor, the residual is a SPECIFIC predictable number, not merely "present". Asserting
    only `is not None` would pass a synthesis field computed any which way, including a copy
    of `wall.seconds` that never subtracted anything.
    """
    with harness.tmpdir() as d:
        run_root = _run_dir(d)
        _write_anchor(os.path.join(run_root, "report"), pipeline_seconds=300)
        doc = _emit(t, run_root)
        if doc is None:
            return
        phases = (doc.get("run_cost") or {}).get("phases") or {}
        want = REAL_SECONDS - 300
        got = phases.get("4_synthesis")
        t.equal(got is not None and abs(got - want) <= 2, True,
                "CONTROL: wall (~%ss) minus 0_anchor (300s) is ~%ss, got %r"
                % (REAL_SECONDS, want, got))


def check_the_anchor_work_root_is_spanned_even_when_it_is_named_anchor(t):
    """Until 2026-08-24, `dirname(--stats)` was never spanned as a root of its own -- only
    `dirname(--out)` was walked, and this fixture's `anchor/` was pruned from THAT walk by
    name (EXCLUDE_FROM_SPAN). Naming the anchor-work root literally `anchor/` used to make it
    invisible on both counts at once: pruned as a child, and never walked as a root in its own
    right. That double invisibility is not what caused the real bug (the real anchor-work
    directory was a session scratchpad, never named `anchor/`), but this fixture is kept and
    updated rather than deleted, because it is the sharpest possible case: if the fix still
    special-cased "unless the directory is called anchor", this is exactly the fixture that
    would go on passing with the OLD behavior while masking the real regression.

    EXCLUDE_FROM_SPAN only prunes CHILDREN of a walk, never the root being walked -- so once
    `_combine_spans` wiring spans `dirname(--stats)` directly, its name stops mattering, and
    this fixture flips from "wall missing" to "wall present, read from the anchor-work root".
    """
    with harness.tmpdir() as d:
        stats_dir = os.path.join(d, "anchor")
        os.makedirs(stats_dir, exist_ok=True)
        stats_path = os.path.join(stats_dir, "stats.json")
        with open(stats_path, "w") as fh:
            fh.write("{}")
        # A controlled gap, not back-to-back writes: makes the span a fixed number instead of
        # whatever the test machine's own write speed happens to produce between two files.
        GAP = 5
        t0 = time.time() - GAP
        os.utime(stats_path, (t0, t0))
        _write_anchor(stats_dir, pipeline_seconds=200)
        os.utime(os.path.join(stats_dir, "anchor.json"), (t0 + GAP, t0 + GAP))
        doc = _emit(t, d, stats=stats_path)
        if doc is None:
            return
        run_cost = doc.get("run_cost") or {}
        wall = run_cost.get("wall") or {}
        t.equal(abs(wall.get("seconds", -1) - GAP) <= 1, True,
                "wall now comes from the anchor-work root's own two files (~%ss apart), not "
                "None -- dirname(--stats) is spanned regardless of what it is named, got %r"
                % (GAP, wall))
        t.contains(wall.get("derived_from", ""), "anchor-work root",
                   "and says the span came from the anchor-work root, not the output "
                   "directory it did not actually come from")
        phases = run_cost.get("phases") or {}
        t.equal(phases.get("0_anchor"), 200,
                "0_anchor is unaffected -- always read from anchor.json directly, never from "
                "mtimes")
        want_synthesis = round(wall["seconds"] - 200) if wall else None
        t.equal(phases.get("4_synthesis"), want_synthesis,
                "4_synthesis is still wall.seconds - 0_anchor, computed honestly even where "
                "it comes out negative in a fixture this degenerate (no other artifact in "
                "either root) -- emit-gate.py's negative-synthesis rule is the backstop for "
                "exactly this shape, new-run.py does not clamp it")


# ---- the real 2026-08-24 shape: two SEPARATE roots, neither nested in the other ----------
# _run_dir() above nests report/ under root, and the old single-root walk already saw it fine
# because a walk of a root recursively sees its own subdirectories. The real bug was never
# about nesting: anchor.py's work directory was a dispatched agent's session scratchpad
# (/private/tmp/.../scratchpad/anchor-work/) and --out pointed the payload at a completely
# different tree under miraudit-runs/. Neither contained the other. anchor.json's mtime
# (15:04:44) was 153 seconds earlier than the earliest file the old code could see in the
# --out tree alone (15:07:17) -- not excluded, not missed by a rule, structurally absent from
# the walk because the walk never started there. `4_synthesis` came out `-34.0` in the real
# payload as a result.

def _separate_roots(base, gap, pipeline_seconds):
    """Two sibling directories, deliberately not nested either way."""
    anchor_work = os.path.join(base, "anchor-work")
    run_dir = os.path.join(base, "run-dir")
    os.makedirs(anchor_work, exist_ok=True)
    os.makedirs(run_dir, exist_ok=True)

    stats_path = os.path.join(anchor_work, "stats.json")
    with open(stats_path, "w") as fh:
        fh.write("{}")
    t_anchor = time.time() - REAL_SECONDS - gap
    os.utime(stats_path, (t_anchor, t_anchor))
    _write_anchor(anchor_work, pipeline_seconds=pipeline_seconds)
    os.utime(os.path.join(anchor_work, "anchor.json"), (t_anchor, t_anchor))

    t_run_start, t_run_end = t_anchor + gap, t_anchor + gap + REAL_SECONDS
    for name, when in (("checks-run-checks-emit.json", t_run_start), ("report.md", t_run_end)):
        path = os.path.join(run_dir, name)
        with open(path, "w") as fh:
            fh.write("x")
        os.utime(path, (when, when))
    return anchor_work, run_dir, stats_path


def check_the_combined_span_reaches_into_a_separate_anchor_work_root(t):
    """The single most important check in this file: the real failure shape, scaled down
    from REAL_SECONDS/153s to something a test can assert deterministically without waiting
    on it. Asserts the three things the fix promises: the combined span is anchored to
    whichever root's earliest file is actually earliest (not just the run directory's own),
    the residual comes out non-negative once the anchor-work root is actually visible, and
    `derived_from` says plainly that two directories were unioned.
    """
    GAP = 50
    with harness.tmpdir() as d:
        anchor_work, run_dir, stats_path = _separate_roots(d, gap=GAP, pipeline_seconds=200)
        doc = _emit(t, run_dir, stats=stats_path)
        if doc is None:
            return
        run_cost = doc.get("run_cost") or {}
        wall = run_cost.get("wall") or {}
        t.equal(bool(wall), True,
                "a run split across two separate roots still gets a wall block")
        if wall:
            want_seconds = REAL_SECONDS + GAP
            t.equal(abs(wall["seconds"] - want_seconds) <= 2, True,
                    "combined span reaches back to anchor.json's mtime, %ss earlier than the "
                    "run directory's own earliest file, not just the run directory's own "
                    "%ss -- got %ss" % (GAP, REAL_SECONDS, wall.get("seconds")))
            t.contains(wall.get("derived_from", ""), "TWO directories",
                       "and says plainly the span covers two directories, not one")
        phases = run_cost.get("phases") or {}
        synthesis = phases.get("4_synthesis")
        t.equal(synthesis is not None and synthesis >= 0, True,
                "4_synthesis must be non-negative once the anchor-work root is actually "
                "visible: pipeline_seconds=200 against a combined wall of ~%ss "
                "(REAL_SECONDS + the %ss gap only the anchor-work root could see), got %r"
                % (REAL_SECONDS + GAP, GAP, synthesis))


def check_the_common_case_omitting_out_is_untouched(t):
    """CONTROL for the whole fix, using new-run.py's OWN default rather than an
    approximation of it: with `--out` omitted, `out = dirname(abspath(stats)) /
    "miraudit-<until>.json"` by construction, so dirname(out) == dirname(stats) EXACTLY, not
    merely nested -- the same directory. Every run before 2026-08-24 took this path, which is
    why the bug went unnoticed until a dispatched cold run was the first to pass an explicit
    --out elsewhere. new-run.py's wiring guards the second span with
    `abspath(_stats_dir) != abspath(_run_dir)`, so this scenario must never reach
    _combine_spans with two real sides -- checked two ways: the wording stays single-root,
    and the seconds figure matches exactly what the unmodified single-root walk gives.
    """
    with harness.tmpdir() as d:
        stats_path = os.path.join(d, "stats.json")
        report_path = os.path.join(d, "report.md")
        t0 = time.time() - REAL_SECONDS
        for path, when in ((stats_path, t0), (report_path, t0 + REAL_SECONDS)):
            with open(path, "w") as fh:
                fh.write("{}" if path.endswith(".json") else "x")
            os.utime(path, (when, when))
        empty_corpus = os.path.join(d, "empty-corpus")
        os.makedirs(empty_corpus, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, os.path.join(harness.SCRIPTS, "new-run.py"),
             "--checkout", t.checkout, "--corpus", empty_corpus, "--stats", stats_path,
             "--since", "2026-07-13", "--until", "2026-08-12"],
            capture_output=True, text=True, timeout=300)
        out = os.path.join(d, "miraudit-2026-08-12.json")
        if not os.path.exists(out):
            t.failures.append("new-run.py wrote no payload at the default path: " +
                              (proc.stderr or proc.stdout or "")[-300:])
            return
        doc = json.load(open(out))
        wall = (doc.get("run_cost") or {}).get("wall") or {}
        t.equal(bool(wall), True, "CONTROL: still gets a wall block")
        t.absent(wall.get("derived_from", ""), "TWO directories",
                 "CONTROL: dirname(out) == dirname(stats) by construction when --out is "
                 "omitted, so the second span never fires and the wording stays single-root")
        t.equal(abs(wall.get("seconds", -1) - REAL_SECONDS) <= 2, True,
                "CONTROL: the span is exactly what the unmodified single-root walk would "
                "have produced, got %r" % wall.get("seconds"))
