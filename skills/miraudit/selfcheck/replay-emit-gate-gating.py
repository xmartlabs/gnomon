"""emit-gate.check(): the rules that decide whether a run may be rendered at all.

Every check passes an explicit empty flags_dir. check(doc_path=None) falls back to
os.getcwd(), so a stray grounding-diverged.json anywhere near the repo root would otherwise
turn results over without anyone noticing.

The eight-row assertions are generated from the SHIPPED ROWS, so a ninth row is covered the
day it lands rather than the day someone remembers this file.
"""
import contextlib
import io
import json
import os
import harness

NEEDS = ()

gate = harness.load("emit-gate.py")


_REAL_PINNED = gate.pinned_ref
_RESOLVED = _REAL_PINNED()


def _check(doc, flags_dir, notes=None):
    """gate.check() with the pin resolved once instead of once per call.

    check() asks pin-consistency.py for the pinned ref by SUBPROCESS, and this file calls it
    forty-two times. That was seven seconds of a tier whose entire argument is that it costs
    nothing to run, and a suite people skip is a suite that stops catching things.

    The two checks below that deliberately patch pinned_ref are left alone: the cache is
    substituted only while the shipped function is still the one installed.
    """
    patched = gate.pinned_ref is not _REAL_PINNED
    if not patched:
        gate.pinned_ref = lambda: _RESOLVED
    try:
        return gate.check(doc, doc_path=None, flags_dir=flags_dir, notes=notes)
    finally:
        if not patched:
            gate.pinned_ref = _REAL_PINNED


def _where(bad, prefix):
    return [v for v in bad if v.startswith(prefix)]


def check_empty_skeleton_is_refused(t):
    """The shape new-run.py writes before anyone fills it in must not read as 'clean'.

    The gate's rules are gated on findings[] being non-empty, so an untouched skeleton used
    to exit 0 printing 'clean. Every finding answered all eight Phase 3 rows.' -- a sentence
    about eight rows nobody answered. It even NOTED that the payload had no tool.ref and
    passed anyway.
    """
    with harness.tmpdir() as flags:
        bad = _check(harness.skeleton(), flags)
        t.equal(bool(bad), True, "the untouched skeleton is refused")
        t.equal(bool(_where(bad, "corpus:")), True,
                "and the violation names `corpus`, the field output-schema.md already "
                "calls mandatory")


def check_populated_corpus_passes(t):
    # CONTROL for the rule above. Without it, "refuses the skeleton" could mean "refuses
    # everything", which would stop every real run instead of the empty ones.
    with harness.tmpdir() as flags:
        t.equal(_where(_check(harness.payload(), flags), "corpus:"), [],
                "CONTROL: a payload with a real fingerprint raises no corpus violation")


def check_an_empty_window_is_still_a_measurement(t):
    # The rule is presence, never magnitude: a window with no activity is a legitimate
    # result, and failing it would make the gate an opinion about the corpus.
    with harness.tmpdir() as flags:
        doc = harness.payload(corpus={"tool_calls": 0, "sessions": 0, "sidechain_share": None,
                                      "window": "2026-07-12 -> 2026-08-11", "sources": []})
        t.equal(_where(_check(doc, flags), "corpus:"), [],
                "zero tool calls is a number, not a missing field")


def check_a_partial_fingerprint_is_refused(t):
    """Some-but-not-all of the fingerprint reads as a comparable run and is not one.

    This check exists because fault injection said so: gutting the `missing` computation --
    the branch that catches a partial corpus -- turned nothing red. The empty-dict case was
    covered twice and the partial case not at all.
    """
    with harness.tmpdir() as flags:
        for drop in gate.CORPUS_KEYS:
            corpus = dict(harness.payload()["corpus"])
            del corpus[drop]
            bad = _where(_check(harness.payload(corpus=corpus), flags), "corpus:")
            t.equal(bool(bad), True, "a fingerprint missing %r is refused" % drop)
            if bad:
                t.contains(bad[0], drop, "and the violation names the missing field")
        # A present-but-null field is missing too: new-run.py writes nulls into the skeleton,
        # so `in (None, "")` is the load-bearing half, not `not in corpus`.
        corpus = dict(harness.payload()["corpus"])
        corpus[gate.CORPUS_KEYS[0]] = None
        t.equal(bool(_where(_check(harness.payload(corpus=corpus), flags), "corpus:")), True,
                "a null field counts as missing, not as present")
        # CONTROL: all four present and non-null is clean.
        t.equal(_where(_check(harness.payload(), flags), "corpus:"), [],
                "CONTROL: the complete fingerprint raises nothing")


def check_corpus_rule_is_not_gated_on_findings(t):
    # Same reasoning the shipped tool.ref rule already states: an empty-findings run still
    # publishes its axes and its dismissals, and the fingerprint is what places them.
    with harness.tmpdir() as flags:
        doc = harness.skeleton()
        doc["findings"] = []
        t.equal(bool(_where(_check(doc, flags), "corpus:")), True,
                "the corpus rule fires even with findings[] empty")


def check_all_buckets_empty_is_refused_on_its_own(t):
    """The skeleton signature, isolated from the corpus rule that also catches it.

    Fault injection wrote this one too: disabling the buckets rule turned nothing red,
    because the skeleton trips the corpus rule as well. A payload with a perfectly good
    fingerprint and nothing in any bucket is the case only this rule sees.
    """
    with harness.tmpdir() as flags:
        doc = harness.payload(dismissed=[])            # valid corpus, every bucket empty
        bad = _where(_check(doc, flags), "buckets:")
        t.equal(bool(bad), True, "a good fingerprint does not excuse an unfilled file")
        # CONTROL: ONE populated bucket is enough, and each of them counts.
        for bucket, entry in (("dismissed", {"id": "D1", "killed_by": "a fact"}),
                              ("findings", harness.finding()),
                              ("process_friction", {"what": "x", "cost": "y"})):
            one = harness.payload(dismissed=[])
            one[bucket] = [entry]
            t.equal(_where(_check(one, flags), "buckets:"), [],
                    "CONTROL: %r populated clears the rule" % bucket)


def check_a_clean_payload_is_clean(t):
    with harness.tmpdir() as flags:
        doc = harness.payload(findings=[harness.finding()])
        t.equal(_check(doc, flags), [], "the harness's own valid payload passes")


def check_every_row_must_be_answered(t):
    with harness.tmpdir() as flags:
        for key in gate.ROWS:
            f = harness.finding()
            del f["refuted"][key]
            bad = _check(harness.payload(findings=[f]), flags)
            t.equal(len(bad), 1, "deleting refuted.%s leaves exactly one violation" % key)
            if bad:
                t.contains(bad[0], "refuted.%s" % key, "and it names the missing row")


def check_row_verdict_fail_is_refused(t):
    with harness.tmpdir() as flags:
        key = sorted(gate.ROWS)[0]
        f = harness.finding()
        f["refuted"][key]["verdict"] = "fail"
        bad = _check(harness.payload(findings=[f]), flags)
        t.equal(len(bad), 1, "a failed row is exactly one violation")
        if bad:
            t.contains(bad[0], "dismissed[]", "and says where it belongs instead")
        # CONTROL: the same finding with the row passing is clean.
        f["refuted"][key]["verdict"] = "pass"
        t.equal(_check(harness.payload(findings=[f]), flags), [], "CONTROL: 'pass' is clean")


def check_row_note_required_and_stripped(t):
    with harness.tmpdir() as flags:
        key = sorted(gate.ROWS)[0]
        for note, want in (("", True), ("   ", True), ("a fact", False)):
            f = harness.finding()
            f["refuted"][key]["note"] = note
            bad = [v for v in _check(harness.payload(findings=[f]), flags) if "no note" in v]
            t.equal(bool(bad), want, "note %r is %s" % (note, "refused" if want else "fine"))


def check_verdict_vocabulary(t):
    with harness.tmpdir() as flags:
        key = sorted(gate.ROWS)[0]
        for verdict in sorted(gate.VERDICTS):
            f = harness.finding()
            f["refuted"][key]["verdict"] = verdict
            bad = _check(harness.payload(findings=[f]), flags)
            # 'fail' is a valid verdict AND a violation: it is answered, but it did not
            # survive. Vocabulary and outcome are two different rules.
            want = 1 if verdict == "fail" else 0
            t.equal(len(bad), want, "verdict %r" % verdict)
        for bogus in ("PASS", "ok"):
            f = harness.finding()
            f["refuted"][key]["verdict"] = bogus
            t.equal(bool(_check(harness.payload(findings=[f]), flags)), True,
                    "verdict %r is outside the vocabulary" % bogus)


def check_shape_direction_confidence_vocabularies(t):
    with harness.tmpdir() as flags:
        for field, allowed in (("shape", gate.SHAPES), ("direction", gate.DIRECTIONS),
                               ("confidence", gate.CONFIDENCE)):
            for value in sorted(allowed):
                t.equal(_check(harness.payload(findings=[harness.finding(**{field: value})]),
                               flags), [], "%s=%r is accepted" % (field, value))
            bad = _check(harness.payload(findings=[harness.finding(**{field: "made up"})]),
                         flags)
            t.equal(len(bad), 1, "%s outside its vocabulary is one violation" % field)


def check_evidence_triplet_required(t):
    with harness.tmpdir() as flags:
        for key in ("command", "control", "output"):
            f = harness.finding()
            f["evidence"][key] = ""
            bad = _check(harness.payload(findings=[f]), flags)
            t.equal(len(bad), 1, "a blank evidence.%s is one violation" % key)
            if bad:
                t.contains(bad[0], "evidence.%s" % key, "and names the field")


def check_not_checked_required(t):
    with harness.tmpdir() as flags:
        bad = _check(harness.payload(findings=[harness.finding(not_checked="")]), flags)
        t.equal(len(bad), 1, "an empty not_checked is one violation")


def check_what_would_close_it_optional_but_not_blank(t):
    with harness.tmpdir() as flags:
        t.equal(_check(harness.payload(findings=[harness.finding()]), flags), [],
                "absent is fine -- this gate governs the artifact, not the message")
        bad = _check(harness.payload(findings=[harness.finding(what_would_close_it="")]),
                     flags)
        t.equal(len(bad), 1, "present-but-blank is refused")


def check_anchor_branches(t):
    with harness.tmpdir() as flags:
        f = [harness.finding()]
        cases = (
            ({"ok": False, "note": "anything"}, True,
             "ok=false with findings is a hard stop -- Phase 0 is a gate"),
            ({"ok": None, "note": ""}, True, "ok=null with findings and no note is refused"),
            ({"ok": None, "note": "ran --local"}, False, "ok=null WITH a note is fine"),
            ({"ok": True, "note": ""}, False, "ok=true needs no note"),
        )
        for anchor, want, why in cases:
            bad = _where(_check(harness.payload(anchor=anchor, findings=f), flags), "anchor:")
            t.equal(bool(bad), want, why)
        # And with no findings, even ok=false is not an anchor violation: there is nothing
        # unsafe to read.
        t.equal(_where(_check(harness.payload(anchor={"ok": False, "note": ""}), flags),
                       "anchor:"), [], "ok=false with no findings raises no anchor violation")


def check_tool_ref_rule_searches_the_note_for_the_ref(t):
    real = gate.pinned_ref
    gate.pinned_ref = lambda: "aaaaaaa"
    try:
        with harness.tmpdir() as flags:
            f = [harness.finding()]
            for note, want, why in (
                ("", True, "a wrong ref with no note is refused"),
                ("deliberate re-pin", True,
                 "a non-empty note that does NOT name the ref is STILL refused -- this is "
                 "the case proving the rule searches for the ref rather than checking the "
                 "note is non-blank"),
                ("deliberate re-pin to bbbbbbb", False, "naming the ref clears it"),
            ):
                doc = harness.payload(tool={"name": "x", "ref": "bbbbbbb", "contract": "19"},
                                      anchor={"ok": None, "note": note}, findings=f)
                t.equal(bool(_where(_check(doc, flags), "tool.ref:")), want, why)
            # Prefix match, both directions.
            for ref in ("aaaaaaa", "aaaaaaa1234"):
                doc = harness.payload(tool={"name": "x", "ref": ref, "contract": "19"})
                t.equal(_where(_check(doc, flags), "tool.ref:"), [],
                        "ref %r matches the pin by prefix" % ref)
    finally:
        gate.pinned_ref = real


def check_missing_pin_degrades_to_a_note_not_a_pass(t):
    real = gate.pinned_ref
    gate.pinned_ref = lambda: None
    try:
        with harness.tmpdir() as flags:
            notes = []
            doc = harness.payload(tool={"name": "x", "ref": "bbbbbbb", "contract": "19"})
            t.equal(_where(_check(doc, flags, notes), "tool.ref:"), [],
                    "an unreadable pin does not manufacture a violation")
            t.equal(any("pin" in n for n in notes), True,
                    "but it is NOTED -- a gate that cannot tell 'nothing was wrong' from "
                    "'nobody looked' is not a gate")
    finally:
        gate.pinned_ref = real


def check_not_raised_carries_the_same_burden(t):
    with harness.tmpdir() as flags:
        base = harness.finding(id="NR1", why_not="too small", reconsider_if="it grows")
        t.equal(_check(harness.payload(not_raised=[base]), flags), [],
                "a complete not_raised entry is clean")
        for key in gate.NOT_RAISED_KEYS:
            entry = dict(base)
            entry[key] = ""
            bad = _check(harness.payload(not_raised=[entry]), flags)
            t.equal(len(bad), 1, "a blank %s is one violation" % key)
        entry = dict(base)
        del entry["refuted"]
        t.equal(bool(_check(harness.payload(not_raised=[entry]), flags)), True,
                "not_raised without a refuted block is refused")


def check_dismissed_and_reported_required_fields(t):
    with harness.tmpdir() as flags:
        t.equal(len(_check(harness.payload(dismissed=[{"id": "D1", "killed_by": ""}]),
                           flags)), 1, "dismissed without killed_by is one violation")
        t.equal(_check(harness.payload(dismissed=[{"id": "D1", "killed_by": "a fact"}]),
                       flags), [], "CONTROL: with killed_by it is clean")
        for key in ("confirmed_by", "state"):
            entry = {"id": "R1", "confirmed_by": "them", "state": "merged"}
            entry[key] = ""
            t.equal(len(_check(harness.payload(reported=[entry]), flags)), 1,
                    "reported without %s is one violation" % key)


def check_a_finding_must_say_what_it_is_about(t):
    """Either which axes, or which published surface -- never neither.

    The case that forced this: token_usage is summed per transcript line and feeds NO axis,
    so the only way to send it through a reporter that demanded `axes` was to write a false
    axis name. That is not cosmetic -- the flag rule below keys on axis names to decide
    whether a finding gets blocked because THAT axis's check could not reproduce its number,
    so an invented entry there changes the verdict too.
    """
    with harness.tmpdir() as flags:
        both_absent = harness.finding(axes=[])
        both_absent.pop("surface", None)
        bad = _check(harness.payload(findings=[both_absent]), flags)
        t.equal(len(bad), 1, "a finding naming neither is exactly one violation")
        if bad:
            t.contains(bad[0], "surface", "and the violation names the way out")

        # CONTROL, both directions: either one alone is enough.
        by_axis = harness.finding(axes=["Verification"])
        by_axis.pop("surface", None)
        t.equal(_check(harness.payload(findings=[by_axis]), flags), [],
                "CONTROL: naming axes is enough")

        by_surface = harness.finding(axes=[], surface='stats["token_usage"]')
        t.equal(_check(harness.payload(findings=[by_surface]), flags), [],
                "CONTROL: naming a surface is enough")

        blank = harness.finding(axes=[], surface="   ")
        t.equal(bool(_check(harness.payload(findings=[blank]), flags)), True,
                "a whitespace surface is not a name")


def check_cost_units_is_optional_but_typed_when_present(t):
    """`cost` stays prose; `cost_units` is the comparable half, and it is opt-in.

    Omitting it must always pass: inventing a number for a cost nobody measured is worse
    than having none, and 74 distinct prose values across the saved runs say the prose is
    where the value is.
    """
    with harness.tmpdir() as flags:
        base = {"phase": "0", "what": "the pipeline looked hung", "cost": "four re-runs"}
        t.equal(_where(_check(harness.payload(process_friction=[base]), flags),
                       "process_friction"), [],
                "CONTROL: no cost_units at all is clean -- the field is optional")

        good = dict(base, cost_units={"unit": "runs", "value": 4})
        t.equal(_where(_check(harness.payload(process_friction=[good]), flags),
                       "process_friction"), [], "a well-formed cost_units is clean")

        for unit in sorted(gate.COST_UNITS):
            entry = dict(base, cost_units={"unit": unit, "value": 0})
            t.equal(_where(_check(harness.payload(process_friction=[entry]), flags),
                           "process_friction"), [], "unit %r is in the vocabulary" % unit)

        for bad, why in (
            ({"unit": "coffees", "value": 2}, "a unit nobody else emits cannot be compared"),
            ({"unit": "runs", "value": "four"}, "prose in value belongs in `cost` instead"),
            ({"unit": "runs", "value": True}, "a bool is not a quantity"),
            ({"unit": "runs"}, "a unit with no value measures nothing"),
            ("four runs", "a bare string is not the structured half"),
        ):
            entry = dict(base, cost_units=bad)
            t.equal(bool(_where(_check(harness.payload(process_friction=[entry]), flags),
                                "process_friction")), True, why)


def check_run_cost_is_optional_but_typed_when_present(t):
    """`run_cost.checks/arms/adhoc_checks` used to be a bare number, and two saved runs wrote
    the SAME field with two different meanings under it: one wrote `13` meaning a COUNT of
    checks, the next wrote `101.3` meaning SECONDS of wall clock. Same shape as cost_units
    above: closed vocabulary, opt-in, and `null` stays legal for "not measured".

    `gate_retries` rides the exact same validation loop in emit-gate.py (widened, not
    duplicated -- see the `for key in (...)` tuple there), so it is folded into this same
    check rather than getting a copy of it.
    """
    with harness.tmpdir() as flags:
        t.equal(_where(_check(harness.payload(), flags), "run_cost"), [],
                "CONTROL: no run_cost at all is clean -- payloads written before this field "
                "existed carry none")

        blank = {"wall": None, "checks": None, "arms": None, "adhoc_checks": None,
                 "gate_retries": None}
        t.equal(_where(_check(harness.payload(run_cost=blank), flags), "run_cost"), [],
                "every field null is clean -- not measured is the common case (no A/B ran, "
                "so `arms` is null on most runs; a corrupted gate-attempt log is null too)")

        for key in ("checks", "arms", "adhoc_checks", "gate_retries"):
            for unit in sorted(gate.RUN_COST_UNITS):
                good = dict(blank, **{key: {"unit": unit, "value": 4}})
                t.equal(_where(_check(harness.payload(run_cost=good), flags), "run_cost"), [],
                        "%s with unit %r is in the vocabulary" % (key, unit))

            for bad, why in (
                (101.3, "a bare float is the exact ambiguous form that let seconds and a "
                        "count collide unlabeled"),
                (13, "a bare int is the exact ambiguous form that let seconds and a count "
                     "collide unlabeled"),
                ({"unit": "coffees", "value": 2}, "a unit nobody else emits cannot be "
                                                  "compared"),
                ({"unit": "seconds", "value": "sixty"}, "prose in value is not a quantity"),
                ({"unit": "seconds", "value": True}, "a bool is not a quantity"),
                ({"unit": "seconds"}, "a unit with no value measures nothing"),
                ("101.3 seconds", "a bare string is not the structured half"),
            ):
                entry = dict(blank, **{key: bad})
                t.equal(bool(_where(_check(harness.payload(run_cost=entry), flags),
                                    "run_cost")), True, "%s: %s" % (key, why))


def check_negative_synthesis_is_refused(t):
    """A 2026-08-24 cold run shipped `run_cost.phases.4_synthesis: -34.0` into a rendered
    report: `wall` was derived from a directory that never saw anchor.py's own work
    directory, so the residual it fed came out negative and nothing caught it. Fixed at the
    source in new-run.py (`_combine_spans`), and backstopped here: negative is never
    legitimate regardless of what produced it, so the gate refuses it outright rather than
    trusting the fix that closed today's specific cause to close every future one too.
    """
    with harness.tmpdir() as flags:
        for bad, why in ((-34.0, "the real shape: a float"), (-1, "an int is just as bad")):
            entry = {"phases": {"0_anchor": 100.0, "4_synthesis": bad}}
            t.equal(bool(_where(_check(harness.payload(run_cost=entry), flags),
                                "run_cost.phases.4_synthesis")), True,
                    "%s: a negative synthesis duration is refused" % why)

        t.equal(_where(_check(harness.payload(run_cost={"phases": {"4_synthesis": 0}}),
                              flags), "run_cost.phases.4_synthesis"), [],
                "CONTROL: zero is a legitimate residual, not refused")
        t.equal(_where(_check(harness.payload(run_cost={"phases": {"4_synthesis": 685.3}}),
                              flags), "run_cost.phases.4_synthesis"), [],
                "CONTROL: a normal positive residual is clean")
        t.equal(_where(_check(harness.payload(run_cost={"phases": {"4_synthesis": None}}),
                              flags), "run_cost.phases.4_synthesis"), [],
                "CONTROL: null (missing wall or missing 0_anchor) is not measured, not "
                "negative -- new-run.py's own control for this, unaffected")
        t.equal(_where(_check(harness.payload(run_cost={"phases": {"0_anchor": 100.0}}),
                              flags), "run_cost.phases.4_synthesis"), [],
                "CONTROL: 4_synthesis absent entirely (a payload from before this field "
                "existed) is clean")
        t.equal(_where(_check(harness.payload(run_cost={}), flags),
                       "run_cost.phases.4_synthesis"), [],
                "CONTROL: no phases object at all is clean")


def check_exit_codes(t):
    # render-report.py branches on this and nothing else pins it.
    with harness.tmpdir() as d:
        clean = os.path.join(d, "clean.json")
        json.dump(harness.payload(), open(clean, "w"))
        bad = os.path.join(d, "bad.json")
        json.dump(harness.skeleton(), open(bad, "w"))
        with contextlib.redirect_stdout(io.StringIO()):
            ok = gate.main(["emit-gate.py", clean])
            violating = gate.main(["emit-gate.py", bad])
            missing = gate.main(["emit-gate.py", os.path.join(d, "nope.json")])
        t.equal(ok, 0, "a clean payload exits 0")
        t.equal(violating, 1, "a violating payload exits 1")
        t.equal(missing, 2, "an unreadable path exits 2, distinct from a violation")


def check_the_measured_ref_rule_catches_what_tool_ref_cannot(t):
    """The comparison `tool.ref` was always described as making, and never made.

    anchor.py filled `tool.ref` from `pin-consistency.py --field ref`, which reads the ```pin
    block and ignores --checkout on purpose -- that value is what CLONES a checkout, so it
    cannot require one. emit-gate then compared that against pinned_ref(), the same call.
    Both sides came out of one constant and the rule was equal by construction.

    It was not theoretical: a cold run measured the read-only reference clone twelve commits
    behind the pin, the payload read the pin, and the gate passed clean.
    """
    with harness.tmpdir() as flags:
        pin = _RESOLVED
        doc = harness.payload(findings=[harness.finding()])
        doc["tool"] = {"name": "xl-ai-insights", "ref": pin, "contract": "19:19:19",
                       "measured_ref": "deadbee"}
        doc["anchor"] = dict(doc["anchor"], note="ran with --local")
        bad = _check(doc, flags)
        t.equal(bool(_where(bad, "tool.measured_ref:")), True,
                "a run against a ref the note does not name is refused")
        t.equal(bool(_where(bad, "tool.ref:")), False,
                "and the old rule stays silent, which is exactly why this one had to exist")


def check_naming_the_measured_ref_in_the_note_clears_it(t):
    # CONTROL. Measuring another ref on purpose is legitimate and has to cost four words, not
    # a refusal -- the same bar the tool.ref rule sets. A rule that refused either way would
    # pass the check above while making a deliberate run impossible to publish.
    with harness.tmpdir() as flags:
        doc = harness.payload(findings=[harness.finding()])
        doc["tool"] = {"name": "xl-ai-insights", "ref": _RESOLVED, "contract": "19:19:19",
                       "measured_ref": "deadbee"}
        doc["anchor"] = dict(doc["anchor"],
                             note="measured deadbee on purpose; both compute 19:19:19")
        bad = _check(doc, flags)
        t.equal(bool(_where(bad, "tool.measured_ref:")), False,
                "CONTROL: naming the ref in the note clears it")


def check_an_absent_measured_ref_is_not_a_failure(t):
    # A git-archive tree has no .git and cannot report a ref, and every payload written before
    # the field existed carries none. Failing on absence would refuse the whole back catalogue
    # and the contributor path, to say nothing about a mismatch nobody observed.
    with harness.tmpdir() as flags:
        doc = harness.payload(findings=[harness.finding()])
        doc["tool"] = {"name": "xl-ai-insights", "ref": _RESOLVED, "contract": "19:19:19"}
        bad = _check(doc, flags)
        t.equal(bool(_where(bad, "tool.measured_ref:")), False,
                "a payload with no measured_ref is not refused for lacking one")
