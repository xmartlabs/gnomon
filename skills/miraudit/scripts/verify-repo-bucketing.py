"""Injection-based falsification of verification-reality.py's per-session repo labelling.

    python3 verify-repo-bucketing.py --checkout <a gnomon checkout>

Every case carries a control: something that MUST come out a specific way, so an
unexpected number means something. Black-box on purpose: this writes synthetic
transcript files and runs `verification-reality.py` itself as a subprocess, reading its
printed table, rather than importing an internal function. The bugs this exists to catch
were never in one function -- one lived in `repo_of`, the other in the loop that decides
WHICH cwd wins for a session -- and a script that only unit-tests `repo_of` would have
missed the second one entirely. This checks the same observable output a real audit reads.

This does not verify anything about gnomon's scoring. It has no `# miraudit-covers:` tag
and is not claiming an axis; it verifies OUR OWN diagnostic tooling and is wired into
run-checks.py's ALWAYS list instead, next to fingerprint.py and axis-terms.py.
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
SCRIPT = os.path.join(HERE, "verification-reality.py")

# Timestamps inside the window this run was given, matching verify-fanout-fix.py's approach:
# a fixture with its own fixed dates that ignores --since/--until would announce it honoured
# the window and not.
IN = WINDOW.start.strftime("%Y-%m-%dT%H:%M:%S.000Z")

# A directory name that cannot be mistaken for anyone's real project, nested under the REAL
# $HOME because verification-reality.py computes HOME from os.path.expanduser("~") itself and
# cannot be told to use a fake one. Nothing under here needs to exist on disk as a project --
# only the transcript's `cwd` field needs to read as this path.
FIXTURE_ROOT = f"{HOME}/.mfx"


def event(sid, i, cwd, tool, file_path=None, ts=IN):
    inp = {"command": "ls"} if tool == "Bash" else {"file_path": file_path}
    return {"type": "assistant", "sessionId": sid, "session_id": sid, "timestamp": ts,
            "isSidechain": False, "cwd": cwd, "uuid": f"u{sid}{i}",
            "message": {"role": "assistant", "model": "claude-opus-5",
                        "content": [{"type": "tool_use", "id": f"t{sid}{i}",
                                     "name": tool, "input": inp}]}}


def write_transcript(root, sid, events):
    path = os.path.join(root, "projects", f"-fixture-{sid}", f"{sid}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def run_table(corpus_root):
    """Invoke the real script and return {label: sessions} parsed from its printed table.

    Fixed-width slicing, because a repository label can contain spaces and a looser split
    would be fooled by one. But the width is DERIVED from the header row rather than written
    down: it used to hardcode 28, matching `f"{r[:27]:<28}{n:>6}"` in the source, and the day
    that column was widened -- to make rows under a shared parent directory distinguishable,
    which SKILL.md asks a reader to do -- all six cases went red at once against a script that
    was working correctly. A copy of another file's format string is a second declaration of
    it, and this is the file whose whole job is to catch two declarations drifting.
    """
    p = subprocess.run(
        [sys.executable, SCRIPT, "--checkout", args.checkout, "--corpus", corpus_root,
         "--since", WINDOW.start.date().isoformat(), "--until", WINDOW.end.date().isoformat()],
        capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        sys.exit(f"verification-reality.py exited {p.returncode} against the fixture:\n"
                 f"{p.stdout}\n{p.stderr}")
    rows = {}
    in_table = False
    edge = None
    for line in p.stdout.splitlines():
        if line.startswith("repository"):
            in_table = True
            # The `sess` column is right-aligned in six characters, so where its header ends
            # is where its field ends, and the label field is everything before that field.
            edge = line.index("sess") + len("sess")
            continue
        if not in_table or line.startswith("-") or line.startswith("TOTAL"):
            continue
        label, sess = line[:edge - 6].strip(), line[edge - 6:edge].strip()
        if label and sess.isdigit():
            rows[label] = int(sess)
    return rows


FAILED = []


def check(label, table, key, expect):
    """Exact match. A fragmentation bug that scatters one repo's sessions across several
    rows sharing a prefix would still sum correctly under startswith(), which is precisely
    the false pass this exists to avoid: it wrongly cleared this test's own case 2 the first
    time (single-repo, three subdirectories) before check_unfragmented was split out below.
    """
    got = table.get(key, 0)
    good = got == expect
    if not good:
        FAILED.append(label)
    print(f"  [{'ok' if good else '??'}] {label:<58} expected {expect:<3} got {got}")


def check_unfragmented(label, table, prefix, expect_sessions):
    """The property `check` cannot express: not just N sessions somewhere under this
    prefix, but N sessions in exactly ONE row. Two rows of 1 and 2 sum to the same total
    as one row of 3, and only this distinguishes them.
    """
    matches = {k: n for k, n in table.items() if k.startswith(prefix)}
    total = sum(matches.values())
    good = len(matches) == 1 and total == expect_sessions
    if not good:
        FAILED.append(label)
    print(f"  [{'ok' if good else '??'}] {label:<58} expected 1 row of {expect_sessions:<3} "
          f"got {len(matches)} row(s) totalling {total}  {sorted(matches) if not good else ''}")


print(header(args, WINDOW))

with tempfile.TemporaryDirectory(prefix="miraudit-selftest-") as tmp:
    # 1. Two DIFFERENT single-repo cwds that share a two-segment parent must stay two rows.
    #    The bug this guards: truncating to a fixed depth fused them into one.
    write_transcript(tmp, "1a1a1a1a-0000-4000-8000-000000000001",
                      [event("1a1a1a1a-0000-4000-8000-000000000001", 0,
                             f"{FIXTURE_ROOT}/parent/repo-a", "Write",
                             f"{FIXTURE_ROOT}/parent/repo-a/src/x.py")])
    write_transcript(tmp, "1a1a1a1a-0000-4000-8000-000000000002",
                      [event("1a1a1a1a-0000-4000-8000-000000000002", 0,
                             f"{FIXTURE_ROOT}/parent/repo-b", "Write",
                             f"{FIXTURE_ROOT}/parent/repo-b/src/y.py")])

    # 2. Three sessions, ONE cwd, each editing a different subdirectory. Must stay one row.
    #    The bug this guards: splitting wherever an edited file's path diverges fragmented a
    #    single repo by its own internal directory structure (app/, components/, lib/).
    for i, sub in enumerate(("app", "components", "lib")):
        sid = f"2b2b2b2b-0000-4000-8000-00000000000{i}"
        write_transcript(tmp, sid,
                          [event(sid, 0, f"{FIXTURE_ROOT}/single-repo", "Write",
                                 f"{FIXTURE_ROOT}/single-repo/{sub}/f.py")])

    # 3. One session, cwd is a real project, but most of its edits land under a path shaped
    #    like agent config. Must attribute to the project, not swallow into agent config.
    #    The bug this guards: labelling by the MOST-EDITED file's path instead of the
    #    session's own cwd sent real project sessions to `agent config` whenever a side
    #    activity (syncing a skill, writing memory) outweighed the project work by count.
    sid = "3c3c3c3c-0000-4000-8000-000000000001"
    ev3 = [event(sid, 0, f"{FIXTURE_ROOT}/heavy-project", "Write",
                 f"{FIXTURE_ROOT}/heavy-project/src/main.py")]
    ev3 += [event(sid, i, f"{FIXTURE_ROOT}/heavy-project", "Write",
                  f"{HOME}/.claude/skills/some-skill/f{i}.py") for i in range(1, 20)]
    write_transcript(tmp, sid, ev3)

    # 4. cwd changes mid-session (a brief excursion into a scratchpad); the FIRST cwd wins.
    sid = "4d4d4d4d-0000-4000-8000-000000000001"
    write_transcript(tmp, sid, [
        event(sid, 0, f"{FIXTURE_ROOT}/stable-project", "Write",
              f"{FIXTURE_ROOT}/stable-project/a.py"),
        event(sid, 1, "/tmp/some-scratchpad", "Write", "/tmp/some-scratchpad/b.py"),
    ])

    # CONTROL: a session that really is agent config, with no other project touched at all,
    # must still read as agent config -- proves the special case was not disabled to fix 3.
    sid = "5e5e5e5e-0000-4000-8000-000000000001"
    write_transcript(tmp, sid, [event(sid, 0, f"{HOME}/.claude", "Write",
                                       f"{HOME}/.claude/skills/some-skill/g.py")])

    table = run_table(tmp)

check("1. two repos sharing a parent stay distinct rows", table,
      ".mfx/parent/repo-a", 1)
check("1. (sibling)", table, ".mfx/parent/repo-b", 1)
check_unfragmented("2. one repo, three subdirectories, stays ONE row", table,
                   ".mfx/single-repo", 3)
check("3. most edits elsewhere still attributes to the project cwd", table,
      ".mfx/heavy-project", 1)
check("3. CONTROL: none of it leaks into agent config", table, "agent config", 1)
check("4. cwd captured at first sight, not last", table,
      ".mfx/stable-project", 1)

if FAILED:
    print(f"\n  {len(FAILED)} case(s) did not behave as written; the first is {FAILED[0]!r}.")
    print("  verification-reality.py's per-repo table is not safe to read right now.")
    raise SystemExit(1)
