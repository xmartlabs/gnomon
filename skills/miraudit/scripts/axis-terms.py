"""Which TERMS of each axis the payload never shows, for every axis at once.

    python3 axis-terms.py --checkout <copy> --since --until --stats <stats.json> \
        [--comparison <file.json> ...]

axis-coverage.py counts axes. This counts the terms inside them, because that is a level
lower than the manifest can see and it is where the defect lived: Skill fluency was covered
as an axis while 30% of it was a term absent from `signals`. Generalising that one recovery
to every axis is all this file is.

THE ANCHOR IS THEIR OWN SCORE, NOT THE SHAPE OF THEIR CODE. Term values are found by
mapping each expression to a published signal, and that mapping uses name heuristics that
will not survive a rename. That is tolerable only because nothing is believed until the
parsed terms rebuild the published `normalized_score`. A mapping that guesses wrong makes
the rebuild disagree and the axis is reported NOT DECOMPOSABLE.

Three outcomes per axis:
  REPRODUCED       every term evaluated, and they rebuild the published score
  ONE UNKNOWN      all but one evaluated, so the last is determined by algebra (this is the
                   Skill fluency recovery, applied wherever it fits)
  NOT DECOMPOSABLE two or more opaque, the rebuild disagrees, or NOTHING was evaluated

That last clause is the scar. A first version dropped a term whose `wsum(` was followed by
a comment, landed on ONE UNKNOWN with zero known terms, and published "100% of Discipline
is decided by an unpublished term" -- a false finding, because with nothing known the
algebra returns the score itself and cannot fail. One unknown out of one term is not a
recovery. Comments are now stripped before parsing AND the branch requires a known term.

A RECOVERED VALUE IS CHECKED AGAINST THE SIGNALS BEFORE IT IS CALLED UNDISCLOSED. The same
first version reported Verification's coverage term as published nowhere. It is published,
as `test_coverage`, under a name the expression does not use -- and the algebra recovered
0.3672 against a published 0.3673, which is now a control rather than a false positive.

Axes that are not a `wsum` are named as such rather than silently skipped, and so are the
ones where a wsum is only PART of the axis. Neither is a parse failure, and calling them
one would be a finding about our own code.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import parse, header, load_stats, require  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0], {
    "--comparison": {"action": "append", "default": [], "metavar": "PATH",
                     "help": "a comparison-2 payload; repeatable"},
})
stats = load_stats(args.stats)
if not stats:
    sys.exit("error: --stats is required; this reads an anchored run's payload.")

AQ = os.path.join(args.checkout, "gnomon", "scoring", "aq.py")
if not os.path.exists(AQ):
    sys.exit(f"error: no {AQ}. The scoring module moved; this parse is anchored to it.")

print(header(args, WINDOW))


# ---- parsing ------------------------------------------------------------------------------
def strip_comments(text):
    """Drop `#` comments, respecting quotes. A comment between `wsum(` and its first term is
    what made the parser lose a term silently."""
    out, quote, i = [], None, 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = None
            out.append(ch)
        elif ch in "'\"":
            quote = ch
            out.append(ch)
        elif ch == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


SRC = strip_comments(open(AQ).read())


def balanced(text, start):
    """The slice from the '(' at `start` to its matching ')', quotes respected."""
    depth, i, quote = 0, start, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return None


def split_top(text):
    """Split on commas that are not inside brackets or quotes."""
    out, buf, depth, quote = [], "", 0, None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote and text[i - 1] != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
            continue
        buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


ASSIGN_RX = re.compile(r"(\w+)\s*=\s*wsum\(")
parsed = {}
for m in re.finditer(r"\bwsum\(", SRC):
    if SRC[max(0, m.start() - 40):m.start()].strip().endswith("def"):
        continue
    body = balanced(SRC, m.end() - 1)
    if body is None:
        continue
    axis, terms, skipped = None, [], []
    for arg in split_top(body):
        if arg.startswith("axis="):
            axis = arg.split("=", 1)[1].strip().strip("\"'")
        elif arg.startswith("("):
            parts = split_top(balanced(arg, 0) or "")
            if len(parts) >= 2:
                try:
                    terms.append((float(parts[0]), parts[1]))
                except ValueError:
                    skipped.append(arg[:40])
            else:
                skipped.append(arg[:40])
        elif arg:
            skipped.append(arg[:40])
    if axis is None:
        back = ASSIGN_RX.search(SRC, max(0, m.start() - 200), m.end())
        axis = f"<{back.group(1)}>" if back else "<anonymous>"
    parsed[axis] = (terms, skipped)

# ---- the payload --------------------------------------------------------------------------
scored = {a["name"]: a for p in (stats.get("agentic") or {}).get("pillars") or []
          for a in p.get("axes") or []}

CONST_RX = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b")
GET_RX = re.compile(r"\.get\(\s*[\"'](\w+)[\"']")


def constant(name):
    try:
        return require([("gnomon.scoring.aq", name)], f"{name} is gone.")[0]
    except SystemExit:
        return None


def signal_for(name, signals, used):
    """A published signal for a variable name. Heuristic on purpose -- the reproduction
    check below is what makes a wrong guess safe: it disagrees instead of lying."""
    base = name.lstrip("_")
    for cand in (name, base, base.replace("_distinct", ""), f"{base}_median",
                 f"{base}_distinct", f"{base}_share"):
        if cand in signals and cand not in used:
            return cand
    return None


def evaluate(expr, signals, used):
    """The term's value, or None with a reason. Only the shapes gnomon actually uses."""
    if expr.startswith("rate("):
        inner = balanced(expr, expr.index("(")) or ""
        gm = GET_RX.search(inner)
        pair = None
        if gm and f"{gm.group(1)}_per_call" in signals:
            pair = gm.group(1)
        else:
            # rate_facts publishes <k>_per_call with <k>_per_call_target. The local name need
            # not match the signal (review_n -> review_skills), so fall back to the unique
            # unconsumed pair rather than inventing a mapping.
            pairs = [k[:-len("_per_call")] for k in signals
                     if k.endswith("_per_call") and k[:-len("_per_call")] not in used]
            if len(pairs) != 1:
                return None, ("no rate pair in signals" if not pairs
                              else f"{len(pairs)} rate pairs, ambiguous")
            pair = pairs[0]
        used.add(pair)
        r, t = signals.get(f"{pair}_per_call"), signals.get(f"{pair}_per_call_target")
        if r is None or not t:
            return None, "the rate term was not scored (published as null)"
        return min(1.0, r / t), f"rate {pair}"

    if expr.startswith("sat("):
        parts = split_top(balanced(expr, expr.index("(")) or "")
        if len(parts) != 2:
            return None, "sat() with an unexpected arity"
        gm = GET_RX.search(parts[0])
        key = signal_for(gm.group(1) if gm else parts[0].strip(), signals, used)
        if key is None:
            return None, f"sat() over {parts[0].strip()[:26]}, no signal maps to it"
        used.add(key)
        cm = CONST_RX.search(parts[1])
        if cm:
            target, label = constant(cm.group(1)), cm.group(1)
            if target is None:
                return None, f"{label} is not importable"
        else:
            m2 = re.search(r"[\d.]+", parts[1])
            if not m2:
                return None, f"sat() target {parts[1].strip()[:18]} is neither name nor number"
            target, label = float(m2.group()), f"unnamed literal {m2.group()}"
        return min(1.0, signals[key] / target), f"sat {key} / {label}"

    bare = expr.strip()
    if re.fullmatch(r"_?\w+", bare):
        # A term assigned from sat(<k>_share, <k>_target) elsewhere. Same disclosure
        # convention as rate_facts, so read it the same way rather than by variable name:
        # `planning_habit` is published as planning_practice_share against its target.
        pairs = [k[:-len("_share")] for k in signals
                 if k.endswith("_share") and f"{k[:-len('_share')]}_target" in signals
                 and k[:-len("_share")] not in used]
        if len(pairs) == 1:
            p = pairs[0]
            used.add(p)
            t = signals[f"{p}_target"]
            return (min(1.0, signals[f"{p}_share"] / t) if t else 0.0,
                    f"sat {p}_share / {p}_target")
        # A bare name the payload already publishes as a 0..1 term value (o_harn).
        key = signal_for(bare, signals, used)
        v = signals.get(key) if key else None
        if isinstance(v, (int, float)) and 0.0 <= v <= 1.0:
            used.add(key)
            return float(v), f"published as {key}"
    return None, "opaque"


def published_as(value, signals, used):
    """Does a signal already carry this recovered value under another name? Verification's
    coverage term does, and calling it undisclosed was a false positive.

    A UNIQUE match only. At 1.0 several signals collide -- Orchestration matched three at
    once -- and 'it equals one of three numbers that are all 1.0' is a coincidence, not a
    disclosure. Ambiguous means unknown, not published."""
    hits = [k for k, v in signals.items()
            if k not in used and isinstance(v, float) and 0.0 <= v <= 1.0
            and abs(v - value) < 1e-3]
    return hits if len(hits) == 1 else []


# ---- report -------------------------------------------------------------------------------
PARTIAL_AXIS = {
    "Orchestration": "the wsum is o_quality only; the axis blends it with a"
                     " confidence-weighted frequency term (aq.py:300-312)",
}
NOT_WSUM = {
    "Model mix": "hand-rolled arithmetic with an if/else fallback (aq.py:582-584)",
    "Context Intelligence": "a single sat(), no wsum",
    "Grounding": "a single sat(), no wsum",
    "Recovery": "not built by wsum",
}

print("PER-AXIS TERM ACCOUNTING")
undisclosed, renamed, reproduced, recovered = [], [], 0, 0
for name in sorted(scored, key=lambda n: -(scored[n].get("base_weight") or 0)):
    ax = scored[name]
    sig = ax.get("signals") or {}
    norm = ax.get("normalized_score")
    entry = parsed.get(name)
    print(f"\n  {name}  ({ax.get('base_weight')} base, normalized {norm:.4f})")
    if entry is None:
        print(f"    NOT A WSUM — {NOT_WSUM.get(name, 'no wsum found for this axis name')}")
        print("    Not a parse failure. Named so its absence never reads as coverage.")
        continue
    terms, skipped = entry
    if name in PARTIAL_AXIS:
        print(f"    PARTIAL — {PARTIAL_AXIS[name]}")
    if skipped:
        print(f"    PARSE DROPPED {len(skipped)} argument(s): {skipped}")
        print("    NOT DECOMPOSABLE. A term the parse cannot read is not a term that is absent.")
        continue
    if "partial_terms" in ax:
        print(f"    partial_terms present: {ax['partial_terms']} — a term was dropped upstream")

    used, values, unknown = set(), [], []
    for coef, expr in terms:
        val, how = evaluate(expr, sig, used)
        short = re.sub(r"\s+", " ", expr)[:52]
        if val is None:
            unknown.append((coef, short, how))
            print(f"    {coef:>5}  UNKNOWN   {short}")
            print(f"    {'':>5}            {how}")
        else:
            values.append((coef, val))
            print(f"    {coef:>5}  {val:.4f}    {how}")

    total = sum(c for c, _ in terms if c is not None)
    known_sum = sum(c * v for c, v in values)
    if name in PARTIAL_AXIS:
        # The algebra solves against normalized_score, and here that number is the BLEND,
        # not this wsum's value. Solving it would be arithmetic on two different quantities.
        # It happened to agree on the corpus this was written against because every term was
        # 1.0, which is exactly the kind of accident a coincidence check has to refuse.
        print("    -> NOT DECOMPOSABLE: normalized_score is the blended axis, not this wsum,")
        print("       so neither the rebuild nor the algebra applies to it.")
        continue
    if not unknown:
        predicted = known_sum / total if total else 0
        agree = abs(predicted - norm) < 1e-6
        reproduced += agree
        print(f"    -> REPRODUCED {predicted:.6f} vs published {norm:.6f}"
              f"  {'agree' if agree else 'DISAGREE'}")
        if not agree:
            print("       NOT DECOMPOSABLE — a term is missing or mismapped. Ignore the lines"
                  " above.")
    elif len(unknown) == 1 and values:
        coef, short, _why = unknown[0]
        x = (norm * total - known_sum) / coef if coef else None
        share = coef / total
        hits = published_as(x, sig, used)
        recovered += 1
        print(f"    -> ONE UNKNOWN, determined by algebra: {x:.4f}  ({share:.0%} of the axis)")
        if hits:
            print(f"       Published after all, under {' or '.join(hits)} — the expression"
                  " names a local, the payload names the number.")
            renamed.append((name, hits[0], x))
        else:
            undisclosed.append((name, share, x, short))
    elif len(unknown) == 1:
        print("    -> NOT DECOMPOSABLE: one unknown and NOTHING known, so the algebra returns"
              " the score itself and proves nothing.")
    else:
        print(f"    -> NOT DECOMPOSABLE: {len(unknown)} terms opaque, algebra underdetermined")

# ---- what the run should look at ------------------------------------------------------------
print("\n\nTERMS THAT DECIDE A SCORE AND ARE PUBLISHED NOWHERE")
if not undisclosed:
    print("  none")
for name, share, value, expr in sorted(undisclosed, key=lambda r: -r[1]):
    print(f"  {name:24} {share:.0%} of the axis   value here {value:.4f}")
    print(f"  {'':24} {expr}")
if undisclosed:
    print("\n  CANDIDATES, not findings. Phase 3 applies unchanged: a term nobody publishes")
    print("  is a disclosure observation until it is shown to change an order or cost")
    print("  someone points.")

# ---- controls ---------------------------------------------------------------------------
print("\nCONTROLS")
print(f"  A  {reproduced} axes rebuilt from their parsed terms and agreed exactly, and")
print("     {} more resolved a single unknown. An incomplete parse cannot reach either:"
      .format(recovered))
print("     it disagrees, or it has nothing known and says so.")

if renamed:
    for name, key, val in renamed:
        print(f"  B  {name}: algebra recovered {val:.4f} and the payload independently"
              f" publishes {key}={scored[name]['signals'][key]}. The one-unknown branch is")
        print("     validated against a number this script never used to compute it.")
else:
    print("  B  No recovered term matched a published signal, so the one-unknown branch is")
    print("     unvalidated in this run. Treat its outputs as weaker than the reproduced ones.")

sf = [r for r in undisclosed if r[0] == "Skill fluency"]
if sf:
    ok = abs(sf[0][2] - 1.0) < 0.005 or abs(sf[0][2] - 0.6) < 0.005
    print(f"  C  Skill fluency recovers {sf[0][2]:.4f} —"
          f" {'a branch skill-fluency-term.py knows' if ok else 'OFF BOTH BRANCHES'}")
    if not ok:
        raise SystemExit(1)
else:
    print("  C  Skill fluency did not reach the one-unknown branch; the generalisation of")
    print("     skill-fluency-term.py is not exercised, so treat this run as unvalidated.")

for path in args.comparison:
    with open(os.path.expanduser(path)) as fh:
        payload = json.load(fh)
    axes = {a["name"]: a for a in payload.get("axes", [])}
    stem = os.path.splitext(os.path.basename(path))[0].replace("comparison-", "")
    out = []
    for name, _share, _v, _e in undisclosed:
        ax, entry = axes.get(name), parsed.get(name)
        if not ax or not ax.get("signals") or not entry:
            out.append(f"{name}: no signals")
            continue
        used, values, unk = set(), [], []
        for coef, expr in entry[0]:
            val, _how = evaluate(expr, ax["signals"], used)
            (values if val is not None else unk).append((coef, val))
        total = sum(c for c, _ in entry[0] if c is not None)
        if len(unk) == 1 and unk[0][0] and values:
            x = (ax["normalized_score"] * total - sum(c * v for c, v in values)) / unk[0][0]
            out.append(f"{name} {x:.3f}")
        else:
            out.append(f"{name}: {len(unk)} unknown")
    print(f"  D  {stem:6} {'   '.join(out)}")
if args.comparison and undisclosed:
    print("     Cross-corpus: a term that never varies carries weight without discriminating;")
    print("     one that does can invert an order the published signals imply.")
