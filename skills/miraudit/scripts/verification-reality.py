"""Is the reported test-coverage figure real? Splits verification by repository.

A single corpus-wide percentage hides the thing that matters: editing a throwaway script
in a folder with no suite is not comparable to editing a service in a repo that has one.
This splits both sides of the ratio.

  - denominator: sessions that edited code, GROUPED BY REPOSITORY
  - numerator: four progressively wider definitions
      1. ran a test command the tool recognises (bash_runs_tests)
      2. ...or pushed (a pre-push hook runs the suite, invisible to the tool)
      3. ...or wrote/edited a test file
      4. ...or one of the above happened in ANOTHER session the same day, same repo
  - and separately, at FILE level with --repo: of the code files touched there, how many
    have a co-located test today. Resolved against a git ref, not the working tree, so a
    deleted worktree cannot read as "no test".

**Which repo to pass, since the corpus spans many.** Run without `--repo` first and read the
by-repository table. **Its rows are the session's own `cwd`, relative to $HOME** -- where the
session was actually launched, not a guess reconstructed from an edited file's path. An
earlier version bucketed by truncating a FILE path to two segments below $HOME instead, which
sent you somewhere you could not pass on either side of the mistake: it fused unrelated
repositories that merely shared a parent directory into one row (a real corpus had one such
row holding six repositories under a client folder), and -- proven when the fix was first
attempted and it broke this worse -- a segment-divergence heuristic fused a single repo's own
subdirectories (`app/`, `components/`, `lib/`) into several spurious rows instead. Session
`cwd` sidesteps both: measured across a
real corpus, 97 of 104 sessions carry exactly one `cwd` for their whole duration, and it is
the actual checkout root a person or agent cd'd into, not a path an internal directory
structure can be mistaken for. Skip `agent config` (`~/.claude`) and `ephemeral (tmp)` --
neither is a project -- and pass the path of the busiest row that
is one repository. There is no representative repo and this does not average them, so a single
`--repo` result describes that repo and nothing else.

**Skipping it is a real gap, not a formality.** `run-checks.py` leaves this check out when
`--repo` is absent and says so; the session-level half still runs and the manifest still goes
green through it, so a run can finish with half of Verification's evidence ungathered and
nothing red to show for it. A cold run did exactly that and had no stated basis for choosing
otherwise, which is why this paragraph exists.
"""
import collections
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0], extra={
    "--repo": dict(help="path to one git repo for the file-level co-located-test check"),
    "--ref": dict(default="HEAD",
                  help="git ref to resolve file existence against (default: HEAD)"),
})
REPO, ROOT = args.checkout, args.corpus
from gnomon.taxonomy import (WRITE_TOOLS as WRITES, bash_runs_tests,  # noqa: E402
                             classify_change_target)

HOME = os.path.expanduser("~")


def repo_of(cwd):
    """Label a session by the directory it was actually launched from -- not a guess
    reconstructed by truncating an edited file's path to a fixed depth.

    Two truncation-based attempts preceded this and both broke on real corpora. A flat
    2-segment cut fused unrelated repositories sharing a parent directory into one row (a
    real corpus had one such row holding six repos under a client folder, no way to tell
    them apart). Making the cut adaptive -- split deeper wherever paths diverge -- broke
    the opposite way: a single repo's own
    subdirectories (`app/`, `components/`, `lib/`) diverge from each other too, so it
    fragmented ordinary repos into several spurious rows. Neither flaw is reachable from
    `cwd`: it is not a path INSIDE a project that divergence has to reason about, it is the
    project's own root, recorded once per tool call by the harness itself. No depth to
    choose, so no depth to get wrong.

    A third flaw only showed up once this ran: the old file-path scheme labelled a session
    by whichever repo its MOST-EDITED file belonged to, and a session working in a real
    project that happens to also touch files under ~/.claude -- syncing a skill, writing to
    memory -- got filed under `agent config` whenever that side activity outweighed the
    project work by raw edit count. On a real corpus, 13 of 18 sessions the old scheme
    called `agent config` were launched from one real repository, one with 447 such edits
    in a single session. `cwd` cannot make that mistake: it is where the session started,
    not what it touched most.
    """
    p = str(cwd or "")
    if not p:
        return "other"
    if p.startswith(("/tmp/", "/private/tmp/", "/var/folders/")):
        return "ephemeral (tmp)"
    if p.startswith(HOME + "/.claude"):
        return "agent config"
    if p.startswith(HOME + "/"):
        return p[len(HOME) + 1:]
    return "other"


S = collections.defaultdict(lambda: {
    "repo": None, "code": 0, "testfile": 0, "testrun": 0,
    "push": 0, "day": None, "codefiles": set()})

for p in sorted(glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True)):
    try:
        f = open(p)
    except OSError:
        continue
    with f:
        for line in f:
            if '"tool_use"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ts, sid = e.get("timestamp"), e.get("sessionId")
            if not ts or not sid:
                continue
            try:
                dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt not in WINDOW:
                continue
            c = (e.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                name, inp = b.get("name", ""), (b.get("input") or {})
                s = S[sid]
                s["day"] = s["day"] or dt.date()
                # First cwd seen for the session, kept for its duration. Measured: 97 of 104
                # sessions in a real window never change cwd at all; the few that do mostly
                # move into a subdirectory of the same checkout (prisma/migrations) rather
                # than a different project, so "first" is not a coin flip on those either.
                if s["repo"] is None and e.get("cwd"):
                    s["repo"] = repo_of(e["cwd"])
                fp = str(inp.get("file_path") or inp.get("notebook_path") or "")
                if name in WRITES and fp:
                    kind = classify_change_target(fp)
                    if kind == "code":
                        s["code"] += 1
                        s["codefiles"].add(fp)
                    elif kind == "test":
                        s["testfile"] += 1
                if name == "Bash":
                    cmd = str(inp.get("command", ""))
                    if bash_runs_tests(cmd):
                        s["testrun"] += 1
                    if re.search(r'\bgit\s+push\b', cmd):
                        s["push"] += 1

coding = {sid: s for sid, s in S.items() if s["code"] > 0}
for s in coding.values():
    s["repo"] = s["repo"] or "other"

# level 4: something in ANOTHER session the same day and repo
by_day_repo = collections.defaultdict(lambda: {"testrun": 0, "push": 0})
for s in S.values():
    if s["day"]:
        k = (s["day"], s["repo"] or "other")
        by_day_repo[k]["testrun"] += s["testrun"]
        by_day_repo[k]["push"] += s["push"]

print(header(args, WINDOW))
print("=" * 92)
print("Sessions that edited code, by repository, with widening numerators")
print("=" * 92)
print(f"{'repository':<28}{'sess':>6}{'ran tests':>13}{'+push':>13}"
      f"{'+wrote test':>13}{'+same day':>13}")
print("-" * 92)


def pct(a, b):
    return f"{a}/{b} {100 * a // max(1, b):>3}%"


groups = collections.Counter(s["repo"] for s in coding.values())
tot = [0, 0, 0, 0, 0]
for r, _n in groups.most_common():
    sids = [sid for sid, s in coding.items() if s["repo"] == r]
    n = len(sids)
    n1 = sum(1 for sid in sids if coding[sid]["testrun"] > 0)
    n2 = sum(1 for sid in sids if coding[sid]["testrun"] or coding[sid]["push"])
    n3 = sum(1 for sid in sids if coding[sid]["testrun"] or coding[sid]["push"]
             or coding[sid]["testfile"])
    n4 = sum(1 for sid in sids
             if coding[sid]["testrun"] or coding[sid]["push"] or coding[sid]["testfile"]
             or by_day_repo[(coding[sid]["day"], r)]["testrun"]
             or by_day_repo[(coding[sid]["day"], r)]["push"])
    print(f"{r[:27]:<28}{n:>6}{pct(n1, n):>13}{pct(n2, n):>13}"
          f"{pct(n3, n):>13}{pct(n4, n):>13}")
    for i, v in enumerate((n, n1, n2, n3, n4)):
        tot[i] += v
print("-" * 92)
print(f"{'TOTAL':<28}{tot[0]:>6}{pct(tot[1], tot[0]):>13}{pct(tot[2], tot[0]):>13}"
      f"{pct(tot[3], tot[0]):>13}{pct(tot[4], tot[0]):>13}")
print("\nOnly the first column is what the scoring tool counts. A pre-push hook that runs")
print("the suite is invisible to it: bash_runs_tests('git push') is False.")

# ---- FILE level: do the files you touched have a co-located test? ----
if not args.repo:
    print("\nPass --repo <path-to-a-git-repo> for the file-level co-located-test check.")
    raise SystemExit(0)

import subprocess

repo = os.path.expanduser(args.repo)
name = os.path.basename(repo.rstrip("/"))
listing = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", args.ref],
                         capture_output=True, text=True)
if listing.returncode != 0:
    raise SystemExit(f"\ncannot read {args.ref} in {repo}: {listing.stderr.strip()}")
tree = set(listing.stdout.splitlines())

print()
print("=" * 92)
print(f"FILE level in {name}, resolved against {args.ref}")
print("=" * 92)
print("Resolved against a ref, not the working tree: transcripts reference paths from")
print("worktrees that may since have been deleted, and those read as 'no test'.")

# repo-relative path, tolerating worktree suffixes like <repo>-TICKET-123
STRIP = re.compile(r'.*/' + re.escape(name) + r'[^/]*/(.+)$')

# What counts as code, and what counts as a test, is THEIRS: classify_change_target reads
# _CODE_EXTS (37 extensions) and _TEST_NAME_RX, which also recognises __tests__/, tests/,
# a test_ prefix and _test/_spec suffixes. An earlier version of this block asked only for
# "<base>.test.<ext>" beside the file over a 7-extension list of its own, so a repo laying
# tests out any other way read as untested. That is the `stale-paths` scar with a new
# mechanism, and this file is where it was committed.
# The MATCHING is still ours -- see the note printed below.
MARKERS = re.compile(r'(^test_|[._-](test|spec)$|^(test|spec)$)', re.I)


def stem(path):
    """Basename with its extension and any test/spec marker removed: the subject a test
    is a test OF. `foo.test.ts` -> `foo`, `test_foo.py` -> `foo`, `foo_spec.rb` -> `foo`."""
    base = path.rsplit("/", 1)[-1]
    base = base.rsplit(".", 1)[0] if "." in base else base
    prev = None
    while prev != base:
        prev = base
        base = MARKERS.sub("", base).strip("._-")
    return base


def parent(p):
    return p.rsplit("/", 1)[0] if "/" in p else ""


tests_anywhere = collections.defaultdict(set)   # stem -> {path of the test file}
for p in tree:
    if classify_change_target(p) == "test":
        tests_anywhere[stem(p)].add(p)

touched = set()
for s in coding.values():
    for fp in s["codefiles"]:
        m = STRIP.match(fp)
        if m and classify_change_target(fp) == "code":
            touched.add(m.group(1))

if not touched:
    raise SystemExit(f"\n  no code files from {name} in this window.")

by_area = collections.Counter()
without = []
n_elsewhere = 0
for rel in sorted(touched):
    where = tests_anywhere.get(stem(rel), set())
    d = parent(rel)
    # Strict: the test sits in the file's own directory, or in a test directory directly
    # under it. Matching by stem across the whole repo is NOT enough -- on the corpus this
    # was written against it paired src/controllers/v2/invoice.ts with
    # src/services/v2/invoice.test.ts, a different module that happens to share a name.
    has = any(parent(t) == d or parent(parent(t)) == d for t in where)
    if not has and where:
        n_elsewhere += 1
    parts = rel.split("/")
    area = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if parts else "root")
    by_area[(area, has)] += 1
    if not has:
        without.append(rel)

n = len(touched)
with_test = n - len(without)
print(f"\n  {n} distinct code files touched")
print(f"    with a test beside it or under it : {with_test:>4}  ({100 * with_test // max(1, n)}%)")
print(f"    without                           : {len(without):>4}")
print(f"    (of those, {n_elsewhere} have a same-named test somewhere else in the repo,")
print("     which is a name collision as often as it is a real test -- not counted)")
print(f"\n  {'area':<34}{'with':>6}{'without':>9}{'%':>6}")
for area in sorted({a for a, _ in by_area}):
    y, no = by_area[(area, True)], by_area[(area, False)]
    print(f"  {area[:33]:<34}{y:>6}{no:>9}{100 * y // max(1, y + no):>5}%")
print("\n  untested, first 12:")
for rel in without[:12]:
    print(f"    {rel}")
if len(without) > 12:
    print(f"    ... and {len(without) - 12} more")

print("\n  NOT CHECKED: whether the test that matches a name actually exercises that file.")
print("  `classify_change_target` decides what is code and what is a test -- that half is")
print("  theirs, and it recognises __tests__/, tests/, test_ and _spec, not just one layout.")
print("  Pairing a test to its subject is OURS and deliberately strict, so a repo that keeps")
print("  tests in a top-level tests/ tree mirroring src/ reads LOW here. Read this as a")
print("  lower bound, and check the layout before quoting it.")
# miraudit-covers: Verification
