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
  claimed, so signals the counterfactual cuts stop existing. `second-corpus.sh` pins the
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

| | A | B | C | D |
|---|---|---|---|---|
| window | 2026-07-07 → 2026-08-06 | 2026-07-11 → 2026-08-10 | 2026-07-12 → 2026-08-11 | 2026-07-12 → 2026-08-11 |
| contract | `17:17:17` | `17:17:17` | `17:17:17` | `17:17:17` |
| schema | — | **`comparison-2`** (re-run, window pinned) | `comparison-1` | **`comparison-2`** |
| `anchor.ok` | `null` | `null` | `null` | `null` |
| tool calls | 42.874 | 5.862 | 42.003 | 3.702 |
| sessions | 125 | 49 | 281 | 30 |
| project roots | 20 | 15 | **74** | 14 |
| sources scored | claude | claude | claude, codex | claude |
| sidechain share | 0,626 | 0,358 | 0,669 | 0,458 |
| Bash share | 0,631 | 0,663 | 0,426 | **0,384** |
| `explore_to_doing` | 1,124 | 0,974 | 1,439 | 1,469 |
| ... without thinking | 0,219 | 0,193 | 0,722 | 0,624 |
| `thinking_share` | 0,806 | 0,802 | 0,708 | **0,590** |
| AQ | 92 | 82 | **93** | 87 |

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

**Rule 1 — row 3, and four corpora have not changed which two.** Delta 0 on all four
(92→92, 82→82, 93→93, 87→87), controls move on all four (69/55, 66/54, 69/55, 73/62),
`not_cuttable` the identical list every time. Signals cut: 10 / 5 / 11 / 7 — never the same
set, so row 1 never applies and row 3 always does.

Above threshold in **all four**, and it is the same pair the two-corpus intersection found:

| señal | A | B | C | D | eje |
|---|---|---|---|---|---|
| `cli_calls` | 9,61× | 13,53× | 2,34× | 8,81× | Token economy (`aq.py:585-589`) |
| `evidence_eligible_sessions` | 1,67× | 1,67× | 1,64× | 1,67× | Context Intelligence (`aq.py:484`) |

Eleven other signals are pinned on some corpora and not others, which is what row 3 exists to
filter. `evidence_eligible_sessions` sits at 1,67× on three of the four and 1,64× on the
fourth, which is a tighter agreement than anything else in the table and is worth a second
look rather than a claim.

One wrinkle worth stating: on D, **Context Intelligence is not scored at all** — the axis is
absent from the payload and Craft renormalizes without it. So on D that signal is saturated
while the axis it feeds is dropped. It does not weaken the pair; it does mean "these two
signals feed the two axes at identical maxima" is a statement about A, B and C.

**Rule 2 — fires, and the spread keeps widening while the scores do not.** Four ratios:
0,974 / 1,124 / 1,439 / **1,469**. That is a 51% spread, and the axis scores 24,5 / 25,0 /
25,0 / 31,0-of-31 — every one of them at or within half a point of its ceiling. Under the
band as written, 0,90-or-above: the axis does not discriminate in this range.

**Rule 3 — the fourth corpus moves it off the row it was on.** `thinking_share` reads
0,806 / 0,802 / 0,708 / **0,590**. D lands between 0,50 and 0,70, which is the rule's
**middle** row, not its top one: *«report the range and stop calling it dominant.»*

So the range is reported and the word is dropped. It is **59% to 81%** across four people,
not "80%", and the consequence varies by a factor of three:

| | ratio | without thinking | Grounding | would score | loses |
|---|---|---|---|---|---|
| A | 1,124 | 0,219 | 25,0/25 | 5,5 | 19,5 |
| B | 0,974 | 0,193 | 24,5/25 | 4,8 | 19,7 |
| C | 1,439 | 0,722 | 25,0/25 | 18,1 | 6,9 |
| D | 1,469 | 0,624 | 31,0/31 | 19,3 | 11,7 |

The composition claim survives on four corpora — thinking blocks are a majority of the
numerator every time — and the magnitude claim is dead as a single number. The 7-point AQ
cost is A's, measured once, on A.

D is also the only one below the 0,70 edge, and it is the only different role in the set.
That is one observation, not a pattern, and it is written here so a fifth corpus can test it
rather than confirm it.

**Rule 4 — answered.** `actions_per_prompt` reads 6,4 / 6,7 / — / 7,6. Three of three that
carry the field are inside the 5–20 band. The rule's own row: *«two of two inside a band four
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

### Not settled by this set

- **Model mix**, 50/50 on all three, and this method cannot test it: its signals are in
  `not_cuttable` on all three runs, the identical list each time (`offload_share`,
  `distinct_models`, `review_skills`). They are derived, so cutting them post-hoc is not
  available. Reaching them means driving the accumulator from a transformed corpus.
- **Whether the ceiling axes discriminate lower down.** All three of these people are at or
  near the top of five axes. That the axes do not separate *them* is measured; that the axes
  would not separate someone much further down is not, and nothing here should be read as
  saying so.
- **Calibration.** Four corpora are not a distribution, and people who agree to run an audit
  are not a random sample of the graded population. All four are self-selected volunteers
  from one workplace. The Skill fluency reversal is what that costs in practice: three of
  them shared a branch of a binary term for reasons that had nothing to do with the term.

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
- **A POSIX shell.** The orchestration is a bash script, and this list has been wrong about
  that from the beginning: it named the three above and never named the shell, on all three
  pages that carry it. **On Windows, run it from Git Bash**, which Git for Windows already
  installs. A bare `bash` there is `C:\Windows\System32\bash.exe`, the WSL launcher, and
  with no distribution installed it fails *inside* WSL with
  `execvpe(/bin/bash) failed: No such file or directory` — a message about a missing shell,
  produced on a machine that has one. Reported by the first Windows runner, on their first
  attempt.

  In WSL proper it also works, with two extra steps nobody would guess: `uv` and `python3`
  have to be installed **inside** the distribution, and the corpus is on the Windows side,
  so it needs `--corpus /mnt/c/Users/<user>/.claude/projects`. The WSL home is empty and a
  run there would otherwise score nothing and say so in a way that looks like a bug.
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
`bash <clone>/skills/miraudit/scripts/second-corpus.sh`.

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
