<span class="gn-label">Metrics</span>

# Insights & trend

<p class="gn-thesis">Around the scores, the profile adds readings that explain them: a level and archetype, the developer's strongest habits, the few things worth working on next, and how the score moved over time.</p>

None of these readings change the AQ. They are derived from the same month of sessions to make the numbers actionable.

## Level and archetype

The AQ total maps to a [level](how-scoring-works.md#levels), from Novice to Elite. The archetype pairs that level with a short line that names the developer's weakest pillar, so the headline always points at something to work on. Source: `gnomon/scoring/archetype.py`.

## Signature moves

Up to five patterns the developer already does well, picked from what the month shows: reviewing the agent's work, thinking before building, building at pace, planning, keeping the human in charge of decisions, working through the shell, and researching before acting. Each one appears only when its evidence clears a threshold, so the list is earned, not filler. Source: `gnomon/scoring/insights.py`.

## Growth edges

Up to three concrete things to work on next, ranked by how much they would help. They come from GStack terms that fall short of their target and from any AQ axis filled less than 45%. Each edge carries a severity (high, medium, low) so the first one is the one to start with. Source: `gnomon/scoring/insights.py`.

## Steering reading

A descriptive reading of how much the agent does per human instruction: a long leash at 12 or more actions per instruction, a medium leash at 6 or more, and a short leash below that, together with how often the agent stopped to ask a question. It describes a working style and is not scored; see [Steering leverage](efficiency/steering-leverage.md). Source: `gnomon/scoring/insights.py`.

## Trend

The profile keeps up to six months of AQ history and shows the change from the previous month. A month that mixes several tools is marked approximate, because its sources may have measured different signals. Source: `gnomon/scoring/trend.py`.

## Model usage

How many turns ran on each model, as a count and a share, with input, output and cached tokens. It is context for [Model mix](savvy/model-mix.md), not a score. Source: `gnomon/scoring/profiles.py`.
