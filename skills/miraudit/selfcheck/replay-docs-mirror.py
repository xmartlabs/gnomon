"""Does the code read what the documentation says the payload carries?

Mechanism-level, not text-level: for each documented key, delete it, re-render and re-gate,
and require that SOMETHING changes. A key whose removal changes nothing is a key the code
does not read -- and a token match could never tell you that, because the word is present in
both files either way.

This is the check that found the skill's own example run had drifted: it carries `hypotheses`,
`verdict` and `corpus.sources_scored`, and no shipped code reads any of the three.
"""
import contextlib
import json
import os
import re
import harness

NEEDS = ()

rr = harness.load("render-report.py")
gate = harness.load("emit-gate.py")
ri = harness.load("render-issue.py")

SCHEMA_MD = os.path.join(harness.SKILL, "references", "output-schema.md")
EXAMPLE = os.path.join(harness.SKILL, "references", "example-run",
                       "miraudit-2026-08-10.json")

# Documented keys nothing reads YET, each with the reason it is allowed to be inert. An
# entry here is a decision on the record; a deleted assertion is not.
KNOWN_UNREAD = {
    "schema_version": "carried for future migrations; nothing branches on it yet",
    "run": "provenance for a human reader (date, label, purpose); the renderer does not "
           "consume it",
    "run_cost": "the gate validates checks/arms/adhoc_checks's shape when present and the "
                "schema documents it, but the renderer still does not surface it",
    # Superseded schema, preserved verbatim in references/example-run rather than migrated.
    # `verdict` is now derived by the renderer from `anchor` and the buckets; `hypotheses`
    # was split into findings/not_raised/dismissed. Migrating that entry would mean INVENTING
    # the eight refutation rows and the why_not/reconsider_if pair the current schema
    # requires for a not_raised, and fabricating a refutation is the exact thing this skill
    # exists to catch. So they stay, inert and named, instead of being quietly deleted or
    # quietly filled in.
    "verdict": "schema v0; the renderer derives its own verdict from anchor + buckets",
    "hypotheses": "schema v0; split into findings/not_raised/dismissed. Not migrated -- see "
                  "the note above on why fabricating the required rows would be worse",

    # Nested residue of the same v0 schema, in buckets whose OTHER fields are still current.
    # These cannot be waived by naming the bucket, because the bucket is live. Each is a
    # field the v0 example carries that the current schema does not document and no shipped
    # code reads; none is drift between the docs and the code, which is what this file
    # measures. The documented-schema check above is the one that would catch real drift,
    # and it is green.
    "axes[].note": "schema v0; the current axes entry carries evidence + not_checked",
    "axes[].shape": "schema v0; shapes belong to findings, and an axis is what is left when "
                    "a gap maps to no shape at all",
    "reported[].axes": "schema v0; a reported entry is a pointer to a sent issue, not a "
                       "second copy of the finding",
    "reported[].evidence": "schema v0; see reported[].axes",
    "reported[].magnitude": "schema v0; see reported[].axes",
    "reported[].not_checked": "schema v0; see reported[].axes",
    "reported[].shape": "schema v0; see reported[].axes",
    "process_friction[].fix": "schema v0; what was done about it lives in `what` now",
    "process_friction[].how_found": "schema v0; see process_friction[].fix",
}


def _documented_example():
    """The ```json block from output-schema.md, parsed. It is the schema's own worked
    example, so it is the honest list of what the docs claim a payload carries."""
    body = open(SCHEMA_MD, encoding="utf-8").read()
    match = re.search(r"```json\n(\{.*?\n\})\n```", body, re.S)
    if not match:
        return None
    text = re.sub(r'"…"', '"x"', match.group(1))
    try:
        return json.loads(text)
    except ValueError:
        return None


def _observable(doc):
    """Everything the SHIPPED code produces from a payload: the rendered report, the gate's
    verdict, and the issue draft. If deleting a key moves none of the three, nothing reads it.

    render-issue was missing here, and it is the consumer that matters most: it is the code
    path that PUBLISHES to a maintainer. Leaving it out made the walk ask "does the report or
    the gate read this", which is the wrong question for anything whose only reader is the
    draft. `findings[].what_would_close_it` is exactly that -- render-issue refuses to draft
    without it, render-report never prints it, and the gate only checks it when it is already
    present, so deleting it moved nothing and the field read as dead.

    These three are the whole set. emit-comparison.py is NOT a fourth: it reads gnomon's
    stats.json and the corpus and builds its own payload, and never opens a miraudit run.

    What no walk can observe is a person reading the JSON. That is a real residual limit of
    this check and not a to-do: some fields are recorded so a human or a later comparison can
    read them, and for those KNOWN_UNREAD with a written reason is the answer, not a fourth
    consumer.
    """
    notes = []
    try:
        rendered = rr.render(doc)
    except Exception as exc:                                   # noqa: BLE001
        rendered = "RENDER RAISED %s" % type(exc).__name__
    try:
        violations = sorted(gate.check(doc, doc_path=None, flags_dir=_EMPTY, notes=notes))
    except Exception as exc:                                   # noqa: BLE001
        violations = ["GATE RAISED %s" % type(exc).__name__]
    try:
        draft = ri.render(doc, set())
    except Exception as exc:                                   # noqa: BLE001
        # A raise IS an observation: render-issue refuses a payload missing what it needs,
        # and which exception it raises differs by which key went away.
        draft = "DRAFT RAISED %s %s" % (type(exc).__name__, exc)
    return rendered, violations, sorted(notes), draft


_EMPTY = None


@contextlib.contextmanager
def _pin_held():
    """Resolve the pin once instead of once per key.

    gate.check() asks pin-consistency.py for the pinned ref by SUBPROCESS, and this walk
    calls check() once per documented key. Deepening it into the bucket rows turned roughly
    fifty spawns into two hundred, and this one file into half the suite's wall clock -- a
    zero-token tier that takes long enough to skip stops being run, which is the whole
    argument for having one.

    Holding it fixed is sound here and not a shortcut: the pin does not vary between the
    arms being compared, so every arm sees the same value and the comparison is unchanged.
    """
    real = gate.pinned_ref
    resolved = real()
    gate.pinned_ref = lambda: resolved
    try:
        yield
    finally:
        gate.pinned_ref = real


def _unread_keys(doc):
    """Top-level, corpus.*, and bucket-row keys whose removal changes nothing the code emits."""
    baseline = _observable(doc)
    dead = []
    for key in sorted(doc):
        if key in KNOWN_UNREAD or not doc[key]:
            continue
        trimmed = {k: v for k, v in doc.items() if k != key}
        if _observable(trimmed) == baseline:
            dead.append(key)
    for key in sorted(doc.get("corpus") or {}):
        trimmed = json.loads(json.dumps(doc))
        del trimmed["corpus"][key]
        if _observable(trimmed) == baseline:
            dead.append("corpus.%s" % key)
    # Inside the list buckets too. This walk used to stop at the top level and at corpus.*,
    # which is shallower than the schema it mirrors -- and a documented field that lives one
    # level down was therefore invisible to the very check written to find inert fields.
    # `process_friction[].cost_units` was exactly that: defined in the schema, validated by
    # the gate, read by nothing, and reported by nothing because this loop never reached it.
    for bucket in sorted(doc):
        rows = doc.get(bucket)
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            continue
        # A bucket already ruled inert is not re-litigated field by field. Without this the
        # walk re-reported all eleven of `hypotheses`' keys, which is one decision already on
        # the record arriving eleven more times.
        if bucket in KNOWN_UNREAD:
            continue
        for key in sorted(rows[0]):
            if not rows[0][key] or "%s[].%s" % (bucket, key) in KNOWN_UNREAD:
                continue
            trimmed = json.loads(json.dumps(doc))
            for row in trimmed[bucket]:
                row.pop(key, None)
            if _observable(trimmed) == baseline:
                dead.append("%s[].%s" % (bucket, key))
    return dead


def check_the_schema_example_parses(t):
    # Vacuity guard. Every check below would pass trivially against a None.
    t.equal(_documented_example() is not None, True,
            "the ```json block in output-schema.md is present and parses")


def check_every_documented_key_is_read_by_the_code(t):
    global _EMPTY
    doc = _documented_example()
    if doc is None:
        return
    with harness.tmpdir() as d:
        _EMPTY = d
        with _pin_held():
            dead = _unread_keys(doc)
    t.equal(dead, [],
            "keys the schema documents that no shipped code reads (add to KNOWN_UNREAD with "
            "a reason, or wire them up)")


def check_the_control_catches_a_key_that_really_is_unread(t):
    """Without this, an empty `dead` list could mean the detector never fires at all."""
    global _EMPTY
    doc = _documented_example()
    if doc is None:
        return
    doc["a_key_no_code_will_ever_read"] = ["x"]
    with harness.tmpdir() as d:
        _EMPTY = d
        with _pin_held():
            dead = _unread_keys(doc)
    t.equal("a_key_no_code_will_ever_read" in dead, True,
            "CONTROL: an invented key IS reported as unread")


def check_the_control_catches_an_unread_key_one_level_down(t):
    """The nested half of the control above.

    The top-level control passes even when the walk stops at depth one, which is how
    `process_friction[].cost_units` sat here undetected: defined in the schema, validated by
    the gate, read by nothing, and invisible to the check written to find exactly that.
    """
    global _EMPTY
    doc = _documented_example()
    if doc is None:
        return
    for row in doc.get("process_friction") or []:
        row["a_nested_key_no_code_will_ever_read"] = "x"
    with harness.tmpdir() as d:
        _EMPTY = d
        with _pin_held():
            dead = _unread_keys(doc)
    t.equal("process_friction[].a_nested_key_no_code_will_ever_read" in dead, True,
            "CONTROL: an invented key inside a bucket row IS reported as unread")


def check_the_prose_and_the_worked_example_document_the_same_keys(t):
    """The other half of the hole, and the one that hid `what_would_close_it`.

    Everything above reads the ```json block, so a key documented ONLY in prose is invisible
    to all of it -- including to the check that exists to find fields nothing reads. That is
    how a field render-issue.py REFUSES TO DRAFT WITHOUT sat here undetected: described at
    output-schema.md:158, absent from the example, therefore never deleted, therefore never
    missed.

    It matters beyond this file. The worked example is what a person copies, and the five
    keys it was missing were the five hardest to get right -- the eight-row `refuted` block
    and the not_raised pair. new-run.py PRINTS those at the moment somebody is about to
    answer them, and its comment says why: a run learned they existed by being refused at
    the gate and paid a render cycle for it. An example that shows them costs nothing.
    """
    body = open(SCHEMA_MD, encoding="utf-8").read()
    documented = sorted(set(re.findall(r"\*\*`([A-Za-z_][A-Za-z0-9_.]*)`\*\*", body)))
    t.equal(len(documented) > 5, True,
            "vacuity guard: the prose actually names keys in bold")
    example = _documented_example()
    if example is None:
        return
    flat = json.dumps(example)
    missing = [k for k in documented if '"%s"' % k.split(".")[-1] not in flat]
    t.equal(missing, [],
            "keys the prose documents that the worked example never shows -- a reader copies "
            "the example, and what it omits is what they learn by being refused")


def check_the_shipped_example_run_matches_the_current_schema(t):
    """The skill's own worked example, held to the rule it exists to demonstrate."""
    global _EMPTY
    if not os.path.exists(EXAMPLE):
        t.note("no example-run on disk; nothing to compare")
        return
    doc = json.load(open(EXAMPLE, encoding="utf-8"))
    with harness.tmpdir() as d:
        _EMPTY = d
        with _pin_held():
            dead = _unread_keys(doc)
    t.equal(dead, [],
            "references/example-run carries keys no shipped code reads -- rendering it drops "
            "them in silence, which is the drift this skill reports in other people's tools")


def check_the_shipped_example_run_passes_the_gate_it_demonstrates(t):
    if not os.path.exists(EXAMPLE):
        t.note("no example-run on disk; nothing to gate")
        return
    doc = json.load(open(EXAMPLE, encoding="utf-8"))
    real = gate.pinned_ref
    gate.pinned_ref = lambda: (doc.get("tool") or {}).get("ref")
    try:
        with harness.tmpdir() as d:
            violations = gate.check(doc, doc_path=None, flags_dir=d)
    finally:
        gate.pinned_ref = real
    # pinned_ref is patched to the example's OWN ref on purpose: an example is allowed to
    # describe a run at an older commit. What it is not allowed to do is fail the structural
    # rules it is published to demonstrate.
    t.equal(violations, [],
            "the example run passes its own gate, judged against its own ref")
