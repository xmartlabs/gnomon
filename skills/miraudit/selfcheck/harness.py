"""Shared machinery for the offline replays. Stdlib only, on purpose.

The replays import the SHIPPED code and assert against it. A replay that reimplements the
rule tests the reimplementation, which is the failure this whole tier exists to avoid, so
nothing in here restates a rule from scripts/ -- it only builds inputs and records results.
"""
import contextlib
import datetime
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
UTC = datetime.timezone.utc


def load(script_name):
    """Import a hyphenated script from scripts/ by path, and return the module.

    spec_from_file_location, not SourceFileLoader().load_module(): the two call sites that
    already do this (new-run.py, pin-consistency.py) use the deprecated form, and
    pyproject.toml declares requires-python = ">=3.9" with no upper bound. Only the modules
    that do no work at import time can be loaded this way -- most scripts/ files call
    _common.parse() at module level, which fires argparse and exits.
    """
    path = os.path.join(SCRIPTS, script_name)
    name = "miraudit_sc_" + os.path.splitext(script_name)[0].replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recorder:
    """Collects failures for one check. Distinguishes a failure from an error from a note.

    A note is something the check could NOT verify. It is not a pass, and printing it is the
    whole point: emit-gate.py makes the same distinction for the same reason.
    """

    def __init__(self):
        self.failures = []
        self.notes = []
        self.checkout = None

    def equal(self, got, want, why):
        if got != want:
            self.failures.append("%s: got %r, want %r" % (why, got, want))

    def contains(self, haystack, needle, why):
        if needle not in haystack:
            self.failures.append("%s: %r not found in %.300r" % (why, needle, haystack))

    def absent(self, haystack, needle, why):
        if needle in haystack:
            self.failures.append("%s: %r should not be in %.300r" % (why, needle, haystack))

    def raises(self, exc_type, fn, why):
        try:
            fn()
        except exc_type as exc:
            return exc
        except Exception as exc:  # noqa: BLE001 - a different exception is a real failure
            self.failures.append("%s: raised %s, want %s" % (why, type(exc).__name__,
                                                             exc_type.__name__))
            return None
        self.failures.append("%s: nothing raised, want %s" % (why, exc_type.__name__))
        return None

    def completes(self, fn, why):
        """Assert fn() returns instead of exiting. The positive half of every guard check.

        Written as an assertion rather than as a bare call: a bare call relies on SystemExit
        propagating out of the check, which reads as 'no news is good news' and is not -- it
        used to abort the runner instead of reddening this one line.
        """
        try:
            return fn()
        except SystemExit as exc:
            self.failures.append("%s: exited with %r, want a normal return" % (why, exc))
        except Exception as exc:  # noqa: BLE001
            self.failures.append("%s: raised %s" % (why, type(exc).__name__))
        return None

    def note(self, message):
        self.notes.append(message)


@contextlib.contextmanager
def argv(args):
    """Run with sys.argv set, restoring argv AND sys.path.

    _common.parse() does sys.path.insert(0, checkout); without restoring, one replay's fake
    checkout stays on the path for every replay after it.
    """
    old_argv, old_path = sys.argv[:], sys.path[:]
    sys.argv = list(args)
    try:
        yield
    finally:
        sys.argv, sys.path[:] = old_argv, old_path


@contextlib.contextmanager
def quiet():
    """Silence stdout at the FILE DESCRIPTOR level, not just sys.stdout.

    render-report.py runs emit-gate.py as a subprocess, so contextlib.redirect_stdout does
    not reach it -- the child writes to fd 1 directly and lands in the runner's output.
    """
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    sys.stdout.flush()
    os.dup2(devnull, 1)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)
        os.close(devnull)
        os.close(saved)


@contextlib.contextmanager
def tmpdir():
    path = tempfile.mkdtemp(prefix="miraudit-selfcheck-")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextlib.contextmanager
def fake_checkout():
    """A directory that satisfies _common.parse()'s checkout test and nothing more.

    parse() validates the checkout with isdir(checkout/gnomon) and nothing else, which is
    what makes this tier possible at all. Do NOT put stub modules in here to widen the tier:
    a check that imports a stubbed gnomon.taxonomy is testing the stub.
    """
    with tmpdir() as path:
        os.makedirs(os.path.join(path, "gnomon"))
        yield path


def corpus(events, root=None):
    """Write events to <root>/projects/-fixture/<sid>.jsonl, grouped by sessionId."""
    base = os.path.join(root, "projects", "-fixture")
    os.makedirs(base, exist_ok=True)
    by_session = {}
    for event in events:
        by_session.setdefault(event.get("sessionId") or "no-session", []).append(event)
    for sid, group in by_session.items():
        with open(os.path.join(base, "%s.jsonl" % sid), "w") as fh:
            for event in group:
                fh.write(json.dumps(event) + "\n")
    return base


def event(sid="s1", when="2026-07-15T12:00:00Z", blocks=None, **extra):
    """One transcript event. Defaults to an assistant message with one Bash tool_use."""
    if blocks is None:
        blocks = [tool_use("Bash")]
    body = {"type": "assistant", "sessionId": sid, "timestamp": when,
            "message": {"role": "assistant", "content": blocks}}
    body.update(extra)
    return body


def tool_use(name="Bash", **inputs):
    return {"type": "tool_use", "name": name, "input": inputs or {"command": "true"}}


def stamp(day, hour=12):
    return datetime.datetime(2026, 7, day, hour, tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- payload builders -------------------------------------------------------------------
# Shaped from the SHIPPED emit-gate constants, never from a copy of them: a ninth refutation
# row arrives here the day it is added to ROWS, without anyone editing this file.

_gate = load("emit-gate.py")


def finding(**overrides):
    """A findings[] entry complete enough that emit-gate.check() returns no violation."""
    body = {
        "id": "F1",
        "axis": "Verification",
        "axes": ["Verification"],
        "shape": sorted(_gate.SHAPES)[0],
        "direction": sorted(_gate.DIRECTIONS)[0],
        "confidence": "fact",
        "claim": "a claim",
        "evidence": {"command": "python3 x.py", "control": "a control", "output": "42"},
        "not_checked": "what this did not check",
        "refuted": {key: {"verdict": "pass", "note": "answered"} for key in _gate.ROWS},
    }
    body.update(overrides)
    return body


def payload(**overrides):
    """A doc that emit-gate.check() returns [] for. Deep-merges one level of overrides."""
    body = {
        "schema_version": "1",
        "tool": {"name": "xl-ai-insights", "ref": "", "contract": "19:19:19"},
        "corpus": {"tool_calls": 42003, "sessions": 281, "sidechain_share": 0.48,
                   "window": "2026-07-12 -> 2026-08-11", "sources": ["claude"]},
        "anchor": {"published": None, "reproduced": 91, "ok": None,
                   "note": "ran with --local, so nothing was fetched to anchor against"},
        "axes": [],
        "findings": [],
        "not_raised": [],
        "reported": [],
        # Populated on purpose, and it is not padding. The minimal VALID run is not the one
        # with nothing in it -- SKILL.md's position is that a run which audited and found
        # nothing still fills `dismissed` with what it killed. All five buckets empty at once
        # is the skeleton, which the gate now refuses. Leaving this empty made payload() model
        # a shape no real run produces.
        "dismissed": [{"id": "D0", "killed_by": "re-measured with the window pinned"}],
        "process_friction": [],
    }
    body.update(overrides)
    return body


def skeleton():
    """The shape new-run.py writes before a human fills it in: every bucket empty."""
    return {
        "schema_version": "1",
        "tool": {"name": "xl-ai-insights", "ref": None, "contract": None},
        "corpus": {},
        "anchor": {"published": None, "reproduced": None, "ok": None, "note": ""},
        "axes": [], "findings": [], "not_raised": [], "reported": [], "dismissed": [],
        "process_friction": [],
    }
