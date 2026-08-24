"""Refuses to let a run emit a finding that did not survive Phase 3.

    python3 emit-gate.py <miraudit-<date>.json> [--flags-dir <run>/checks]

Phase 3 says "Nothing is reported until it survives every row" and Phase 1 says the
per-axis scripts emit "candidates for Phase 3, never findings". Both were prose, in a
file the auditor had open, and a cold run promoted a candidate to findings[] anyway --
one whose own evidence said the fixture was the whole result while the payload pointed
at a different cause. Nothing chirped. It was caught by a person asking "is that
verified?", which is exactly the check that must not depend on someone remembering.

So the table becomes data. A finding carries `refuted`, with one entry per row and a
verdict in {pass, fail, n/a}. A `fail` means it did not survive, and a finding that did
not survive does not belong in findings[] -- it belongs in dismissed[] with the fact
that killed it. The gate cannot judge whether a note is honest; it can insist that the
row was answered at all, which is where the failure actually happened.

Exit codes: 0 clean, 1 violations found, 2 the file could not be read.
"""
import json
import os
import subprocess
import sys

# Keyed to the Phase 3 table in SKILL.md. Order is the table's order.
ROWS = {
    "window_or_corpus": "Does the window or corpus explain it, rather than the code?",
    "denominator_theirs": "Is the denominator theirs, or one you invented?",
    "fairest_operationalization": "Is the operationalization the fairest, or the flattering one?",
    "already_conceded": "Have you already conceded the opposite?",
    "paths_and_refs_exist": "Do the paths and refs you checked still exist?",
    "control_present": "Without the control, does the zero prove anything?",
    "tooling_reshaped_evidence": "Did your own tooling reshape the evidence first?",
    "one_condition_neutralized": "Several conditions can cause this. Does neutralizing ONE leave it unchanged?",
}
# The two judgement fields a not_raised entry carries beyond a finding's burden. A constant
# because new-run.py announces them the way it already announces ROWS: a run that adds its
# first not_raised entry had no way to learn these existed except by being refused, and it
# paid a render cycle for that. The requirement was never the problem; not stating it was.
NOT_RAISED_KEYS = ("why_not", "reconsider_if")

# The fields fingerprint.py prints, and the buckets a filled-in run has at least one of.
CORPUS_KEYS = ("tool_calls", "sessions", "window", "sources")

# `process_friction[].cost` is prose, and it stays prose: across the saved runs it holds 74
# distinct values and the specific ones are the valuable ones ("three separate polls of the
# background log that showed nothing new"). A unit cannot carry that. What a unit CAN carry
# is the part two runs can be compared on, so it is an optional companion field rather than
# a replacement -- `none` is in the vocabulary because a friction entry with no cost is a
# real and common case, recorded so the next run does not rediscover it.
COST_UNITS = {"runs", "renders", "minutes", "seconds", "none"}

# `run_cost.checks/arms/adhoc_checks` used to be a bare number, and two saved runs both filled
# it that way with two different meanings: one wrote 13 (a COUNT of checks run), the next wrote
# 101.3 (SECONDS of wall clock) -- same field, same schema, un-comparable. Only two units exist
# because only two mechanisms produce this number: a check count or a stopwatch.
RUN_COST_UNITS = {"seconds", "count"}
BUCKETS = ("findings", "not_raised", "reported", "dismissed", "process_friction")

# What the other buckets need beyond an id, hoisted for the same reason NOT_RAISED_KEYS was:
# new-run.py prints them at the moment somebody is about to fill the file, and it has to read
# them from here rather than carry its own copy. A cold run paid a refused render plus a grep
# through this file and render-report.py to learn these existed -- the exact cost the printed
# reminders exist to remove for the fields they already cover.
REPORTED_KEYS = ("confirmed_by", "state")
DISMISSED_KEYS = ("killed_by",)
FRICTION_KEYS = ("phase", "what", "cost")

# What a `not_checked` entry is ABOUT, so the same hole declared by two runs in two different
# sentences lands on one key. Across the saved payloads there are 357 distinct `not_checked`
# strings collapsing to ~228 holes, and a single hole carries SIXTEEN wordings -- nothing could
# count them because nothing tied them to an identity.
#
# Seeded only from kinds that already have three or more independent wordings on record.
# Inventing kinds for holes nobody has declared is the "plausible rows nobody validated" trap:
# a vocabulary is a claim about what exists, and this one is meant to describe, not to suggest.
BLIND_SPOT_KINDS = {
    "calibration",           # is the threshold fitted against any population at all
    "population",            # is the GRADED population representative
    "invisible-to-corpus",   # the behaviour happens where no transcript can see it
    "reimplementation-gap",  # their primitive is private, so our number is ours to own
    "not-localized",         # several conditions trip one gate and none was neutralized alone
    "bound-only",            # the figure is a bound, and the gap to theirs is unattributed
    "renderer-not-checked",  # in the payload, absent from what a person reads
    "other-backend",         # true here, unmeasured for anyone using a different backend
    "not-decomposable",      # the published score cannot be rebuilt from its own terms
}

VERDICTS = {"pass", "fail", "n/a"}
SHAPES = {"dropped-term", "saturated", "contaminated-denominator",
          "signal-not-attributable-to-person", "signal-reused"}
DIRECTIONS = {"overestimates", "underestimates", "faithful"}
CONFIDENCE = {"fact", "hypothesis"}
BOUNDS = {"upper", "lower"}


FLAGS = {"grounding-diverged.json": "Grounding"}

from importlib.machinery import SourceFileLoader  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def pinned_ref():
    """The ref the ```pin block names, or None when it cannot be resolved.

    Asks pin-consistency.py rather than parsing known-state.md again. That file's own comment
    says why: a second copy of the parser is the same mistake it exists to remove, one level
    down. None is returned, not raised -- a gate that cannot find the pin should say so and
    keep checking everything else, the way it already handles a missing SKILL.md.
    """
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "pin-consistency.py"),
                            "--field", "ref"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    ref = r.stdout.strip()
    return ref if r.returncode == 0 and ref else None


def find_flags(doc_path, explicit=None):
    """Return (directory searched, {flag file: axis}) for the flags checks leave behind.

    A check that says "nothing below this line is usable" is telling the run something, and
    until now it told nobody: the message went to stdout and no gate read it. Making it a
    file is right and the path is where it goes wrong. The first version of this wrote the
    flag beside `--stats` and looked for it beside the run JSON, which in a real run are
    `anchored-payload/` and the run root, so it never fired once. Two conventions is the
    same as none, and it fails open, which is the worst direction for a gate to fail in.

    So: one order, stated, and the caller is told which directory answered.

    The order WALKS UP, and that is not tidiness. Fixing the two conventions left a second way
    to miss: `new-run.py` defaults the run JSON beside `--stats`, which is the anchored
    payload's directory, while `run-checks.py` leaves flags in the run root's `checks/`. Follow
    both defaults and the gate searched `anchor/report/checks`, found no directory, and passed
    a Grounding finding with a real flag two levels above it. A cold run found that, and it is
    the same fail-open this function was written to remove, arriving through a sibling's
    default path instead of through this one.
    """
    if explicit:
        roots = [os.path.abspath(os.path.expanduser(explicit))]
    else:
        base = os.path.dirname(os.path.abspath(doc_path)) if doc_path else os.getcwd()
        roots, node = [], base
        for _ in range(4):
            roots.append(os.path.join(node, "checks"))
            parent = os.path.dirname(node)
            if parent == node:
                break
            node = parent
        roots.append(base)
    for root in roots:
        found = {name: axis for name, axis in FLAGS.items()
                 if os.path.exists(os.path.join(root, name))}
        if found:
            return root, found
    existing = [r for r in roots if os.path.isdir(r)]
    return (existing[0] if existing else roots[-1]), {}


def _checkout_hint():
    """Where the scoring module is, for the one predicate that reads a constant out of it.

    The gate is handed a payload, not a checkout, so this looks beside the skill -- and
    returns None rather than guessing when it is not there, which degrades that predicate to
    a note instead of answering wrongly.
    """
    for candidate in (os.path.join(os.path.dirname(os.path.dirname(HERE)), "gnomon"),
                      os.path.join(os.path.dirname(HERE), "gnomon")):
        if os.path.isdir(os.path.join(candidate, "gnomon", "scoring")):
            return candidate
    return None


def check(doc, doc_path=None, flags_dir=None, notes=None):
    """Return the list of violations. `notes` is an optional list the caller passes in to
    collect the things this could NOT check, which is not the same as a pass and has to be
    printed rather than swallowed. Optional so that importing this module keeps working."""
    bad = []
    if notes is None:
        notes = []

    def fail(where, msg):
        bad.append(f"{where}: {msg}")

    searched, flagged = find_flags(doc_path, flags_dir)

    anchor = doc.get("anchor") or {}
    if anchor.get("ok") is False and doc.get("findings"):
        fail("anchor", "ok is false and findings[] is not empty. Phase 0 is a gate: if the "
                       "base run does not reproduce the published number, every finding is "
                       "unsafe to read and none should be emitted.")
    # A null anchor is the common case, not an oversight: most runs have no published figure
    # at the pinned contract to compare against, and second-corpus.md says a null is usable
    # for composition and shape while only a false disqualifies. Demanding `true` would stop
    # every run this skill can currently produce, and stop contributors entirely. What was
    # missing is not the pass, it is the reason -- so the reason is what this requires.
    elif anchor.get("ok") is not True and doc.get("findings"):
        if not (anchor.get("note") or "").strip():
            fail("anchor", f"ok is {anchor.get('ok')!r} and findings[] is not empty, with no "
                           "`note` saying why. A run that never compared against a published "
                           "number can still be worth emitting, and the reader has to be told "
                           "which it was. Write what was gated and what was not.")

    # Which ref the run measured is the frame for every number under it, so this is NOT gated
    # on findings[] the way the anchor rules above are: a run against the wrong checkout has
    # the wrong axes and the wrong dismissals too, and those are what an empty-findings run
    # publishes. The case: a run pointed the pipeline at the working checkout instead of a
    # copy of the pin, read a contract four commits ahead, gated everything on that, and said
    # so in `anchor.note` -- so "there is a note" would have passed it. Naming the ref is the
    # bar because a deliberate run at another ref can clear it in four words, and an accident
    # cannot clear it at all.
    tool_ref = ((doc.get("tool") or {}).get("ref") or "").strip()
    pin = pinned_ref()
    if pin is None:
        notes.append("the ```pin block could not be read, so `tool.ref` was not compared "
                     "against it. Everything else still ran.")
    elif not tool_ref:
        notes.append("the payload carries no `tool.ref`, so there was nothing to compare "
                     "against the pin.")
    elif not (tool_ref.startswith(pin) or pin.startswith(tool_ref)):
        note = (anchor.get("note") or "")
        if tool_ref not in note:
            fail("tool.ref", f"the run measured {tool_ref} and the pin is {pin}, and "
                             f"`anchor.note` does not name {tool_ref}. Either it measured a "
                             "checkout it did not mean to, or it re-pinned on purpose; the "
                             "file reads the same either way. If it was on purpose, say so in "
                             "the note and name the ref. If it was not, the axes and the "
                             "dismissals below are about a different version of the tool.")

    # The rule above compares the payload's `tool.ref` against the pin -- and for a run built
    # by anchor.py those were the SAME VALUE, both read from the ```pin block, so it could
    # never fail. This is the comparison that rule was always described as making. It uses
    # `measured_ref`, the ref the pipeline actually ran against, and it is the half that can
    # catch a pipeline pointed at the wrong directory.
    #
    # Absent is not a failure: a git-archive copy has no .git and cannot report a ref, and
    # every payload written before this field existed carries none. Silence about a field
    # nobody wrote is right; silence about a mismatch is what this closes.
    measured = ((doc.get("tool") or {}).get("measured_ref") or "").strip()
    if measured and pin and not (measured.startswith(pin) or pin.startswith(measured)):
        note = (anchor.get("note") or "")
        if measured not in note:
            fail("tool.measured_ref",
                 f"the pipeline ran against {measured} and the pin is {pin}, and "
                 f"`anchor.note` does not name {measured}. This is the check `tool.ref` was "
                 "always advertised as making: that one reads the pin on both sides and "
                 "cannot fail. A run at another ref is fine and takes four words in the note; "
                 "an accident reads identical and does not.")

    # The fingerprint is what places every other number in this file, and output-schema.md
    # already calls `corpus` "mandatory, emitted before any other number" -- the gate just
    # never read it. Like the tool.ref rule above, this is NOT gated on findings[]: an
    # empty-findings run still publishes its axes and its dismissals, and those are exactly
    # what a reader cannot place without knowing which corpus produced them.
    #
    # Presence, never magnitude. A window with no activity is a legitimate measurement, and
    # failing it would make the gate an opinion about somebody's month.
    corpus = doc.get("corpus")
    if not isinstance(corpus, dict) or not corpus:
        fail("corpus", "the payload carries no corpus fingerprint. Without it the numbers "
                       "below cannot be placed against another machine's, which is the one "
                       "thing the JSON exists to make possible.")
    else:
        missing = [k for k in CORPUS_KEYS if corpus.get(k) in (None, "")]
        if missing:
            fail("corpus", f"the fingerprint is missing {', '.join(missing)}. Phase 0 prints "
                           "all of it before any other number; a payload that drops a field "
                           "reads as a comparable run and is not one.")

    # `run_cost.checks/arms/adhoc_checks/gate_retries`: absent is fine (payloads written
    # before a field existed carry none), and null is fine (not measured -- no A/B ran, so
    # `arms` is null on most runs; a corrupted gate-attempt log degrades `gate_retries` to
    # null rather than a fabricated 0, see render-report.py's `_prior_gate_fails`). What is not
    # fine is the bare number the field used to be, because that shape is exactly what let a
    # count and a seconds figure collide unlabeled in the same key -- `gate_retries` is the
    # same shape and the same closed vocabulary, so it rides the same rule rather than a copy.
    run_cost = doc.get("run_cost")
    if isinstance(run_cost, dict):
        for key in ("checks", "arms", "adhoc_checks", "gate_retries"):
            if key not in run_cost:
                continue
            val = run_cost[key]
            if val is None:
                continue
            w = f"run_cost.{key}"
            if not isinstance(val, dict):
                fail(w, "is not an object. It is a bare number, which is the ambiguous form "
                        "that let two saved runs write the same field with two different "
                        f"meanings: {{\"unit\": one of {sorted(RUN_COST_UNITS)}, \"value\": "
                        "a number}}.")
                continue
            if val.get("unit") not in RUN_COST_UNITS:
                fail(w, f"unit {val.get('unit')!r} is not one of {sorted(RUN_COST_UNITS)}. "
                        "A unit nobody else emits cannot be compared, which is the only "
                        "reason this field exists.")
            if not isinstance(val.get("value"), (int, float)) or isinstance(val.get("value"),
                                                                             bool):
                fail(w, "value is not a number.")

    # `run_cost.phases.4_synthesis`: a sign constraint, not a shape one, so it does not ride
    # the loop above -- that loop is about a value being the wrong TYPE, this is about a
    # value that IS a number and is still wrong. `4_synthesis` is `wall.seconds - 0_anchor`
    # (new-run.py's run_cost_phases()), and negative means the artifacts new-run.py could see
    # spanned LESS time than Phase 0 alone took, which is never legitimate: Phase 0 finishes
    # before Phases 1-4 even start. A 2026-08-24 cold run shipped `-34.0` all the way into a
    # rendered report because `wall` was derived from a directory that never saw anchor.py's
    # own work directory at all (fixed in new-run.py's `_combine_spans`) -- this rule is the
    # backstop for whatever the next way to get that wrong turns out to be.
    if isinstance(run_cost, dict):
        phases = run_cost.get("phases")
        if isinstance(phases, dict):
            synthesis = phases.get("4_synthesis")
            if isinstance(synthesis, (int, float)) and not isinstance(synthesis, bool) \
                    and synthesis < 0:
                fail("run_cost.phases.4_synthesis",
                     f"is {synthesis!r}, a negative duration. Phase 0 (anchor.py's shell-out) "
                     "finishes before Phases 1-4 start, so the residual covering them can "
                     "never be less than zero -- a negative number means the span this was "
                     "subtracted from missed real time, not that synthesis ran backwards.")

    # `run_cost.agent`: filled only by whatever DISPATCHES miraudit as a subagent, never by
    # scripts/ -- so absence is the normal case and this block does not require the object.
    # `tool_uses` is the one field agent-cost.py always produces deterministically (a plain
    # block count, never absent for a file that parsed at all), so it is the one required
    # when the object is present at all; the rest are read the same mechanical way but are
    # noisier and stay optional and nullable.
    agent_cost = (doc.get("run_cost") or {}).get("agent") if isinstance(run_cost, dict) else None
    if isinstance(agent_cost, dict):
        w = "run_cost.agent"
        tu = agent_cost.get("tool_uses")
        if not isinstance(tu, int) or isinstance(tu, bool) or tu < 0:
            fail(w, f"tool_uses {tu!r} is not a non-negative integer. This is the one field "
                    "agent-cost.py always derives from a plain block count, so it is required "
                    "structurally rather than left optional like the rest of this object.")
        for key in ("duration_ms", "output_tokens_total", "context_peak"):
            if key not in agent_cost:
                continue
            val = agent_cost[key]
            if val is None:
                continue
            if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
                fail(f"{w}.{key}", f"{val!r} is not a non-negative number or null.")

    # An untouched skeleton has every bucket empty at once, which is not the same as a run
    # that audited and found nothing -- that one fills `dismissed`. Distinguishing them is
    # the difference between "clean" meaning a result and "clean" meaning nobody looked.
    if not any(doc.get(bucket) for bucket in BUCKETS):
        fail("buckets", f"every one of {', '.join(BUCKETS)} is empty. A run that found "
                        "nothing still fills `dismissed` with what it killed; all of them "
                        "empty at once is the skeleton new-run.py writes, not a result.")

    for i, f in enumerate(doc.get("findings", [])):
        w = f"findings[{i}] {f.get('id', '<no id>')}"
        if f.get("shape") not in SHAPES:
            fail(w, f"shape {f.get('shape')!r} is not one of the five Phase 2 keys")
        if f.get("direction") not in DIRECTIONS:
            fail(w, f"direction {f.get('direction')!r} is not one of {sorted(DIRECTIONS)}")
        if f.get("confidence") not in CONFIDENCE:
            fail(w, f"confidence {f.get('confidence')!r} is not 'fact' or 'hypothesis'. "
                    "A sentence of prose here is how a run hedges instead of deciding.")
        mag = f.get("magnitude") or {}
        if mag and mag.get("bound") is not None and mag.get("bound") not in BOUNDS:
            fail(w, f"magnitude.bound {mag.get('bound')!r} is not 'upper', 'lower' or absent")
        ev = f.get("evidence") or {}
        for k in ("command", "control", "output"):
            if not (ev.get(k) or "").strip():
                fail(w, f"evidence.{k} is empty. Report only findings carrying a "
                        "reproducible command and a control that passed.")
        # A finding has to say what it is ABOUT, and an axis list is not the only way. The
        # one that forced this: token_usage is summed per transcript line, and it feeds NO
        # axis -- naming one would have been false, and the flag logic below keys on axis
        # names, so a made-up entry there also decides whether the finding gets blocked by
        # some other axis's check. Either say which axes, or name the surface.
        if not (f.get("axes") or (f.get("surface") or "").strip()):
            fail(w, "neither `axes` nor `surface`. Say which axes this is about, or name the "
                    "published surface it is about (a stats key, a payload field). A finding "
                    "that names neither cannot be placed, and inventing an axis to fill the "
                    "gap is a wrong denominator with extra steps.")
        if not f.get("not_checked"):
            fail(w, "not_checked is empty. A finding that claims complete coverage "
                    "without naming its blind spots is the failure mode to avoid.")
        # Optional here on purpose: this gate governs the audit artifact, and a run that
        # raises something for its own records does not owe anyone a closing condition.
        # render-issue.py requires it, because the message that goes out does.
        if "what_would_close_it" in f and not (f["what_would_close_it"] or "").strip():
            fail(w, "what_would_close_it is present but empty. Either write the observation "
                    "that would settle it either way, or leave the field out.")

        for flag, axis in flagged.items():
            if any(axis in a for a in f.get("axes") or []):
                fail(w, f"{flag} is in {searched}, so the check covering {axis} reported that "
                        "its own re-derivation disagrees with the tool's published figure. A "
                        "finding about that axis rests on a number this run could not "
                        "reproduce.")

        ref = f.get("refuted")
        if not isinstance(ref, dict):
            fail(w, "no `refuted` block. Phase 3 is not optional and not prose: answer "
                    f"all {len(ROWS)} rows with a verdict in {sorted(VERDICTS)}.")
            continue
        for key, question in ROWS.items():
            row = ref.get(key)
            if not isinstance(row, dict) or "verdict" not in row:
                fail(w, f"refuted.{key} unanswered — {question}")
                continue
            v = row.get("verdict")
            if v not in VERDICTS:
                fail(w, f"refuted.{key} verdict {v!r} is not one of {sorted(VERDICTS)}")
            elif v == "fail":
                fail(w, f"refuted.{key} is 'fail', so this did not survive Phase 3 and "
                        "does not belong in findings[]. Move it to dismissed[] with the "
                        f"fact that killed it. Row: {question}")
            if not (row.get("note") or "").strip():
                fail(w, f"refuted.{key} has no note. The verdict without the fact behind "
                        "it is the same unchecked claim in a smaller box.")

    # not_raised carries the same proof burden as findings -- it is a CONFIRMED finding
    # somebody chose not to send. Only the two judgement fields are extra.
    for i, f in enumerate(doc.get("not_raised", [])):
        w = f"not_raised[{i}] {f.get('id', '<no id>')}"
        for k in NOT_RAISED_KEYS:
            if not (f.get(k) or "").strip():
                fail(w, f"{k} is empty. Without it this list is a graveyard the next run "
                        "re-derives from scratch, which is what the state exists to avoid.")
        ref = f.get("refuted")
        if not isinstance(ref, dict):
            fail(w, "no `refuted` block. Deciding not to send something is not a reason to "
                    "skip proving it: a finding nobody proved has not earned the right to "
                    "be remembered as true.")
        else:
            for key, question in ROWS.items():
                row = ref.get(key)
                if not isinstance(row, dict) or row.get("verdict") not in VERDICTS:
                    fail(w, f"refuted.{key} unanswered or invalid — {question}")

    for i, f in enumerate(doc.get("process_friction", [])):
        w = f"process_friction[{i}]"
        units = f.get("cost_units")
        if units is None:
            continue
        if not isinstance(units, dict):
            fail(w, "cost_units is not an object. It is the comparable half of `cost`: "
                    f"{{\"unit\": one of {sorted(COST_UNITS)}, \"value\": a number}}.")
            continue
        if units.get("unit") not in COST_UNITS:
            fail(w, f"cost_units.unit {units.get('unit')!r} is not one of "
                    f"{sorted(COST_UNITS)}. A unit nobody else emits cannot be compared, "
                    "which is the only reason this field exists.")
        if not isinstance(units.get("value"), (int, float)) or isinstance(units.get("value"),
                                                                          bool):
            fail(w, "cost_units.value is not a number. Prose belongs in `cost`, which is "
                    "kept precisely so this field does not have to carry it.")

    for i, d in enumerate(doc.get("dismissed", [])):
        if not (d.get("killed_by") or "").strip():
            fail(f"dismissed[{i}] {d.get('id', '<no id>')}",
                 "killed_by is empty. Record the fact that killed it, not the verdict, "
                 "so nobody reopens it next month.")

    for i, r in enumerate(doc.get("reported", [])):
        for k in REPORTED_KEYS:
            if not (r.get(k) or "").strip():
                fail(f"reported[{i}] {r.get('id', '<no id>')}", f"{k} is empty")

    # ---- what earlier runs already declared, compared against what this one recorded --------
    # Phase 4 only, and named nowhere in Phases 0-3. A cold run that reads a list of holes
    # before measuring stops measuring and starts confirming; it happened here with
    # known-state.md and the run said so itself. blind-spots.py has no browse mode for the
    # same reason, and its registry carries keys with no prose at all.
    try:
        _bs = SourceFileLoader(
            "blind_spots", os.path.join(HERE, "blind-spots.py")).load_module()
        # The SAME directory find_flags resolved, not the caller's working directory. This
        # read `flags_dir or os.getcwd()`, so run from the skill tree -- which is what Phase 4
        # implies -- it looked for saturation.json where nobody writes one, evaluated 0 of 5
        # reopening conditions, and printed "carries no row for cli_share" about a file that
        # plainly carries it. A gate whose verdict depends on where you were standing is the
        # exact fail-open the walk-up above exists to close, reintroduced one function later.
        _sat = None
        for _dir in (searched, flags_dir, os.path.dirname(os.path.abspath(doc_path or "."))):
            if not _dir:
                continue
            _sat_path = os.path.join(_dir, "saturation.json")
            if os.path.exists(_sat_path):
                with open(_sat_path) as _fh:
                    _sat = json.load(_fh)
                break
        if _sat is None:
            notes.append("no saturation.json beside the run, so no reopening condition that "
                         "reads a signal could be evaluated. run-checks.py writes one; a run "
                         "that skipped it has this half of the gate switched off.")
        _viol, _lines = _bs.report(doc, _sat, _checkout_hint())
        for _line in _lines:
            notes.append(_line.strip())
        for _v in _viol:
            fail("blind-spots", _v)
    except Exception as exc:                                   # noqa: BLE001
        # A comparison that cannot run is a note, never a refusal: the registry is about other
        # runs' declarations, and a payload is not wrong because this file could not be read.
        notes.append(f"the blind-spot comparison did not run ({type(exc).__name__}), so "
                     "nothing was checked against what earlier runs declared")

    return bad


def main(argv):
    flags_dir = None
    argv = list(argv)
    if "--flags-dir" in argv:
        i = argv.index("--flags-dir")
        try:
            flags_dir = argv[i + 1]
        except IndexError:
            sys.exit("error: --flags-dir needs a path")
        del argv[i:i + 2]
    if len(argv) != 2:
        sys.exit(__doc__)
    path = argv[1]
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read {path}: {exc}")
        return 2

    notes = []
    bad = check(doc, doc_path=path, flags_dir=flags_dir, notes=notes)
    searched, flagged = find_flags(path, flags_dir)
    print(f"emit gate: {os.path.basename(path)}")
    print(f"  findings {len(doc.get('findings', []))}  "
          f"not_raised {len(doc.get('not_raised', []))}  "
          f"dismissed {len(doc.get('dismissed', []))}  "
          f"reported {len(doc.get('reported', []))}")
    # Said out loud because the alternative is failing open in silence: no flag file and no
    # directory reads exactly like a clean run, and a gate that cannot tell "nothing was
    # wrong" from "nobody looked" is not a gate.
    print(f"  check flags: {', '.join(flagged) if flagged else 'none'} "
          f"(looked in {searched}{'' if os.path.isdir(searched) else ', which does not exist'})")
    for n in notes:
        print(f"  note: {n}")
    if not bad:
        print("  clean. Every finding answered all eight Phase 3 rows.")
        print("  NOT CHECKED: whether the notes are true. This gate reads structure, not "
              "honesty -- it cannot tell a real refutation from a plausible sentence.")
        return 0
    print(f"\n  {len(bad)} violation(s) — nothing should be rendered from this file:\n")
    for b in bad:
        print(f"  - {b}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
