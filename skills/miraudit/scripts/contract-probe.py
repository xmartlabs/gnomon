"""Do the tool's predicates still BEHAVE the way this skill's checks assume?

`require()` already asks whether a symbol still exists. Nothing asked whether it still does
the same thing, and that is the gap this probe closes: when the tool tightens a definition
without renaming anything, every check keeps running, keeps printing, and quietly stops
meaning what its labels say.

That is not hypothetical. `tmp-and-recovery.py` reported "sessions that qualify ONLY through
ephemeral scratchpad" long after the tool started excluding scratchpad writes itself. The
section could not have produced a true row, and it never failed -- it was found by reading a
diff by hand, months of runs later. One assertion here would have turned that into a red
line on the first run after the change.

Each case names the check that depends on it, so a failure says who breaks, not just what.

    python3 contract-probe.py --checkout <copy> --since YYYY-MM-DD --until YYYY-MM-DD

Exits non-zero on the first behaviour that moved. Run it before the checks -- anchor.py
does.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, require  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])

(classify_change_target, bash_runs_tests, WRITE_TOOLS, is_mcp_knowledge_write,
 classify_mcp_subcategory, _is_compounding_path, parse_workflow_agent_dispatch) = require(
    [("gnomon.taxonomy", "classify_change_target"),
     ("gnomon.taxonomy", "bash_runs_tests"),
     ("gnomon.taxonomy", "WRITE_TOOLS"),
     ("gnomon.taxonomy", "is_mcp_knowledge_write"),
     ("gnomon.taxonomy", "classify_mcp_subcategory"),
     ("gnomon.taxonomy", "_is_compounding_path"),
     ("gnomon.taxonomy", "parse_workflow_agent_dispatch")],
    "A predicate this skill's checks are built on is gone. Every check that imported it "
    "has to be re-read before anyone quotes its output.")
(strip_injections,) = require(
    [("gnomon.config", "strip_injections")],
    "The prompt-cleaning helper moved; any instruction count built on it is unanchored.")

SCRATCHPAD = "/private/tmp/claude-502/-Users-x-proj/" \
             "abcdef01-2345-4678-9abc-def012345678/scratchpad/a.py"
WF = ("/Users/x/.claude/projects/p/1111/subagents/workflows/wf_abc/agent-a1.jsonl")

# (what it must do, the call, the expected value, which check leans on it)
CASES = [
    ("a harness scratchpad write is not a code change",
     lambda: classify_change_target(SCRATCHPAD), "other",
     "recovery-reality: its scratchpad section was deleted the day this became true"),
    ("a /tmp path that is NOT a scratchpad still is",
     lambda: classify_change_target("/tmp/anything/src/a.ts"), "code",
     "the same section: it had loosened this into `any /tmp` and counted the wrong files"),
    ("tests under __tests__/ are tests",
     lambda: classify_change_target("src/a/__tests__/foo.test.ts"), "test",
     "verification-reality, which used to recognise only <base>.test.<ext>"),
    ("a python test_ prefix is a test",
     lambda: classify_change_target("src/a/test_foo.py"), "test",
     "verification-reality"),
    (".mjs is code",
     lambda: classify_change_target("eslint.config.mjs"), "code",
     "verification-reality, whose own 7-extension list missed it"),
    ("a markdown file is not code",
     lambda: classify_change_target("docs/readme.md"), "doc",
     "every check that filters writes down to code"),

    ("a real test command runs tests",
     lambda: bash_runs_tests("npm test"), True,
     "fidelity-audit, verification-reality"),
    ("a bare cd does not",
     lambda: bash_runs_tests("cd /Users/x/some/long/path/that/exceeds/seventy/characters"),
     False,
     "the `truncated-evidence` scar: a run once reported that it did, from a cut string"),

    ("Edit and Write are writes",
     lambda: {"Edit", "Write"} <= set(WRITE_TOOLS), True,
     "every check that counts writes"),

    ("a memory write credits compounding",
     lambda: is_mcp_knowledge_write("mem0", "add_memory"), True,
     "verify-compounding-symmetry, fidelity-audit"),
    ("a memory read does not",
     lambda: is_mcp_knowledge_write("mem0", "search_memories"), False,
     "verify-compounding-symmetry: this is its control"),
    ("the memory server is knowledge-subcategory",
     lambda: classify_mcp_subcategory("mem0", "add_memory"), "knowledge",
     "fidelity-audit's Compounding section"),

    ("CLAUDE.md is a compounding artifact",
     lambda: _is_compounding_path("/Users/x/repo/CLAUDE.md"), True,
     "fidelity-audit"),
    ("an ordinary source file is not",
     lambda: _is_compounding_path("/Users/x/repo/src/index.ts"), False,
     "fidelity-audit: without this the axis would credit every write"),

    ("a dispatched Workflow transcript resolves to its parent session",
     lambda: parse_workflow_agent_dispatch(WF)[0], "1111",
     "verify-fanout-fix, and finding #1 that upstream merged"),
    ("an ordinary transcript does not",
     lambda: parse_workflow_agent_dispatch("/Users/x/.claude/projects/p/1111.jsonl")[0], None,
     "verify-fanout-fix: this is its no-double-count control"),

    ("a bare slash command cleans to nothing",
     lambda: strip_injections("<command-name>/foo</command-name>"), "",
     "the actions_per_prompt denominator in the ad-hoc example"),
    ("typed text survives cleaning",
     lambda: bool(strip_injections("please fix the invoice job")), True,
     "the same denominator: if this ever returns empty, every prompt count is zero"),
]

print(header(args, WINDOW))
print("=" * 92)
print("CONTRACT PROBE — behaviour, not names. `require` asks if a symbol exists; this asks")
print("whether it still does the same thing, which is the failure nothing else catches.")
print("=" * 92)

failed = []
for what, call, expected, who in CASES:
    try:
        got = call()
    except Exception as exc:                                    # noqa: BLE001
        got = f"raised {type(exc).__name__}"
    good = got == expected
    if not good:
        failed.append((what, expected, got, who))
    print(f"  [{'ok' if good else 'MOVED'}] {what:<52} -> {str(got)[:18]:<18}"
          f"{'' if good else f'expected {expected!r}'}")

print(f"\n  {len(CASES) - len(failed)}/{len(CASES)} behaviours unchanged.")
if failed:
    print("\n  THESE MOVED. Each line names the check built on it; re-read those before")
    print("  quoting any output, and delete the ones whose subject is gone:")
    for what, expected, got, who in failed:
        print(f"    - {what}: expected {expected!r}, got {got!r}")
        print(f"      leans on it: {who}")
    raise SystemExit(1)

print("\n  NOT CHECKED: this probe covers the predicates the checks in scripts/ import, and")
print("  nothing else. An axis whose formula changed without touching any of these still")
print("  passes here -- that is what the contract string in Phase 0 is for. A green probe")
print("  says the ground under the checks did not move, not that the score means the same.")
