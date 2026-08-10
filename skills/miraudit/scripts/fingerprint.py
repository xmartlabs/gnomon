"""Corpus fingerprint. Print this before any other number.

Counts compared across machines mean nothing without it: the one substantive disagreement
with a tool's authors turned out to be the two sides measuring different corpora.

Absorbed from an earlier script that carried nine hardcoded `[audit: N]` values from one
person's run and parsed its own argv, so it accepted neither --checkout nor --until. The
comparison half is gone; if you need to compare against a published run, read that run's
stats.json rather than pasting its numbers here.
"""
import collections
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats, dig, find_all  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])

files = glob.glob(os.path.join(args.corpus, "**", "*.jsonl"), recursive=True)

lines = tool_calls = sidechain = 0
tools = collections.Counter()
sources = collections.Counter()
sessions = set()

for path in files:
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        continue
    with fh:
        for line in fh:
            lines += 1
            if '"tool_use"' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            timestamp = event.get("timestamp")
            if not timestamp:
                continue
            try:
                when = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                continue
            if when not in WINDOW:
                continue
            content = (event.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_calls += 1
                tools[block.get("name")] += 1
                if event.get("isSidechain"):
                    sidechain += 1
                if event.get("sessionId"):
                    sessions.add(event["sessionId"])
                if event.get("source"):
                    sources[event["source"]] += 1

print(header(args, WINDOW))
print("=" * 62)
print("CORPUS FINGERPRINT  (must match to compare figures across machines)")
print("=" * 62)
print(f"  .jsonl files          {len(files):,}")
print(f"  total lines           {lines:,}")
print(f"  tool calls in window  {tool_calls:,}")
print(f"  sessions in window    {len(sessions):,}")
print(f"  sidechain share       {100 * sidechain / max(tool_calls, 1):.1f}%")
if sources:
    print(f"  sources               {', '.join(sorted(sources))}")

print("\n  top 15 tools in window")
for name, count in tools.most_common(15):
    print(f"    {count:>7,}  {name}")

# These counts are NOT the tool's. This walks every .jsonl under the corpus root; the tool
# applies its own eligibility, source handling and session rules, and lands somewhere else.
# A cold run hit the gap with nothing to tell it which number to quote, so print both.
stats = load_stats(args.stats)
if stats:
    # Both names are ambiguous here: `total_sessions` appears per source and per month,
    # `tool_calls` per month as well as in the axis signals. Searching by name returned one
    # month's count and printed it as the window's, so each needs saying which it means.
    theirs_sessions = dig(stats, "volume", "total_sessions")

    # The window total is what the axes are scored on, so take it from the signals blocks
    # rather than an axis index -- reordering the axes must not silently change the number.
    # Every signals block should agree; if they ever stop agreeing, say so instead of picking.
    in_signals = {value for path, value in find_all(stats, "tool_calls")
                  if "/signals/" in path and isinstance(value, int)}
    theirs_calls = in_signals.pop() if len(in_signals) == 1 else (
        f"disagree: {sorted(in_signals)}" if in_signals else None)
    print()
    print("=" * 62)
    print("THEIRS vs OURS  (they will differ; that is expected)")
    print("=" * 62)
    print(f"  {'':<22}{'theirs':>12}{'ours':>12}")
    print(f"  {'sessions':<22}{str(theirs_sessions):>12}{len(sessions):>12,}")
    print(f"  {'tool calls in window':<22}{str(theirs_calls):>12}{tool_calls:>12,}")
    print("""
  Which to quote:
    - Comparing THIS corpus against another machine's: quote OURS. Both sides run this
      script, so both sides count the same way.
    - Comparing against a number the tool published: quote THEIRS, from stats.json.
    - Never mix them in one claim. That is the invented-denominator mistake with extra
      steps: two populations, one ratio.""")
else:
    print("\n  (pass --stats to print the tool's own counts beside these)")
