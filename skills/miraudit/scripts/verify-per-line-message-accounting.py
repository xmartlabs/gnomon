#!/usr/bin/env python3
"""Does the per-event loop count one assistant message once, or once per content block?

One assistant message is written as SEVERAL JSONL lines -- one per content block -- and each
line repeats the same `usage` object. Measured over 400 files of a real corpus: of 13,432
assistant messages, 9,632 span two or more lines (up to 29).

The corpus carries its own control. Across those multi-line messages:

    input_tokens                 differs between lines in     0 cases
    cache_read_input_tokens      differs between lines in     0 cases
    cache_creation_input_tokens  differs between lines in     0 cases
    output_tokens                differs between lines in 2,171 cases

So three of the four are per-MESSAGE constants and one is per-BLOCK. Summing all four per
line is right for exactly one of them.

This check pins what the accumulator does rather than asserting what it should do -- the
same convention verify-compounding-symmetry.py uses for the add_memory asymmetry. It goes
red when the behaviour CHANGES, which is the event worth being told about.

Three counters sit on that path (accumulator.py:1050-1079) and all three take the block
count as a multiplier:

    assistant_turns   published in volume, scored by nothing
    model_counter     -> stack.models -> offload_share -> model_mix, an AQ axis (weight 50)
    token_usage       -> model_usage[].tokens_*, published, scored by nothing

So this is NOT only about tokens: `model_counter` reaches a score, and not uniformly -- on
the corpus this was written against the default model averaged 1.97 blocks per message and
the others 2.05-2.45, so the ratio drifts toward reporting more offloading than happened.

`token_usage` itself feeds no axis: aq.py builds Token economy from cli_share, not from here.
"""
import os
import sys

sys.path.insert(0, os.environ.get("MIRAUDIT_SCRIPTS", os.path.dirname(os.path.abspath(__file__))))
from _common import parse, header  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0], needs_corpus=False)

from gnomon.cli.accumulator import Accumulator  # noqa: E402

SINCE, UNTIL = WINDOW.start, WINDOW.end
TS = (SINCE + (UNTIL - SINCE) / 2).strftime("%Y-%m-%dT%H:%M:%S.000Z")
MODEL = "claude-opus-5"
USAGE = {"input_tokens": 10, "output_tokens": 100,
         "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 500}


def line(mid, block, uid):
    """One JSONL line: one content block, carrying the WHOLE message's usage.

    This is the shape the harness actually writes, not an invention -- the fixture that
    matters is the one shaped like the real transcript, and a single-line fixture cannot
    see this defect at all.
    """
    return {"type": "assistant", "sessionId": "s1", "timestamp": TS, "isSidechain": False,
            "cwd": "/repo", "uuid": uid,
            "message": {"id": mid, "role": "assistant", "model": MODEL,
                        "content": [block], "usage": dict(USAGE)}}


def totals(events):
    a = Accumulator()
    a.begin_file("claude", "/U/.claude/projects/-p/s1.jsonl")
    for e in events:
        a.observe(e, SINCE, UNTIL)
    return dict(a.model_tokens[MODEL])


def counters(events):
    """The other two counters on the same path, from the same fixture.

    model_counter is the one that reaches a score: stack.models -> offload_share ->
    model_mix. A check that looked only at token_usage would report a payload defect and
    miss the axis entirely.
    """
    a = Accumulator()
    a.begin_file("claude", "/U/.claude/projects/-p/s1.jsonl")
    for e in events:
        a.observe(e, SINCE, UNTIL)
    return {"model_counter": a.model_counter[MODEL], "assistant_turns": a.assistant_turns}


TEXT = {"type": "text", "text": "thinking out loud"}
TOOL = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "true"}}
MORE = {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/a"}}

one_line = [line("msg_A", TOOL, "u0")]
three_lines = [line("msg_B", TEXT, "u1"), line("msg_B", TOOL, "u2"),
               line("msg_B", MORE, "u3")]

print(header(args, WINDOW))
print("ONE assistant message, written as N lines, each repeating the same `usage`.")
print(f"Per-message truth: input={USAGE['input_tokens']}, "
      f"cache_read={USAGE['cache_read_input_tokens']}, "
      f"cache_creation={USAGE['cache_creation_input_tokens']}; "
      f"per-block: output={USAGE['output_tokens']}\n")

single, spread = totals(one_line), totals(three_lines)
FIELDS = (("input", "input_tokens", 1), ("cache_read", "cache_read_input_tokens", 1),
          ("cache_creation", "cache_creation_input_tokens", 1),
          ("output", "output_tokens", 3))

# PINNED is what the accumulator does TODAY; IMPLIED is what the transcript format says the
# number means. They disagree for three of the four, and that disagreement IS the finding.
#
# The check asserts against PINNED, not against IMPLIED, following the same convention
# verify-compounding-symmetry.py uses for the add_memory asymmetry: a check that fails on a
# known, reported gap turns every run red and stops carrying information. Red here means the
# tool MOVED -- which is the event worth being told about, whether it moved toward the format
# or further away.
BLOCKS = 3
PINNED = {label: USAGE[key] * BLOCKS for label, key, _ in FIELDS}
IMPLIED = {label: USAGE[key] * (BLOCKS if per_block == BLOCKS else 1)
           for label, key, per_block in FIELDS}

print(f"{'field':<18}{'1 line':>9}{'3 lines':>10}{'pinned':>9}{'implied':>9}{'factor':>9}")
print("-" * 66)
FAILED = []
for label, key, per_block in FIELDS:
    got1, got3 = single.get(label, 0), spread.get(label, 0)
    ok = (got1 == USAGE[key]) and (got3 == PINNED[label])
    if not ok:
        FAILED.append(f"{label}: 1 line gave {got1} (pinned {USAGE[key]}), "
                      f"3 lines gave {got3} (pinned {PINNED[label]})")
    drift = "" if PINNED[label] == IMPLIED[label] else "  <- inflated"
    print(f"{label:<18}{got1:>9}{got3:>10}{PINNED[label]:>9}{IMPLIED[label]:>9}"
          f"{got3 / max(1, USAGE[key]):>8.1f}x  {'[ok]' if ok else '[??]'}{drift}")

# The two counters that are not tokens. model_counter is the one with a score behind it.
c1, c3 = counters(one_line), counters(three_lines)
print(f"\n{'counter':<18}{'1 line':>9}{'3 lines':>10}{'pinned':>9}{'implied':>9}   reaches")
print("-" * 78)
for label, reaches in (("model_counter", "stack.models -> model_mix (an AQ axis)"),
                       ("assistant_turns", "volume, scored by nothing")):
    got1, got3 = c1[label], c3[label]
    ok = (got1 == 1) and (got3 == BLOCKS)
    if not ok:
        FAILED.append(f"{label}: 1 line gave {got1}, 3 lines gave {got3} "
                      f"(pinned 1 and {BLOCKS})")
    print(f"{label:<18}{got1:>9}{got3:>10}{BLOCKS:>9}{1:>9}   {reaches}  "
          f"{'[ok]' if ok else '[??]'}")
print("\n  model_counter is why this is not only a payload defect: stack.models feeds")
print("  offload_share = 1 - top/total, so a per-model difference in blocks-per-message")
print("  moves that ratio. Whether it moves the SCORE depends on saturation -- sat() clamps")
print("  at OFFLOAD_SHARE_TARGET, so a corpus already above it absorbs the whole bias and a")
print("  corpus below it does not.")

# CONTROL. The single-line case must be right whatever happens to the multi-line one: if it
# were also wrong, the comparison above would be measuring something else entirely.
print("\n  CONTROL: the one-line message must be exact for every field")
for label, key, _ in FIELDS:
    got, want = single.get(label, 0), USAGE[key]
    if got != want:
        FAILED.append(f"CONTROL {label}: one line gave {got}, want {want}")
    print(f"    {label:<16}{got:>8}  want {want:<8}{'[ok]' if got == want else '[??]'}")

infl = [l for l, _k, _b in FIELDS if PINNED[l] != IMPLIED[l]]
print()
if infl:
    print(f"  INFLATED by the block count: {', '.join(infl)}.")
    print("  These are published to a person by profiles.model_usage_from_models "
          "(tokens_input,\n  tokens_cache_read, tokens_cache_creation). They do NOT feed the "
          "AQ: aq.py builds\n  Token economy from cli_share, so no score moves.")
else:
    print("  No per-message field moved with the block count.")

print("\n  NOT CHECKED: the size-weighted factor over a real corpus. The 3x here is this")
print("  fixture's block count, not a measurement of anybody's month.")

# ---- two credit policies inside one number ------------------------------------------------
# The section above is about ONE message written as several lines. This one is about counters
# where the same accumulator applies two different rules and publishes one figure. That is
# harder to see than the line-splitting, because there is no second number to compare against:
# the counter is internally inconsistent and looks fine from outside.
#
# Finding #4 in this investigation is one instance of it, already accepted upstream. These are
# the same shape found by looking for the shape rather than by stumbling on it.


def fresh():
    a = Accumulator()
    a.begin_file("claude", "/U/.claude/projects/-p/s1.jsonl")
    return a


def result_event(tuid, uid):
    """A tool_result carrying an error, repeated verbatim -- which real transcripts do."""
    return {"type": "user", "sessionId": "s1", "timestamp": TS, "cwd": "/repo", "uuid": uid,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tuid, "is_error": True,
                 "content": "boom"}]}}


print("\n\nTWO CREDIT POLICIES INSIDE ONE COUNTER")
print("-" * 78)

# 1. tool_errors vs the map three lines above it, in the SAME `if` block.
a = fresh()
for i, e in enumerate([result_event("t9", "e1"), result_event("t9", "e2")]):
    a.observe(e, SINCE, UNTIL)
sticky = sum(1 for v in a._tool_result_is_error.values() if v is True)
print(f"  one tool_use_id, two identical error results")
print(f"    tool_errors                 {a.tool_errors:>3}   counted per occurrence")
print(f"    _tool_result_is_error map   {sticky:>3}   deduped on (src, session, tool_use_id)")
if not (a.tool_errors == 2 and sticky == 1):
    FAILED.append(f"tool_errors asymmetry moved: tool_errors={a.tool_errors}, map={sticky}")
print("    Both are set inside one `if b.get(\"is_error\")` block, and the map's own comment")
print("    says the dedup is deliberate. tool_errors feeds error_rate_per_100_tools and")
print("    Recovery's denominator; the map feeds the ordered facts. A repeated result moves")
print("    one and not the other.")

# CONTROL: distinct ids must move both, or the comparison above is about nothing.
a = fresh()
for tuid, uid in (("t1", "c1"), ("t2", "c2")):
    a.observe(result_event(tuid, uid), SINCE, UNTIL)
sticky2 = sum(1 for v in a._tool_result_is_error.values() if v is True)
print(f"\n  CONTROL: two DISTINCT tool_use_ids -> tool_errors {a.tool_errors}, map {sticky2}")
if not (a.tool_errors == 2 and sticky2 == 2):
    FAILED.append(f"CONTROL distinct ids: tool_errors={a.tool_errors}, map={sticky2}")

# 2. api_errors: two independent `if`s, not `elif`.
a = fresh()
a.observe({"type": "system", "sessionId": "s1", "timestamp": TS, "uuid": "a1",
           "isApiErrorMessage": True, "retryAttempt": 1}, SINCE, UNTIL)
both = a.api_errors
a = fresh()
a.observe({"type": "system", "sessionId": "s1", "timestamp": TS, "uuid": "a2",
           "isApiErrorMessage": True}, SINCE, UNTIL)
one = a.api_errors
print(f"\n  one system event carrying BOTH markers   api_errors {both:>3}")
print(f"  CONTROL: the same event with one marker  api_errors {one:>3}")
if not (both == 2 and one == 1):
    FAILED.append(f"api_errors double-count moved: both={both}, one={one}")
print("    The two branches are `if`, not `elif`, so an event that is an API error AND a")
print("    retry counts twice. It feeds Recovery's 0.15 penalty term through")
print("    api_errors_retries per 100 tools.")

if FAILED:
    print(f"\n  {len(FAILED)} case(s) did not behave as pinned; the first is {FAILED[0]!r}.")
    print("  The tool MOVED. Read the accumulator's usage branch and decide which direction:")
    print("  toward `implied` means the gap was fixed and this table should be re-pinned;")
    print("  away from it means it got worse. Do not edit the numbers before reading it.")
    raise SystemExit(1)
# miraudit-covers: Model mix
