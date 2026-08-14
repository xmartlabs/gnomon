# Measuring an axis that has no script

Most of the score has no check, and Phase 1 still has to report a gap and a direction for
each axis. **Do not read the uncovered list from here. Run `scripts/axis-coverage.py`.**

This paragraph used to name the uncovered axes itself, and it named five: Skill fluency,
Tool command, Grounding, Token economy and Steering leverage. It was wrong — Model mix had
no check either and was never added — and no run noticed, because nothing enumerated the
axes. The manifest derives them from the anchored payload and from the checkout, and the
difference between those two is also the `dropped-term` detector, so Steering leverage shows
up under "dropped" rather than "uncovered": it is withheld upstream and never reaches the
payload at all.

**The count is deliberately absent here.** The correction to this paragraph replaced a wrong
hand-typed number with a right one, and the right one was stale within a day: two checks
graduated into `scripts/` and every total moved. A number in prose is a number nobody
re-derives, which is the whole failure this file's opening line exists to prevent.

**And a tag is not a measurement.** `# miraudit-covers:` is a grep over source comments: it
says a script claims an axis, not that it ran, exited 0, or that anybody wrote down a gap and
a direction. Pass `--run <the run's JSON>` and the manifest requires the record instead of
the claim. Run it that way before emitting — the first run to do so found five axes green on
a tag with no recorded measurement behind any of them.

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

   **Run it with `run-checks.py --also <your file>`**, which puts it in the same batch as
   everything else and exports `MIRAUDIT_SCRIPTS` so the import resolves. The run's output
   directory is nowhere near the skill, so a relative `../scripts` cannot reach `_common.py`
   from there and neither can walking up. `example-adhoc-check.py` carries the resolver to
   copy: environment variable first, then a walk, then an error naming the fix. It used to
   carry a plain `../scripts`, correct only where the example itself sits, so the file this
   document calls "the shape to copy" could not import once it was copied where this
   document says to put it. A cold run hit that and invented its own convention to get past
   it, and a second person would have invented a different one.

4. **Check that "theirs" covers the same population before you compare it.** gnomon walks
   **every source directory it finds** — `claude`, `codex`, `opencode`, `cursor` — and the
   top-level `behavior` block is the aggregate over all of them. `--corpus` is one of those,
   so on a window where a second source contributed, the two numbers describe different
   populations and the difference is nobody counting wrong. The payload settles it:
   `scoring_inputs_by_source[<source>]` publishes that source's own figures, and the run log
   prints `sources: claude(…), codex(…)`. This cost a real diagnosis: a check reported 70
   explore actions too many and 126 doing too few on a June window and agreed on an August
   one, and the whole gap was 12 codex sessions. Its own `not_checked` sent the next reader
   after a per-tool comparison, which would never have found it. **Agreement on the windows
   you happen to have tested is not evidence** that the populations match — three of five
   windows agreed, and all three were the claude-only ones.

5. **Print both numbers and the direction.** Theirs, yours, and `faithful` /
   `overestimates` / `underestimates`. A size without a direction is how a report ends up
   arguing the opposite of what its data shows.

6. **Carry a control.** Row 6 of the Phase 3 gate already demands one for synthetic
   fixtures; when the subject is a corpus measurement it means a case that **must** come out
   different — a second operationalization that should agree, or a branch of the tool's own
   arithmetic driven by its imported constants. Without one, a number here could be the scan
   misfiring rather than a measurement.

   When the control is a whole second pipeline run — a patched copy against an unpatched one
   — **`scripts/run-arms.py` runs the arms at once**, and always runs `--checkout` as the arm
   named `base`, because an A/B without its unpatched arm is not an A/B. An arm costs about
   85 seconds, which is where a full audit's time actually goes: on one run the anchor and
   all thirteen committed checks were finished 63 seconds in and everything after that was
   arms. Concurrency stops at the copy rather than the arm, since `uv run --project` builds
   `.venv` inside it, so two copies over two windows is 2x and not 4x.

   **An arm that edits the payload in memory is cheaper and has two traps, both of which have
   now cost a real finding.**

   *The payload validates itself, fail-closed.* `_planning_skill_evidence` cross-checks six
   `planning_skill_*` fields and returns `unmeasured` when the published share disagrees with
   numerator over denominator by more than 1e-6. An arm that edits two of the six does not
   score differently: the term drops out, `wsum` renormalizes onto its neighbour, and the axis
   comes back at its **maximum**. That is a believable number and a false one. Change the
   whole consistent set, and put the untouched payload through first as the control that must
   reproduce what the tool published.

   *Re-encoding a ratio can move it more than the correction does.* An arm that computes a
   corrected share and pushes it back through the real integer denominator inherits that
   denominator's granularity. `round(0.245878 * 51) = 13` reads back as 0.2549, nine tenths of
   a point above the share being tested, which was enough to move Discipline 15.0 to 15.3 and
   the AQ 89 to 90 — and 1 AQ was the entire claim. Scale the denominator instead, or assert
   the round trip: re-read the share you wrote and fail if it is not the one you computed.

7. **`not_checked`, non-empty**, like any finding. Name the question you did not ask.

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

**Graduating is where defects enter, so it has a checklist.** An ad-hoc check is written
against one machine, one run and one corpus; `scripts/` is none of those. Every line below
comes from something that actually got through.

- `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`. **Never `expanduser("~")`.**
  The one check that graduated before this list hardcoded the installed skill's path, and an
  insert at position 0 sits *ahead* of the script's own directory: running the fork's copy
  imported the installed `_common.py`. Proven by putting a sentinel in a copy — the
  hardcoded form could not see it, the `__file__` form could. Byte-identical today, so it
  was latent, which is exactly why nobody caught it.
- **Scoring constants through `require()`**, never as literals. Where the value genuinely is
  an unnamed inline literal, see the rule below rather than copying it in silently.
- **No paths from this machine and no personal names.** The file is going to a public fork.
- **Rename the usage line too.** The graduated check kept naming the file it used to be.
- **Derive weights and maxima from the payload** (`base_weight`), not from `/25` and `/50`
  typed into an f-string.
- **Re-run the manifest afterwards.** Graduating is the only thing that moves its totals.

### When the number cannot be imported

Some values have no named constant to import: the Model mix targets, its weights, and the
cli_share target are unnamed literals inside `compute_aq`. Copying them is unavoidable;
copying them *silently* is not. Beware the near-miss — `PLANNING_PRACTICE_TARGET` is also
`0.30` and is a different target, so importing it would be right by coincidence.

Rebuild the axis from **their** published signals and the copied literal, and compare
against the score they published. That turns a stale copy into a failed control instead of a
confident wrong number. Then state the range the probe is blind to: `sat()` is flat above
the observed value, so a target lowered underneath it is invisible, and when every term is
saturated the weights are unconstrained too. Both graduated checks print exactly that, and
the probe was verified by injection — a target raised above the observed share makes the
control disagree and the script exit 1; lowered, it agrees, as the blind-range line says.

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
