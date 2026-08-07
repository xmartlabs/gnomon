"""Shared argument handling for miraudit checks.

Every check needs the same two things: a checkout of the scoring tool to import its own
predicates from, and a corpus of agent transcripts to measure. Neither is guessable, so
both are explicit.

    python3 <check>.py --checkout /path/to/gnomon [--corpus ~/.claude/projects] [--days 30]

Importing the tool's own predicates (`bash_runs_tests`, `classify_change_target`,
`classify_mcp_subcategory`) is deliberate: a denominator you invent yourself produces a
number that is true and meaningless.
"""
import argparse
import datetime
import os
import sys

DEFAULT_CORPUS = "~/.claude/projects"


def parse(description, extra=None):
    """Return (args, cutoff_datetime) and put the checkout on sys.path."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--checkout", required=True,
                   help="path to a checkout of the scoring tool (read-only)")
    p.add_argument("--corpus", default=DEFAULT_CORPUS,
                   help=f"transcript corpus root (default: {DEFAULT_CORPUS})")
    p.add_argument("--days", type=int, default=30,
                   help="window size in days (default: 30, matching the published report)")
    for flag, kwargs in (extra or {}).items():
        p.add_argument(flag, **kwargs)
    args = p.parse_args()

    args.checkout = os.path.expanduser(args.checkout)
    args.corpus = os.path.expanduser(args.corpus)

    if not os.path.isdir(os.path.join(args.checkout, "gnomon")):
        sys.exit(f"error: {args.checkout} does not look like a gnomon checkout "
                 "(no gnomon/ package inside). Pass --checkout.")
    if not os.path.isdir(args.corpus):
        sys.exit(f"error: corpus not found at {args.corpus}. Pass --corpus.")

    sys.path.insert(0, args.checkout)
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=args.days))
    return args, cutoff


def require(module_attrs, hint):
    """Import names from the checkout, failing loudly if the version lacks them.

    A check written against one contract silently measuring another is worse than a check
    that refuses to run.
    """
    import importlib
    out = []
    for dotted, name in module_attrs:
        try:
            out.append(getattr(importlib.import_module(dotted), name))
        except (ImportError, AttributeError):
            sys.exit(f"error: this checkout has no {dotted}.{name}. {hint}")
    return out


def header(args, cutoff):
    return (f"checkout: {args.checkout}\n"
            f"corpus:   {args.corpus}\n"
            f"window:   last {args.days} days (since {cutoff.date()})\n")
