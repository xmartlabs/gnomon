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
allowed-tools: Bash(python3 *) Bash(uv *)
---

# miraudit

Audits a score someone else's code computed about your work. It does not compute a score,
propose formula changes, or rank anyone.

**Does the number measure what this person actually does?** That question survives the
formula changing, so findings are shapes of infidelity, not a list of known bugs. Resolve
this skill's directory once and prefix every script call.

<investigate_before_measuring>
Never claim an axis is unfaithful without having run the measurement. Never cite a file:line
you have not opened. Never report a number you did not produce in this run. An unrun check
is not evidence.
</investigate_before_measuring>

## Phase 0 — Anchor. Gate.

1. Compare the installed version to `references/known-state.md`. **The contract string is
   the gate; the commit is a hint.** A different contract invalidates every finding below
   it. A different commit with the same contract needs one look at the diff: if it misses
   scoring, taxonomy and the accumulator, say so and carry on. Invocation and traps live
   there too, because they expire and this file should not.
2. Reproduce the published number on a **copy** of the checkout, over **the report's own
   window**. A window ending *now* drifts daily and includes the audit session itself.
3. **If the base run does not reproduce it, stop.** The method is wrong before any finding.
   Give `scripts/anchor.sh` the `--published` and `--expect-contract` values so it stops on
   its own. Omit them and it prints the number and asks you to compare, which is where the
   gate leaks: this step read as enforced for a long time while nothing enforced it.
4. Print the corpus fingerprint — files, lines, tool calls, sources, window — before any
   other number. Counts compared across machines mean nothing without it.
5. Pass that same end date to every check in `scripts/`, or they measure days the report
   does not.

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

`saturated` is the one shape a single corpus cannot settle — it cannot separate a pinned axis
from a person who clears every bar. Report it as a hypothesis until a second corpus confirms
it; the protocol and its decision rule are in `references/second-corpus.md`.

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
| Did your own tooling reshape the evidence first? | "it counts a bare `cd` as a test run" — the display had truncated the command |
| Several conditions can cause this. Does neutralizing **one** leave it unchanged? | "the routing term is dropped by Workflow children" — removing them alone did not restore it |

Survivors become findings. The rest go to `dismissed` with the fact that killed them, so
nobody reopens them. Worked examples: `references/refutation.md`.

## Phase 4 — Emit

Write `miraudit-<date>.json`, then render `miraudit-<date>.md` **from it**. Two
hand-written sources drift, and a report that drifted from its evidence is the defect this
skill catches.

Report only findings carrying a reproducible command and a control that passed. Confirmed
but already sent goes to `reported`; what the audit itself cost you goes to
`process_friction`. **An empty `findings` with a populated `dismissed` is a good result.**

## Never

- **Write inside the audited repository.** Patch a throwaway copy. The specific way this
  happens: running the entry point without `--output-dir` writes `stats.json`, `report.md`,
  `summary.json`, `narrative_input.md` and `profile.html` into the project directory. All
  five are gitignored there, so `git status` stays clean and the write is invisible. **Check
  with `ls`.** A rule you can follow in good faith and break anyway needs its case named.
- **Ship a fixture without a control**, a case that must come out non-zero. Otherwise a
  zero may just be a broken fixture.
- **Rewrite a predicate or a constant you could import.** Yours drifts from theirs, and then
  the gap you report is your own: a hand-rolled test regex read 28% where their predicate
  read 34%. Hardcoded, a check also keeps printing confidently after its subject is gone.
- **Recommend an action whose only purpose is moving the number** — connecting MCP servers
  nobody will use, splitting one edit into five because the counter increments per call.
  The score is a description; an audit that teaches people to decorate it has destroyed
  what it measured. If a suggestion only makes sense because someone is watching, cut it.
- **Report a finding as an improvement opportunity.** A gap between the number and the
  behaviour is a defect in the measurement, not a to-do list for the person measured.
- **State a claim that could vary as a fact.** Mark it a hypothesis.
- **Write "only", "never" or "always"** without running the enumeration that would falsify
  it. Too expensive? Weaken the claim.
