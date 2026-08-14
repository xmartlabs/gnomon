"""Phase 0 in one command: copy the checkout, reproduce the published number over the
report's own window, print the corpus fingerprint, and leave stats.json where the other
checks can read it with --stats.

    python3 anchor.py --checkout <path> --since YYYY-MM-DD --until YYYY-MM-DD
                      [--corpus <path>] [--published <N>] [--expect-contract <X>]

--published and --expect-contract turn Phase 0 into an actual gate: without them the script
prints the number and trusts you to compare it, which is what it used to do.

Never runs against the original checkout. Everything happens on a copy under --work.

PYTHON, NOT BASH, AND THAT IS THE POINT. This was a bash script, and every published list of
what a contributor needs said "python3, git and uv" while the whole path required a POSIX
shell. On Windows `bash` is the WSL launcher, so the first Windows runner got
`execvpe(/bin/bash) failed` from inside WSL — a missing-shell error on a machine with a
shell. Nothing here needs a shell now: copying, globbing and process spawning are all
stdlib, and the one external command is the scoring tool's own console script.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _common import load_stats, find_key  # noqa: E402

# Line-buffered even when the output is a pipe. Python block-buffers a redirected stdout, so
# a log captured with `| tee` came out in an order that contradicts the run: the fingerprint
# and the THEIRS vs OURS table printed ABOVE the banners that produced them. `python3 -u`
# fixes that too and depends on the caller remembering.
#
# On its own that is not enough, and an earlier version of this comment claimed the
# subprocesses "write through immediately", which is wrong. They inherit the same pipe and
# block-buffer in turn: piped, `xl-ai-insights` held its whole progress output, so the run
# showed nothing for the minutes it takes and looked hung. A cold run polled the log four
# times and ran `ps` to establish it had not died. The pipeline is launched with
# PYTHONUNBUFFERED=1 for that reason -- see the env= on its subprocess.run below.
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:  # pragma: no cover - Python < 3.7
    pass

DEFAULT_CORPUS = os.path.join(os.path.expanduser("~"), ".claude", "projects")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="anchor", description=__doc__.strip().splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checkout", required=True)
    p.add_argument("--since", required=True, metavar="YYYY-MM-DD")
    p.add_argument("--until", required=True, metavar="YYYY-MM-DD")
    p.add_argument("--corpus", default=DEFAULT_CORPUS)
    p.add_argument("--work", default=None)
    p.add_argument("--published", default="")
    p.add_argument("--expect-contract", dest="expect", default="")
    # argparse exits 2 on a missing required flag, which is what the shell version did, but
    # it cannot explain WHY the window is required. That reason is the one worth keeping.
    args = p.parse_args(argv)

    checkout = os.path.abspath(os.path.expanduser(args.checkout))
    if not os.path.isdir(os.path.join(checkout, "gnomon")):
        sys.exit(f"error: {checkout} does not look like a checkout "
                 "(no gnomon/ package inside).")

    # tempfile.gettempdir(), not TMPDIR-or-/tmp. Windows sets TEMP, not TMPDIR, so the
    # fallback would have been a literal /tmp on a machine with no such directory --
    # the same class of assumption as calling `bash`, surviving one layer deeper.
    work = args.work or os.path.join(
        tempfile.gettempdir(), f"miraudit-anchor.{os.getpid()}")
    work = os.path.abspath(os.path.expanduser(work))
    copy, out = os.path.join(work, "checkout"), os.path.join(work, "report")
    os.makedirs(out, exist_ok=True)

    print("==> copying the checkout (the original is never written to)")
    if os.path.exists(copy):
        shutil.rmtree(copy)
    shutil.copytree(checkout, copy, symlinks=True)

    # --corpus used to reach only contract-probe.py and fingerprint.py, never the pipeline.
    # So `--corpus X` fingerprinted X and SCORED the default corpus, and the payload and the
    # fingerprint described different corpora with nothing saying so. On the default corpus
    # they happen to agree, which is why it survived every run here.
    #
    # The scoring tool's own flag is --claude-dir=PATH (sources/discovery.py:48); its
    # resolver takes either the config root or the transcripts subdir (discovery.py:92-98),
    # so --corpus passes straight through. Only when it differs from the default, so
    # existing runs are unchanged.
    #
    # IT OVERRIDES THE CLAUDE SOURCE ONLY. Codex, Gemini, Cursor and the rest keep resolving
    # to their own default locations, so on a machine where any of those clears the
    # source-volume threshold the run is a mix. Read the "Found N transcript files across
    # ..." line and `sources_scored` in the payload, which is what makes the mix visible.
    dirflag = []
    if os.path.normpath(args.corpus) != os.path.normpath(DEFAULT_CORPUS):
        dirflag = [f"--claude-dir={args.corpus}"]
        print(f"    corpus override: --claude-dir={args.corpus}")

    def check(script, *extra):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, script), "--checkout", copy,
             "--corpus", args.corpus, "--since", args.since, "--until", args.until,
             *extra], check=False)

    # pin-consistency derives the pinned contract by reading versioning.py OUT of the ref, so
    # it needs a real repository. Every check gets `copy`, which is a `git archive` extraction
    # with no .git, and it would have degraded to "could not derive" on every run.
    def check_pin(*extra):
        return check("pin-consistency.py", "--pin-repo", args.checkout, *extra)

    # Before the pipeline, not after: these cost milliseconds and the pipeline costs minutes,
    # and a checkout whose predicates have moved makes every later number unsafe anyway.
    print("==> checking the pin agrees with itself and with the checkout")
    if check_pin().returncode != 0:
        return 1

    expect = args.expect
    if not expect:
        # Default it from the pin block rather than making the operator carry the value
        # across from a markdown file by hand. An unpassed flag used to mean no comparison
        # at all, which is how a gate ends up documented and unenforced.
        # --checkout, because the contract is DERIVED from the pinned ref rather than stored
        # beside it, so resolving it needs a repository that has that commit. args.checkout is
        # the clone the operator pointed at; the throwaway copy made below would not do, since
        # `git archive` leaves no .git behind.
        expect = subprocess.run(
            [sys.executable, os.path.join(HERE, "pin-consistency.py"), "--field", "contract",
             "--checkout", args.checkout],
            capture_output=True, text=True).stdout.strip()
        if expect:
            print(f"    --expect-contract defaulted to {expect} from the pin block")

    print("\n==> probing the predicates the checks are built on")
    # Skip the probe's own four-line banner: the checkout, corpus and window were printed a
    # moment ago and repeating them buries the eighteen assertions that matter. The bash
    # version did this with `| tail -n +5`.
    probe = subprocess.run(
        [sys.executable, os.path.join(HERE, "contract-probe.py"), "--checkout", copy,
         "--corpus", args.corpus, "--since", args.since, "--until", args.until],
        capture_output=True, text=True)
    print("\n".join(probe.stdout.splitlines()[4:]))
    if probe.returncode != 0:
        print(probe.stderr, file=sys.stderr)
        return 1

    print(f"\n==> reproducing the published number: {args.since} -> {args.until}")
    # `xl-ai-insights`, the packaged console script -- NOT `python -m gnomon.cli.insights`.
    # `-m` puts the CURRENT DIRECTORY on sys.path first, so it imports whatever ./gnomon/ the
    # caller happened to be standing in and `--project` only supplies the environment.
    # Measured: from a directory holding a v16 fork the pipeline scored 16:16:16 while
    # --project pointed at a v17 copy. A console script is a FILE, so sys.path starts at its
    # own directory and the caller's location cannot shadow the package. cwd=copy is belt and
    # braces against anyone restoring the `-m` form.
    rc = subprocess.run(
        ["uv", "run", "--project", copy, "xl-ai-insights", "--local", "--console",
         "--no-open", f"--since={args.since}", f"--until={args.until}",
         f"--output-dir={out}", *dirflag], cwd=copy, check=False,
        env=dict(os.environ, PYTHONUNBUFFERED="1")).returncode
    if rc != 0:
        print(f"\nerror: the scoring tool exited {rc}.", file=sys.stderr)
        return 1

    stats = None
    for root, _dirs, files in os.walk(out):
        if "stats.json" in files:
            stats = os.path.join(root, "stats.json")
            break
    if not stats:
        print(f"\nerror: the run produced no stats.json under {out}.", file=sys.stderr)
        print("Phase 0 is a gate: without a reproduced number, no finding is safe to read.",
              file=sys.stderr)
        return 1

    if gate(stats, args.published, expect) != 0:
        return 1

    # A record of what Phase 0 established, written beside the payload so the next step reads
    # it instead of retyping it. It is state, NOT a gate: nothing requires this file to exist
    # in order to run, because the alternative was measured and it stops the tool dead. Most
    # runs have no published figure at the pinned contract, and second-corpus.md says a null
    # is usable for composition and shape while only a false disqualifies. Requiring a pass
    # here would end the contributor path, which emits its payload with `ok` null by design.
    ref = subprocess.run(
        [sys.executable, os.path.join(HERE, "pin-consistency.py"), "--field", "ref"],
        capture_output=True, text=True).stdout.strip() or None
    with open(os.path.join(os.path.dirname(stats), "anchor.json"), "w") as fp:
        json.dump({"ref": ref, "contract": expect or None,
                   "published": args.published or None,
                   "reproduced": find_key(load_stats(stats), "aq_0_100"),
                   "ok": True if args.published else None,
                   "contract_probe": "18/18" if expect else None,
                   "window": {"since": args.since, "until": args.until}}, fp, indent=2)

    print()
    # Read, unlike before. pin-consistency's return code is read at line 96 and this one was
    # not, so any future failure here was invisible -- and Phase 0 asks for the fingerprint
    # before any other number, which makes a silent absence the worst kind.
    if check("fingerprint.py", "--stats", stats).returncode != 0:
        print("\nerror: the fingerprint did not run. Phase 0 wants it printed before any "
              "other number,\nso the run should not continue without it.", file=sys.stderr)
        return 1

    print("\n==> anchored")
    print(f"    stats.json : {stats}")
    print(f"    copy       : {copy}\n")
    if args.published:
        print(f"The gate passed: this run reproduced {args.published}. Pass the same window,"
              " and the COPY —")
    else:
        print("Compare that AQ against the published one BEFORE measuring anything. If they"
              " differ,")
        print("the method is wrong before any finding is. Then pass the same window, and the"
              " COPY —")
    print("never the original, which the checks would write __pycache__ into:\n")
    print(f"    python3 {os.path.join(HERE, '<check>.py')} --checkout {copy} \\")
    print(f"        --since {args.since} --until {args.until} --stats {stats}\n")
    print("Every check takes that exact shape. Checks that do not read stats.json accept"
          " --stats")
    print("and ignore it, so one command works for all of them.")
    return 0


def gate(stats_path, published, expect):
    """Print the number the gate is ABOUT, then enforce it.

    The console run emits a GStack archetype line saying "Elite", which is a different
    scoring system and has been misread as satisfying this gate. Nothing else prints the AQ,
    so a run could not check what it was told to check.
    """
    stats = load_stats(stats_path)
    aq = find_key(stats, "aq_0_100")
    tier = find_key(stats, "tier")
    contract = find_key(stats, "score_contract_id")

    print()
    print("=" * 62)
    print("THE NUMBER TO COMPARE  (this, not the archetype line above)")
    print("=" * 62)
    if aq is None:
        print("  aq_0_100 not found in stats.json.")
        print("  Do NOT proceed: the gate cannot be checked, which is the same as failing it.")
        return 1
    print(f"  AQ        {aq}")
    print(f"  tier      {tier}")
    print(f"  contract  {contract}")

    failed = []
    if published:
        same = str(aq).strip() == published.strip()
        print(f"\n  published {published}   ->  "
              f"{'reproduced' if same else 'DOES NOT MATCH'}")
        if not same:
            failed.append(f"the run gives {aq}, the published number is {published}")
    if expect:
        same = str(contract).strip() == expect.strip()
        print(f"  expected contract {expect}   ->  "
              f"{'match' if same else 'DOES NOT MATCH'}")
        if not same:
            failed.append(f"the checkout is on {contract}, not {expect}")
    if failed:
        print("\n  GATE FAILED: " + "; ".join(failed) + ".")
        print("  The method is wrong before any finding is. Do not run the checks.")
        return 1
    # Per flag, not on the conjunction. `if not published and not expect` stayed silent
    # whenever EITHER was given, so passing --published alone skipped the contract gate with
    # nothing on screen saying a gate had been skipped. Half a gate reads like a whole one.
    if not published:
        print("\n  The NUMBER was not gated. Pass --published <N> to have this script"
              " compare")
        print("  it instead of asking you to.")
    if not expect:
        print("\n  The CONTRACT was not gated. Pass --expect-contract <X>; the value is the")
        print("  `contract` field of the block at the top of references/known-state.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
