"""Derives run_cost.agent from a subagent's own transcript, so nobody hand-copies it.

    python3 agent-cost.py <subagent-transcript.jsonl> [--emit <path>]

The payload schema has a slot for what dispatching miraudit as a subagent cost --
`run_cost.agent` -- and the only source for it, before this script existed, was the
completion notification's `<usage>` block: an orchestrator would have had to read
`<subagent_tokens>...</subagent_tokens><tool_uses>...</tool_uses><duration_ms>...</duration_ms>`
off an ephemeral notification and retype the numbers by hand. That notification is not
saved anywhere; miss it and the figures are gone. The same numbers are durably on disk the
whole time, in the subagent's own transcript file, and cross-checking against it is what
caught the one number in that block worth distrusting.

`subagent_tokens` in the harness notification is NOT a sum of tokens used across the run --
it is close to the LAST message's input+output+cache_read+cache_creation total, i.e. a
final-context snapshot. Checked against two real cold runs: the harness reported
130010/160998 while the real cumulative `output_tokens` summed to 28558/47410 and
`cache_read_input_tokens` alone summed past seven and twelve million. Reporting
`subagent_tokens` as "tokens used" would be exactly the kind of mislabeled metric this skill
exists to catch in OTHER tools, so this script never emits a field by that name. It emits
`context_peak` instead, named for what it actually is, and `output_tokens_total`, the real
cumulative sum `subagent_tokens` is often mistaken for.

`tool_uses` and `duration_ms` are the trustworthy numbers here: a straight count of
`tool_use` content blocks and a delta between two timestamps already in the transcript,
both near-deterministic reconstructions of what the harness notification already claims (and
both independently reproduced this file's own `tool_uses`/`duration_ms` against two real
runs, matching exactly and within tens of milliseconds respectively). `output_tokens_total`
and `context_peak` are read the same way but are noisier and model/turn-shape dependent --
informational, not for cross-run comparison. See references/output-schema.md for the field
split and the reasoning behind it.

OFFLINE tier: reads exactly the transcript path it is given, imports nothing from
`gnomon.*`, and never walks `~/.claude/projects` on its own -- that walk is the caller's
job, because a script running inside the corpus-walk pipeline has no access to its own
dispatch transcript anyway. Nothing in scripts/'s own pipeline (new-run.py, render-report.py,
anchor.py) calls this: `run_cost.agent` is filled by whatever DISPATCHES miraudit, never by
anything inside the audit it dispatches.

Exit codes: 0 computed (even over an empty or fully malformed file, which reports zeros
and every line skipped), 2 the file could not be opened at all.
"""
import argparse
import datetime
import json
import os
import sys


def _parse_ts(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def measure(path):
    """Return (result_dict, skipped_line_count) for one transcript file.

    Every failure mode here is "skip the line and keep going", never "crash the script" --
    a subagent transcript is written by a live harness process and a partial last line from
    a process that was still writing when read is a normal shape, not a corrupt file.
    """
    first_ts = last_ts = None
    tool_uses = 0
    output_tokens_total = 0
    last_usage = None
    skipped = 0
    lines_seen = 0

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            lines_seen += 1
            try:
                event = json.loads(line)
            except ValueError:
                skipped += 1
                continue
            if not isinstance(event, dict):
                skipped += 1
                continue

            ts = event.get("timestamp")
            if ts:
                try:
                    _parse_ts(ts)
                except ValueError:
                    ts = None
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

            if event.get("type") != "assistant":
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue

            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_uses += 1

            usage = message.get("usage")
            if isinstance(usage, dict):
                output_tokens_total += usage.get("output_tokens") or 0
                # Last one wins by construction: file order is transcript order, so the
                # last assistant message with a usage block IS the run's final turn.
                last_usage = usage

    duration_ms = None
    if first_ts and last_ts:
        duration_ms = round((_parse_ts(last_ts) - _parse_ts(first_ts)).total_seconds() * 1000)

    context_peak = None
    if last_usage:
        context_peak = sum(last_usage.get(k) or 0 for k in (
            "input_tokens", "output_tokens",
            "cache_read_input_tokens", "cache_creation_input_tokens"))

    result = {
        "tool_uses": tool_uses,
        "duration_ms": duration_ms,
        "output_tokens_total": output_tokens_total if last_usage else None,
        "context_peak": context_peak,
    }
    return result, skipped, lines_seen


def main(argv=None):
    p = argparse.ArgumentParser(prog="agent-cost", description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("transcript", help="a subagent's own .jsonl transcript file")
    p.add_argument("--emit", metavar="PATH", default=None,
                   help="write the result as run_cost.agent-shaped JSON")
    args = p.parse_args(argv)

    path = os.path.expanduser(args.transcript)
    try:
        result, skipped, lines_seen = measure(path)
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}")
        return 2

    print(f"agent-cost: {path}")
    print(f"  lines read       {lines_seen:,} ({skipped} skipped: malformed or non-object)")
    print(f"  tool_uses        {result['tool_uses']}")
    print(f"  duration_ms      {result['duration_ms']}")
    print(f"  output_tokens_total  {result['output_tokens_total']}"
          "   (real cumulative cost -- unlike the harness notification's subagent_tokens)")
    print(f"  context_peak     {result['context_peak']}"
          "   (last turn's snapshot, not a sum -- informational only)")

    if args.emit:
        with open(os.path.expanduser(args.emit), "w") as fh:
            json.dump(result, fh, indent=2)
            fh.write("\n")
        print(f"\n  wrote {args.emit}: paste straight into payload.run_cost.agent")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
