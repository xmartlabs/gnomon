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
  Requires python3, git and uv, and no shell: the orchestration is Python, so PowerShell
  and CMD are fine and Git Bash is not needed. Reads the agent transcript corpus and a
  checkout of the scoring tool; writes only inside its own output directory.
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
   A matching contract is not enough on its own: `scripts/contract-probe.py` asserts that
   the predicates still *behave* the same, which is the failure a version string cannot
   express. `anchor.py` runs it before the pipeline.
2. Reproduce the published number on a **copy** of the checkout, over **the report's own
   window**. A window ending *now* drifts daily and includes the audit session itself.
3. **If the base run does not reproduce it, stop.** The method is wrong before any finding.
   Give `scripts/anchor.py` the `--published` and `--expect-contract` values so it stops on
   its own. Omit them and it prints the number and asks you to compare, which is where the
   gate leaks: this step read as enforced for a long time while nothing enforced it.
4. Print the corpus fingerprint — files, lines, tool calls, sources, window — before any
   other number. Counts compared across machines mean nothing without it.
5. Pass that same end date to every check in `scripts/`, or they measure days the report
   does not.

## Phase 1 — Per-axis fidelity

0. **Run `scripts/axis-coverage.py` first.** It lists every scored axis, which ones a check
   claims, and which the run is about to skip. It exits non-zero while any is unaccounted
   for, so "no script exists" can no longer pass for "nobody looked". It also reports axes
   present in the scoring source and **absent from the payload**, which is the `dropped-term`
   shape of Phase 2 arriving for free.
1. Take each axis's declared signals from the stats payload.
2. **Re-measure that behaviour from the corpus directly.** Never derive ground truth from
   the tool's own aggregates; a comparison against itself proves nothing.
3. Report the gap **and its direction**: faithful, overestimates, underestimates.
4. **Re-run it with `--run <your JSON>` before emitting.** A tag says a script claims an
   axis; it does not say anybody recorded a gap, a direction and a control. Reported the
   first way, a run once verdicted "11 of 11" while its own artifact held six.
5. **`scripts/axis-terms.py` goes a level lower**, because an axis can be covered while a
   term inside it is invisible — which is where the one hard finding lived. It rebuilds each
   axis from the terms in the scoring source and lists those absent from `signals`. What it
   emits are candidates for Phase 3, never findings.

Use `scripts/` where a check exists, and expect the unscripted path to be normal rather
than exceptional. **How many axes that is, and which, comes from the manifest — never from
this file.** The list was prose once, was wrong about an axis for as long as it existed,
and the fix that replaced it with a corrected count went stale the next day. Its procedure
is `references/ad-hoc-checks.md`, with a worked example beside it; the short version is
that you write a runnable script into the run's output directory, import the tool's own
primitives, print both numbers with a direction, and carry a control.

An agent conceives that measurement; the machine runs it; the number decides. What leaves
the run is a file anyone can re-run, never a verdict. `references/design-rationale.md`
argues why that division is the only place an agent belongs in this skill.

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
it; the protocol and its decision rules are in `references/second-corpus.md`.

**Two corpora are on record there, and what they support is narrow.** The AQ delta was zero
on both, but the signals cut were not the same set, so the rule's own third row applies:
report only what is pinned on both. That is two signals, and they feed the two axes that
scored identical maxima on both. Five other axes separate the two people by a wide margin,
so "the score is mostly ceiling" is refuted by the same pair that establishes the narrow
claim. Quote the narrow one.

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

**This table is data, not prose.** Every finding carries a `refuted` block with one entry
per row and a verdict in `pass` / `fail` / `n/a`, and `scripts/emit-gate.py` refuses the
file if a row is unanswered or if any row is `fail` — a `fail` means it did not survive,
and what did not survive is not a finding. The rows were prose until a cold run, with this
file open, promoted a candidate whose own evidence said the fixture was the whole result.
Nothing chirped; a person asking "is that verified?" caught it. That is the check that must
not depend on someone remembering.

## Phase 4 — Emit

Start the file with **`scripts/new-run.py`**, which prefills `tool`, `anchor` and
`corpus` from the anchored run and prints the eight refutation rows you will have to
answer. Retyping those numbers is mechanical work that fails silently. Then run
**`scripts/render-report.py`** on it. That script
gates the file with `emit-gate.py` and writes the markdown only if the gate exits 0, so the
two cannot be done out of order or the second done without the first. Do not hand-write the
markdown and do not write your own renderer: two hand-written sources drift, and a report
that drifted from its evidence is the defect this skill catches. The one that shipped before
this script existed was invented per run, which meant two people auditing the same tool
handed its maintainers two documents with nothing in common.

The gate reads structure and not honesty. It cannot tell a real refutation from a plausible
sentence, and it says so on every clean run.

Report only findings carrying a reproducible command and a control that passed. Confirmed
but already sent goes to `reported`; confirmed and deliberately not sent goes to
`not_raised` with the reason and the condition that would reopen it; what the audit itself
cost you goes to `process_friction`. **An empty `findings` with a populated `dismissed` is a
good result.**

## Phase 5 — Send. Optional, and often correct to skip.

The report is a file. It becomes a message to a person only here, and this phase exists
because the skill used to end at Phase 4 and leave somebody holding a confirmed finding with
nowhere to put it.

**Only `findings[]` goes.** That list already means "survived every row", which is the whole
claim you make when you spend a maintainer's time. `not_raised` does not go, by definition.
`process_friction` never goes: it is about your tooling. If `anchor.ok` is false, nothing
goes at all.

**`scripts/render-issue.py` assembles the draft** from `findings[]` and refuses when
there is nothing to send, when the anchor failed, or when a finding lacks a field the
structure needs. It leaves visible markers where judgement is required and counts
them, so a half-filled draft cannot pass for a finished one. Do not hand-copy the
skeleton: that is how the format degrades from one person to the next.

`references/reporting.md` has the shape and the reasoning behind it. The short version is
that a question about intent gets answered while a bug report gets defended, that provenance
goes before the first number, that every figure is a published field of their payload or a
derivation you state, and that each claim carries the command that reproduces it, the
control, the blind spots, and what would close it.

**Read what you are about to publish before you publish it.** A report quotes paths, session
ids and repository names out of your corpus, and a public issue is a poor place to find that
out.

## Never

- **Write inside the audited repository.** Patch a throwaway copy. The specific way this
  happens: running the entry point without `--output-dir` writes `stats.json`, `report.md`,
  `summary.json`, `narrative_input.md` and `profile.html` into the project directory. All
  five are gitignored there, so `git status` stays clean and the write is invisible. **Check
  with `ls`.** A rule you can follow in good faith and break anyway needs its case named.
- **Assume you are running the copy because you pointed a flag at it.** `uv run --project`
  supplies the environment, not the code: with `python -m`, the module comes from the
  working directory. Runs of this skill measured the read-only clone for a long time and
  reported the right number, because the clone is the pinned commit. Use the packaged
  console script, which cannot be shadowed that way.
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
