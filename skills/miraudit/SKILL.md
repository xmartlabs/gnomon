---
name: miraudit
description: >
  Audits whether a score computed about your own work actually reflects what you did, and
  reports gaps with executable proof and a control. Use when a metric looks wrong,
  unexplained, or moved without a reason — "my score dropped", "the metric is wrong",
  "this doesn't reflect what I do", "why does it say that", "mi score bajó", "la métrica
  está mal", "esto no refleja lo que hago" — or when auditing a gnomon / xl-ai-insights /
  AQ report, an engineering dashboard, or a productivity scorecard.
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

0. **Run the self-check first.** It is offline, needs no corpus, costs no tokens and takes
   seconds, and it is the only thing that tells you the tooling you are about to audit *with*
   is intact:

   ```
   python3 selfcheck/run.py --checkout <a checkout of the audited tool>
   ```

   It prints its own totals and names anything it skipped; without `--checkout` the tier that
   needs one is skipped, and a skipped check is not a passed one. No count is written down
   anywhere on purpose — the battery grows, and a number in a document is a second declaration
   that goes stale and then cannot tell a grown battery from a half-skipped one. Any failure
   stops the run: a red here means a finding you produce later is about your own tool.

1. Compare the installed version to `references/known-state.md`. `pin-consistency.py` reads
   the pin block for you, so open the file for two things: the invocation traps, and the
   "reviewed and dismissed" list, which is what stops a run re-raising something already
   dead. Its refresh procedure and its version history are for re-pinning and cost a run
   nothing. **The contract string is the gate; the commit is a hint.** A different contract invalidates every finding below
   it. A different commit with the same contract needs one look at the diff: if it misses
   scoring, taxonomy and the accumulator, say so and carry on. Invocation and traps live
   there too, because they expire and this file should not.
   A matching contract is not enough on its own: `scripts/contract-probe.py` asserts that
   the predicates still *behave* the same, which is the failure a version string cannot
   express. `anchor.py` runs it before the pipeline.
2. Reproduce the published number on a **copy** of the checkout, over **the report's own
   window**. A window ending *now* drifts daily and includes the audit session itself.
   **Let `anchor.py` make that copy; do not run the pipeline yourself against a working
   checkout.** A run did, read a contract four commits ahead of the pin, and gated its whole
   audit on drift it had introduced. `emit-gate.py` compares `tool.measured_ref` --
   the ref the pipeline actually ran against -- to the pin now, but the cheaper place to not
   do this is here. Note which field: the older `tool.ref` rule reads the pin on **both**
   sides, because `anchor.py` filled that field from the pin block, so it was equal by
   construction and never caught anything. A cold run measured a clone twelve commits behind
   the pin and passed clean.
   **Run it in the foreground and let the call return.** It takes about 90 seconds. Do not
   background it and then wait on a notification: if you are a subagent, none arrives. A run
   lost its entire audit that way, printing `waiting` while the `stats.json` it was waiting
   for had already been written correctly.

   This is about backgrounding a **shell command**, and it is not the rule about dispatching
   a **child agent** -- there, ending your turn is correct and the child's result is
   delivered back to you. Two different mechanisms; neither refutes the other. Nothing in
   this skill dispatches an agent anyway: `allowed-tools` grants Bash and nothing else, and
   the parallelism lives inside the Python.
   The reverse direction is also real: when something else dispatches THIS skill as a
   subagent, whoever dispatched it can fill `run_cost.agent` in the payload from the
   completion notification's `<usage>` block, or by running `scripts/agent-cost.py` against
   the run's own transcript file if it has access to it -- see `references/output-schema.md`.
3. **If the base run does not reproduce it, stop.** The method is wrong before any finding.
   Give `scripts/anchor.py` the `--published` and `--expect-contract` values so it stops on
   its own. Omit them and it prints the number and asks you to compare, which is where the
   gate leaks: this step read as enforced for a long time while nothing enforced it.
   **A null anchor is normal and has to say so.** Where no published figure exists at the
   pinned contract there is nothing to gate the number against, and `emit-gate.py` asks for
   the reason rather than the pass: a file whose `anchor.ok` is not `true` and whose
   `findings[]` is not empty needs a non-empty `anchor.note`. `anchor.py` leaves an
   `anchor.json` beside the payload so Phase 4 reads what Phase 0 resolved instead of
   deriving it again.
4. Print the corpus fingerprint — tool calls, sessions, sidechain share, sources, window —
   before any other number. Counts compared across machines mean nothing without it. File
   and line totals are printed beside it and are **not** part of it: they count every
   transcript on disk rather than the window, so they drift while you work. Two runs four
   hours apart on one machine and one fixed window read 260,129 lines against 262,456 with
   every windowed number identical.
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
   **That JSON comes from Phase 4, and the order is: `new-run.py`, fill `axes[]`, re-run this
   with `--run`, then render.** Read without that sentence the two phases contradict each
   other, since `--run` wants a file only a Phase 4 script creates; a cold run lost minutes
   deciding whether the manifest had to be green before the skeleton existed. It does not.
   Step 0 runs on nothing and tells you what is uncovered; this step runs at the end and tells
   you what went unrecorded.
5. **`scripts/axis-terms.py` goes a level lower**, because an axis can be covered while a
   term inside it is invisible — which is where the one hard finding lived. It rebuilds each
   axis from the terms in the scoring source and lists those absent from `signals`. What it
   emits are candidates for Phase 3, never findings.

**`scripts/run-checks.py` runs them all at once** and writes the same `<check>.out` files,
because they are independent read-only processes and doing them one at a time is a habit.
It builds its list from the same `# miraudit-covers:` grep the manifest uses, so a check
cannot be missing from the run while still looking covered, and it names what it skipped for
want of a flag — a skipped check is not a passed one. Ad-hoc checks go in with `--also`, and
it exports `MIRAUDIT_SCRIPTS` for them so their import of `_common.py` resolves from a run
directory that sits nowhere near the skill. Pass `--emit <run>/checks/run-checks-emit.json`
(and `run-arms.py --emit <run>/run-arms-emit.json`, when an A/B runs) so Phase 4's
`render-report.py` can fill `run_cost.checks`/`adhoc_checks`/`arms` itself instead of that
number never getting filled at all, which is what happened to every saved run before this.
Iterating on one `--also` check without re-running the whole battery each time takes
`--only <name>` — see `references/output-schema.md`.

**`verification-reality.py` runs either way, and `--repo` adds its file-level half.** Without
the flag it does the session-level pass and prints a by-repository table. **Read that table
before choosing**, and read `repo_of` in the script before trusting a row: they are labels,
not paths, so the busiest one is regularly `agent config`, meaning `~/.claude`, or a directory
holding many checkouts. Skip those and pass the busiest row that is one repository. There is
no representative repo and the check does not average them.

Use `scripts/` where a check exists, and expect the unscripted path to be normal rather
than exceptional. **How many axes that is, and which, comes from the manifest — never from
this file.** The list was prose once, was wrong about an axis for as long as it existed,
and the fix that replaced it with a corrected count went stale the next day. Its procedure
is `references/ad-hoc-checks.md`, with a worked example beside it; the short version is
that you write a runnable script into the run's output directory, import the tool's own
primitives, print both numbers with a direction, and carry a control. **That short version
is enough unless you are actually writing one** — a run whose manifest already comes back
covered has no reason to open it.

An agent conceives that measurement; the machine runs it; the number decides. What leaves
the run is a file anyone can re-run, never a verdict. `references/design-rationale.md`
argues why that division is the only place an agent belongs in this skill. It is an
argument, not a procedure: read it to challenge the design, not to follow it.

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
it; the protocol and its decision rules are in `references/second-corpus.md`. **The rules are
its first section and the rest is the record of corpora**, which answers "what did other
machines show" and not "how do I audit this one". Grep it for the rule you need rather than
reading it through: it is the largest file here by a wide margin.

**Several corpora are on record there and what they support is narrow. How many, and which,
comes from that file and never from this one** — a count written here goes stale the day one
arrives, and this paragraph said "two" while five were on record. The AQ delta is zero on
every corpus, but the signals cut are never the same set, so the rule's own third row
applies: report only what is pinned on all of them. That is two signals, and they feed axes
that score identical maxima everywhere. Other axes separate the same people by a wide margin,
so "the score is mostly ceiling" is refuted by the same set that establishes the narrow
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
handed its maintainers two documents with nothing in common. It also derives
`run_cost.gate_retries` on its own, from a log of real gate attempts it writes beside the
payload -- nothing to fill in by hand, unlike `run_cost.agent` above.

The gate reads structure and not honesty. It cannot tell a real refutation from a plausible
sentence, and it says so on every clean run.

**If you edit the JSON after rendering, render again.** Gating at render time proves the file
was clean *then*, and nothing watches it afterwards. A run rendered a valid skeleton, added
its dismissals to the JSON with a script, and never re-rendered: the report on disk was about
an earlier version of that run, and the gate had passed honestly. `render-report.py --check`
answers it — the renderer is deterministic, so it re-renders and compares exactly.

**The gate now also reads `tool.ref` against the pin.** A run that measured a checkout other
than the pinned one has to name that ref in `anchor.note`, because a deliberate re-pin and a
pipeline pointed at the wrong directory produce the same file otherwise. This is not gated on
`findings[]` like the anchor rules are: the axes and the dismissals are about that ref too,
and an empty-findings run publishes both.

Report only findings carrying a reproducible command and a control that passed. Confirmed
but already sent goes to `reported`; confirmed and deliberately not sent goes to
`not_raised` with the reason and the condition that would reopen it; what the audit itself
cost you goes to `process_friction`. **An empty `findings` with a populated `dismissed` is a
good result.**

6. **Read what earlier runs already declared, and only now.** `emit-gate.py` compares this
   payload against `references/blind-spots.json` and prints what you did not touch. It refuses
   the run when an entry names a reopening condition your own corpus already meets: sixteen
   runs re-declared one hole as open while carrying the observation that would have closed it.

   **Phase 4 and nowhere earlier, on purpose.** A cold run that read a list of holes during
   Phase 0 reported that it anchored the whole investigation before a single measurement
   existed. `scripts/blind-spots.py` has no browse mode for the same reason — it answers what
   your finished payload missed, and cannot be asked what the holes are.

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
