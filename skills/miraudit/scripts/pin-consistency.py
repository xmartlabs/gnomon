"""Do the places that state the pin still agree — with each other, and with the checkout.

    python3 pin-consistency.py --checkout <copy> [--offline] [--contract-only]

The pin lived in three places and the refresh procedure named two. The third is a pasteable
`--expect-contract` command in README.md, so a stale value there is executable-wrong rather
than merely out of date. Nothing read any of them: known-state.md was prose for a human, and
an operator who forgot the flag simply got no comparison.

Runs beside contract-probe.py, before the pipeline, because that is the cheapest place to
fail. Cheap enough that --since/--until/--stats are accepted and ignored, like every other
check, so one command shape works for all of them.
"""
import os
import re
import subprocess
import sys
from importlib.machinery import SourceFileLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, require  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)

KNOWN = os.path.join(SKILL, "references", "known-state.md")
README = os.path.join(SKILL, "README.md")
SKILL_MD = os.path.join(SKILL, "SKILL.md")
GATE = os.path.join(HERE, "emit-gate.py")

def read_block():
    with open(KNOWN) as fh:
        text = fh.read()
    m = re.search(r"^```pin\n(.*?)^```", text, re.M | re.S)
    if not m:
        sys.exit(f"error: no ```pin block in {KNOWN}. It is the source; without it every "
                 "other copy is just another copy.")
    block = {}
    for line in m.group(1).strip().splitlines():
        k, _, v = line.partition(":")
        block[k.strip()] = v.strip()
    for required in ("ref", "contract", "branch"):
        if required not in block:
            sys.exit(f"error: the ```pin block has no `{required}`.")
    return block, text


# --field prints one value and leaves. second_corpus.py needs `ref` and anchor.py needs
# `contract`, and the alternative was a second copy of this parser inlined in each of them,
# which is the same mistake as the copies it exists to remove, one level down. Handled BEFORE
# parse(), because reading the pin must not require a checkout: `ref` is what clones one.
if "--field" in sys.argv:
    _block, _ = read_block()
    _which = sys.argv[sys.argv.index("--field") + 1]
    if _which not in _block:
        sys.exit(f"error: the ```pin block has no `{_which}`.")
    print(_block[_which])
    raise SystemExit(0)

args, _WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--offline": {"action": "store_true",
                  "help": "skip the upstream check; it is advisory either way"},
    "--contract-only": {"action": "store_true", "dest": "contract_only",
                        "help": "skip the ref comparison and the upstream check. For CI, "
                                "where the checkout is the repository at HEAD rather than a "
                                "clone of the pinned commit"},
}, needs_corpus=False)

block, known_text = read_block()
# Defensive because this file is opened from two very different places. In a clone it is
# next door; inside the built wheel it is package data, and the FIRST version of this check
# crashed a contributor's run on `open(README)` after the packaging fix had already been
# applied to references/ and not to this. A consistency check that cannot find one of the
# things it compares should say so, not take the run down with it.
readme_text = ""
try:
    with open(README) as fh:
        readme_text = fh.read()
except OSError:
    pass

failures = []
notes = []

# 1 -- the prose sentence in known-state.md, which is what a person actually reads.
m = re.search(r"\*\*Validated against:\*\*\s*`([0-9a-f]{7,40})`\s*on\s*`([\w./-]+)`"
              r"\s*\(contract\s*`([\d:]+)`\)", known_text)
if not m:
    failures.append("known-state.md has no `**Validated against:**` sentence in the shape "
                    "this reads. The block and the prose can no longer be compared.")
else:
    if m.group(1) != block["ref"]:
        failures.append(f"known-state.md prose says ref {m.group(1)}, the block says "
                        f"{block['ref']}")
    if m.group(3) != block["contract"]:
        failures.append(f"known-state.md prose says contract {m.group(3)}, the block says "
                        f"{block['contract']}")

# 2 -- README's pasteable command. Somebody copies this one and runs it.
found = set(re.findall(r"--expect-contract\s+([\d:]+)", readme_text))
if not readme_text:
    notes.append(f"no README.md beside this script ({README}), so its pasteable "
                 "--expect-contract example could not be compared. Expected inside a built "
                 "wheel; a defect in a clone.")
elif not found:
    notes.append("README.md no longer shows an --expect-contract example; nothing to drift.")
elif found != {block["contract"]}:
    failures.append(f"README.md shows --expect-contract {sorted(found)}, the block says "
                    f"{block['contract']}")

# 2b -- the Phase 3 table against emit-gate.ROWS. The eight rows live in three places on
# purpose, at three depths: ROWS is what the artifact must answer and is imported by
# new-run.py rather than copied; SKILL.md's table carries each question WITH the scar that
# earned it, in the one file every run loads; refutation.md holds the full write-up for the
# seven that came from a death. Only the first two are the same sentence twice, and nothing
# compared them until a run asked why the rows appeared in two files. They agree today.
skill_text = ""
try:
    with open(SKILL_MD) as fh:
        skill_text = fh.read()
except OSError:
    pass
_tbl = re.search(r"\| Try to refute \| The scar \|\n\|[-| ]+\|\n((?:\|.*\n)+)", skill_text)
if not skill_text:
    notes.append(f"no SKILL.md beside this script ({SKILL_MD}), so the Phase 3 table could "
                 "not be compared against emit-gate.ROWS. Expected inside a built wheel, "
                 "which ships scripts/ and references/ and not the skill file itself.")
elif not _tbl:
    failures.append("SKILL.md has no Phase 3 table in the shape this reads, so the rows a "
                    "run is told to answer can no longer be compared with the rows the gate "
                    "enforces.")
else:
    _gate_rows = SourceFileLoader("_pin_gate", GATE).load_module().ROWS
    _flat = lambda s: re.sub(r"[*`]", "", s).strip().rstrip(".").lower()
    _table = [_flat(l.split("|")[1]) for l in _tbl.group(1).strip().split("\n")]
    _code = [_flat(v) for v in _gate_rows.values()]
    if _table != _code:
        _only_gate = [q for q in _code if q not in _table]
        _only_doc = [q for q in _table if q not in _code]
        failures.append(
            f"SKILL.md's Phase 3 table and emit-gate.ROWS disagree: {len(_table)} rows "
            f"against {len(_code)}."
            + (f" Only in the gate: {_only_gate}." if _only_gate else "")
            + (f" Only in SKILL.md: {_only_doc}." if _only_doc else "")
            + " A row the gate enforces and the procedure never states is a row nobody "
              "answers on purpose.")

# 3 -- the checkout itself. SCORE_CONTRACT_ID is COMPUTED from three integers in
# scoring/versioning.py, so it cannot be grepped; importing is the only honest read, and
# require() is the mechanism the rest of the skill already uses.
(SCORE_CONTRACT_ID,) = require(
    [("gnomon.scoring.versioning", "SCORE_CONTRACT_ID")],
    "The contract identifier moved. Every comparison in this skill is scoped to it, so "
    "there is nothing to scope to until it is found again.")
if SCORE_CONTRACT_ID != block["contract"]:
    failures.append(f"the checkout computes contract {SCORE_CONTRACT_ID}, the block says "
                    f"{block['contract']}. This is the gate; the ref below is a hint.")

# 4 -- is the checkout the commit the block names? A hint, so it is reported either way and
# fails only when it can be resolved AND disagrees.
#
# --contract-only drops it, and the case is CI. There the checkout is the repository at the
# HEAD of a pull request, which by construction is not the pinned commit, so this would fail
# on every commit after a re-pin. A gate that is always red is not a gate, and it would bury
# check 3 -- the one CI exists to run, because it catches `scoring/versioning.py` moving while
# the block stays behind. The ref is documented as a hint everywhere else; here it is noise.
head = None
if args.contract_only:
    notes.append("--contract-only: the ref comparison and the upstream check were skipped. "
                 "The contract check above is the one that gates.")
try:
    r = subprocess.run(["git", "-C", args.checkout, "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True, timeout=10)
    head = r.stdout.strip() or None
except (OSError, subprocess.SubprocessError):
    head = None
if args.contract_only:
    pass
elif head is None:
    notes.append("the checkout has no resolvable HEAD (a `git archive` copy has no .git), "
                 "so the ref could not be compared. The contract check above still ran.")
elif not head.startswith(block["ref"]) and not block["ref"].startswith(head):
    failures.append(f"the checkout is at {head}, the block pins {block['ref']}")

# 5 -- has upstream moved past the pin? ADVISORY, never fatal: a second-corpus runner with
# no network must not be blocked by a fact that changes nothing about their own run.
if not args.offline and not args.contract_only and block.get("upstream"):
    try:
        r = subprocess.run(["git", "ls-remote", block["upstream"],
                            f"refs/heads/{block['branch']}"],
                           capture_output=True, text=True, timeout=20)
        remote = (r.stdout.split() or [""])[0][:len(block["ref"])]
        if remote and remote != block["ref"]:
            notes.append(f"upstream {block['branch']} is at {remote}, past the pinned "
                         f"{block['ref']}. Not an error: the pin is deliberate, and a run "
                         "against a moved upstream is a different contract question.")
    except (OSError, subprocess.SubprocessError):
        notes.append("upstream could not be reached; skipped, which is not a failure.")

print("pin consistency")
print(f"  block          ref {block['ref']}  contract {block['contract']}"
      f"  branch {block['branch']}")
print(f"  checkout       ref {head or 'unresolvable'}  contract {SCORE_CONTRACT_ID}")
for n in notes:
    print(f"  note           {n}")
if failures:
    print()
    for f in failures:
        print(f"  DRIFTED: {f}")
    print("\n  The pin is the one thing a second corpus and this run have to share. Fix the")
    print("  ```pin block in references/known-state.md and the copies that quote it.")
    raise SystemExit(1)
print("  ok             every stated pin agrees with the block and with the checkout")
