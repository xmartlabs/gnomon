# Measuring an axis that has no script

Most of the score has no check, and Phase 1 still has to report a gap and a direction for
each axis. **Do not read the uncovered list from here. Run `scripts/axis-coverage.py`.**

This paragraph used to name the uncovered axes itself, and it named five: Skill fluency,
Tool command, Grounding, Token economy and Steering leverage. It was wrong — Model mix (50)
has no check either and was never added — and no run noticed, because nothing enumerated the
axes. The manifest derives them from the anchored payload and from the checkout, and the
difference between those two is also the `dropped-term` detector, so Steering leverage now
shows up under "dropped" rather than "uncovered": it is withheld upstream and never reaches
the payload at all. Today that is five uncovered scored axes worth 175 of 350 base points,
plus one dropped worth 50.

`design-rationale.md` argues why an agent belongs here and nowhere else: **conceiving the
counter-measurement is the hard part and is not mechanical; deciding is mechanical and must
stay that way.** This file is the mechanical half — what the agent has to leave behind so
its judgement never becomes the verdict.

## The procedure

1. **Read the declared signals** from the payload, `axes[].signals`, not from memory. They
   change between contracts and the report is the only current statement of them.

2. **Find the primitive that already produces each one and import it.** `bash_runs_tests`,
   `classify_change_target`, `strip_injections`, `parse_workflow_agent_dispatch` and the
   scoring constants are all public. A predicate you write yourself makes the gap you report
   your own: a hand-rolled test regex read 28% where theirs read 34%. If no public primitive
   exists, say so in the output rather than quietly writing one.

3. **Write a script, do not run a one-liner.** It goes in the run's output directory, takes
   the same `--checkout / --since / --until / --stats` shape as everything in `scripts/`,
   and imports `scripts/_common.py`. This is the step that keeps the verdict deterministic:
   what leaves the run is a file anyone can re-run on another corpus, not a paragraph about
   what an agent concluded. `second-corpus.md` depends on exactly this — a command carrying
   this machine's paths is not a measurement anybody else can repeat.

4. **Print both numbers and the direction.** Theirs, yours, and `faithful` /
   `overestimates` / `underestimates`. A size without a direction is how a report ends up
   arguing the opposite of what its data shows.

5. **Carry a control.** Row 6 of the Phase 3 gate already demands one for synthetic
   fixtures; when the subject is a corpus measurement it means a case that **must** come out
   different — a second operationalization that should agree, or a branch of the tool's own
   arithmetic driven by its imported constants. Without one, a number here could be the scan
   misfiring rather than a measurement.

6. **`not_checked`, non-empty**, like any finding. Name the question you did not ask.

## What `_common.py` gives you

No markdown file used to mention it, which meant every ad-hoc check started by reinventing
it. It is `scripts/_common.py`:

| | |
|---|---|
| `parse(description)` | the standard flags, window validation, and it puts `--checkout` on `sys.path` |
| `Window` | half-open `[start, end)`; filter with `in`, never with `<` |
| `iter_events(corpus, window)` | every transcript event in the window |
| `iter_tool_uses(corpus, window)` | every `tool_use` block in the window, as a `Use` |
| `require([(module, name)], hint)` | import from the checkout, exit loudly if the version lacks it |
| `load_stats` / `find_key` / `dig` | read the anchored payload |
| `header(args, window)` | the banner every check prints |

**Use `iter_events` / `iter_tool_uses` rather than writing the scan.** The window filter is
not a parameter there, and that is the point: four live checks still carry a hand-written
copy of that loop, and the fifth copy is why the helpers exist — it dropped the
`if when not in window` line and measured the entire corpus under a windowed header. Nothing
in its output said so. `iter_tool_uses` counts identically to `fingerprint.py` on purpose,
verified at 42,664 on the corpus it was written against, so an ad-hoc denominator can be
placed against the run's own fingerprint.

## Graduation: a check earns `scripts/` by being needed twice

Ad-hoc is the default and the resting state. A check moves into `scripts/` only when a
**second, independent run** needed the same measurement. Until then it lives in its run's
output directory and is listed under "Ad-hoc checks seen once" in `known-state.md`.

Same reasoning as `design-rationale.md`'s rule that a gate row is earned by a death rather
than invented. v17 forced three fixtures to be deleted outright; every script in `scripts/`
is something a person has to re-verify at each re-pin, so a library that grows on "this
seemed useful" is a bill someone pays later.

## The worked example

`example-adhoc-check.py`, beside this file, is what the procedure produces. It measures
Steering leverage, which carries 50 of Efficiency's 100 and had no check of any kind.

Two things in it are worth copying, and both are mistakes it made first.

**`find_key` refused, and it was right to.** `actions_per_prompt` appears six times in the
payload with four different values: under `/behavior`, under `/autonomy/components`, under
`/agentic/steering_leverage`, and once per source-month. `find_key` raises instead of
returning the first hit. The fix is `dig` with an explicit path and a comment saying which
slice and why — not a quieter lookup.

**The first denominator was wrong by 2.4x, and it looked fine.** Counting user messages that
were not sidechains gave 5954 instructions against their implied ~2471, which would have
published "overestimates by 3.7" from a population the tool never counted — the
`invented-denominator` scar exactly. The accumulator skips four flags, not one:
`isMeta`, `isCompactSummary`, `isVisibleInTranscriptOnly`, `isSidechain`. With all four the
check reads **6.4 against their 6.4**, an independent reproduction.

That is the argument for step 4 in one number. A gap you cannot explain is a bug in your
measurement until proven otherwise, and the way to find out is to keep narrowing it against
their code — not to publish it with a confident direction attached.
