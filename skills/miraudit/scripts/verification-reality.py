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

args, CUT = parse(__doc__.strip().splitlines()[0], extra={
    "--repo": dict(help="path to one git repo for the file-level co-located-test check"),
    "--ref": dict(default="HEAD",
                  help="git ref to resolve file existence against (default: HEAD)"),
})
REPO, ROOT = args.checkout, args.corpus
from gnomon.taxonomy import bash_runs_tests, classify_change_target  # noqa: E402

WRITES = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

HOME = os.path.expanduser("~")


def repo_of(path):
    """Label a file by the project it belongs to, without a hardcoded project list.

    Heuristic, and deliberately so: transcripts reference paths that may no longer exist,
    so walking up to a .git directory is not available. Two segments below $HOME is the
    level at which real projects sit for most layouts; everything else is bucketed.
    """
    p = str(path or "")
    if not p:
        return "other"
    if p.startswith(("/tmp/", "/private/tmp/", "/var/folders/")):
        return "ephemeral (tmp)"
    if p.startswith(HOME + "/.claude"):
        return "agent config"
    if p.startswith(HOME + "/"):
        parts = p[len(HOME) + 1:].split("/")
        if len(parts) >= 3:
            return "/".join(parts[:2])
        return parts[0] if parts else "other"
    return "other"


S = collections.defaultdict(lambda: {
    "repos": collections.Counter(), "code": 0, "testfile": 0, "testrun": 0,
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
            if dt < CUT:
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
                fp = str(inp.get("file_path") or inp.get("notebook_path") or "")
                if name in WRITES and fp:
                    kind = classify_change_target(fp)
                    if kind == "code":
                        s["code"] += 1
                        s["repos"][repo_of(fp)] += 1
                        s["codefiles"].add(fp)
                    elif kind == "test":
                        s["testfile"] += 1
                        s["repos"][repo_of(fp)] += 1
                if name == "Bash":
                    cmd = str(inp.get("command", ""))
                    if bash_runs_tests(cmd):
                        s["testrun"] += 1
                    if re.search(r'\bgit\s+push\b', cmd):
                        s["push"] += 1

coding = {sid: s for sid, s in S.items() if s["code"] > 0}
# dominant repo for the session
for s in coding.values():
    s["repo"] = s["repos"].most_common(1)[0][0] if s["repos"] else "other"

# level 4: something in ANOTHER session the same day and repo
by_day_repo = collections.defaultdict(lambda: {"testrun": 0, "push": 0})
for s in S.values():
    if s["day"]:
        k = (s["day"], s["repos"].most_common(1)[0][0] if s["repos"] else "other")
        by_day_repo[k]["testrun"] += s["testrun"]
        by_day_repo[k]["push"] += s["push"]

print(header(args, CUT))
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
CODE_EXT = re.compile(r'\.(ts|tsx|js|jsx|py|go|rb)$')

touched = set()
for s in coding.values():
    for fp in s["codefiles"]:
        m = STRIP.match(fp)
        if m and CODE_EXT.search(fp):
            touched.add(m.group(1))

if not touched:
    raise SystemExit(f"\n  no code files from {name} in this window.")

by_area = collections.Counter()
without = []
for rel in sorted(touched):
    base = CODE_EXT.sub("", rel)
    ext = rel.rsplit(".", 1)[-1]
    has = f"{base}.test.{ext}" in tree or f"{base}.spec.{ext}" in tree
    parts = rel.split("/")
    area = "/".join(parts[:2]) if len(parts) > 2 else (parts[0] if parts else "root")
    by_area[(area, has)] += 1
    if not has:
        without.append(rel)

n = len(touched)
with_test = n - len(without)
print(f"\n  {n} distinct code files touched")
print(f"    with a co-located test : {with_test:>4}  ({100 * with_test // max(1, n)}%)")
print(f"    without                : {len(without):>4}")
print(f"\n  {'area':<34}{'with':>6}{'without':>9}{'%':>6}")
for area in sorted({a for a, _ in by_area}):
    y, no = by_area[(area, True)], by_area[(area, False)]
    print(f"  {area[:33]:<34}{y:>6}{no:>9}{100 * y // max(1, y + no):>5}%")
print("\n  untested, first 12:")
for rel in without[:12]:
    print(f"    {rel}")
if len(without) > 12:
    print(f"    ... and {len(without) - 12} more")
