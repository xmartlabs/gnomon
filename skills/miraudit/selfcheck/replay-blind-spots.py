"""The blind-spot registry: derived identity, one gate rule, and no prose.

Across the saved payloads there are 357 distinct `not_checked` strings collapsing to ~228
holes. One hole carries SIXTEEN wordings. One finding appears under five different hand-typed
ids. Nothing could count any of it, because nothing tied a declaration to an identity.

The rule that matters is the least obvious one: several recorded reopening conditions reduce to
"a corpus arrives whose signals sit below a pinned threshold", which is decidable from the run's
own artifacts -- and the run this was built against carried five such observations while runs
kept re-declaring the same hole as open.
"""
import json
import os
import harness

NEEDS = ()

bs = harness.load("blind-spots.py")
gate = harness.load("emit-gate.py")


def _registry(root, entries):
    path = os.path.join(root, "blind-spots.json")
    with open(path, "w") as fh:
        json.dump({"entries": entries}, fh)
    return path


def _entry(**over):
    body = {"id": "Alpha/calibration/sig", "anchor": "Alpha", "kind": "calibration",
            "term": "sig", "runs": 4, "first_seen": "2026-08-10",
            "last_seen": "2026-08-20", "reopens_when": None}
    body.update(over)
    return body


def _doc(not_checked, axis="Alpha"):
    return {"axes": [{"name": axis, "not_checked": not_checked}],
            "findings": [], "not_raised": [], "reported": []}


def check_two_wordings_of_one_hole_reach_one_key(t):
    # The whole point. The prose is free and the key never reads it.
    a, _ = bs.keys_in(_doc([{"kind": "calibration", "term": "sig",
                             "note": "is the target fitted against anything at all"}]))
    b, _ = bs.keys_in(_doc([{"kind": "calibration", "term": "sig",
                             "note": "nobody has published the distribution this assumes"}]))
    t.equal(a, b, "two unrelated sentences about one hole produce the same key")
    t.equal(sorted(a), ["Alpha/calibration/sig"], "and it is derived from position and kind")


def check_a_different_kind_moves_the_key(t):
    # CONTROL for the check above: if every entry collapsed to one key the count would be a
    # constant, and a constant is not an identity.
    a, _ = bs.keys_in(_doc([{"kind": "calibration", "term": "sig", "note": "x"}]))
    b, _ = bs.keys_in(_doc([{"kind": "population", "term": "sig", "note": "x"}]))
    t.equal(a != b, True, "CONTROL: changing the kind changes the key")


def check_a_bare_string_stays_legal_and_is_counted_once(t):
    # 29 payloads on disk are bare strings and the shipped example run is one of them. Failing
    # them would make the migration the gate's problem instead of the writer's, and N lines of
    # nagging is how a summary stops being read -- so it is ONE line.
    keyed, unkeyed = bs.keys_in(_doc(["a sentence nobody keyed", "another one"]))
    t.equal(keyed, set(), "bare strings produce no key")
    t.equal(unkeyed, 2, "and are counted, not rejected")


def check_the_shipped_example_run_is_not_refused(t):
    # Regression guard on the real thing, not on a fixture of it.
    path = os.path.join(harness.SKILL, "references", "example-run",
                        "miraudit-2026-08-10.json")
    if not os.path.exists(path):
        t.note("no example-run on disk")
        return
    with open(path) as fh:
        doc = json.load(fh)
    viol, _lines = bs.report(doc, None, None)
    t.equal(viol, [], "the shipped example run produces no blind-spot violation")


def check_a_met_reopening_condition_is_a_violation(t):
    with harness.tmpdir() as d:
        reg = _registry(d, [_entry(reopens_when={
            "kind": "signal_below_threshold", "signal": "sig", "threshold": "SIG_TARGET"})])
        sat = {"signals_cut": [{"signal": "sig", "above_threshold": False}]}
        viol, _ = bs.report(_doc([]), sat, None, path=reg)
        t.equal(len(viol), 1, "exactly one violation")
        t.contains(viol[0], "Alpha/calibration/sig", "naming the entry")
        t.contains(viol[0], "below its threshold", "and what the corpus showed")


def check_a_signal_above_its_threshold_is_not_a_violation(t):
    # THE control. Without it the rule passes by always firing, which is the failure mode that
    # would take the gate's credibility with it: a wrong red whose cheapest fix is editing the
    # registry turns a post-measurement gate into something runs edit to go green.
    with harness.tmpdir() as d:
        reg = _registry(d, [_entry(reopens_when={
            "kind": "signal_below_threshold", "signal": "sig", "threshold": "SIG_TARGET"})])
        sat = {"signals_cut": [{"signal": "sig", "above_threshold": True}]}
        viol, _ = bs.report(_doc([]), sat, None, path=reg)
        t.equal(viol, [], "CONTROL: a saturated signal reopens nothing")


def check_a_missing_saturation_file_is_not_a_violation(t):
    with harness.tmpdir() as d:
        reg = _registry(d, [_entry(reopens_when={
            "kind": "signal_below_threshold", "signal": "sig", "threshold": "SIG_TARGET"})])
        viol, lines = bs.report(_doc([]), None, None, path=reg)
        t.equal(viol, [], "no saturation output means nothing is judged")
        t.contains(" ".join(lines), "not evaluable",
                   "and the count of unjudged conditions is stated")
        t.contains(" ".join(lines), "NOT EVALUABLE Alpha/calibration/sig",
                   "naming which one, so the fix is to widen saturation, not to guess here")


def check_a_new_key_is_reported_and_never_failed(t):
    # Failing a new hole would punish the run that found something, and would turn the registry
    # into guidance by the back door: runs would start writing to fit it.
    with harness.tmpdir() as d:
        reg = _registry(d, [_entry()])
        doc = _doc([{"kind": "other-backend", "term": "brand_new"}])
        viol, lines = bs.report(doc, None, None, path=reg)
        t.equal(viol, [], "a key in no registry is not a failure")
        t.contains(" ".join(lines), "1 new", "and the summary says one is new")
        t.contains(" ".join(lines), "Alpha/other-backend/brand_new", "naming it")


def check_prose_in_the_registry_is_refused(t):
    # The check least worth shipping without: it is what stops the anchoring hazard creeping
    # back one helpful sentence at a time. An entry that explains itself is a hypothesis a
    # cold run can adopt before measuring anything.
    with harness.tmpdir() as d:
        reg = _registry(d, [_entry(why="the target was never fitted against a population")])
        _entries, bad = bs.load_registry(reg)
        t.equal(len(bad), 1, "a registry entry carrying prose is a violation")
        t.contains(bad[0], "why", "naming the offending key")


def check_a_kind_outside_the_vocabulary_is_refused(t):
    with harness.tmpdir() as d:
        reg = _registry(d, [_entry(kind="calibraton")])
        _entries, bad = bs.load_registry(reg)
        t.equal(len(bad), 1, "a typo'd kind is refused rather than silently making a new key")
        t.contains(bad[0], "vocabulary", "and the message names the closed set")


def check_every_shipped_kind_passes(t):
    # CONTROL for the check above, iterated from the SHIPPED vocabulary so a tenth kind is
    # covered the day it is added.
    with harness.tmpdir() as d:
        for kind in sorted(gate.BLIND_SPOT_KINDS):
            reg = _registry(d, [_entry(kind=kind)])
            _entries, bad = bs.load_registry(reg)
            t.equal(bad, [], f"CONTROL: shipped kind `{kind}` is accepted")


def check_the_shipped_registry_is_schema_pure(t):
    entries, bad = bs.load_registry()
    t.equal(bad, [], "the registry that ships carries keys only, and no kind outside the set")
    t.equal(len(entries) > 0, True, "vacuity guard: it is not empty")


def check_there_is_no_browse_mode(t):
    # Not a style preference. A cold run that reads a list of holes before measuring stops
    # measuring and starts confirming; that happened here with known-state.md and the run
    # reported it as friction.
    import contextlib
    import io as _io
    buf = _io.StringIO()
    code = None
    try:
        with harness.quiet():
            with contextlib.redirect_stdout(buf):
                bs.main([])
    except SystemExit as exc:
        code = exc.code
    t.equal(code not in (0, None), True, "asking without --run exits non-zero")
    t.contains(str(code), "no browse mode",
               "and says the absence is deliberate rather than looking like a missing feature")


def check_the_verdict_does_not_depend_on_the_working_directory(t):
    """A gate that answers differently depending on where you were standing is not a gate.

    This read `flags_dir or os.getcwd()`, so run from the skill tree -- which is what Phase 4
    implies -- it looked for saturation.json where nobody writes one, evaluated 0 of 5
    reopening conditions, and printed "carries no row for cli_share" about a file that plainly
    carries it. Found by a cold run, which is the only thing that stands in the real directory.

    The same fail-open the flag walk-up exists to close, reintroduced one function later.
    """
    import os as _os
    with harness.tmpdir() as d:
        run_dir = _os.path.join(d, "run")
        checks = _os.path.join(run_dir, "checks")
        _os.makedirs(checks)
        # Rows for the signals the SHIPPED registry actually names, read from it rather than
        # invented: gate.check() uses the shipped registry, so a fixture full of made-up
        # signal names leaves every condition unevaluable either way and the arms agree for
        # the wrong reason. That is how the first version of this check passed against the bug.
        entries, _bad = bs.load_registry()
        rows = [{"signal": (e.get("reopens_when") or {}).get("signal"),
                 "above_threshold": True}
                for e in entries
                if (e.get("reopens_when") or {}).get("kind") == "signal_below_threshold"]
        t.equal(bool(rows), True, "vacuity guard: the shipped registry names signals to probe")
        with open(_os.path.join(checks, "saturation.json"), "w") as fh:
            json.dump({"signals_cut": rows}, fh)
        run_path = _os.path.join(run_dir, "miraudit-2026-08-20.json")
        doc = harness.payload(findings=[harness.finding()])
        doc["axes"] = [{"name": "Alpha", "not_checked": []}]
        with open(run_path, "w") as fh:
            json.dump(doc, fh)

        # One of these directories is the one a buggy cwd-relative lookup WOULD find the file
        # in, and the others are not. Without `checks` in the list every arm agreed on "no
        # saturation anywhere" and the check passed against the bug -- the fixture has to make
        # the two behaviours produce different answers before comparing them.
        seen = []
        for cwd in (harness.SKILL, checks, run_dir, d):
            here = _os.getcwd()
            try:
                _os.chdir(cwd)
                notes = []
                gate.check(doc, doc_path=run_path, flags_dir=None, notes=notes)
                line = next((n for n in notes if "reopen conditions met" in n), "")
                seen.append(line)
            finally:
                _os.chdir(here)
        t.equal(len(set(seen)), 1,
                "the same payload gets the same answer from three working directories")
        t.equal(bool(seen[0]), True, "vacuity guard: a summary line was produced at all")
