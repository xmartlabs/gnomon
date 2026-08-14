"""Run every Phase 1 check at once instead of one after another.

    python3 run-checks.py --checkout <copy> --since --until --stats <stats.json> \
        --out-dir <run>/checks [--jobs N] [--repo PATH] [--comparison PATH] [--also PATH]

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
case rather than the exception and they are the slowest thing to run by hand.
"""
import concurrent.futures
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, claims  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# axis-coverage.py claims axes so it appears in `claims()`, but it is the manifest rather than
# a measurement: Phase 1 runs it first to see what is uncovered and again with --run to check
# what was recorded. Running it here would answer a question nobody asked yet.
EXCLUDED = {"axis-coverage.py"}

# Carry no `miraudit-covers:` tag and belong to every run anyway. fingerprint.py is not here
# on purpose -- Phase 0 requires it printed before any other number, and a line inside a
# parallel batch is not before anything.
ALWAYS = ("saturation-counterfactual.py", "axis-terms.py")


def per_script_args(name, args):
    """Flags a specific check needs beyond the shared shape. Absent means it is skipped."""
    comparisons = [x for c in args.comparison for x in ("--comparison", c)]
    # Runs either way. Without --repo it does the session-level half and prints the
    # by-repository table you need in order to choose a repo, so skipping it was worse than
    # useless: SKILL.md tells you to read that table first and the driver made that a walk you
    # had to do by hand. It is additive now, and the summary says which half ran.
    if name == "verification-reality.py":
        return ["--repo", args.repo] if args.repo else []
    if name in ("axis-terms.py", "skill-fluency-term.py"):
        return comparisons
    # A check that leaves a flag behind must leave it where emit-gate.py looks, which is the
    # run's checks/ directory. Its own default is beside --stats, and in a real run that is
    # the anchored payload's directory rather than this one.
    if name == "grounding-modelmix.py":
        return ["--flags-dir", os.path.abspath(args.out_dir)]
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
    "--timeout": {"type": int, "default": 600, "metavar": "SECONDS",
                  "help": "per-check wall clock ceiling (default: 600)"},
})

print(header(args, WINDOW))

covered = sorted({f for files in claims(os.path.join(HERE, "*.py")).values()
                  for f in files} - EXCLUDED)
work, skipped = [], []
for name in covered + [a for a in ALWAYS if a not in covered]:
    extra = per_script_args(name, args)
    if extra is None:
        skipped.append(name)
        continue
    work.append((name, os.path.join(HERE, name), extra))
for path in args.also:
    work.append((os.path.basename(path), os.path.abspath(os.path.expanduser(path)), []))

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
if skipped:
    print(f"  skipped, missing the flag they need: {', '.join(skipped)}")
    print("  a skipped check is not a passed one.")

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

bad = [(n, c) for n, c, _s, _o in results if c != 0]
print("\n  NOT CHECKED: whether any of these is RIGHT. This runs them and reports how they")
print("  exited; a check that prints a wrong number still exits 0. Read the .out files.")
if bad:
    print(f"\n  {len(bad)} did not exit 0: "
          f"{', '.join(f'{n} ({c})' for n, c in bad)}")
    print("  Some exit non-zero by design when their control fires. Open those first.")
    sys.exit(1)
