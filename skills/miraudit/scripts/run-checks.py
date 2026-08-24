"""Run every Phase 1 check at once instead of one after another.

    python3 run-checks.py --checkout <copy> --since --until --stats <stats.json> \
        --out-dir <run>/checks [--jobs N] [--repo PATH] [--comparison PATH] [--also PATH] \
        [--only NAME] [--emit <run>/checks/run-checks-emit.json]

The checks are independent read-only processes: each opens the corpus, prints, and exits.
Nothing one writes is read by another, and `render-report.py` consumes them only afterwards.
Run serially they take about as long as their sum, and the sum is dominated by the same work
repeated -- every check walks all of `--corpus` again, so a run parses the whole transcript
set once per check rather than once.

Parallelism does not fix that redundancy; it hides it, which is the cheap half of the fix and
the half that changes nothing about any check's logic or output. Parsing the window once into
a shared intermediate is the other half, and it would touch every check and require
re-verifying each, so it is deliberately not attempted here.

The work list comes from `claims()` in `_common.py`, the same grep for `# miraudit-covers:`
that axis-coverage.py builds its manifest from. That is the point of it living there: a
second list would drift, and a check missing from this driver would still look covered.

Ad-hoc checks written into the run's own directory take `--also`, because they are the normal
case rather than the exception and they are the slowest thing to run by hand. `--also` alone
still re-runs the whole battery beside it -- on a real saved run, adding ONE ad-hoc check this
way cost ~194 seconds of re-running twelve checks that had not changed. `--only NAME`
(repeatable, matched by basename) restricts execution to just the named checks, so
`--also new.py --only new.py` runs JUST the ad-hoc check. It is for iterating on one check
fast; the canonical `--emit` run that feeds `run_cost` should be the final, unrestricted one,
so the battery and adhoc numbers in that file both come from checks that actually ran.

`--emit <path>` writes the wall/serial numbers this already prints, plus a per-check
breakdown, as JSON -- for `render-report.py` to patch `run_cost.checks`/`adhoc_checks` from,
the same way `axis-terms.py --emit` feeds `axis-coverage.py --terms`. Optional; omitting it
changes nothing.
"""
import concurrent.futures
import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, claims  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# axis-coverage.py is the manifest rather than a measurement: Phase 1 runs it first to see what
# is uncovered and again with --run to check what was recorded. Running it here would answer a
# question nobody asked yet.
#
# This comment used to say it "claims axes so it appears in claims()". It does not, and has not
# for as long as anyone checked: its only `miraudit-covers:` string sits mid-sentence, and
# COVERS_RX is line-anchored. So the subtraction below removes nothing and the guard is inert --
# a second declaration that quietly stopped agreeing with the thing it declared. The exclusion
# stays as a guard for the day the manifest does gain a tag, and the inertness is now REPORTED
# rather than assumed, below.
EXCLUDED = {"axis-coverage.py"}

# Carry no `miraudit-covers:` tag and belong to every run anyway. fingerprint.py is not here
# on purpose -- Phase 0 requires it printed before any other number, and a line inside a
# parallel batch is not before anything. verify-repo-bucketing.py is here for a different
# reason: it verifies OUR OWN diagnostic tooling, not gnomon's scoring, so it has no axis to
# claim -- but two broken versions of that tooling shipped in one afternoon before anyone
# wrote it, both caught only because a person happened to eyeball a real corpus's table.
ALWAYS = ("saturation-counterfactual.py", "axis-terms.py", "verify-repo-bucketing.py",
          "unmeasured-surface.py")


def per_script_args(name, args):
    """Flags a specific check needs beyond the shared shape. Every branch returns a list.

    It used to say "absent means it is skipped", and the caller carried a whole skipped/
    warning path for that -- but no branch ever returned None, so the list was always empty
    and its "a skipped check is not a passed one" could not print. Documented behaviour that
    nothing implements reads as covered and is not.
    """
    comparisons = [x for c in args.comparison for x in ("--comparison", c)]
    # Runs either way. Without --repo it does the session-level half and prints the
    # by-repository table you need in order to choose a repo, so skipping it was worse than
    # useless: SKILL.md tells you to read that table first and the driver made that a walk you
    # had to do by hand. It is additive now, and the summary says which half ran.
    if name == "verification-reality.py":
        return ["--repo", args.repo] if args.repo else []
    if name == "skill-fluency-term.py":
        return comparisons
    # A check that leaves a flag behind must leave it where emit-gate.py looks, which is the
    # run's checks/ directory. Its own default is beside --stats, and in a real run that is
    # the anchored payload's directory rather than this one.
    if name == "grounding-modelmix.py":
        return ["--flags-dir", os.path.abspath(args.out_dir)]
    # Two checks can write machine-readable output that ANOTHER check reads, and neither was
    # ever asked to. axis-terms' verdicts let axis-coverage.py see an axis that is covered by a
    # tag while its published score cannot be rebuilt from its own terms -- a contradiction
    # that lived in two separate reports and had to be spotted by a person reading both.
    # saturation-counterfactual's `above_threshold` is the single implementation of "this
    # signal is below its target", which anything asking that question has to reuse rather
    # than write a second time.
    if name == "axis-terms.py":
        return comparisons + ["--emit", os.path.join(os.path.abspath(args.out_dir),
                                                     "axis-terms.json")]
    if name == "saturation-counterfactual.py":
        return ["--emit", os.path.join(os.path.abspath(args.out_dir), "saturation.json")]
    return []


args, WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--out-dir": {"required": True, "metavar": "PATH",
                  "help": "directory for the <check>.out files; created if absent"},
    "--jobs": {"type": int, "default": min(8, os.cpu_count() or 4), "metavar": "N",
               "help": "checks to run at once (default: min(8, cpu count))"},
    "--repo": {"default": None, "metavar": "PATH",
               "help": "passed to verification-reality.py, which runs either way and gains "
                       "its file-level half with it"},
    "--comparison": {"action": "append", "default": [], "metavar": "PATH",
                     "help": "a comparison-2 payload; repeatable, passed to the checks "
                             "that read other corpora"},
    "--also": {"action": "append", "default": [], "metavar": "PATH",
               "help": "an ad-hoc check written for this run; repeatable"},
    "--only": {"action": "append", "default": [], "metavar": "NAME",
               "help": "restrict this run to just these checks (by basename, battery or "
                       "--also); repeatable. Skips the rest of the battery instead of "
                       "re-running it"},
    "--timeout": {"type": int, "default": 600, "metavar": "SECONDS",
                  "help": "per-check wall clock ceiling (default: 600)"},
    "--emit": {"metavar": "PATH", "default": None,
               "help": "write the wall/serial numbers and a per-check breakdown as JSON, for "
                       "render-report.py to patch run_cost.checks/adhoc_checks from"},
})

print(header(args, WINDOW))

covered_all = {f for files in claims(os.path.join(HERE, "*.py")).values() for f in files}
covered = sorted(covered_all - EXCLUDED)
work = []
for name in covered + [a for a in ALWAYS if a not in covered]:
    work.append((name, os.path.join(HERE, name), per_script_args(name, args)))

# Every check this batch is about to run must exist. A rename used to slip through: the
# subprocess failed, its traceback landed in the .out, and the table reported it as a check
# that FAILED rather than as wiring that broke. Different problems, different fixes, and
# only one of them is about gnomon.
_absent = [name for name, path, _ in work if not os.path.exists(path)]
if _absent:
    sys.exit(f"error: {', '.join(_absent)} is named here but not on disk. Something was "
             "renamed and ALWAYS or its covers tag was not. Fix the wiring, not the check.")

# A script with no tag and no ALWAYS entry runs NOWHERE, and nothing else reports it:
# axis-coverage.py names uncovered AXES, never uncovered scripts. That is how a check gets
# written, committed, and never executed once.
#
# Driver-or-orphan is DERIVED, never listed. A hardcoded roster of drivers would be a second
# declaration of the same fact, drifting the day someone adds one -- the exact shape this
# exists to catch. A file is accounted for when it claims an axis, is named in
# ALWAYS/EXCLUDED, or some other script OR procedure file invokes it by name. The procedure
# files have to be in there: run-arms.py is invoked by the model from ad-hoc-checks.md and
# by no script at all, so scanning code alone reports a live driver as dead.
_scripts = sorted(glob.glob(os.path.join(HERE, "*.py")))
_skill = os.path.dirname(HERE)
_callers = _scripts + sorted(glob.glob(os.path.join(_skill, "*.md"))) \
    + sorted(glob.glob(os.path.join(_skill, "references", "*.md")))
_named = set()
for _caller in _callers:
    try:
        with open(_caller, encoding="utf-8", errors="replace") as _fh:
            _body = _fh.read()
    except OSError:
        continue
    for _other in _scripts:
        _base = os.path.basename(_other)
        if _other != _caller and _base in _body:
            _named.add(_base)
# An EXCLUDED entry only does something while that file actually claims an axis. Strip the tag
# and the exclusion becomes a no-op that still reads like a guard -- which is what happened here,
# undetected, for the whole life of the comment above it.
_inert = sorted(name for name in EXCLUDED if name not in covered_all)
if _inert:
    print(f"  INERT EXCLUSION: {', '.join(_inert)} claims no axis, so excluding it removes")
    print("  nothing. Either it lost its `# miraudit-covers:` tag, or the exclusion is stale.")

_orphans = sorted(os.path.basename(f) for f in _scripts
                  if os.path.basename(f) not in
                  set(covered) | set(ALWAYS) | EXCLUDED | _named | {"_common.py"})
if _orphans:
    print(f"  ORPHANS, named by no script and no procedure: {', '.join(_orphans)}")
    print("  Add a `# miraudit-covers:` tag, or ALWAYS, or delete them. A check the runner")
    print("  never calls is not coverage.")
for path in args.also:
    work.append((os.path.basename(path), os.path.abspath(os.path.expanduser(path)), []))

# `adhoc_names` is taken BEFORE --only filters work down, because it is used below (in the
# --emit breakdown) to tell an ad-hoc check apart from a battery one -- and a check that
# --only dropped from work never gets there to be told apart at all.
adhoc_names = {os.path.basename(p) for p in args.also}

# --only composes with --also rather than replacing it: filtering the already-built work list
# (battery + ALWAYS + --also) is the smallest change that lets `--also new.py --only new.py`
# run JUST the ad-hoc check. Orphan/exclusion detection above this line stays against the
# FULL claims() set on purpose -- those are integrity checks about the whole battery, not
# about what this one invocation is about to execute, and narrowing them to --only would make
# a partial run look like it audited the battery's wiring, which it did not.
if args.only:
    _wanted = set(args.only)
    _unknown = sorted(_wanted - {name for name, _p, _e in work})
    if _unknown:
        sys.exit(f"error: --only names {', '.join(_unknown)}, not in this run's work list "
                 "(battery + --also). Check the basename.")
    work = [item for item in work if item[0] in _wanted]

os.makedirs(args.out_dir, exist_ok=True)

shared = ["--checkout", args.checkout, "--corpus", args.corpus,
          "--until", args.window_end.date().isoformat(),
          "--since", WINDOW.start.date().isoformat()]
if args.stats:
    shared += ["--stats", args.stats]


# An ad-hoc check lives in the RUN's output directory, which is nowhere near the skill, so
# `../scripts` cannot reach `_common.py` and neither can walking up from either end. The
# driver is the one process that knows where the scripts are, so it says so. Without this the
# first cold run to write an ad-hoc check invented its own convention to import the shared
# helpers, and the second person would have invented a different one.
ENV = dict(os.environ, MIRAUDIT_SCRIPTS=HERE)


def run(item):
    name, path, extra = item
    out = os.path.join(args.out_dir, os.path.splitext(name)[0] + ".out")
    began = time.monotonic()
    try:
        proc = subprocess.run([sys.executable, path] + shared + extra, env=ENV,
                              capture_output=True, text=True, timeout=args.timeout)
        text, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        text = (exc.stdout or "") + (exc.stderr or "")
        text += f"\n\nrun-checks: KILLED after {args.timeout}s.\n"
        code = None
    with open(out, "w") as fh:
        fh.write(text)
    return name, code, time.monotonic() - began, out


print(f"RUNNING {len(work)} checks, {args.jobs} at a time -> {args.out_dir}")

wall = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
    results = list(pool.map(run, work))
wall = time.monotonic() - wall

print(f"\n{'check':<34}{'exit':>6}{'seconds':>10}")
for name, code, secs, _ in sorted(results, key=lambda r: -r[2]):
    print(f"  {name:<32}{'KILLED' if code is None else code:>6}{secs:>10.1f}")

serial = sum(r[2] for r in results)
print(f"\n  wall clock {wall:.1f}s against {serial:.1f}s of check time "
      f"({serial / wall:.1f}x)" if wall else "")

# Written before the possible sys.exit(1) below, on purpose -- a batch with a red check still
# paid for the checks that ran, and that cost is exactly what a re-run wants to avoid paying
# twice. `battery`/`adhoc` split by `adhoc_names` (computed before --only filtered work) so
# `render-report.py` can tell "the checks battery cost" from "how many ad-hoc checks ran" --
# the same distinction run_cost.checks and run_cost.adhoc_checks carry in the schema.
if args.emit:
    breakdown = [{"name": name, "seconds": round(secs, 3),
                 "exit": code, "adhoc": name in adhoc_names, "out": out}
                for name, code, secs, out in results]
    battery = [c for c in breakdown if not c["adhoc"]]
    adhoc = [c for c in breakdown if c["adhoc"]]
    emit_doc = {
        "wall": round(wall, 3),
        "serial": round(serial, 3),
        "ratio": round(serial / wall, 3) if wall else None,
        "battery": {"count": len(battery),
                    "seconds": round(sum(c["seconds"] for c in battery), 3)},
        "adhoc": {"count": len(adhoc),
                  "seconds": round(sum(c["seconds"] for c in adhoc), 3)},
        "checks": breakdown,
    }
    with open(os.path.expanduser(args.emit), "w") as fh:
        json.dump(emit_doc, fh, indent=2)
        fh.write("\n")
    print(f"\n  wrote {args.emit}: {len(breakdown)} check result(s) for render-report.py")

# A check that ran at HALF SCOPE exits 0 and reads identically to one that ran fully. The
# skipped/warning path this replaced could at least print a line; a reduced scope printed
# nothing at all, so "verification-reality.py 0" meant two different things and you had to
# remember which. Reduced coverage that announces itself is the whole point of the sentence
# below about a skipped check.
if not args.repo and any(n == "verification-reality.py" for n, _c, _s, _o in results):
    print("\n  HALF SCOPE: verification-reality.py ran without --repo, so it did the "
          "session-level\n  half and skipped the file-level pairing of test to subject. It "
          "exits 0 either way.\n  Read its by-repository table, pick a repo, and re-run it "
          "with --repo for the other half.")

bad = [(n, c) for n, c, _s, _o in results if c != 0]
print("\n  NOT CHECKED: whether any of these is RIGHT. This runs them and reports how they")
print("  exited; a check that prints a wrong number still exits 0. Read the .out files.")
if bad:
    print(f"\n  {len(bad)} did not exit 0: "
          f"{', '.join(f'{n} ({c})' for n, c in bad)}")
    print("  Some exit non-zero by design when their control fires. Open those first.")
    sys.exit(1)
