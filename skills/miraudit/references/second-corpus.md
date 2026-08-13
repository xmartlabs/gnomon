# Running it on a second corpus

One corpus cannot tell **"the axis saturates"** from **"this person clears every bar."**
That sentence is printed by `scripts/saturation-counterfactual.py` itself, under
`NOT CHECKED`, and it is the reason this document exists. A run on one machine produces a
hypothesis; the same gap measured on a second, independent corpus is what turns it into a
statement about the axis.

This is the one thing the audit cannot do for itself. Everything else here is code.

## The decision rule, stated before the data

Fix the rule first, so the second run cannot be read to mean whatever the first one wanted.
Corpus **A** is the run already in hand; **B** is the new one.

### 0. The PowerShell before/after, written before the after exists

Contract `18:18:18` scores `PowerShell` as a shell, so re-running a Windows corpus first
measured at `17:17:17` is a before/after on one person, one window and one machine. Corpus E
is the only such corpus on record, and it is **Bash 42.94% against PowerShell 1.45%**: a
Windows developer working in Bash, not the PowerShell-primary person upstream asked for. Say
that when reporting it. A small movement here is not evidence that the fix is small for the
person it was written for.

Its before is Tool command 21.0/28 with `clis` 28, Token economy 50.0/50 with `cli_share`
0.97, and Grounding 25.0/25.

| What the after shows | What it means |
|---|---|
| Token economy or Grounding rise | Impossible as stated: both already sit at their ceiling, so this would mean the before was misread and the comparison is void |
| Tool command rises | PowerShell surfaced CLI heads `clis_distinct` was not counting. The only one of the three with headroom, so the only one that can carry a signal |
| Nothing moves | The fix is worth nothing to a Bash-primary Windows developer. Report exactly that. It bounds the common Windows case instead of answering the open question |

The open question is unchanged either way: nobody has measured a corpus where PowerShell is
the primary shell, and `#75` is still an argument from the formula rather than from data.

**The after arrived, and the rule fired as written.** Same person, same window, `03b87a0` /
`18:18:18`. Tool command **21.0 to 21.4**, `clis` **28 to 29**: PowerShell surfaced exactly
one CLI head that was not being counted. Token economy and Grounding did not move, both
already at their ceiling, which is the row that says they could not.

Two other axes moved and **neither is the fix**, which is only visible because all eleven
were compared rather than the three the rule names. The corpus is not identical between the
runs: same window, but 125 sessions against 122 and 27,527 tool calls against 27,423, three
sessions having aged out of a rolling retention window between one run and the next.

| axis | move | what its own signals say |
|---|---|---|
| Tool command | +0.4 | `clis` rose while `tool_calls` fell. A shrinking corpus cannot add a distinct CLI, so the direction rules the corpus out |
| Verification | +0.3 | `test_covered_change_sessions` held at 51 while `eligible_change_sessions` fell 60 to 59. 51/60 = 0.8500 and 51/59 = 0.8644, reproducing both published values. The denominator moved, not the work |
| Recovery | −0.1 | `api_retries` 130 to 129 |

Verification not being the fix is also what upstream said to expect: `bash_runs_tests`,
`bash_writes_file` and `bash_runs_knowledge` parse bash syntax, so Verification coverage
stays Bash-only until there are PowerShell-aware predicates, and a test pins that limit.

So the honest headline is **+0.4 of 28 on one axis for a Bash-primary Windows developer**,
and that bounds the common Windows case rather than answering the question upstream asked.

### 1. `aq-is-mostly-ceiling` — read `saturation.delta` and `saturation.signals_cut`

| What B's at-threshold arm does | What it means | What happens to the finding |
|---|---|---|
| Does **not** move, same signals cut | Two independent people sit above the same thresholds | `aq-is-mostly-ceiling` is a defect in the axes. Raise it. |
| **Moves** | The headroom is doing work for B; A's plateau describes A | Withdraw the finding to `hypothesis`. What is left is a calibration question about the targets, not a fidelity claim. |
| Moves for some signals, not others | Saturation is per-signal, not global | Report **only** the signals pinned on both. A signal pinned on A alone is not evidence about the axis. |

### 2. Does Grounding discriminate? — read `profile.explore_to_doing`

On corpus A the scored ratio sits at 1.10 to 1.15 across model families whose exploration
tool calls per session differ by 2.2x, and the axis saturates at 1.0. Whether that is an
axis failing to separate people, or one person exploring consistently, is exactly what a
second corpus decides.

**Read the SCORE, not only the ratio.** The axis is `sat(ratio, 1.0)`, so everything at or
above 1.0 is the same 25/25 and the ratio stops carrying information past the ceiling. Two
people at 1.13 and 0.98 are not on opposite sides of anything: they score 25,0 and 24,5.

| B's ratio | What it means | What happens |
|---|---|---|
| **0.90 or above** | Both sit at or within a hair of the ceiling, which is where the axis stops separating anyone | The axis does not discriminate **in this range**. Worth raising, with both ratios and both scores. |
| Below 0.75 | The ratio separates people; A's value describes A | Nothing to raise. Say so. |
| 0.75 to 0.90 | Genuinely in between | Report the pair, claim nothing. |
| Any of the above, but with a very different `grounding.thinking_share` | The ratios agree for different reasons | The composition is the story, not the ratio. Report both, claim neither. |

**This band exists because the first version had none, and B landed in the gap it left.**
The original cut hard at 1.0: at-or-above raised the finding, below withdrew it. B came in at
**0.974** — 2.6% under the line, scoring 24,5/25. By the letter, withdraw; by the effect,
indistinguishable from A. A rule written to stop motivated reading had a boundary that made
either reading arguable, which is the same failure as having no rule.

So the band was written **before a third corpus existed**, exactly as the original was, and
B is scored against it. Anyone re-reading this should know that order: the rule was widened
after seeing one value it could not classify, and not after seeing a value it classified in
a way somebody disliked. If a third corpus lands at 0.80, this table stays as it is.

### 3. Is the thinking share structural? — read `grounding.thinking_share`

A reads 0.81. **This is the rule that can kill the Grounding write-up**, which is why it is
written down before B exists.

| B's share | What happens |
|---|---|
| 0.70 to 0.90 | Structural rather than personal. The write-up holds and gains a second data point. |
| Below ~0.50 | It is a property of how A works, not of the axis. **Withdraw the write-up**, and say in the same message that a second corpus is what withdrew it. |
| In between | Report the range and stop calling it dominant. Two points are not a distribution. |

### 4. Does the steering band separate anyone? — read the Steering leverage axis

The band is 5 to 20 actions per instruction, and the term is withheld upstream pending
validation. A reads 6.4, inside it.

| B's value | What it means |
|---|---|
| Also inside 5 to 20 | Two of two inside a band four times as wide as it is deep says little. Record it; do not raise it. |
| Outside | The band does discriminate, and withholding it costs a real signal. Worth telling them, since that validation is what they are waiting on. |

Two corpora is the minimum, not the target. Three or more is what makes the per-signal
column readable. None of these rules produces a finding on its own: they produce a second
data point, and anything built on it still goes through the Phase 3 gate.

Conditions for B to count at all:

- **`tool.contract` must match A's.** Comparing a `16:16:16` run against a `17:17:17` run is
  not a comparison: PR #66 removed `TOOLSEARCH_PER_CALL_TARGET`, `TEST_RUNS_PER_CALL_TARGET`
  and `TASK_CALLS_PER_CALL_TARGET`, three rather than the two an earlier version of this file
  claimed, so signals the counterfactual cuts stop existing. `second_corpus.py` pins the
  clone to one commit precisely so this cannot drift between runners.
- **`anchor.ok` may be `null`, and that is not the same as `true`.** It is `true` only when
  the runner passed the number their own report shows. Most runners have no published report
  to match, so the field records "nobody checked" rather than pretending. A `false` is
  disqualifying; a `null` means the run is usable for composition and shape but carries no
  reproduction guarantee, and the write-up has to say so.
- **The window is each runner's own**, not a shared one. The default is the last 30 complete
  days, ending yesterday so the audit session is not measuring itself while it is still being
  written.
- **Both runs must come from the local CLI, never from the dashboard.** The mirdash
  deployment lags the contract: one run whose local output was AQ 91 on `17:17:17` showed
  97 on the web, in an older layout with fewer Craft axes. This is also why the number is no
  longer part of the ask — sending someone to read their AQ sends them to the wrong number.

## Corpora on record

| | A | B | C | D | E |
|---|---|---|---|---|---|
| window | 07-07→08-06 | 07-11→08-10 | 07-12→08-11 | 07-12→08-11 | 07-12→08-11 |
| contract | `17:17:17` | `17:17:17` | `17:17:17` | `17:17:17` | `17:17:17` |
| schema | — | `comparison-2` | `comparison-1` | `comparison-2` | `comparison-2` |
| `anchor.ok` | `null` | `null` | `null` | `null` | `null` |
| platform | macOS | macOS | macOS | macOS | **Windows** |
| tool calls | 42.874 | 5.862 | 42.003 | 3.702 | 25.677 |
| sessions | 125 | 49 | 281 | 30 | 125 |
| project roots | 20 | 15 | **74** | 14 | 39 |
| sources scored | claude | claude | claude, codex | claude | claude |
| sidechain share | 0,626 | 0,358 | 0,669 | 0,458 | 0,460 |
| Bash share | 0,631 | 0,663 | 0,426 | **0,384** | 0,429 |
| `explore_to_doing` | 1,124 | 0,974 | 1,439 | 1,469 | 1,435 |
| ... without thinking | 0,219 | 0,193 | 0,722 | 0,624 | 0,505 |
| `thinking_share` | 0,806 | 0,802 | 0,708 | **0,590** | 0,656 |
| AQ | 92 | 82 | 93 | 87 | **95** |

**Every column above is `17:17:17`, and the pin this skill ships is `18:18:18`.** Somebody
installing it today cannot reproduce a single comparison in that table with the checkout
`known-state.md` hands them. The table is not wrong; it is closed. Read it as the record of
a contract that has moved, and put new corpora in the table below.

### On `18:18:18`

`tool.contract` must match for two corpora to be compared, so these do not go in the table
above. Three exist, and **F is the first that is not a re-run of a corpus already up there**:
a different person, their own window, and the smallest of the three.

| | A | E | F |
|---|---|---|---|
| window | 07-12→08-11 | 07-12→08-11 | 07-13→08-12 |
| contract | `18:18:18` | `18:18:18` | `18:18:18` |
| ref | `03b87a0` | `03b87a0` | `03b87a0` |
| schema | `comparison-2` | `comparison-2` | `comparison-2` |
| `anchor.ok` | `null` | `null` | `null` |
| platform | macOS | **Windows** | macOS |
| tool calls | 40.896 | 25.573 | 5.589 |
| sessions | 101 | 122 | 50 |
| project roots | 21 | 39 | **6** |
| sources scored | claude | claude | claude |
| sidechain share | 0,609 | 0,462 | 0,434 |
| Bash share | 0,639 | 0,430 | 0,586 |
| `explore_to_doing` | 1,080 | 1,400 | 1,103 |
| ... without thinking | 0,199 | 0,493 | 0,348 |
| `thinking_share` | 0,815 | 0,656 | 0,685 |
| `steering.actions_per_prompt` | 7,0 | 8,7 | 8,4 |
| AQ | 91 | **95** | 82 |

**A moved 92 → 91 and that is not a decline**, it is a different window on a different
contract: A's `17:17:17` column is 07-07→08-06 and this one is 07-12→08-11. E is the pair
worth reading, because it is the same window on both contracts — rule 0 holds its
before/after, and what moved was the axis PowerShell touches.

**F and B both score 82 and are not the same person.** The contributor says so, and the
profile says the same thing without being asked: 6 project roots against B's 15, `Read` at
0,216 against 0,120, `thinking_share` 0,685 against 0,802, and B's `TaskUpdate`, `TaskCreate`
and `StructuredOutput` all absent from F's top ten. Their windows overlap on 28 of 30 days,
so carrying that difference on the four days they do not share needs at least 895 tool calls
and 9 project roots living exclusively inside two of them. Two people landing on the same
total is what a score with five pinned axes looks like from outside; it is not evidence of a
shared corpus, and it was worth ruling out rather than assuming either way.

**What three corpora pin, which one could not.** `steering.axis_present_in_payload` is
`false` on all three and `band_validated` is `false` on all three, so the Steering leverage
axis is withheld for everyone rather than for one person's setup — 50 of the Efficiency
pillar's 100 base points, dropped and renormalized onto Recovery. And all three sit INSIDE
the unvalidated band [5, 20], at 7,0 / 8,7 / 8,4, so on this evidence the withholding costs
points rather than saving them. What none of them can settle is whether any artifact a person
reads says the term was withheld: that is a property of the renderer, and the comparison
payload does not capture it.

#### The rules, re-run inside this contract

Extending the `17:17:17` findings by one column would break the admission rule this file
opens with, so the rules are run again on the three, and what they decide here is stated
separately from what they decided there.

**Rule 1 — row 3 again, and the surviving pair is the same pair.** Delta 0 on all three
(91→91, 95→95, 82→82), controls moved on all three (68/54, 69/55, 65/53), `not_cuttable` the
identical list. Signals cut: 11 / 10 / 6, never the same set, so row 1 never applies and row 3
always does. Above threshold on all three, with every anchor resolved against `03b87a0`:

| señal | A | E | F | eje |
|---|---|---|---|---|
| `cli_calls` | 11,42× | 13,96× | **16,84×** | Token economy (`aq.py:609-610`) |
| `evidence_eligible_sessions` | 1,67× | 1,67× | 1,67× | Context Intelligence (`aq.py:503`) |
| `compounding_writes` | 2,67× | 18,04× | 1,40× | Compounding (`aq.py:515`) |
| `planned_eligible_sessions` | 1,84× | 1,63× | 1,10× | Discipline (`aq.py:350`) |
| `planning_ratio_explore_to_doing` | 1,08× | 1,37× | 1,11× | Grounding (`aq.py:484`) |

**Five rows on three corpora is weaker than two rows on four, and the direction is the
trap.** An intersection only shrinks as corpora arrive, so a longer list here means fewer
people have been measured at this contract, not more agreement. Three of these five are on
the list because nobody outside this group has run `18:18:18` yet. The two that also survived
four corpora at `17:17:17` are the two that two independent sets agree on, and those are the
ones to quote.

**Rule 2 — fires again.** 1,080 / 1,400 / 1,103, all at or above the 0,90 band, all scoring
25,0/25. The 51% spread the `17:17:17` set showed is reproduced inside this one and still
buys nobody a point.

**Rule 3 — F lands in the rule's middle row, beside E.** `thinking_share` reads 0,815 /
0,656 / **0,685**. The composition claim holds: thinking blocks are a majority of the
numerator on all three. The magnitude does not, and the factor between them is three:

| | ratio | without thinking | Grounding | would score | loses |
|---|---|---|---|---|---|
| A | 1,080 | 0,199 | 25,0/25 | 5,0 | 20,0 |
| E | 1,400 | 0,493 | 25,0/25 | 12,3 | 12,7 |
| F | 1,103 | 0,348 | 25,0/25 | 8,7 | 16,3 |

**Rule 4 — recorded, not raised**, for the third time and for the same reason: 7,0 / 8,7 /
8,4 is a third of a band four times as wide as it is deep.

#### Axis by axis, and why F is the useful one

These are published scores read directly, no rule involved.

| eje | A | E | F | max | spread |
|---|---|---|---|---|---|
| Orchestration | 33,0 | 33,0 | **20,3** | 33 | 12,7 |
| Verification | **19,3** | 31,9 | 26,7 | 35 | 12,6 |
| Skill fluency | 20,6 | 22,0 | **11,0** | 22 | 11,0 |
| Tool command | 20,7 | 21,4 | **10,7** | 28 | 10,7 |
| Recovery | 97,1 | 91,3 | 91,2 | 100 | 5,9 |
| Discipline | 17,0 | 17,0 | 12,5 | 17 | 4,5 |
| Compounding | 20,0 | 20,0 | 20,0 | 20 | 0,0 |
| Context Intelligence | 20,0 | 20,0 | 20,0 | 20 | 0,0 |
| Grounding | 25,0 | 25,0 | 25,0 | 25 | 0,0 |
| Model mix | 50,0 | 50,0 | 50,0 | 50 | 0,0 |
| Token economy | 50,0 | 50,0 | 50,0 | 50 | 0,0 |

**Five axes worth 165 of 350 base points are identical to the decimal for all three**, and
they are the same five the `17:17:17` set pinned. F is what makes that worth more than a
repetition: the earlier set was five people scoring 82 to 95, where "everybody is at the
ceiling" and "everybody here is strong" are the same sentence. F scores 10,7 of 28 on Tool
command, 11,0 of 22 on Skill fluency and 20,3 of 33 on Orchestration — under half the axis on
one of them — and still takes the maximum on all five. The axes that do not separate people
do not separate them from someone the rest of the scorecard separates cleanly.

**Skill fluency: the undisclosed term is disclosed now, and F is where that pays off.**
`18:18:18` publishes `process_skills_matched` and `compounding_skills_matched` as diagnostics
that score nothing (`aq.py:395` and `aq.py:561`); neither appears in any `17:17:17` payload in
this file. So `skill-fluency-term.py` now has two independent routes to the same bit, and on
all three payloads the algebra and the diagnostic agree. Its Tool command control reproduced
0,737500 against 0,737500 published on the run that produced this table — a different value
from the 0,654167 quoted further down, because the control is recomputed against whichever
corpus and window the script is pointed at, and it is the equality that matters rather than
the number. What F adds is the case the D reversal could
not supply: F **matched** the names, so its term is 1,0, and it still scores the lowest Skill
fluency in the set because its rate is 0,50× target. A low score is not evidence that the
hidden term missed, which is the inference D's write-up makes easy to draw.

**Context Intelligence: a sixth person at coverage 1,0.** F publishes 20 grounded sessions of
20 eligible, against a target of 0,60. The section below now reads six for six above 98%, and
F is the lowest-scoring corpus on record — so "everyone measured is at 100%" is no longer a
statement about strong corpora only.

**What F does not add.** macOS, `claude` only, and the smallest corpus here. It says nothing
about the PowerShell question, which is what upstream actually asked for and is still
unmeasured.

**D is the one that was worth waiting for.** A different role, the smallest corpus of the
four, and the only one where **Context Intelligence is missing from the payload entirely** —
Craft's remaining three axes carry 100 points of base 80, so Verification reads 44,0/44 and
Grounding 31,0/31. A dropped axis observed in somebody else's run, not inferred from ours.

C arrived 2026-08-12 and is the least like the other two: 74 project roots, a second source
scored, and Bash at 0,43 where A and B sit at 0,63 and 0,66. It is also the only one that
uses `Grep` at all (6,5% of its tool mix), which retires a note carried in this
investigation's own `CLAUDE.md` — `Grep`/`Glob` being unavailable is a property of one
machine's configuration, not of the harness.

B arrived 2026-08-11. **Both files carry `anchor.ok: null`**, for different reasons: B's
runner had no published report to match, and A's comparison was emitted without
`--published`. A's 92 *was* gated separately — the Phase 0 anchor reproduced it against the
published number — but that is a different artifact, and reading `null` as `true` because
somewhere else it passed is exactly the substitution the field exists to prevent. So: usable
for composition and shape, no reproduction guarantee travelling with either file.

The tool-call counts are each emitter's own live count over its window, which is why A reads
42.874 here and 42.508 in its `stats.json`: the same fixed window grows as resumed sessions
gain events timestamped inside it. Compared like for like, both counted the same way.

### What the rules decided

**Axis by axis, which is the part no rule anticipated, and it needs no rule: these are their
own published scores, read directly.** Five axes separate the three people widely — on one of
them B beats A, on two of them C is at the ceiling A is nowhere near — and five are pinned at
the top for all three.

| eje | A | B | C | max | spread |
|---|---|---|---|---|---|
| Tool command | 18,3 | 12,1 | **28,0** | 28 | 15,9 |
| Orchestration | 33,0 | 19,6 | 29,3 | 33 | 13,4 |
| Discipline | 16,5 | 6,7 | 12,4 | 17 | 9,8 |
| Skill fluency | 21,1 | 15,6 | **22,0** | 22 | 6,4 |
| Verification | 23,0 | **29,2** | 24,6 | 35 | 6,2 |
| Recovery | 97,0 | 91,6 | 95,9 | 100 | 5,4 |
| Compounding | 20,0 | 19,4 | 20,0 | 20 | 0,6 |
| Grounding | 25,0 | 24,5 | 25,0 | 25 | 0,5 |
| Context Intelligence | 20,0 | 20,0 | 20,0 | 20 | 0,0 |
| Model mix | 50,0 | 50,0 | 50,0 | 50 | 0,0 |
| Token economy | 50,0 | 50,0 | 50,0 | 50 | 0,0 |

**Five axes worth 165 of 350 base points sit at or within 3% of their ceiling for all three.**
That statement needs no counterfactual and no decision rule: it is three published payloads
compared. Keep it separate from the signal-level claim below, which is an inference from a
method and is governed by rule 1.

**Rule 1 — row 3, and five corpora have not changed which two.** Delta 0 on all five
(92→92, 82→82, 93→93, 87→87, 95→95), controls move on all five (69/55, 66/54, 69/55,
73/62, 69/55), `not_cuttable` the identical list every time. Signals cut: 10 / 5 / 11 / 7 /
10 — never the same set, so row 1 never applies and row 3 always does.

Above threshold in **all five**, and it is the same pair the two-corpus intersection found.
The anchors are resolved against `03b87a0`, the commit this skill ships, and not against the
`17:17:17` tree the ratios were measured on — a reader can only open the first. Both moved:
`aq.py:484` used to point here and now points at Grounding, which is the way an anchor rots
without going missing.

| señal | A | B | C | D | E | eje |
|---|---|---|---|---|---|---|
| `cli_calls` | 9,61× | 13,53× | 2,34× | 8,81× | 13,47× | Token economy (`aq.py:609-610`) |
| `evidence_eligible_sessions` | 1,67× | 1,67× | 1,64× | 1,67× | 1,67× | Context Intelligence (`aq.py:503`) |

That second row is not headroom, and the section below takes it apart: 1,667 is exactly
`1 / CONTEXT_INTELLIGENCE_TARGET`, so every one of those is a coverage of 1,0.

Eleven other signals are pinned on some corpora and not others, which is what row 3 exists to
filter. `evidence_eligible_sessions` sits at 1,67× on three of the four and 1,64× on the
fourth, which is a tighter agreement than anything else in the table and is worth a second
look rather than a claim.

One wrinkle worth stating: on D, **Context Intelligence is not scored at all** — the axis is
absent from the payload and Craft renormalizes without it. So on D that signal is saturated
while the axis it feeds is dropped. It does not weaken the pair; it does mean "these two
signals feed the two axes at identical maxima" is a statement about A, B and C.

**Rule 2 — fires, and the spread keeps widening while the scores do not.** Five ratios:
0,974 / 1,124 / 1,435 / 1,439 / **1,469**. A 51% spread, and every one of the five scores
sits at or within half a point of its own ceiling. Under the band as written, 0,90-or-above:
the axis does not discriminate in this range.

**Rule 3 — two of five now sit in the middle row.** `thinking_share` reads
0,806 / 0,802 / 0,708 / **0,590** / **0,656**. D and E both land between 0,50 and 0,70, the
rule's **middle** row: *«report the range and stop calling it dominant.»*

So the range is reported and the word is dropped. It is **59% to 81%** across five people,
not "80%", and the consequence varies by a factor of three:

| | ratio | without thinking | Grounding | would score | loses |
|---|---|---|---|---|---|
| A | 1,124 | 0,219 | 25,0/25 | 5,5 | 19,5 |
| B | 0,974 | 0,193 | 24,5/25 | 4,8 | 19,7 |
| C | 1,439 | 0,722 | 25,0/25 | 18,1 | 6,9 |
| D | 1,469 | 0,624 | 31,0/31 | 19,3 | 11,7 |
| E | 1,435 | 0,505 | 25,0/25 | 12,6 | 12,4 |

The composition claim survives on four corpora — thinking blocks are a majority of the
numerator every time — and the magnitude claim is dead as a single number. The 7-point AQ
cost is A's, measured once, on A.

D is also the only one below the 0,70 edge, and it is the only different role in the set.
That is one observation, not a pattern, and it is written here so a fifth corpus can test it
rather than confirm it.

**Rule 4 — answered.** `actions_per_prompt` reads 6,4 / 6,7 / — / 7,6 / 8,5. Four of four
that carry the field are inside the 5–20 band, spanning a third of its width. The rule's own row: *«two of two inside a band four
times as wide as it is deep says little. Record it; do not raise it.»* Recorded, not raised.

**Skill fluency: I reversed this finding on three corpora and the fourth reversed it back.**

That sentence is the finding. Two commits ago the recovered term was 1,0 on A, B and C, and
the write-up was rewritten to say it was a constant that lifted everyone equally and cost
nobody points. D came back **0,6**.

| | skills_distinct | rate vs target | normalized | recovered term 3 | axis |
|---|---|---|---|---|---|
| A | 43/40 | 0,86× | 0,9581 | 1,0 | 21,1/22 |
| B | 11/40 | 1,10× | 0,7100 | 1,0 | 15,6/22 |
| C | — | — | 22,0/22 forces ≥0,992 | 1,0 | 22,0/22 |
| **D** | **17/40** | **3,92×** | **0,6500** | **0,6** | **14,3/22** |
| E | 40/40 | 1,59× | 1,0000 | 1,0 | 22,0/22 |

**Compare B and D, because that pair is the whole argument.** On both signals the axis
actually publishes, D beats B: more distinct skills (17 against 11) and nearly four times the
per-call rate (3,92× target against 1,10×). D scores **lower** — 14,3 against 15,6. The only
thing separating them is a term nobody can see, and it costs D **2,6 points of a 22-point
axis**.

D is not somebody who avoids skills. D uses more of them, more often, than the corpus that
outscores them. What D does not do is use a skill whose *name* contains one of
`subagent-driven`, `brainstorm`, `writing-plans`, `cerberus` or `systematic-debugging`. The
term is not measuring skill fluency; it is measuring whether five particular names appear.

**The methodological lesson is worth more than the finding.** Three corpora agreeing on a
BINARY term is close to no evidence: with two possible values you have learned nothing until
you have seen both, and self-selected volunteers who share a workplace and a set of skills
will sit on the same branch. The `not_checked` line written at the time said exactly this —
*"never varied means across everyone measured, not by construction"* — and it was right, and
I drew the conclusion anyway. Recovered by `scripts/skill-fluency-term.py`, whose control is
the same algebra on Tool command where every term IS disclosed: 0,654167 predicted against
0,654167 published.

### Context Intelligence: a 60% target that nobody scores under 98%

Six corpora put `evidence_eligible_sessions` above threshold every time at a nearly constant
multiple — 1,67 / 1,67 / **1,64** / 1,67 / 1,67 / 1,67. That is not six independent
observations of headroom. `CONTEXT_INTELLIGENCE_TARGET = 0,60` (`aq.py:18`) and the axis is
`sat(coverage, 0,60)`, so a multiple of 1,667 is exactly **coverage = 1,0**.

Three corpora publish the numbers directly. The fourth does not, and is recoverable anyway:
the bisection point IS `0,60 × eligible_change_sessions`, so dividing it back out gives the
denominator.

| | grounded_sessions | write_sessions | coverage | source |
|---|---|---|---|---|
| A | 50 | 50 | 1,000 | published signals |
| B | 15 | 15 | 1,000 | published signals |
| C | 124 | **126** | **0,984** | derived from its bisection point, 75,6 / 0,60 |
| D | — | — | 1,000 | axis absent from the payload; the counterfactual still cuts the signal at 1,67× |
| E | 60 | 60 | 1,000 | published signals |
| F | 20 | 20 | 1,000 | published signals |

**Against a target of 60%, five people are at 100% and the sixth is at 98,4%.** The axis
awards full marks from 0,60 upward, and every person measured sits in the top 2% of its
input range. It cannot discriminate between any of them, and it would take somebody at 59%
before it said anything at all. F is the corpus that stops this reading as a property of
strong corpora: it ties for the lowest total on record and it is one of the five at 1,000.

**The derivation carries a control, because otherwise it is just arithmetic that suits us.**
Three corpora publish the denominator *and* were bisected, so the method can be checked
against them before it is trusted on the one that cannot:

| | derived `thr / 0,60` | published `write_sessions` | |
|---|---|---|---|
| A | 50 | 50 | agree |
| B | 15 | 15 | agree |
| E | 60 | 60 | agree |

Three for three, exactly. That is what makes C's 126 quotable, and it is also why **C does
not need to re-run**: a `comparison-2` file from that corpus would publish a number three
independent checks already reconstruct.

**C is the reason this is stated carefully.** An earlier version of this section said the
numerator and the denominator were the same set — that grounded_sessions equalled
write_sessions by construction. C is 124 of 126: two sessions wrote code without a
qualifying call first. The metric CAN come out below 1,0, so whatever produces these numbers
is behaviour and not an identity, and the "by construction" reading is withdrawn.

What remains is a calibration observation rather than a fidelity defect, and it is filed as
one: a 60% target on a quantity where the observed floor is 98%. Whether the graded
population has mass below 60% is exactly what none of these five corpora can say.

### One Windows corpus, and one thing it makes visible

E is the only non-macOS run. Nothing platform-shaped shows up where it would be easiest to
imagine one: its `cli_share` is 0,97, the same as everyone's, because it runs Bash under the
harness like the rest.

What it does expose is a hole the other four could not. `classify_tool("PowerShell")` returns
**`other`** — verified by importing it — and `other` is on **neither side** of Grounding's
explore/doing ratio. Separately, `cli_counter` only ever increments under
`elif name == "Bash"` (`accumulator.py:1414`), so a PowerShell call contributes nothing to
`cli_calls` or `clis_distinct` either. A whole shell is invisible to three axes.

On E it barely matters: PowerShell is 1,45% of its tool mix, and E scores at the ceiling on
Grounding and Token economy anyway. **The magnitude here is small and the shape is not.** For
somebody whose primary shell is PowerShell rather than an occasional one, the same three axes
would be reading a fraction of their work. That is a hypothesis about a person we have not
measured, and it is written as one.

### Not settled by this set

- **Model mix**, 50/50 on every corpus in this file, and this method cannot test it: its
  signals are in `not_cuttable` on every run, the identical list each time (`offload_share`,
  `distinct_models`, `review_skills`). They are derived, so cutting them post-hoc is not
  available. Reaching them means driving the accumulator from a transformed corpus.

  What the payloads *do* say, and it took a sixth corpus to be worth writing down: the
  routing term reads `state: "unmeasured"` on **every payload on record that publishes it**
  — five distinct people, both contracts, both platforms — and every one of them reads
  `eligible_completed_substantive_pairs: 0` with `excluded_reasons: {}`. An empty exclusion
  map beside a zero denominator says nothing was ever a candidate, which is a different thing
  from candidates being filtered out, and it is the reading that survives when a single corpus
  cannot tell the two apart. **This is a recorded observation and not a finding**: it has not
  been through the Phase 3 gate, and one local attempt to name a cause for it already died on
  row 8. What six corpora change is only that the zero is not one person's setup.
- **Whether the ceiling axes discriminate lower down.** F moved this and did not settle it.
  Until F arrived, every corpus here scored 82 to 95 and "these axes do not discriminate" was
  indistinguishable from "these particular people are all strong". F reads 10,7 of 28 on Tool
  command and 11,0 of 22 on Skill fluency, and takes the maximum on all five that never move,
  so the plateau is not a property of strong corpora. How far below F somebody would have to
  be before those five said anything is still unmeasured, and nothing here should be read as
  saying so.
- **Calibration.** Six corpora are not a distribution, and people who agree to run an audit
  are not a random sample of the graded population. Every one is a self-selected volunteer.
  The Skill fluency reversal is what that costs in practice: three of them shared a branch of
  a binary term for reasons that had nothing to do with the term.

## Traps a runner actually hit

Every one of these came from a real first attempt, not from imagination.

- **Windows needs no shell now.** The orchestration was bash; it is Python. The first
  Windows attempt could not start at all — `bash` there is the WSL launcher, and with no
  distribution installed it failed *inside* WSL with `execvpe(/bin/bash) failed`.
- **Where the file lands is decided before the work, not after.** The second Windows attempt
  ran the whole thing — pin, probe 18/18, pipeline, AQ, counterfactual with controls moving
  — and then lost the payload to a `PermissionError`, because the terminal had started in
  `C:\Program Files (x86)\Cmder` and `--out-dir` defaults to the working directory. The run
  now probes for writability first and falls back to the home directory, loudly. A run that
  fails on its last line after two minutes of correct work is the worst possible place to
  fail.
- **The scoring tool may ask an interactive question.** It offers to add
  `"cleanupPeriodDays": 180` to `~/.claude/settings.json` and waits on `[y/N]`. Enter
  declines and changes nothing. Worth knowing before it appears, and worth remembering if
  this is ever run somewhere nothing can answer it.
- **`--output-dir` is reported as an "unknown flag ignored". It is not ignored.** The
  scoring tool's source-directory parser claims every `--*-dir=` argument and warns about
  the ones it does not own. The run announces this before it happens.

## What the runner needs

- `python3`, `git`, and **`uv`** — the scoring tool's entry point runs under `uv run`, so a
  machine without it fails at the anchor. An earlier version of this list said "python3 and
  git", which would have sent someone into a failure two minutes into their first run.
- **No shell.** PowerShell and CMD are fine and Git Bash is not needed. A requirement that
  is absent earns a line because this one was real for a while and the list never named it:
  it said the three above while the whole path went through `bash`, on all three pages that
  carry it. On Windows a bare `bash` is `C:\Windows\System32\bash.exe`, the WSL launcher,
  and with no distribution installed it fails *inside* WSL with
  `execvpe(/bin/bash) failed: No such file or directory` — a message about a missing shell,
  produced on a machine that has one. That is what the first Windows runner got, on their
  first attempt. Git Bash would have worked and was still the wrong fix: the orchestration
  moved into Python, so `scripts/second-corpus.sh` is a one-line shim that execs
  `second_corpus.py`, and there is one implementation rather than two.

  None of this is needed on Windows now. It is kept for anyone who is inside WSL for their
  own reasons, where two steps nobody would guess still apply: `uv` and `python3` have to be
  installed **inside** the distribution, and the corpus is on the Windows side, so it needs
  `--corpus /mnt/c/Users/<user>/.claude/projects`. The WSL home is empty and a run there
  would otherwise score nothing and say so in a way that looks like a bug.
- Their own transcript corpus at `~/.claude/projects` (the default; `--corpus` overrides it).
- A copy of `scripts/` on disk. **Installing this as a Claude skill is not required**: no
  agent is involved in producing the comparison file, so the directory is enough.

That is the whole list. There is no published report to find and no path to supply.

It costs about 16 MB in a temp directory and under two minutes, measured. Nothing is
uploaded: the entry point runs with `--local`.

## What to run

**Nothing needs to be installed.** Contributing a corpus needs the scripts, not the skill:
no agent takes part, so there is no reason to put anything in somebody's config to ask them
for a favour.

```bash
uvx --from "git+https://github.com/ftrinidad/gnomon@feat/miraudit-skill#subdirectory=skills/miraudit" \
    miraudit-second-corpus
```

One line, nothing installed, nothing left behind, and the same shape as the scoring tool's
own `uvx --from git+... xl-ai-insights` that this audience already types. The result lands
in the directory you ran it from. Verified end to end.

The `@branch#subdirectory=` is the ugly part, and it is not the mechanism: it is there
because the skill lives on a branch of a fork. If it ever merges upstream, the fork and the
branch drop out of that URL and the rest stays as it is.

**Do not write that shorter command down until it works.** An earlier version of this
paragraph showed it fully formed, one sentence away from the real one and looking exactly
like it, and it got copied and run. It fails with `has no subdirectory skills/miraudit`,
which is accurate and still costs the reader a confused minute. A command that does not work
yet is a broken command, however clearly the surrounding prose says "later".

From a clone instead, if someone prefers to read the scripts before running them:
`python3 <clone>/skills/miraudit/scripts/second_corpus.py`. The `second-corpus.sh` next to
it still works and is only a shim that execs that file; it is the form quoted in reports
that are already out, and it is the one form of the command that needs a shell.

If the runner also wants the skill itself, to audit their own corpus rather than only
contribute to a comparison, that is the install path in the README. The `#branch` suffix
there is required: the bare form clones the default branch and reports "No skills found".

No arguments. It clones the scoring tool at the pinned commit, scores the last 30 complete
days, and writes one file **into the directory you ran it from**. Every default is printed
at the top of the run and recorded in the file, so nothing about it is implicit.

The path above is spelled out on purpose. An earlier version of this line said
`scripts/second-corpus.sh`, which is relative to the skill directory and fails from anywhere
else — the first thing someone hits, before they have any reason to trust the rest.
Substitute wherever the directory actually lives if it is not installed as a skill.

It takes minutes, not seconds: it reproduces a score and the counterfactual re-scores the
payload many times over. Run it where it can finish; a watchdog that kills it partway
reports nothing.

A full `/miraudit` is worth having if the runner wants their own audit, but it is not what
this comparison needs and it should not be the price of contributing one.

## What comes back

**`miraudit-comparison-<date>.json`**, written by `emit-comparison.py`. A few kilobytes,
produced entirely by scripts. It is deliberately NOT the full `miraudit-<date>.json`: that
one carries findings and directions, which need judgement and cannot be asked of a
volunteer.

The fields the comparison reads:

- `tool.contract` — the gate above.
- `anchor.ok` — `true`, `false`, or `null` for "nobody checked". See the conditions above.
- `corpus` — tool calls, sessions, sidechain share, window. **A snapshot, not a property of
  the window.** Measured on corpus A: the same fixed window read 42,664 tool calls one
  morning and 42,874 hours later, because resumed sessions kept writing under their original
  dates. A fixed window fixes which days count, not which files exist to be counted. Read
  these as approximate context; the axis scores are the comparable part.
- `profile` — the work signature: tool mix, category shares, distinct project root **count**,
  explore-to-doing with and without thinking. This is what answers "are these two corpora the
  same kind of work?" without anyone describing their job. People describe work in
  incomparable ways, and "backend engineer" does not say whether two people share a codebase.
- `axes[].score` — the share of the total sitting on pinned axes.
- `saturation` — delta, signals cut, and whether the controls moved.
- `grounding` — the composition behind rules 2 and 3.

**What is not compared: the AQ numbers themselves.** This skill does not rank anyone, and a
comparison of two people's totals is exactly the reading it refuses to support.

## What leaves the machine

Counts and shares. **No transcripts, no file contents, no paths, no repository or project
names** — the profile signature reports how many project roots, never which. The whole file
is a few kilobytes and readable in a minute.

Read it before sending it anyway. A rule you can follow in good faith and break by accident
is worth checking with your own eyes rather than trusting a sentence like this one.

## Blind spots this does not remove

- Whether the thresholds are calibrated against a real population. A pinned axis is only a
  defect if the graded population has mass above it, and even several volunteer corpora are
  not that population — they are people who agreed to run an audit, which is not a random
  sample of the graded one.
- The counterfactual examines fourteen signals and cut ten on the corpus it was written
  against. Three are still not cut on any corpus, because their input is a list rather than
  a scalar: model diversity, offload share, and the review-skill count. The declared
  coverage is a floor, and the script prints what it looked for and could not find.
- Corpora produced on the same team, on similar work, are not independent in the way this
  argument needs. The `profile` signature shows whether two corpora *look* alike; it cannot
  show whether they come from the same codebase, because it carries no names. Two people at
  different companies can produce matching signatures, which for the independence question
  is probably fine, and two people in one repo could produce different ones.
- `anchor.ok: null` is the common case now that the number is not part of the ask. It buys
  simplicity at the cost of a reproduction guarantee, and any write-up resting on such a run
  has to say which runs were anchored and which were not.
