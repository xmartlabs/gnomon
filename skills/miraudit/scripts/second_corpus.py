"""One command, one file. This is the entire ask for someone contributing a second corpus:

    uvx --from "git+https://github.com/xmartlabs/gnomon#subdirectory=skills/miraudit" \
        miraudit-second-corpus

Nothing is installed and nothing is left behind. From a clone, the equivalent is
`python3 <clone>/skills/miraudit/scripts/second_corpus.py`.

No arguments. It clones the scoring tool at a pinned commit, scores the last 30 complete
days of your local transcripts, and writes ONE file to send back.

Every default is printed and recorded in the file, so nothing about the run is implicit.
Override any of them if you have a reason:

  --since / --until   your own report's window, if you have a published report to match
  --published <N>     the number that report shows, to make the anchor check itself
  --checkout <path>   an existing checkout instead of cloning
  --ref <commit>      a different commit to pin to
  --out-dir <path>    where the result file goes (default: the working directory)
  --keep              do not delete the scratch directory on success

It uses about 16 MB of scratch and under two minutes. The scratch is deleted when the run
succeeds and kept when it does not.

Nothing is written inside the checkout, and nothing leaves except that one file, which
carries counts and shares. Read it before sending it.

PYTHON, NOT BASH. This was a bash script and needed a POSIX shell that no requirements list
mentioned. On Windows `bash` resolves to the WSL launcher, so the first Windows runner got
`execvpe(/bin/bash) failed` from inside WSL. Requirements are now exactly what the three
docs always claimed: python3, git, uv.
"""
import argparse
import datetime
import os
import shutil
import subprocess
import tempfile
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "https://github.com/xmartlabs/gnomon.git"
DEFAULT_CORPUS = os.path.join(os.path.expanduser("~"), ".claude", "projects")


def pin(field):
    """The pin has ONE home: the ```pin block in references/known-state.md. It used to be a
    literal here as well, kept equal by a step in a written procedure that was already
    incomplete when it was written."""
    r = subprocess.run([sys.executable, os.path.join(HERE, "pin-consistency.py"),
                        "--field", field], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(r.stdout.strip() or r.stderr.strip() or f"error: no `{field}` in the pin.")
    return r.stdout.strip()


def writable(path):
    """Can a file actually be created here? os.access(W_OK) lies on Windows, where it
    reports the read-only ATTRIBUTE rather than the ACL that does the denying."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, f".miraudit-write-probe.{os.getpid()}")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def main(argv=None):
    p = argparse.ArgumentParser(prog="miraudit-second-corpus",
                                description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checkout")
    p.add_argument("--ref")
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--published")
    p.add_argument("--corpus", default=DEFAULT_CORPUS)
    p.add_argument("--out-dir", dest="out_dir", default=os.getcwd())
    p.add_argument("--work")
    p.add_argument("--keep", action="store_true")
    args = p.parse_args(argv)

    ref = args.ref or pin("ref")

    # The scratch holds a clone, a copy of it and the copy's virtualenv: about 16 MB. Nothing
    # used to delete it and the file worth keeping lived inside it, so every run left the
    # whole thing behind. On FAILURE it is kept and the path printed -- a run that broke is
    # exactly when the intermediate files are worth having.
    auto_work = args.work is None
    work = os.path.abspath(os.path.expanduser(
        args.work or os.path.join(tempfile.gettempdir(),
                                  f"miraudit-second-corpus.{os.getpid()}")))

    # The window ends YESTERDAY. A window ending now includes the session running the audit,
    # which is then measuring itself while it is still being written.
    until = args.until or str(datetime.date.today() - datetime.timedelta(days=1))
    since = args.since or str(datetime.date.fromisoformat(until)
                              - datetime.timedelta(days=30))
    defaulted = "   (default: the last 30 complete days)" if not args.since else ""

    # WHERE THE DELIVERABLE GOES, DECIDED BEFORE THE TWO MINUTES OF WORK, NOT AFTER.
    # A Windows runner launched from C:\Program Files (x86)\Cmder -- a terminal that starts
    # in its own install directory -- completed the whole run and then lost it to a
    # PermissionError on the last line. Nothing was wrong with the measurement; it had
    # nowhere to land, and found out last.
    out_dir = os.path.abspath(os.path.expanduser(args.out_dir))
    if not writable(out_dir):
        if args.out_dir != os.getcwd():
            sys.exit(f"error: cannot write to {out_dir}. Pass a different --out-dir.")
        fallback = os.path.expanduser("~")
        if not writable(fallback):
            sys.exit(f"error: cannot write to {out_dir} or to {fallback}. "
                     "Pass --out-dir somewhere writable.")
        print(f"!! this directory is not writable: {out_dir}")
        print(f"!! the result will go to {fallback} instead. Pass --out-dir to choose.\n")
        out_dir = fallback

    os.makedirs(work, exist_ok=True)
    ok = False
    try:
        checkout = args.checkout
        if not checkout:
            checkout = os.path.join(work, "gnomon")
            print(f"==> cloning the scoring tool at {ref} "
                  "(nothing is written to it afterwards)")
            subprocess.run(["git", "clone", "--quiet", REPO_URL, checkout], check=True)
            subprocess.run(["git", "-C", checkout, "checkout", "--quiet", ref], check=True)

        resolved = subprocess.run(["git", "-C", checkout, "rev-parse", "--short", "HEAD"],
                                  capture_output=True, text=True).stdout.strip() or "unknown"

        print()
        print("=" * 62)
        print(f"  scoring tool   {resolved}")
        print(f"  corpus         {args.corpus}")
        print(f"  window         {since} -> {until}{defaulted}")
        print(f"  published      {args.published or 'not given, so the anchor records ok=null rather than true'}")
        print("=" * 62)
        print()

        if not os.path.isdir(args.corpus):
            sys.exit(f"error: no transcript corpus at {args.corpus}. Pass --corpus.")

        print("==> anchoring")
        print("    (the scoring tool will warn that --output-dir is an 'unknown flag"
              " ignored'.")
        print("     It is not ignored: the flag is real and documented, and the run writes"
              " exactly")
        print("     where it says at the end. Its source-directory parser claims every"
              " --*-dir=")
        print("     argument and warns about the ones it does not own.)")
        anchor_args = ["--checkout", checkout, "--since", since, "--until", until,
                       "--corpus", args.corpus, "--work", os.path.join(work, "anchor")]
        if args.published:
            anchor_args += ["--published", args.published]
        if subprocess.run([sys.executable, os.path.join(HERE, "anchor.py"), *anchor_args],
                          check=False).returncode != 0:
            sys.exit("the anchor did not pass. Nothing below it is safe to read.")

        stats = None
        for root, _dirs, files in os.walk(os.path.join(work, "anchor")):
            if "stats.json" in files:
                stats = os.path.join(root, "stats.json")
                break
        copy = os.path.join(work, "anchor", "checkout")

        out = os.path.join(out_dir, f"miraudit-comparison-{until}.json")

        common = ["--checkout", copy, "--corpus", args.corpus, "--since", since,
                  "--until", until, "--stats", stats]
        sat = os.path.join(work, "saturation.json")
        print("\n==> saturation counterfactual")
        # Non-zero here means a control did not move, which makes the headline
        # untrustworthy -- but the emitted json records exactly that, so finish the run and
        # let the reader see `controls_moved: false` instead of getting no file at all.
        if subprocess.run([sys.executable, os.path.join(HERE, "saturation-counterfactual.py"),
                           *common, "--emit", sat], check=False).returncode != 0:
            print("  (a control did not move; recorded in the file)")

        print("\n==> writing the payload")
        emit = [sys.executable, os.path.join(HERE, "emit-comparison.py"), *common,
                "--ref", resolved, "--saturation", sat, "--out", out]
        if args.published:
            emit += ["--published", args.published]
        if subprocess.run(emit, check=False).returncode != 0:
            sys.exit("the payload was not written.")

        print()
        print("=" * 62)
        print("Send this one file back:")
        print(f"    {out}")
        print("=" * 62)
        ok = True
        return 0
    finally:
        if ok and auto_work and not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        elif os.path.isdir(work):
            print(f"\nscratch kept at {work} -- delete it when done.")


if __name__ == "__main__":
    raise SystemExit(main())
