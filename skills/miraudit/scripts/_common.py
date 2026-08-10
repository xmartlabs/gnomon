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
import json
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
    # --since and --stats are universal even where a check ignores them. They used to be
    # per-script: anchor.sh spoke --since/--until while the checks spoke --days/--until, and
    # --stats was accepted by three scripts and rejected by two with nothing saying which.
    # One command shape has to work everywhere, or the caller gets it wrong for free.
    p.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                   help="inclusive start of the window. Alternative to --days; pass the "
                        "published report's start date.")
    p.add_argument("--stats", default=None, metavar="PATH",
                   help="stats.json from the anchored run. Checks that read the tool's own "
                        "numbers use it; the rest accept and ignore it.")
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

    if args.since:
        try:
            start = datetime.datetime.strptime(args.since, "%Y-%m-%d").replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            sys.exit(f"error: --since must be YYYY-MM-DD, got {args.since!r}")
        if start >= end:
            sys.exit(f"error: --since {args.since} is not before --until {args.until}.")
        spanned = (end - start).days
        if args.days != 30 and args.days != spanned:
            sys.exit(f"error: --since/--until span {spanned} days but --days says "
                     f"{args.days}. Pass one or the other, not two that disagree.")
        args.days = spanned
    else:
        start = end - datetime.timedelta(days=args.days)
    return args, Window(start, end)


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


def load_stats(path):
    """Parse an anchored run's stats.json, or return {} when none was given."""
    if not path:
        return {}
    with open(os.path.expanduser(path)) as f:
        return json.load(f)


def find_all(payload, key, path=""):
    """Every (path, value) in the payload under `key`. Order is document order."""
    out = []
    if isinstance(payload, dict):
        for name, value in payload.items():
            here = f"{path}/{name}"
            if name == key:
                out.append((here, value))
            out.extend(find_all(value, key, here))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            out.extend(find_all(value, key, f"{path}[{index}]"))
    return out


def find_key(payload, key):
    """The value of `key`, or None if absent. Raises if the name is ambiguous.

    Searching by name survives the payload being re-nested between releases, which is why
    this exists instead of a hardcoded path. What it does NOT survive is a name that repeats
    with different values, and an earlier version returned the first depth-first hit: asked
    for `tool_calls` it answered with ONE MONTH's count while presenting it as the window's,
    and printed that beside a corpus-wide number as a like-for-like comparison.

    So: unique name, get the value. Repeated name, same value everywhere, get the value.
    Repeated name, different values, refuse and name the paths — the caller has to say which
    one it means. Hardcoding a path is fine when the name is genuinely ambiguous; hardcoding
    it silently is not.
    """
    hits = find_all(payload, key)
    if not hits:
        return None
    distinct = {repr(value) for _, value in hits}
    if len(distinct) > 1:
        where = ", ".join(p for p, _ in hits[:6])
        raise KeyError(
            f"{key!r} appears {len(hits)} times with {len(distinct)} different values "
            f"({where}{', …' if len(hits) > 6 else ''}). Pick one explicitly with dig(); "
            f"returning the first would be a number that looks right and is not.")
    return hits[0][1]


def dig(payload, *path, default=None):
    """Read an explicit path: dig(stats, "volume", "total_sessions").

    Use when find_key refuses. Leave a comment saying why this key needed a path.
    """
    node = payload
    for step in path:
        if isinstance(node, dict) and step in node:
            node = node[step]
        elif isinstance(node, list) and isinstance(step, int) and -len(node) <= step < len(node):
            node = node[step]
        else:
            return default
    return node


def header(args, window):
    kind = "fixed" if args.until else "rolling, ends now"
    return (f"checkout: {args.checkout}\n"
            f"corpus:   {args.corpus}\n"
            f"window:   {window.start.date()} -> {window.end.date()} "
            f"({args.days}d, {kind})\n")
