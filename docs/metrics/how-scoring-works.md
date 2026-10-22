<span class="gn-label">Metrics</span>

# How scoring works

<p class="gn-thesis">gnomon turns a month of agent sessions into one number, the Agentic Quotient (AQ), from 0 to 100. Every part of it is public, from the weights to the targets.</p>

## The AQ score

The AQ is a weighted sum of four pillars. Each pillar scores 0 to 100 from its own axes, and each axis scores 0 to 1 from its terms.

{{ pillars_table() }}

Most terms compare a measured value with a target: `min(1, value / target)`. Reaching the target gives full credit, and going past it gives nothing more, so there is no reward for doing something to excess. Each axis page shows its terms, weights and targets.

## Levels

The total AQ maps to a level. The same cut-offs are used on every axis, so a level means the same thing everywhere in the docs.

{{ levels_table() }}

See the [rubric at a glance](rubric.md) for what each level looks like on each axis.

## A missing signal is never a zero

Not every tool records every signal. Google Antigravity IDE, for example, hides which model ran each turn. When a source cannot record something, gnomon leaves that term or axis out and spreads its weight over the parts it can measure. Nobody loses points for the tool they use. Each axis page lists what every source can measure, and [What each source measures](../sources/coverage.md) has the full matrix.

The same rule covers thin data. A share computed over fewer than 5 eligible sessions is noise (one session out of one is 100%), so it is left out rather than scored. A rate per tool call is scored only when the month has enough tool calls for the target to be reachable.

## What gets scored

- **One calendar month.** Each score covers a trailing window of one calendar month. When sharing a profile, `--window=N` widens it to N months; local runs (`--local`) always use one month.
- **All tools together.** When a developer uses several tools, their sessions are merged and scored once, as one corpus. A per-tool breakdown is kept for diagnosis, but it is not the published score.
- **Behaviour, not volume.** Prompts, sessions and tokens are shown, but they never raise the AQ by themselves. A small, careful month can score higher than a large, careless one.

## Versioned, so scores stay comparable

Every score carries a contract ID, currently `{{ metrics.contract }}`. The ID changes whenever a formula, weight or target changes, and every score-affecting constant is fingerprinted under it. Two scores are compared only when their contract IDs match, so a change to the scoring can never silently mix old and new numbers.

Source: `gnomon/scoring/aq.py`, `gnomon/scoring/aggregate.py`, `gnomon/scoring/calibration.py`, `gnomon/scoring/versioning.py`.
