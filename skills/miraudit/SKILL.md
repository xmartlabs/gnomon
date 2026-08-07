---
name: miraudit
description: >
  Audits whether a score computed about your own work actually reflects what you did, and
  reports gaps with executable proof and a control. Use when a metric looks wrong,
  unexplained, or moved without a reason — "my score dropped", "the metric is wrong",
  "this doesn't reflect what I do", "why does it say that", "mi score bajó", "la métrica
  está mal", "esto no refleja lo que hago" — or when auditing a gnomon / xl-ai-insights /
  AQ report, an engineering dashboard, or a productivity scorecard.
license: MIT
compatibility: >
  Requires python3, git, and uv. Reads the agent transcript corpus and a checkout of the
  scoring tool; writes only inside its own output directory.
allowed-tools: Read Grep Glob
---

# miraudit

Audits a score someone else's code computed about your work. It does not compute a score,
propose formula changes, or rank anyone.

**Does the number measure what this person actually does in their sessions?** That question
survives the formula changing. Findings are shapes of infidelity, not a list of known bugs;
that list expires every release.

**Paths.** Resolve this skill's directory once (the Skill tool result reports it) and prefix
every script call. Never assume the working directory.

<investigate_before_measuring>
Never claim an axis is unfaithful without having run the measurement. Never cite a file:line
you have not opened. Never report a number you did not produce in this run. An unrun check
is not evidence.
</investigate_before_measuring>

## Phase 0 — Anchor. Gate.

1. Resolve the tool's installed version; compare to `references/known-state.md`. If it
   differs, mark every finding unvalidated against that version.
2. Reproduce the published number on a **copy** of the checkout. For gnomon:
   `--local --console --no-open --last=30d`; without the window flag the pillars are
   blended and will not reproduce.
3. **If the base run does not reproduce it, stop.** The method is wrong before any finding.
4. Print the corpus fingerprint (files, lines, tool calls, sources, window) before any other
   number. Counts compared across machines mean nothing without it.

## Phase 1 — Per-axis fidelity

1. Take each axis's declared signals from the stats payload.
2. **Re-measure that behaviour from the corpus directly.** Never derive ground truth from
   the tool's own aggregates; a comparison against itself proves nothing.
3. Report the gap **and its direction**: faithful, overestimates, underestimates.

Use `scripts/` where a check exists. Where none does, reason from the declared signals:
that is the case scripts cannot cover.

## Phase 2 — Structural shapes

Formula-independent. Each is a `shape` key in the output; see
`references/output-schema.md`.

| shape | Look for |
|---|---|
| `dropped-term` | Terms renormalized away for lack of evidence — invisible, and they change what the number means |
| `saturated` | Axes at their ceiling, which no longer discriminate |
| `contaminated-denominator` | Divisor content the person did not produce |
| `signal-not-attributable-to-person` | Counters driven by the harness or a config rule |
| `signal-reused` | One counter feeding two axes or two pillars |

## Phase 3 — Refute. Gate.

**Nothing is reported until it survives every row.** Each one killed a real finding.

| Try to refute | The scar |
|---|---|
| Does the window or corpus explain it, rather than the code? | "ToolSearch appeared July 1" — the corpus started July 1 |
| Is the denominator theirs, or one you invented? | "93% coverage" — 34% under their own eligibility rule |
| Is the operationalization the fairest, or the flattering one? | "Recovery 46.8%" — 90.2% measured properly |
| Have you already conceded the opposite? | a denominator proposal already withdrawn in writing |
| Do the paths and refs you checked still exist? | "13% have tests" — it was reading deleted worktrees |
| Without the control, does the zero prove anything? | base rule for every synthetic fixture |

Survivors become findings. The rest go to `dismissed` with the fact that killed them, so
nobody reopens them. Worked examples: `references/refutation.md`.

## Phase 4 — Emit

Write `miraudit-<date>.json`, then render `miraudit-<date>.md` **from it**. Two
hand-written sources drift, and a report that drifted from its evidence is the defect this
skill catches.

Report only findings carrying a reproducible command and a control that passed. **An empty
`findings` with a populated `dismissed` is a good result.**

## Never

- **Write inside the audited repository.** Patch a throwaway copy.
- **Ship a fixture without a control**, a case that must come out non-zero. Otherwise a
  zero may just be a broken fixture.
- **Invent a denominator.** Find their predicate.
- **Recommend an action whose only purpose is moving the number.**
- **State a claim that could vary as a fact.** Mark it a hypothesis.
- **Write "only", "never" or "always"** without running the enumeration that would falsify
  it. Too expensive? Weaken the claim.
