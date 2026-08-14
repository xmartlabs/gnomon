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
import glob
import json
import os
import re
import sys

DEFAULT_CORPUS = "~/.claude/projects"


def parse(description, extra=None, needs_corpus=True):
    """Return (args, cutoff_datetime) and put the checkout on sys.path.

    `needs_corpus=False` for the checks that never open a transcript. They still ACCEPT
    --corpus, because one command shape has to work for all of them, but they stop
    requiring the directory to exist. pin-consistency.py compares strings and imports one
    constant, and it died in CI on a runner with no ~/.claude at all -- refusing to run over
    an input it does not read.
    """
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
    if needs_corpus and not os.path.isdir(args.corpus):
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


class Use:
    """One tool_use block, with the event it came from. Attribute access, not a tuple, so
    a check that wants only `name` does not have to unpack six positions correctly."""

    __slots__ = ("path", "sid", "when", "order", "name", "input", "block", "event")

    def __init__(self, path, sid, when, order, name, inp, block, event):
        self.path, self.sid, self.when, self.order = path, sid, when, order
        self.name, self.input, self.block, self.event = name, inp, block, event

    @property
    def sidechain(self):
        return bool(self.event.get("isSidechain"))

    @property
    def file_path(self):
        """The write target, under any of the keys the harness uses for it."""
        return str(self.input.get("file_path") or self.input.get("notebook_path") or "")


def iter_tool_uses(corpus, window):
    """Yield a `Use` for every tool_use block in the corpus that falls inside the window.

    Every check needs this loop and each one used to write it again: open the .jsonl, skip
    lines without "tool_use", parse, read the timestamp, filter, walk message.content. Four
    live checks still carry their own copy. The fifth copy is why this exists -- it dropped
    the `if when not in window` line, so the check measured the entire corpus while printing
    a windowed header, and nothing in its output said so. That script is deleted; the way to
    write it again is not.

    So the window is not a parameter you may omit. There is no guard to forget here because
    there is no guard to write.

    Counts identically to fingerprint.py, deliberately: an ad-hoc check whose denominator
    disagrees with the run's own fingerprint is reporting a number nobody can place.
    """
    order = 0
    for path, event, when in iter_events(corpus, window, contains='"tool_use"'):
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            order += 1
            yield Use(path, event.get("sessionId"), when, order,
                      block.get("name", ""), block.get("input") or {}, block, event)


def iter_events(corpus, window, contains=None):
    """Yield (path, event, when) for every transcript event inside the window.

    The lower half of `iter_tool_uses`, separate because not every measurement is about a
    tool call: `actions_per_prompt`, for one, needs the user's messages for its denominator.

    `contains` is a plain substring pre-filter applied to the raw line before parsing it.
    It is an optimisation over a corpus of a few hundred thousand lines and nothing else --
    pass it only when the substring is genuinely implied by what you are looking for, since
    a wrong one silently shrinks the population.
    """
    import glob
    for path in sorted(glob.glob(os.path.join(corpus, "**", "*.jsonl"), recursive=True)):
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if contains is not None and contains not in line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                timestamp = event.get("timestamp")
                if not timestamp:
                    continue
                try:
                    when = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if when not in window:
                    continue
                yield path, event, when


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


# Declared by a grepped comment rather than by importing: a check with a syntax error must
# still be visible as claiming its axis. Silence from a broken file would read as "no script
# exists", which is the distinction axis-coverage.py exists to make. It lives here because
# run-checks.py needs the same list, and two greps for the same tag would drift.
COVERS_RX = re.compile(r'^#\s*miraudit-covers:\s*(.+?)\s*$', re.M)


def claims(pattern):
    """axis name -> [filename, ...] for every script under `pattern` declaring the tag."""
    out = {}
    for path in sorted(glob.glob(pattern)):
        with open(path) as fh:
            for name in COVERS_RX.findall(fh.read()):
                out.setdefault(name, []).append(os.path.basename(path))
    return out
