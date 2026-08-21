#!/usr/bin/env python3
"""Run miraudit's own replays. Zero tokens, no corpus, no network, seconds.

The tier this belongs to exists because a change validated only by a full run is a change
you validate once and then stop validating: a real audit costs a pipeline run and a personal
transcript corpus, and this costs neither.

Two tiers, and the distinction is real rather than a label:

  offline   zero external inputs. Everything that does not `import gnomon.*`.
  checkout  one read-only gnomon checkout, still no corpus and still no tokens. The three
            synthetic-fixture checks need `Accumulator`, and stubbing it would test the stub.

Discovery is a glob, never a list. A list is a second declaration of the same fact and it
drifts -- the file someone forgets to add is exactly the check nobody runs.
"""
import argparse
import glob
import importlib.util
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))


def discover():
    return sorted(glob.glob(os.path.join(HERE, "replay-*.py")))


def load_replay(path):
    name = "miraudit_replay_" + os.path.basename(path)[len("replay-"):-3].replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect(module):
    """Every top-level check_* callable, in SOURCE order -- the report reads better when it
    follows the file, and dict order would follow definition order only by accident."""
    found = [(getattr(fn, "__code__").co_firstlineno, name, fn)
             for name, fn in vars(module).items()
             if name.startswith("check_") and callable(fn) and hasattr(fn, "__code__")]
    return [(name, fn) for _, name, fn in sorted(found)]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--checkout", default=None,
                    help="a gnomon checkout, read-only. Unlocks the checkout tier; the "
                         "offline tier never needs it.")
    ap.add_argument("--list", action="store_true", help="name every check and exit")
    ap.add_argument("-k", dest="filter", default=None,
                    help="substring filter over 'module::check'")
    args = ap.parse_args(argv[1:])

    if args.checkout:
        args.checkout = os.path.expanduser(args.checkout)
        if not os.path.isdir(os.path.join(args.checkout, "gnomon")):
            print("error: %s has no gnomon/ package inside." % args.checkout)
            return 2

    sys.path.insert(0, HERE)
    import harness
    began = time.monotonic()
    tally = {"offline": [0, 0], "checkout": [0, 0]}   # [passed, run]
    skipped_modules, failures, notes = [], [], []

    for path in discover():
        label = os.path.basename(path)[len("replay-"):-3]
        try:
            module = load_replay(path)
        except Exception:
            failures.append(("%s::<import>" % label, traceback.format_exc().strip()))
            tally["offline"][1] += 1
            continue

        needs = tuple(getattr(module, "NEEDS", ()))
        tier = "checkout" if "checkout" in needs else "offline"
        checks = collect(module)
        if "checkout" in needs and not args.checkout:
            skipped_modules.append((label, len(checks)))
            continue

        for name, fn in checks:
            ident = "%s::%s" % (label, name)
            if args.filter and args.filter not in ident:
                continue
            if args.list:
                print("  %-9s %s" % (tier, ident))
                continue
            recorder = harness.Recorder()
            recorder.checkout = args.checkout
            tally[tier][1] += 1
            try:
                fn(recorder)
            except SystemExit:
                # SystemExit is NOT an Exception, so a bare `except Exception` lets it past
                # and it takes the whole runner down -- silently, with no summary line. Found
                # by fault injection: gutting parse()'s checkout guard killed the suite
                # instead of reddening the one check that covers it.
                failures.append((ident, "      the check raised SystemExit -- shipped code "
                                        "exited where the check expected it to return"))
                continue
            except Exception:
                failures.append((ident, traceback.format_exc().strip()))
                continue
            if recorder.failures:
                failures.append((ident, "\n".join("      " + f for f in recorder.failures)))
            else:
                tally[tier][0] += 1
            notes.extend("%s: %s" % (ident, n) for n in recorder.notes)

    if args.list:
        return 0

    for ident, detail in failures:
        print("\nFAIL  %s\n%s" % (ident, detail))
    for note in notes:
        print("\nnote  %s" % note)

    skipped_checks = sum(n for _, n in skipped_modules)
    wall = time.monotonic() - began
    line = "\nselfcheck: offline %d/%d" % (tally["offline"][0], tally["offline"][1])
    if args.checkout:
        line += " · checkout %d/%d" % (tally["checkout"][0], tally["checkout"][1])
    line += " in %.1fs" % wall
    if skipped_checks:
        line += " · %d SKIPPED (%s; no --checkout given)" % (
            skipped_checks, ", ".join(name for name, _ in skipped_modules))
    print(line)
    if skipped_checks:
        # run-checks.py's own sentence, and it is just as true one level down.
        print("  a skipped check is not a passed one.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
