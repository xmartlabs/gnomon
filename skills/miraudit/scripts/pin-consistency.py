"""Do the places that state the pin still agree — with each other, and with the checkout.

    python3 pin-consistency.py --checkout <copy> [--pin-repo <repo>] [--offline]
    python3 pin-consistency.py --checkout <repo> --write

The pin lived in three places and the refresh procedure named two. The third was a pasteable
`--expect-contract` command in README.md, so a stale value there was executable-wrong rather
than merely out of date. Nothing read any of them.

There is one place now. The block names a REF and the contract is derived from the code at
it, so the two cannot disagree: a stored contract could contradict its own ref, and did. That
derivation reads versioning.py out of the ref and executes it, because the id is computed from
three integers and reassembling it from greps is the "rewrite a predicate you could import"
mistake this skill reports in other people's code. It needs a repository that has the ref,
which is what --pin-repo is for: --checkout is often a `git archive` copy with no .git.

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
    for required in ("ref", "branch"):
        if required not in block:
            sys.exit(f"error: the ```pin block has no `{required}`.")
    return block, text


def contract_at(ref, repo):
    """SCORE_CONTRACT_ID as computed by the code at `ref`. Derived, never stored.

    It used to be a fourth field in the block, which meant a value that the ref already
    determines was kept in step by hand -- and it drifted, along with the two copies quoting
    it. Deriving it is not a shortcut: the id is COMPUTED from three integers, so grepping
    them and reassembling the string would be this skill's own "rewrite a predicate you could
    import" mistake. The file is read out of the ref and executed, so the arithmetic is
    theirs.
    """
    r = subprocess.run(["git", "-C", repo, "show", f"{ref}:gnomon/scoring/versioning.py"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, (f"could not read gnomon/scoring/versioning.py at {ref} from {repo}. "
                      "The contract is derived from the pinned ref, so it needs a git "
                      "checkout that has that commit.")
    ns = {"__name__": "_pinned_versioning"}
    try:
        exec(compile(r.stdout, "versioning.py", "exec"), ns)
    except Exception as exc:  # noqa: BLE001 -- their file, any failure is theirs to see
        return None, f"versioning.py at {ref} did not execute: {exc}"
    if "SCORE_CONTRACT_ID" not in ns:
        return None, f"versioning.py at {ref} defines no SCORE_CONTRACT_ID."
    return ns["SCORE_CONTRACT_ID"], None


# --field prints one value and leaves. second_corpus.py needs `ref` and anchor.py needs
# `contract`, and the alternative was a second copy of this parser inlined in each of them,
# which is the same mistake as the copies it exists to remove, one level down. `ref` is
# handled BEFORE parse(), because reading it must not require a checkout: `ref` is what clones
# one. `contract` is derived and therefore does need a repository that has the ref, which is
# why it takes --checkout here rather than being stored.
if "--field" in sys.argv:
    _block, _ = read_block()
    _which = sys.argv[sys.argv.index("--field") + 1]
    if _which == "contract":
        _repo = (sys.argv[sys.argv.index("--checkout") + 1]
                 if "--checkout" in sys.argv else ".")
        _value, _why = contract_at(_block["ref"], os.path.expanduser(_repo))
        if _value is None:
            sys.exit(f"error: {_why}")
        print(_value)
        raise SystemExit(0)
    if _which not in _block:
        sys.exit(f"error: the ```pin block has no `{_which}`.")
    print(_block[_which])
    raise SystemExit(0)

args, _WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--offline": {"action": "store_true",
                  "help": "skip the upstream check; it is advisory either way"},
    "--write": {"action": "store_true",
                "help": "rewrite the block, the prose sentence and README's example from the "
                        "contract this checkout computes. Does the typing, not the validating"},
    "--pin-repo": {"default": None, "dest": "pin_repo", "metavar": "PATH",
                   "help": "a git repository that has the pinned ref, used only to derive the "
                           "contract it implies. Defaults to --checkout, which is wrong "
                           "exactly when --checkout is a `git archive` copy with no .git"},
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
m = re.search(r"\*\*Validated against:\*\*\s*`([0-9a-f]{7,40})`\s*on\s*`([\w./-]+)`", known_text)
if not m:
    failures.append("known-state.md has no `**Validated against:**` sentence in the shape "
                    "this reads. The block and the prose can no longer be compared.")
elif m.group(1) != block["ref"]:
    failures.append(f"known-state.md prose says ref {m.group(1)}, the block says "
                    f"{block['ref']}")

# 2 -- README's pasteable command. Somebody copies this one and runs it.
found = set(re.findall(r"--expect-contract\s+([\d:]+)", readme_text))
if found:
    failures.append(
        f"README.md pastes a literal --expect-contract {sorted(found)}. The contract is "
        "derived from the pinned ref now and anchor.py defaults the flag from it, so a "
        "literal here is a copy that can only go out of date -- and it goes out of date "
        "executable-wrong, because somebody pastes it and runs it.")

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
# 3 -- the checkout you are auditing against the code at the pinned ref. This is the gate,
# and it is now a comparison between two pieces of code rather than between code and a string
# somebody typed. The stored value could disagree with its own ref; a derived one cannot.
PINNED_CONTRACT, why = contract_at(block["ref"], args.pin_repo or args.checkout)
if PINNED_CONTRACT is None:
    # Fail, not note. The comparison below IS the gate, and a run that cannot make it has not
    # passed anything -- the first version of this printed the note and then "ok", which is the
    # fail-open this skill exists to catch, introduced by the commit that removed the stored
    # copy. anchor.py hands its throwaway `git archive` copy to every check, so this is the
    # normal case rather than an exotic one.
    failures.append(f"{why} Pass --pin-repo pointing at a clone that has {block['ref']}; the "
                    f"checkout computes {SCORE_CONTRACT_ID} and nothing compared it.")
elif SCORE_CONTRACT_ID != PINNED_CONTRACT and not args.write:
    failures.append(f"the checkout computes contract {SCORE_CONTRACT_ID}, and the code at the "
                    f"pinned ref {block['ref']} computes {PINNED_CONTRACT}. This is the gate; "
                    "the ref below is a hint.")

# --write. The contract string lives in three places -- the block, the prose sentence a person
# reads, and a pasteable --expect-contract example in README.md -- and a re-pin used to mean
# typing it into all three. Measured: editing only the block leaves two failures behind, which
# is how a re-pin half-lands. The value is not a judgement, it is whatever the checkout
# computes, so the typing is mechanical and belongs here.
#
# It re-resolves the file:line anchors too, and BEFORE it touches the block, because the
# resolution needs the ref the block still names. Two commands in the right order is one
# command somebody eventually runs backwards.
#
# The split is the point. An anchor whose line still exists verbatim at the new ref, exactly
# once, is a pure move: measured on the 19:19:19 re-pin, that was 9 of 9 in aq.py, and it is
# the tedious part people either skip or do wrong. Anything else -- gone, or now ambiguous --
# is left for a person and the run fails until they look.
#
# What none of it does is validate. `validated:` becomes today's date because the field records
# when somebody last looked, and this makes the looking cheaper rather than optional. A content
# resolver moves a line; it cannot tell whether the SENTENCE around it still describes the
# code. The stale claim this skill carried for days was exactly that: `accumulator.py:1414`
# resolved fine and the prose beside it named a branch the file had not contained since #75.
# So it says so, every time, instead of letting a green run imply otherwise.


def resolve_anchors(checkout, old_ref):
    """Renumber `file.py:N` anchors from old_ref to the checkout. Returns (edits, unresolved)."""
    docs = [os.path.join(SKILL, "references", n)
            for n in sorted(os.listdir(os.path.join(SKILL, "references")))
            if n.endswith(".md")] + [SKILL_MD]
    paths = subprocess.run(["git", "-C", checkout, "ls-files", "*.py"],
                           capture_output=True, text=True).stdout.split()
    by_base = {}
    for p in paths:
        by_base.setdefault(os.path.basename(p), []).append(p)

    old_cache, new_cache, edits, unresolved = {}, {}, [], []

    def lines(cache, ref, path):
        key = (ref, path)
        if key not in cache:
            r = subprocess.run(["git", "-C", checkout, "show", f"{ref}:{path}"],
                               capture_output=True, text=True)
            cache[key] = r.stdout.splitlines() if r.returncode == 0 else None
        return cache[key]

    for doc in docs:
        if not os.path.exists(doc):
            continue
        text = original = open(doc).read()
        for base, start, end in sorted(set(re.findall(r"([a-z_]+\.py):(\d+)(?:-(\d+))?", text))):
            where = f"{os.path.basename(doc)} -> {base}:{start}" + (f"-{end}" if end else "")
            cands = by_base.get(base, [])
            if len(cands) != 1:
                why = ("no file by that name in the checkout" if not cands
                       else f"{len(cands)} files share that name, so it is ambiguous")
                unresolved.append(f"{where}: {why}")
                continue
            old_lines = lines(old_cache, old_ref, cands[0])
            new_lines = lines(new_cache, "HEAD", cands[0])
            if old_lines is None or new_lines is None:
                unresolved.append(f"{where}: could not read the file at one of the two refs")
                continue
            n = int(start)
            if n > len(old_lines):
                unresolved.append(f"{where}: the pinned ref's file has only {len(old_lines)} lines")
                continue
            content = old_lines[n - 1]
            hits = [i + 1 for i, l in enumerate(new_lines) if l == content]
            if len(hits) != 1:
                unresolved.append(
                    f"{where}: its line is {'gone' if not hits else f'now at {len(hits)} places'} "
                    f"at the new ref. Read the sentence around it and resolve it by symbol.")
                continue
            if hits[0] == n:
                continue
            new_anchor = f"{base}:{hits[0]}"
            if end:
                new_anchor += f"-{hits[0] + (int(end) - n)}"
            text = text.replace(f"{base}:{start}" + (f"-{end}" if end else ""), new_anchor)
            edits.append(f"{os.path.basename(doc)}: {base}:{start}"
                         + (f"-{end}" if end else "") + f" -> {new_anchor}")
        if text != original:
            with open(doc, "w") as fh:
                fh.write(text)
    return edits, unresolved
if args.write:
    anchor_edits, anchor_unresolved = resolve_anchors(args.checkout, block["ref"])
    new_ref = subprocess.run(["git", "-C", args.checkout, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip() or block["ref"]
    today = subprocess.run(["date", "+%Y-%m-%d"], capture_output=True, text=True).stdout.strip()
    updated = known_text
    updated = re.sub(r"(^```pin\n(?:.*\n)*?)^ref: .*$", rf"\g<1>ref: {new_ref}",
                     updated, count=1, flags=re.M)
    updated = re.sub(r"(^```pin\n(?:.*\n)*?)^validated: .*$", rf"\g<1>validated: {today}",
                     updated, count=1, flags=re.M)
    updated = re.sub(r"\*\*Validated against:\*\*\s*`[0-9a-f]{7,40}`\s*on\s*`([\w./-]+)`"
                     r"[^\n]*?\.",
                     rf"**Validated against:** `{new_ref}` on `\1`, {today}.",
                     updated, count=1)
    with open(KNOWN, "w") as fh:
        fh.write(updated)
    print(f"pin-consistency --write: the block now pins {new_ref}, validated {today}. "
          f"The contract it implies is {SCORE_CONTRACT_ID}, derived and not written down.")
    if anchor_edits:
        print(f"\n  {len(anchor_edits)} anchor(s) renumbered, each because its line survived "
              f"verbatim and exactly once:")
        for e in anchor_edits:
            print(f"    {e}")
    else:
        print("\n  No anchor moved.")
    print("\n  NOT DONE, and this is the part that matters: nothing was validated. Re-run\n"
          "  contract-probe.py and the checks against this ref. Then read the sentences around\n"
          "  the anchors above and ask whether they still describe the code -- renumbering\n"
          "  cannot answer that, and it is where this skill's last stale claim lived for days:\n"
          "  a line that resolved cleanly beside prose naming a branch the file no longer had.\n"
          "  Then re-run this without --write.")
    if anchor_unresolved:
        print(f"\n  {len(anchor_unresolved)} anchor(s) could NOT be resolved and need a person:")
        for u in anchor_unresolved:
            print(f"    {u}")
        raise SystemExit(1)
    raise SystemExit(0)

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
    # A NOTE, not a failure, and only when the contract agrees. SKILL.md has always said "the
    # contract string is the gate; the commit is a hint" and this line said otherwise, so a
    # re-pin forced everyone to move their local clone to the new commit before any run would
    # start -- for a difference the gate above already proved harmless. When the contract does
    # NOT agree, check 3 above has already failed and this adds the commit as context.
    where = (f"the checkout is at {head} and the block pins {block['ref']}")
    if PINNED_CONTRACT is not None and SCORE_CONTRACT_ID == PINNED_CONTRACT:
        notes.append(f"{where}. Not a failure: both compute {SCORE_CONTRACT_ID}, and the "
                     "contract is the gate. Findings stay scoped to what the block names.")
    else:
        failures.append(where)

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
print(f"  pinned         ref {block['ref']}  contract "
      f"{PINNED_CONTRACT or 'underivable'}  branch {block['branch']}")
print(f"  checkout       ref {head or 'unresolvable'}  contract {SCORE_CONTRACT_ID}")
for n in notes:
    print(f"  note           {n}")
if failures:
    print()
    for f in failures:
        print(f"  DRIFTED: {f}")
    print("\n  The pin is the one thing a second corpus and this run have to share.")
    print("  The contract string lives in three places and editing only the block leaves two")
    print("  of these behind. To do the typing:")
    print(f"\n      python3 {os.path.relpath(__file__)} --checkout . --write\n")
    print("  It rewrites all three from what this checkout computes and says what it did not")
    print("  do, which is validate. Read that part.")
    raise SystemExit(1)
print("  ok             every stated pin agrees with the block and with the checkout")
