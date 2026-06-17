# CONTEXT — paxel domain & architecture language

Vocabulary for `paxel.py` (the local builder-profile tool). Architecture terms follow
the depth/seam glossary; the nouns below are domain-specific.

## Pipeline stages

`paxel.py` is one file running four stages, glued by the **Stats** object:

1. **Ingest** — discover transcript files from the six sources and translate each into
   Claude-shaped event dicts (`iter_events` + the per-source readers).
2. **Accumulate** — fold the event stream into metrics (the **EventAccumulator**).
3. **Score** — turn metrics into Execution/Planning/Engineering scores + the **agentic**
   grading (`compute_scores`, `score_breakdown`, `compute_aq`).
4. **Render** — emit `stats.json`, `report.md`, `narrative_input.md`, `profile.html`.

## Terms

- **EventAccumulator** — the deep module behind the accumulation stage. Interface:
  `consume_file(source, events)` folds one file's events (owns per-file reset state:
  error-recovery flag, iteration-depth-since-commit, and the codex empty-seed skip);
  `finalize(churn) -> Stats` derives the final metrics. Constructed with the time
  **window** and drops out-of-window events itself. Pure given its inputs — `git_churn`
  is injected, never called inside, so it is testable with synthetic events alone.

- **Stats** — the declared, JSON-serializable contract between the accumulate, score, and
  render stages. Nested blocks: `corpus`, `volume`, `tools`, `velocity`, `behavior`,
  `rhythm`, `progression`, `stack`, `autonomy`, `token_usage`, `agentic`. `agentic` is
  derived from the other blocks by `compute_aq` during the score stage, written back onto
  Stats — it is not event-derived. `asdict(stats)` must reproduce today's `stats.json`
  byte-for-byte.

- **Feed / orchestration** — `main()` after the deepening: discovers sources, does the
  mtime I/O skip (don't parse files written before the window), hands each file's events
  to the accumulator, runs `git_churn`, then scoring and rendering. No metric logic.

- **Voice samples** — verbatim user text (go-to phrase, most cryptic prompt, biggest
  crash-out) surfaced on the LOCAL profile only, NEVER the shared image. A separate
  channel from Stats (`acc.voice_samples()`), kept off `stats.json` by construction.

- **Source / reader** — one of the six transcript origins (Claude Code, Codex, Gemini,
  Pi, opencode, Cursor). Each has its own schema; all converge on one Claude-shaped event.

## Hard constraint

- **Single-file distribution.** `paxel.py` is run directly via
  `python3 <(curl -sL …/paxel.py)`. It must stay one self-contained file — the
  EventAccumulator and Stats deepenings happen IN PLACE, not as new modules. Do not
  propose splitting paxel.py into a package.
