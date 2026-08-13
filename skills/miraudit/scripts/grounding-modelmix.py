"""Grounding and Model mix, the two axes whose targets cannot be imported.

    python3 grounding-modelmix.py --checkout <copy> --since --until --stats <stats.json>

# miraudit-covers: Grounding
# miraudit-covers: Model mix

Graduated from adhoc-grounding-modelmix.py.

Grounding is `sat(planning_ratio_explore_to_doing, 1.0)` and nothing else. The ratio's
numerator folds `thinking_blocks` into the explore count at accumulator.py:1510, which the
axis name does not suggest and the payload does not show beside it.

Model mix is hand-rolled arithmetic, not a wsum (aq.py:582-584): three weighted terms when
routing scores, and a two-term fallback when it does not. Its distinct/offload halves come
from per-assistant-turn model ids.

`classify_tool`, `_adjusted_doing`, `_models_for_scoring` and `score_linked_routing` are all
public and imported. `Accumulator._is_planning_dispatch` is a private method, so the
planning-dispatch subtraction is NOT reproduced: the check reports the ratio both with their
published subtraction and without any, and says which is which.

Model mix's two targets and its weights are unnamed literals and cannot be imported, so they
are probed the same way cli-mcp.py probes its own: rebuild the axis from THEIR published
signals and compare against the score they published.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats, require, dig, iter_events, iter_tool_uses  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])
stats = load_stats(args.stats)
if not stats:
    sys.exit("error: --stats is required; this reads an anchored run's payload.")

(classify_tool, _adjusted_doing, _models_for_scoring, score_linked_routing) = require(
    [("gnomon.taxonomy", "classify_tool"),
     ("gnomon.scoring.inputs", "_adjusted_doing"),
     ("gnomon.scoring.aq", "_models_for_scoring"),
     ("gnomon.scoring.aq", "score_linked_routing")],
    "One of the classifiers these two axes are built on is gone.")

# Unnamed literals at aq.py:582-584. PLANNING_PRACTICE_TARGET is also 0.30 and is a
# different target; importing it here would be right by coincidence and wrong by meaning.
DISTINCT_MODELS_TARGET = 3
OFFLOAD_SHARE_TARGET = 0.30
MM_WEIGHTS = (.35, .35, .30)      # and (.5, .5) when routing does not score

print(header(args, WINDOW))

cats = collections.Counter()
for use in iter_tool_uses(args.corpus, WINDOW):
    cats[classify_tool(use.name)] += 1

thinking = 0
models = collections.Counter()
for _p, ev, _w in iter_events(args.corpus, WINDOW):
    msg = ev.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        thinking += sum(1 for b in content
                        if isinstance(b, dict) and b.get("type") == "thinking")
    if ev.get("type") == "assistant" and msg.get("model") and not ev.get("__codex_usage__"):
        models[msg["model"]] += 1

axes = {a["name"]: a for p in (stats.get("agentic") or {}).get("pillars") or []
        for a in p.get("axes") or []}

# ---- Grounding ---------------------------------------------------------------------------
raw_doing = cats["produce"] + cats["execute"] + cats["delegate"]
dispatch = dig(stats, "behavior", "planning_dispatch_actions") or 0
doing = _adjusted_doing(raw_doing, dispatch)
explore = cats["explore"] + thinking
ours = explore / doing if doing else 0
theirs = dig(stats, "behavior", "planning_ratio_explore_to_doing")
g_max = axes["Grounding"].get("base_weight")

print("GROUNDING — sat(planning_ratio, 1.0), and what the numerator is made of")
print(f"  explore tool calls                {cats['explore']:>8}")
print(f"  thinking blocks                   {thinking:>8}   folded into the SAME numerator")
print(f"  numerator                         {explore:>8}")
print(f"  denominator (their subtraction)   {doing:>8}   raw {raw_doing}, dispatch {dispatch}")
print(f"  ratio ours {ours:.3f}   theirs {theirs}   -> "
      f"{'faithful' if abs(ours - theirs) < 0.02 else 'DIVERGES'}")
faithful = abs(ours - theirs) < 0.02
if not faithful:
    if args.stats:
        import json as _json
        diverged_path = os.path.join(
            os.path.dirname(os.path.abspath(args.stats)), "grounding-diverged.json")
        with open(diverged_path, "w") as fp:
            _json.dump({"ours": round(ours, 4), "theirs": theirs,
                        "delta": round(abs(ours - theirs), 4)}, fp)
if not faithful:
    # The split used to print in full right here, while the control that invalidates it
    # fired twenty lines below. A reader met a confident "the axis would score 10.0/25"
    # and learned only afterwards not to read it. A June window exposed that: against the
    # payload's own explore_actions and produce/execute/delegate_actions, this check counted
    # 70 explore actions too many and 126 doing actions too few, and both errors push the
    # ratio up. It agreed on an August window, so that agreement was a property of one
    # window's tool mix and not of the check.
    print(f"\n  THE SPLIT IS WITHHELD. Ours and theirs disagree by {abs(ours - theirs):.3f},")
    print("  over the 0.02 tolerance, so the numerator this check builds is not the one the")
    print("  axis scored and any share taken from it would describe this reimplementation")
    print("  rather than the tool. Compare the counts above against the payload's")
    print("  explore_actions, produce_actions, execute_actions and delegate_actions to see")
    print("  which side drifted. Nothing below this line about Grounding is usable.")
else:
    share = thinking / explore if explore else 0
    print(f"\n  thinking is {share:.1%} of the numerator")
    without = cats["explore"] / doing if doing else 0
    print(f"  drop it and the ratio is {without:.3f}, so the axis scores"
          f" {min(1.0, without) * g_max:.1f}/{g_max} instead of {axes['Grounding']['score']}/{g_max}")
    print("  Direction: FAITHFUL to its formula. The gap is disclosure — the payload publishes")
    print("  the ratio and never the split, and the axis is named for grounding while the")
    print("  numerator is dominated by a block the harness emits.")

# ---- Model mix ---------------------------------------------------------------------------
their_models = _models_for_scoring(stats, (stats.get("stack") or {}).get("models", []))
their_total = sum(n for _, n in their_models)
their_top = max((n for _, n in their_models), default=0)
their_offload = (1 - their_top / their_total) if their_total else 0
our_total = sum(models.values())
our_offload = (1 - max(models.values()) / our_total) if our_total else 0
mm = axes["Model mix"]
sig = mm["signals"]
mm_max = mm.get("base_weight")

print("\nMODEL MIX — distinct models and offload share")
print(f"  distinct models    theirs {len(their_models):>4}   ours {len(models):>4}   "
      f"published {sig['distinct_models']}")
print(f"  offload share      theirs {their_offload:>6.3f} ours {our_offload:>6.3f}   "
      f"published {sig['offload_share']}")
routing = sig.get("routing") or {}
print(f"  routing term state {routing.get('state')!r}, score {routing.get('score')}")


def sat(x, target):
    return min(1.0, x / target) if target else 0.0


# ---- controls ------------------------------------------------------------------------------
c1 = abs(ours - theirs) < 0.02
print(f"\n  CONTROL A  our Grounding ratio reproduces theirs within 0.02 -> "
      f"{'yes' if c1 else 'NO — do not read the split above'}")
c2 = len(models) >= 2 and abs(our_offload - their_offload) < 0.05
print(f"  CONTROL B  our model tally reproduces their offload within 0.05 -> "
      f"{'yes' if c2 else 'NO — the model scan diverges from theirs'}")
sanity = classify_tool("Bash"), classify_tool("Read")
c3 = sanity == ("execute", "explore")
print(f"  CONTROL C  classify_tool still buckets Bash/Read as {sanity} -> "
      f"{'as assumed' if c3 else 'MOVED, the split above is measuring something else'}")

# CONTROL D probes the four numbers here that cannot be imported -- two targets and the
# weights -- by rebuilding the axis from THEIR published signals. It runs on theirs, not
# ours, so a divergence in our model scan cannot be mistaken for a moved literal.
t_distinct = sat(sig["distinct_models"], DISTINCT_MODELS_TARGET)
t_offload = sat(sig["offload_share"], OFFLOAD_SHARE_TARGET)
r_score = routing.get("score")
if r_score is None:
    predicted = .5 * t_distinct + .5 * t_offload
    branch = "two-term fallback, routing did not score"
else:
    w1, w2, w3 = MM_WEIGHTS
    predicted = w1 * t_distinct + w2 * t_offload + w3 * r_score
    branch = "three-term, routing scored"
c4 = abs(predicted - mm["normalized_score"]) < 1e-6
print(f"  CONTROL D  the unnamed targets and weights reproduce their own score ({branch}):"
      f" predicted {predicted:.6f} vs published {mm['normalized_score']:.6f}"
      f" -> {'agree' if c4 else 'DISAGREE — a literal moved'}")
blind = [n for n, v, tgt in (("distinct_models", sig["distinct_models"], DISTINCT_MODELS_TARGET),
                             ("offload_share", sig["offload_share"], OFFLOAD_SHARE_TARGET))
         if v >= tgt]
if blind:
    print(f"             BLIND RANGE: {', '.join(blind)} sit at or above target, so sat() is")
    print(f"             flat there and any target lowered underneath is invisible to this")
    print(f"             probe. It can only catch a target raised above the observed value.")
contributing = [t_distinct, t_offload] + ([] if r_score is None else [r_score])
if all(abs(v - 1.0) < 1e-9 for v in contributing):
    print(f"             AND THE WEIGHTS ARE UNCONSTRAINED HERE: every term is 1.0, so any")
    print(f"             weights that sum the same way reproduce this score. On this corpus")
    print(f"             CONTROL D tests the targets only. It agrees; it does not confirm"
          f" {MM_WEIGHTS}.")

print("\n  NOT CHECKED")
print("   - the routing third of Model mix: its producer (_routing_snapshot) is a private")
print("     method over corpus-lifetime state, so it cannot be re-derived independently.")
print("   - whether thinking blocks SHOULD count as exploration. That is a design question")
print("     and this check does not answer it; it measures how much of the axis they are.")

if not (c1 and c3 and c4):
    raise SystemExit(1)
