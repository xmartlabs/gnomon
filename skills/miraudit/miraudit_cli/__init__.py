"""Console entry points, so a contributor runs one standard command instead of three.

This is a thin launcher on purpose. The scripts in `scripts/` are the artifact: they run
standalone with `python3 scripts/<name>.py`, they are what the reports quote, and they are
what someone reads to check that a number is real. Wrapping them in a package must not turn
them into something only a package manager can reach.

So they ship as package data under `miraudit_cli/scripts/`, keeping their hyphenated names,
and this module locates them relative to itself and hands over. Everything after the entry
point behaves identically whether it was reached through `uvx` or through a clone.
"""
import os
import subprocess
import sys

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")


def _run(name, argv=None):
    """Hand over to a script, forwarding arguments and its exit code.

    The exit code matters more than it looks: the anchor is a gate and the counterfactual
    fails when a control does not move. Swallowing a non-zero here would turn every gate in
    the chain into a suggestion.
    """
    path = os.path.join(SCRIPTS, name)
    if not os.path.exists(path):
        sys.exit(f"error: {name} is missing from {SCRIPTS}. The package was built without "
                 "its scripts, which makes this launcher the only thing that works and "
                 "nothing it launches.")
    runner = ["bash"] if name.endswith(".sh") else [sys.executable]
    return subprocess.call(runner + [path] + list(argv if argv is not None else sys.argv[1:]))


def second_corpus():
    raise SystemExit(_run("second-corpus.sh"))


def anchor():
    raise SystemExit(_run("anchor.sh"))
