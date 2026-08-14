"""Run the arms of an A/B at once instead of one after another.

    python3 run-arms.py --checkout <unpatched copy> --arm NAME=<patched copy> \
        --since --until [--window SINCE..UNTIL] --out-dir <run>/ab-<topic> [--jobs N]

An arm is a full pipeline run over a copy of the scoring tool, and it costs about 85 seconds
against this corpus. That is where a run's time actually goes: on one full audit the anchor
and all thirteen committed checks were done 63 seconds in, and the rest was arms.

Arms are independent -- separate copies, separate output directories, nothing shared but the
read-only corpus -- so running them in sequence is a habit rather than a constraint.

**`--checkout` is always run, as the arm named `base`.** An A/B without its unpatched arm is
not an A/B, and every falsification in this skill's history rests on the arm that was supposed
NOT to move. Making it a flag would make it forgettable.

`--window` is repeatable and every arm runs on every window, because "does the patch move it
on a window where it should, and leave alone a window where it should not" is the shape these
comparisons keep taking.

**Concurrency stops at the copy, not at the arm.** `uv run --project X` builds `.venv` inside
X, so two runs over one copy would race on it. Runs are grouped by copy and go in parallel
across copies, serially within one. Two copies over two windows is therefore 2x and not 4x;
give each (arm, window) its own copy to get the rest.
"""
import collections
import concurrent.futures
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, DEFAULT_CORPUS  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--arm": {"action": "append", "default": [], "metavar": "NAME=PATH",
              "help": "a patched copy to run beside the base; repeatable"},
    "--window": {"action": "append", "default": [], "metavar": "SINCE..UNTIL",
                 "help": "an extra window; every arm runs on every window. Repeatable."},
    "--out-dir": {"required": True, "metavar": "PATH",
                  "help": "parent directory; each run gets <arm>--<since>_<until>/ inside it"},
    "--jobs": {"type": int, "default": min(4, os.cpu_count() or 2), "metavar": "N",
               "help": "copies to run at once (default: min(4, cpu count))"},
    "--timeout": {"type": int, "default": 1800, "metavar": "SECONDS",
                  "help": "per-arm wall clock ceiling (default: 1800)"},
})

arms = [("base", args.checkout)]
for spec in args.arm:
    if "=" not in spec:
        sys.exit(f"error: --arm wants NAME=PATH, got {spec!r}")
    name, _, path = spec.partition("=")
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(os.path.join(path, "gnomon")):
        sys.exit(f"error: arm {name!r} at {path} has no gnomon/ inside. It is not a checkout.")
    arms.append((name, path))

windows = [(WINDOW.start.date().isoformat(), args.window_end.date().isoformat())]
for spec in args.window:
    if ".." not in spec:
        sys.exit(f"error: --window wants SINCE..UNTIL, got {spec!r}")
    since, _, until = spec.partition("..")
    if (since, until) not in windows:
        windows.append((since, until))

dirflag = []
if os.path.normpath(args.corpus) != os.path.normpath(os.path.expanduser(DEFAULT_CORPUS)):
    dirflag = [f"--claude-dir={args.corpus}"]

print(header(args, WINDOW))
print(f"{len(arms)} arms x {len(windows)} windows = {len(arms) * len(windows)} pipeline runs")
for name, path in arms:
    print(f"  {name:<16} {path}")
for since, until in windows:
    print(f"  window           {since} -> {until}")
if dirflag:
    print(f"  corpus override: {dirflag[0]}   (claude source only; the rest keep their "
          f"defaults, so read the 'Found N transcript files across ...' line per arm)")
print("\nThe tool warns that --output-dir is an unknown flag it ignored. It is not ignored; "
      "its\nsource-directory parser claims every --*-dir= and complains about the ones it "
      "does not own.")


def run(job):
    name, path, since, until = job
    out = os.path.join(args.out_dir, f"{name}--{since}_{until}")
    os.makedirs(out, exist_ok=True)
    began = time.monotonic()
    # `xl-ai-insights`, the packaged console script -- never `python -m`, which would import
    # whatever ./gnomon/ the caller stands in and leave --project supplying only the env.
    cmd = ["uv", "run", "--project", path, "xl-ai-insights", "--local", "--console",
           "--no-open", f"--since={since}", f"--until={until}",
           f"--output-dir={out}", *dirflag]
    try:
        proc = subprocess.run(cmd, cwd=path, capture_output=True, text=True,
                              timeout=args.timeout)
        text, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        text = (exc.stdout or "") + (exc.stderr or "")
        text += f"\n\nrun-arms: KILLED after {args.timeout}s.\n"
        code = None
    with open(os.path.join(out, "run.log"), "w") as fh:
        fh.write(text)
    stats = os.path.join(out, "stats.json")
    return name, since, until, code, time.monotonic() - began, os.path.exists(stats), out


by_copy = collections.OrderedDict()
for name, path in arms:
    for since, until in windows:
        by_copy.setdefault(path, []).append((name, path, since, until))


def run_group(jobs):
    return [run(job) for job in jobs]


wall = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
    results = [r for group in pool.map(run_group, by_copy.values()) for r in group]
wall = time.monotonic() - wall

print(f"\n{'arm':<16}{'window':<26}{'exit':>6}{'seconds':>10}  stats.json")
for name, since, until, code, secs, has_stats, _out in sorted(results, key=lambda r: -r[4]):
    print(f"  {name:<14}{since + ' -> ' + until:<26}"
          f"{'KILLED' if code is None else code:>6}{secs:>10.1f}  "
          f"{'yes' if has_stats else 'MISSING'}")

serial = sum(r[4] for r in results)
print(f"\n  wall clock {wall:.1f}s against {serial:.1f}s of pipeline time "
      f"({serial / wall:.1f}x across {len(by_copy)} copies)")

print("\n  NOT CHECKED: whether the arms differ for the reason you think. This runs them and")
print("  says which produced a stats.json; comparing the payloads, and confirming the arm")
print("  that must NOT move did not, is the measurement and is not done here.")

bad = [r for r in results if r[3] != 0 or not r[5]]
if bad:
    print(f"\n  {len(bad)} arm(s) did not produce a usable run: "
          f"{', '.join(f'{r[0]} {r[1]}..{r[2]}' for r in bad)}")
    print("  Read their run.log. An A/B missing an arm is not an A/B.")
    sys.exit(1)
