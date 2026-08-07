"""Shared argument handling for miraudit checks.

Every check needs the same two things: a checkout of the scoring tool to import its own
predicates from, and a corpus of agent transcripts to measure. Neither is guessable, so
both are explicit.

    python3 <check>.py --checkout /path/to/gnomon [--corpus ~/.claude/projects]
                       [--days 30] [--until YYYY-MM-DD]

`--until` matters more than it looks. Without it the window ends NOW, which is a rolling
window: it drifts every day, and it includes the audit session itself, since the corpus is
being appended to while the check runs. A published report ends on a fixed boundary. Pass
the report's own end date so the checks and the report describe the same days.

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
    p.add_argument("--until", default=None, metavar="YYYY-MM-DD",
                   help="exclusive end of the window (default: now). Pass the published "
                        "report's end date so the window is fixed, not rolling.")
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
    if args.until:
        try:
            end = datetime.datetime.strptime(args.until, "%Y-%m-%d").replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            sys.exit(f"error: --until must be YYYY-MM-DD, got {args.until!r}")
    else:
        end = datetime.datetime.now(datetime.timezone.utc)
    args.window_end = end
    return args, Window(end - datetime.timedelta(days=args.days), end)


class Window:
    """A half-open [start, end) window. Scripts filter with `in`, not with `<`.

    An earlier version exposed only the start, so every check silently measured up to the
    present moment and could not be pinned to a published report's window.
    """

    def __init__(self, start, end):
        self.start, self.end = start, end

    def __contains__(self, dt):
        return dt is not None and self.start <= dt < self.end


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


def header(args, window):
    kind = "fixed" if args.until else "rolling, ends now"
    return (f"checkout: {args.checkout}\n"
            f"corpus:   {args.corpus}\n"
            f"window:   {window.start.date()} -> {window.end.date()} "
            f"({args.days}d, {kind})\n")
