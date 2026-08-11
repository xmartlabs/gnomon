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

| B's ratio | What it means | What happens |
|---|---|---|
| Also 1.0 to 1.2 | Two different people land on the same side of the ceiling | The axis does not discriminate. Worth raising, with both numbers. |
| Below 1.0, or well above 1.2 | The ratio separates people; A's value describes A | Nothing to raise. Say so. |
| Near 1.0 but with a very different `grounding.thinking_share` | The ratios agree for different reasons | The composition is the story, not the ratio. Report both, claim neither. |

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

## What the runner needs

- `python3`, `git`, and **`uv`** — the scoring tool's entry point runs under `uv run`, so a
  machine without it fails at the anchor. An earlier version of this list said "python3 and
  git", which would have sent someone into a failure two minutes into their first run.
- Their own transcript corpus at `~/.claude/projects` (the default; `--corpus` overrides it).
- A copy of `scripts/` on disk. **Installing this as a Claude skill is not required**: no
  agent is involved in producing the comparison file, so the directory is enough.

That is the whole list. There is no published report to find and no path to supply.

It costs about 16 MB in a temp directory and under two minutes, measured. Nothing is
uploaded: the entry point runs with `--local`.

## What to run

```bash
bash ~/.claude/skills/miraudit/scripts/second-corpus.sh
```

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
