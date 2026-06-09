# AQ refinement — coordination-based Orchestration + honest level ladder (2026-06-11)

Supersedes naming/semantics from the earlier AQ specs (`2026-06-09-paxel-xl-aq-design.md`,
`2026-06-10-aqv2-design.md`). Those remain as historical record; this is the current truth.

## Why

Two complaints, both correct:

1. **Orchestration was a saturating volume counter.** `agent_runs + distinct_types + harness-bit
   + (background + scheduled)` — three of four terms pure count. A serial grinder firing 400
   agents one-at-a-time maxed it, same as a real orchestrator. Volume masked structure.

2. **The archetype ignored level.** It was picked from gstack *shape* (Planning/Execution/
   Engineering) with absolute thresholds in precedence order, so almost everyone cleared
   `Planning >= 7.5` first → "The Architect", regardless of the AQ below. Two profiles with
   wildly different AQ (52 vs 96) got the same flattering label. The headline also rendered
   "You're **a The** Architect" (double article).

## Changes

### Orchestration → coordination, not volume

Replace the `(background + scheduled)` COUNT term with **fan-out**: the median number of agents
coordinated per *orchestrating* session (sessions that dispatch ≥1 agent). A serial grinder
reads `fanout=1`; a real orchestrator reads its team size. Every graded term is bounded [0,1],
so grinding can't move it.

```
orchestration = .30·variety(subagent_types)  + .30·sat(fanout_median, 5)
              + .20·o_harn                    + .20·sat(agent_runs, 400)   # small volume floor
```

- New collection: `agents_per_session` → `behavior["fanout_median"]` (median over sessions with
  agents > 0; robust to one big fan-out outlier).
- Rejected alternatives: *parallel-block dispatch* (≥2 Agent blocks in one assistant message) —
  this harness emits 0 of those, the runtime does concurrency via background + Task-team tools.
  *delegation_share* (sidechain lines ÷ total) — noisy: measures subagent verbosity and competes
  against the user's own main-thread work, not coordination.

### One honest level vocabulary, driven by AQ

The AQ 0–100 is the score that actually separates level (gstack saturates high for nearly
everyone). Collapse the level vocabulary to a single ladder — **no flattery at the floor** — used
for BOTH the AQ tier and the profile headline archetype, so they never contradict:

```
Novice <25 · Apprentice 25–45 · Adequate 45–60 · Proficient 60–75 · Advanced 75–88 · Elite 88–100
```

- `pick_archetype` now reads `agentic.tier` (the rung) and builds a band-aware quote that names
  the **thinnest AQ pillar** — the gap is surfaced, not hidden ("if you fall short, it says so").
- gstack shape (Planning/Execution/Engineering) is no longer a flattering title; it stays a
  scorecard read only.
- Headline copy fixed: `You're<br>{rung}.` (was `You're a<br>{archetype}.`).

### Verification — unchanged

Considered making it a ratio (`verified_sessions / edit_sessions`), then rejected: it craters
review-heavy verification and drops the review signal entirely. Left as-is.

## Verification

- `python3 -m unittest discover -s tests` → green, incl. `test_coordination_beats_volume`,
  `test_volume_alone_cannot_max_orchestration`, `test_level_ladder_honest`,
  `test_archetype_matches_aq_tier`.
- Real-data run: Orchestration 32.9 → 31.0 (earned — coordinates teams of ~4), AQ 96 → Elite,
  headline `You're Elite.`, quote names weakest pillar. archetype == AQ tier.
