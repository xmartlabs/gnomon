"""Steering leverage: is the axis measuring me, or is it not being measured at all?

THIS IS AN EXAMPLE, not a check the operator runs every time. It is what step 3 of the
unscripted-axis procedure in `ad-hoc-checks.md` produces: a runnable file, in the run's
output directory, that anyone on any machine can re-run. Read it as the shape to copy.

It is kept here rather than in `scripts/` on purpose. `scripts/` holds checks that earned
their place by being needed twice; this one has been needed once, and v17 already forced
three fixtures to be deleted, so a library that grows on "seemed useful" is a library
somebody has to re-verify at every re-pin.

Why this axis. Steering leverage carries 50 of the Efficiency pillar's 100 and had no
check of any kind, which is how a run reported `Efficiency 97.0` without noticing that
Recovery was the only axis inside it.

    python3 example-adhoc-check.py --checkout <copy> \
        --since YYYY-MM-DD --until YYYY-MM-DD --stats <stats.json>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _common import parse, header, load_stats, dig, require, iter_events  # noqa: E402

args, WINDOW = parse(__doc__.strip().splitlines()[0])

# Step 2 of the procedure: import the primitives, do not restate them. The band is four
# constants and a branch; writing either one here would drift from the tool the moment
# anyone recalibrates, and would keep printing confidently after the axis is gone.
(BAND_MIN, BAND_MAX, DECAY_SPAN, VALIDATED) = require(
    [("gnomon.scoring.aq", "STEERING_LEVERAGE_BAND_MIN"),
     ("gnomon.scoring.aq", "STEERING_LEVERAGE_BAND_MAX"),
     ("gnomon.scoring.aq", "STEERING_LEVERAGE_DECAY_SPAN"),
     ("gnomon.scoring.aq", "STEERING_LEVERAGE_BAND_VALIDATED")],
    "The steering band may have been renamed or the axis removed. Either way this check "
    "has nothing to say about a checkout that no longer has it.")
(strip_injections,) = require(
    [("gnomon.config", "strip_injections")],
    "The prompt-cleaning helper moved. Counting instructions without it would mean "
    "re-deriving what counts as a human instruction, which is the tool's decision.")


def band_score(app):
    """The axis's own branch, transcribed from aq.py and driven by ITS constants.

    Transcribing four lines of arithmetic is not the same as restating a threshold: every
    number in it is imported, so a recalibration upstream moves this function too.
    """
    if app <= 0:
        return 0.0
    if app < BAND_MIN:
        return app / BAND_MIN
    if app <= BAND_MAX:
        return 1.0
    return max(0.0, 1 - (app - BAND_MAX) / DECAY_SPAN)


# ---------------------------------------------------------------- ours, from the corpus
top_level = instructions = 0
for _path, event, _when in iter_events(args.corpus, WINDOW):
    if event.get("type") == "assistant" or event.get("message", {}).get("role") == "assistant":
        content = (event.get("message") or {}).get("content")
        if isinstance(content, list):
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "tool_use"
                        and not event.get("isSidechain")):
                    top_level += 1
        continue
    message = event.get("message") or {}
    if message.get("role") != "user":
        continue
    # The four flags the accumulator skips on: injected, compacted, transcript-only, and
    # subagent-dispatch instructions are not human instructions. Getting this wrong is the
    # whole risk of an ad-hoc denominator -- the first draft of this file skipped only
    # sidechains and read 5954 instructions against their ~2471, which would have published
    # "overestimates by 3.7" from a population the tool never counted.
    if (event.get("isMeta") or event.get("isCompactSummary")
            or event.get("isVisibleInTranscriptOnly") or event.get("isSidechain")):
        continue
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(parts) if parts else None
    else:
        text = None
    if text is None:
        continue
    is_command = "<command-name>" in text or text.lstrip().startswith("<local-command")
    cleaned = strip_injections(text)
    if (is_command and not cleaned) or cleaned:
        instructions += 1

ours = (top_level / instructions) if instructions else 0

stats = load_stats(args.stats)
# An explicit path, not find_key: the name appears six times with four different values --
# under /behavior, under /autonomy/components, under /agentic/steering_leverage, and once
# per source-month. find_key refuses rather than hand back the first one, which is the
# whole point of it. /behavior is the slice the axis is scored from.
theirs = dig(stats, "behavior", "actions_per_prompt")

print(header(args, WINDOW))
print("=" * 78)
print("STEERING LEVERAGE — actions_per_prompt against a band, not a ceiling")
print("=" * 78)
print(f"  band            {BAND_MIN} .. {BAND_MAX}   (decay span {DECAY_SPAN}, all imported)")
print(f"  ours            {ours:.1f}   ({top_level} top-level tool calls / "
      f"{instructions} instructions)")
print(f"  theirs          {theirs if theirs is not None else 'not in stats.json'}")
if theirs is not None and instructions:
    gap = ours - float(theirs)
    direction = "faithful" if abs(gap) < 0.5 else (
        "overestimates" if gap < 0 else "underestimates")
    print(f"  gap             {gap:+.1f}  ->  {direction}")

print(f"\n  the axis would score   {band_score(ours):.3f}  if the band were live")
print(f"  STEERING_LEVERAGE_BAND_VALIDATED = {VALIDATED}")
if not VALIDATED:
    print("  -> the term is WITHHELD (aq.py, `withheld_unvalidated_band`) and wsum")
    print("     renormalizes, so the Efficiency pillar you read is Recovery alone.")

# ------------------------------------------------------------------------- the control
# Step 5: without a case that MUST come out differently, a number here could be the scan
# misfiring rather than a measurement. These three are arithmetic on the tool's own
# constants, so a recalibration upstream moves the control with the subject.
print("\n  CONTROLS — the band's own branch, no corpus involved:")
mid = (BAND_MIN + BAND_MAX) / 2
cases = [("inside the band", mid, 1.0),
         ("zero", 0, 0.0),
         ("half the floor", BAND_MIN / 2, 0.5),
         ("one decay span above the ceiling", BAND_MAX + DECAY_SPAN, 0.0)]
ok = True
for label, value, expected in cases:
    got = band_score(value)
    good = abs(got - expected) < 1e-9
    ok = ok and good
    print(f"    {label:<34}app={value:<6} -> {got:.3f}   "
          f"{'ok' if good else f'EXPECTED {expected}'}")

print("\n  NOT CHECKED: whether the band is the right band. This check reads where you sit")
print("  in it and whether it is live; 5..20 actions per instruction is a calibration")
print("  claim about a population, and one corpus cannot test it. Nor does it check the")
print("  numerator's sidechain labels, which the axis drops on separately.")

if not ok:
    print("\n  A control did not hold. Every number above is unsafe: the transcription of")
    print("  the band no longer matches the constants it imported.")
    raise SystemExit(1)
