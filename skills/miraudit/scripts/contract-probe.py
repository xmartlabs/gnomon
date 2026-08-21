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
 classify_mcp_subcategory, _is_compounding_path, parse_workflow_agent_dispatch,
 extract_skill_name_from_path, is_plan_file_target, is_substantive_tool,
 bash_writes_file, bash_runs_knowledge, classify_tool) = require(
    [("gnomon.taxonomy", "classify_change_target"),
     ("gnomon.taxonomy", "bash_runs_tests"),
     ("gnomon.taxonomy", "WRITE_TOOLS"),
     ("gnomon.taxonomy", "is_mcp_knowledge_write"),
     ("gnomon.taxonomy", "classify_mcp_subcategory"),
     ("gnomon.taxonomy", "_is_compounding_path"),
     ("gnomon.taxonomy", "parse_workflow_agent_dispatch"),
     ("gnomon.taxonomy", "extract_skill_name_from_path"),
     ("gnomon.taxonomy", "is_plan_file_target"),
     ("gnomon.taxonomy", "is_substantive_tool"),
     ("gnomon.taxonomy", "bash_writes_file"),
     ("gnomon.taxonomy", "bash_runs_knowledge"),
     ("gnomon.taxonomy", "classify_tool")],
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

    # Six predicates that reached a score with nothing probing them. They were invisible for
    # the reason everything else in this skill was invisible: the summary counted its own
    # cases, so 18/18 read as complete coverage of a set nobody had compared against the
    # module. Each gets its positive and its control, because a predicate that answers True
    # to everything passes a one-sided probe.
    ("a skills/<name>/SKILL.md path yields the skill name",
     lambda: extract_skill_name_from_path("/x/.claude/skills/miraudit/SKILL.md"), "miraudit",
     "Skill fluency: skills_distinct and skills_total are built on this extraction"),
    ("an ordinary markdown path yields nothing",
     lambda: extract_skill_name_from_path("/x/docs/README.md"), None,
     "the same axis: if this stopped returning None every doc read would credit a skill"),

    ("a file inside plans/ is a plan artifact",
     lambda: is_plan_file_target("/x/docs/team/plans/3-migrate.md"), True,
     "Discipline: cross-session plan credit (C3/C4) keys on this"),
    ("an ordinary source file is not",
     lambda: is_plan_file_target("/x/src/plans.ts"), False,
     "the same axis: the control that separates a plans/ DIRECTORY from a filename"),

    ("a tool that does project work is substantive",
     lambda: is_substantive_tool("Edit"), True,
     "every denominator built on substantive calls, including orchestratable sessions"),
    ("a status poll is not",
     lambda: is_substantive_tool("mcp__x__get_status"), False,
     "the same denominators: this is the branch that keeps polling out of the numerator"),

    ("a redirect writes a file",
     lambda: bash_writes_file("echo hi > /x/out.txt"), True,
     "Compounding and the writes counters, whenever a write happens through the shell"),
    ("a redirect to /dev/null does not",
     lambda: bash_writes_file("noisy_thing > /dev/null"), False,
     "the same counters: the exclusion that stops every silenced command counting as a write"),

    ("a knowledge command is knowledge",
     lambda: bash_runs_knowledge("gh issue view 86"), True,
     "Context Intelligence: the `knowledge` fact that arms a grounded session"),
    ("an ordinary command is not",
     lambda: bash_runs_knowledge("mkdir -p build"), False,
     "the same axis: without this control every session is grounded"),

    ("a write tool classifies as produce",
     lambda: classify_tool("Write"), "produce",
     "every category count: cat_counter drives Grounding's doing half"),
    ("a read tool does not",
     lambda: classify_tool("Read") == "produce", False,
     "the same counter: the control that keeps reading out of the producing bucket"),
]

# ---- what the module actually exposes ----------------------------------------------------
# The denominator is the predicates that EXIST, derived by introspection, not the cases
# written above. It counted its own cases and printed `18/18`, which reads as complete
# coverage of a set nobody had ever compared against -- the same self-referential denominator
# that let the gate compare the pin against the pin and let axis-coverage report 11/11 while
# a 50-point axis had no check.
#
# Which case probes which predicate is read out of the SOURCE of the CASES list, so adding a
# case counts automatically and deleting one stops counting. It cannot see a predicate reached
# indirectly through another, and it would miscount a name that appears only in a comment in
# there; both are stated rather than assumed.
import inspect  # noqa: E402
from gnomon import taxonomy as _tax  # noqa: E402

_public = sorted(n for n, f in inspect.getmembers(_tax, inspect.isfunction)
                 if not n.startswith("_") and getattr(f, "__module__", "") == _tax.__name__)
_cases_src = inspect.getsource(sys.modules[__name__])
_cases_src = _cases_src[_cases_src.index("CASES = ["):_cases_src.index("# ---- what the module")]
_probed = [n for n in _public if n in _cases_src]
_unprobed = [n for n in _public if n not in _probed]

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
print(f"  {len(_probed)}/{len(_public)} public predicates in gnomon.taxonomy have a case.")
if _unprobed:
    print("  NO CASE AT ALL: " + ", ".join(_unprobed))
    print("  Each of those can change behaviour under a check that imports it and nothing")
    print("  here will say so. This count is derived from the module, not from the list")
    print("  above, which is why it can be short of it.")
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
