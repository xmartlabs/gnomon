"""Tool command and Token economy: both are built from the same CLI/MCP scan.

    python3 cli-mcp.py --checkout <copy> --since --until --stats <stats.json>

# miraudit-covers: Tool command (MCP + CLI)
# miraudit-covers: Token economy

Graduated from adhoc-cli-mcp.py. 78 base points between the two axes and neither had a
check; axis-coverage.py is what made that visible rather than merely true.

Both read the same two counters, so one scan answers both:
  Tool command = wsum(mcp_servers_distinct vs its ceiling, clis_distinct vs its ceiling)
  Token economy = sat(cli_calls / (cli_calls + mcp_calls), an inline target)

`_extract_clis` and `_canon_mcp_server` are public in gnomon.taxonomy and are imported. The
`name.startswith("mcp__")` gate and the `split("__")` server extraction are INLINE in
cli/accumulator.py with no importable helper, so that one step is reproduced here and the
output says so rather than pretending otherwise.

The cli_share target is an unnamed literal (aq.py:589) and cannot be imported. It is
therefore probed rather than trusted: recompute the axis from THEIR published counters and
the literal, and compare against the score they published. The probe also states the range
it is blind to, because sat() is flat above the observed value.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats, require, iter_tool_uses  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
stats = load_stats(args.stats)
if not stats:
    sys.exit("error: --stats is required; this reads an anchored run's payload.")

(_extract_clis, _canon_mcp_server, MCP_CEILING, CLIS_CEILING) = require(
    [("gnomon.taxonomy", "_extract_clis"),
     ("gnomon.taxonomy", "_canon_mcp_server"),
     ("gnomon.scoring.aq", "MCP_SERVERS_DISTINCT_CEILING"),
     ("gnomon.scoring.aq", "CLIS_DISTINCT_CEILING")],
    "The CLI extractor or the ceilings moved; a hand-rolled replacement would make the gap "
    "reported here our own.")

# Not importable: no named constant exists for either (aq.py:589 and :582-584), and the
# 0.30 that PLANNING_PRACTICE_TARGET holds is a DIFFERENT target that happens to share the
# value -- importing it would be right by coincidence and wrong by meaning.
CLI_SHARE_TARGET = 0.70

print(header(args, WINDOW))


def normalize(cmd):
    """accumulator.py normalizes argv-list commands before extracting. That helper is
    private, so this is the one place the scan is not theirs; it is reported below."""
    if isinstance(cmd, list):
        return " ".join(str(c) for c in cmd)
    return cmd or ""


clis = collections.Counter()
mcp_servers = collections.Counter()
mcp_calls = 0
cli_calls = 0
for use in iter_tool_uses(args.corpus, WINDOW):
    if use.name == "Bash":
        for c in _extract_clis(normalize((use.input or {}).get("command"))):
            clis[c] += 1
            cli_calls += 1
    elif use.name.startswith("mcp__"):
        # Inline in accumulator.py:1191-1196, nothing to import.
        parts = use.name.split("__")
        mcp_servers[_canon_mcp_server(parts[1], parts[-1] if len(parts) > 2 else "")] += 1
        mcp_calls += 1

# `tools` at the top level aggregates every source gnomon scored; this scan walks one corpus
# of Claude Code transcripts. On a window where codex also cleared the volume threshold the
# two describe different populations, and comparing them printed `cli_calls theirs 4689 ours
# 4559 -> overestimates` where claude's own published 4361 reverses the sign. The per-source
# block carries the same counters, so the comparable one is available and free.
by_source = stats.get("scoring_inputs_by_source") or {}
scored = sorted(by_source)
t_all = stats.get("tools", {})
t = ((by_source.get("claude") or {}).get("window") or {}).get("tools") or t_all
axes = {a["name"]: a for p in (stats.get("agentic") or {}).get("pillars") or []
        for a in p.get("axes") or []}


def line(label, theirs, ours):
    gap = "faithful" if theirs == ours else (
        "overestimates" if theirs > ours else "underestimates")
    print(f"  {label:24} theirs {theirs:>8}   ours {ours:>8}   {gap}")
    return theirs == ours


print("TOOL COMMAND + TOKEN ECONOMY — re-measured from the corpus")
print(f"  sources gnomon scored     {', '.join(scored) or 'unstated'}")
if scored and scored != ["claude"] and t is not t_all:
    print(f"  comparing against claude's own counters, not the aggregate: the aggregate "
          f"covers\n  {', '.join(s for s in scored if s != 'claude')} too, which this scan "
          f"does not walk. cli_calls {t.get('cli_calls')} against {t_all.get('cli_calls')}.")
ok = []
ok.append(line("mcp_servers_distinct", t.get("mcp_servers_distinct"), len(mcp_servers)))
ok.append(line("clis_distinct", t.get("clis_distinct"), len(clis)))
ok.append(line("cli_calls", t.get("cli_calls"), cli_calls))
ok.append(line("mcp_calls", t.get("mcp_calls"), mcp_calls))

te = axes["Token economy"]
te_max = te.get("base_weight")
share = cli_calls / (cli_calls + mcp_calls) if (cli_calls + mcp_calls) else 0
their_total = (t.get("cli_calls", 0) or 0) + (t.get("mcp_calls", 0) or 0)
their_share = (t.get("cli_calls", 0) or 0) / their_total if their_total else 0
print(f"\n  cli_share ours {share:.4f}   theirs {their_share:.4f}")
print(f"  Token economy scores min(1, cli_share/{CLI_SHARE_TARGET}) -> "
      f"{min(1.0, share / CLI_SHARE_TARGET):.4f}  (axis {te['score']}/{te_max})")

# ---- what the axes actually measure, as opposed to what they are called -------------------
print("\n  WHAT THE TWO NUMBERS ARE MADE OF")
top = clis.most_common(8)
print(f"    {len(clis)} distinct CLIs against a ceiling of {CLIS_CEILING};"
      f" {len(mcp_servers)} MCP servers against {MCP_CEILING}")
print(f"    busiest CLIs: {', '.join(f'{c}x{n}' for c, n in top)}")
print("    cli_calls counts RECOGNISED CLI HEADS PER SHELL PIPELINE, and mcp_calls counts")
print("    tool calls. `git add . && git commit -m x && git push` contributes 3 to the")
print("    numerator without being 3 tool calls; one MCP call contributes 1 to the")
print("    denominator. The ratio is not calls-to-calls.")

# ---- controls -----------------------------------------------------------------------------
chained = _extract_clis("git add . && git commit -m x && git push")
c1 = len(chained) == 3
print(f"\n  CONTROL A  a 3-command chain extracts {chained} -> "
      f"{'3, as the text above claims' if c1 else 'NOT 3 — the claim above is wrong'}")

unknown = _extract_clis("some-tool-nobody-listed --flag")
c2 = len(unknown) == 0
print(f"  CONTROL B  an unlisted binary extracts {unknown} -> "
      f"{'nothing, so Bash work outside KNOWN_CLIS is invisible to both axes' if c2 else 'UNEXPECTED'}")

# CONTROL C is the probe for the one number here that cannot be imported. It runs on THEIR
# counters, not ours, so a divergence in our scan cannot be mistaken for a moved target.
predicted = min(1.0, their_share / CLI_SHARE_TARGET)
c3 = abs(predicted - te["normalized_score"]) < 1e-6
print(f"  CONTROL C  the unnamed {CLI_SHARE_TARGET} target reproduces their own score:"
      f" predicted {predicted:.6f} vs published {te['normalized_score']:.6f}"
      f" -> {'agree' if c3 else 'DISAGREE — the literal moved'}")
if their_share >= CLI_SHARE_TARGET:
    print(f"             BLIND RANGE: sat() is flat above the observed share, so any target")
    print(f"             at or below {their_share:.4f} scores identically here. This probe can")
    print(f"             only catch a target raised above that.")

print("\n  NOT CHECKED")
print("   - argv-list Bash commands: accumulator's normalizer is private and this one is")
print("     a reimplementation, so a divergence there would be ours. The counts above")
print("     agreeing with theirs is the evidence that it did not bite on this corpus.")
print("   - whether the cli_share target is the right one; that is calibration, and the")
print("     literal is inline and unnamed, so it is not even under their fingerprint.")

if not (c1 and c2 and c3):
    raise SystemExit(1)
