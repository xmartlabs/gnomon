"""Four hand-rolled corpus walks against the canonical _common.iter_events.

_common.py:143-149 names this hazard and records that a fifth copy dropped its
`if when not in window` line, so the check measured the entire corpus while printing a
windowed header and nothing in its output said so. Nothing compares the survivors.

Written as a black box against a fixture, deliberately. A grep for `not in WINDOW` catches
exactly one way to break this: replace the guard with `if dt < WINDOW.end` and the token is
still there while everything before the window floods in. So the FIXTURE is the mechanism --
events sit on both boundaries, and a gutted guard changes a number rather than a string.

This also IS the comparison new-run.py:39-41 claims already exists ("the verification for
this script compares the two rather than trusting that"). It did not.
"""
import os
import re
import subprocess
import sys
import harness

NEEDS = ("checkout",)

SINCE, UNTIL = "2026-07-12", "2026-08-11"

# The five positions, and what a gutted guard does to each. Expected population: 2.
EDGES = (
    ("start exactly",   "2026-07-12T00:00:00Z", True),   # a `>` instead of `>=` drops it
    ("midpoint",        "2026-07-27T12:00:00Z", True),
    ("end exactly",     "2026-08-11T00:00:00Z", False),  # a `<=` admits it
    ("a day before",    "2026-07-11T00:00:00Z", False),  # a dropped guard admits it
    ("a day after",     "2026-08-12T00:00:00Z", False),  # a dropped guard admits it
)
WANT = sum(1 for _, _, inside in EDGES if inside)


def _fixture(root):
    """One FAILED tool call per edge, each in its own session.

    Failed, so recovery-reality sees them; distinct sessions, so fidelity-audit's session
    count matches the call count. One number, four walkers.
    """
    events = []
    for i, (_label, when, _inside) in enumerate(EDGES):
        sid, uid = "edge%d" % i, "tu%d" % i
        events.append({"type": "assistant", "sessionId": sid, "timestamp": when,
                       "message": {"role": "assistant", "content": [
                           {"type": "tool_use", "id": uid, "name": "Bash",
                            "input": {"command": "false"}}]}})
        events.append({"type": "user", "sessionId": sid, "timestamp": when,
                       "message": {"role": "user", "content": [
                           {"type": "tool_result", "tool_use_id": uid, "is_error": True,
                            "content": "boom"}]}})
    return harness.corpus(events, root=root)


def _number(text, pattern, t, why):
    match = re.search(pattern, text)
    if not match:
        t.failures.append("%s: no line matching %r in the output" % (why, pattern))
        return None
    return int(match.group(1))


def _walk(t, root, name, extra=()):
    proc = subprocess.run(
        [sys.executable, os.path.join(harness.SCRIPTS, name),
         "--checkout", t.checkout, "--corpus", os.path.dirname(os.path.dirname(root)),
         "--since", SINCE, "--until", UNTIL, *extra],
        capture_output=True, text=True, timeout=180)
    return proc.stdout + proc.stderr


def check_iter_tool_uses_is_the_yardstick(t):
    """Establish the reference before anything is compared against it."""
    _c = harness.load("_common.py")
    import datetime
    utc = datetime.timezone.utc
    window = _c.Window(datetime.datetime(2026, 7, 12, tzinfo=utc),
                       datetime.datetime(2026, 8, 11, tzinfo=utc))
    with harness.tmpdir() as d:
        root = _fixture(d)
        corpus_root = os.path.dirname(os.path.dirname(root))
        t.equal(sum(1 for _ in _c.iter_tool_uses(corpus_root, window)), WANT,
                "iter_tool_uses counts the two in-window calls and neither boundary")
        t.equal(sum(1 for _ in _c.iter_events(corpus_root, window, contains='"tool_use"')),
                WANT, "iter_events agrees on the same population")


def check_fingerprint_counts_what_iter_tool_uses_counts(t):
    """The comparison new-run.py says is already verified. It is now."""
    with harness.tmpdir() as d:
        text = _walk(t, _fixture(d), "fingerprint.py")
        got = _number(text, r"tool calls in window\s+([\d,]+)".replace(",", ""), t,
                      "fingerprint prints its denominator")
        if got is not None:
            t.equal(got, WANT, "fingerprint's denominator equals iter_tool_uses's count")


def check_recovery_reality_walks_the_same_window(t):
    with harness.tmpdir() as d:
        text = _walk(t, _fixture(d), "recovery-reality.py")
        got = _number(text, r"tool calls that failed:\s+(\d+)", t,
                      "recovery-reality prints its population")
        if got is not None:
            t.equal(got, WANT, "its own walk agrees with the canonical one")


def check_fidelity_audit_walks_the_same_window(t):
    with harness.tmpdir() as d:
        text = _walk(t, _fixture(d), "fidelity-audit.py")
        got = _number(text, r"sessions with activity in window:\s+(\d+)", t,
                      "fidelity-audit prints its population")
        if got is not None:
            t.equal(got, WANT, "its own walk agrees with the canonical one")


def check_the_boundaries_are_what_separate_them(t):
    """A CONTROL on the three above: widen the window by one day at each end and the count
    must move to 4, not to 5.

    Without it, "they all say 2" could mean they all share the same broken filter. Moving
    the window and watching the number follow is what says the filter is real.
    """
    with harness.tmpdir() as d:
        root = _fixture(d)
        corpus_root = os.path.dirname(os.path.dirname(root))
        proc = subprocess.run(
            [sys.executable, os.path.join(harness.SCRIPTS, "fingerprint.py"),
             "--checkout", t.checkout, "--corpus", corpus_root,
             "--since", "2026-07-11", "--until", "2026-08-12"],
            capture_output=True, text=True, timeout=180)
        got = _number(proc.stdout + proc.stderr, r"tool calls in window\s+(\d+)", t,
                      "the widened run prints a denominator")
        if got is not None:
            t.equal(got, 4, "widening by a day each side admits the two near boundaries and "
                            "still excludes the new exclusive end")

def _code_fixture(root):
    """The same five edges, but as CODE EDITS with a cwd.

    verification-reality counts sessions that edited code, bucketed by the session's own
    `cwd`, so a Bash call is invisible to it. Same boundaries, same expected population --
    a different shape of event, which is the point: the window filter has to behave the same
    for both or the two checks are measuring different months.
    """
    events = []
    for i, (_label, when, _inside) in enumerate(EDGES):
        events.append({"type": "assistant", "sessionId": "code%d" % i, "timestamp": when,
                       "cwd": "/Users/someone/repo-%d" % i,
                       "message": {"role": "assistant", "content": [
                           {"type": "tool_use", "id": "cu%d" % i, "name": "Write",
                            "input": {"file_path": "/Users/someone/repo-%d/src/thing.ts" % i,
                                      "content": "x"}}]}})
    return harness.corpus(events, root=root)


def check_verification_reality_walks_the_same_window(t):
    with harness.tmpdir() as d:
        text = _walk(t, _code_fixture(d), "verification-reality.py")
        # The TOTAL row's first column is the session denominator. Read by FIELD, not by
        # byte offset: this hardcoded `line[28:34]` and broke the day the label column was
        # widened -- a layout change, not a walk change, failing the check that exists to
        # compare walks. A check coupled to formatting reports the wrong thing when the
        # formatting is what moved.
        line = next((l for l in text.splitlines() if l.startswith("TOTAL")), "")
        t.equal(bool(line), True, "verification-reality prints a TOTAL row")
        if line:
            try:
                got = int(line.split()[1])
            except (ValueError, IndexError):
                t.failures.append("could not read the TOTAL session count from %r" % line)
                return
            t.equal(got, WANT, "its own walk agrees with the canonical one")
