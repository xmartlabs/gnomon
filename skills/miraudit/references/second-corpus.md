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

| What B's at-threshold arm does | What it means | What happens to the finding |
|---|---|---|
| Does **not** move, same signals cut | Two independent people sit above the same thresholds | `aq-is-mostly-ceiling` is a defect in the axes. Raise it. |
| **Moves** | The headroom is doing work for B; A's plateau describes A | Withdraw the finding to `hypothesis`. What is left is a calibration question about the targets, not a fidelity claim. |
| Moves for some signals, not others | Saturation is per-signal, not global | Report **only** the signals pinned on both. A signal pinned on A alone is not evidence about the axis. |

Two corpora is the minimum, not the target. Three or more is what makes the per-signal
column above readable.

Conditions for B to count at all:

- **`anchor.ok` must be true.** If B's base run does not reproduce B's published number,
  nothing measured in it is safe to read, and it is not a second corpus — it is a broken one.
- **`tool.contract` must match A's.** Comparing a `16:16:16` run against a `17:17:17` run is
  not a comparison: PR #66 removes `TOOLSEARCH_PER_CALL_TARGET` and
  `TEST_RUNS_PER_CALL_TARGET` outright, so two of the signals the counterfactual cuts stop
  existing. If the contracts differ, either pin both runs to the same checkout or restrict
  the comparison to the signals present in both, and say which.
- **The window is each runner's own report window**, not a shared one. The anchor gate is
  per-person; forcing a common window breaks reproduction on at least one side.

## What the runner needs

- `python3`, `git`, and `uv`.
- A checkout of the scoring tool (`gnomon`), read-only — the skill copies it before running.
- Their own transcript corpus at `~/.claude/projects` (the default; `--corpus` overrides it).
- **Their own published report: the number and its window.** Without the published number
  there is nothing to anchor against, and Phase 0 is a gate.

## What to run

Install the skill (see the README's *Install*), then:

```
/miraudit
```

It takes minutes, not seconds — Phase 0 reproduces the number and the counterfactuals read
the whole corpus. Run it where it can finish; a watchdog that kills it partway reports
nothing.

The standalone path, if the runner prefers commands to an agent:

```bash
scripts/anchor.sh --checkout /path/to/gnomon --since <report start> --until <report end>

COPY=/path/printed/by/anchor/checkout
STATS=/path/printed/by/anchor/stats.json
python3 scripts/saturation-counterfactual.py --checkout "$COPY" \
    --since <start> --until <end> --stats "$STATS"
```

The counterfactual is the check this comparison is about. The rest of a full `/miraudit` run
is worth having, but the saturation arm is the one that answers the question.

## What comes back

**`miraudit-<date>.json`.** That file is the unit of comparison; the rendered `.md` is for
the runner, not for the merge.

The fields the comparison reads, and nothing else:

- `corpus` — files, lines, tool calls, sources, window. Read this **first**. Counts compared
  across machines mean nothing without it, and the one substantive disagreement in this
  investigation's history was explained entirely by two sides measuring different corpora.
- `tool.contract` and `tool.ref` — the gate above.
- `anchor.ok` — the other gate.
- `axes[].score` and `axes[].max` — the share of the score sitting on pinned axes.
- The `saturated` entry in `findings` (or its absence), with the per-signal `signals cut`
  list from the counterfactual's output.

**What is not compared: the AQ numbers themselves.** This skill does not rank anyone, and a
comparison of two people's totals is exactly the reading it refuses to support. B's AQ
matters only as the thing B's anchor had to reproduce.

## What leaves the machine

The JSON carries aggregate counts, axis scores, and the finding text — **no transcripts, no
file contents, no command history**. `evidence.command` records the command that was run and
`evidence.output` its output, so a runner should read those two fields before sending the
file, and redact paths they do not want to share. Nothing else in the schema quotes the
corpus.

## Blind spots this does not remove

- Whether the thresholds are calibrated against a real population. A pinned axis is only a
  defect if the graded population has mass above it, and even several volunteer corpora are
  not that population — they are people who agreed to run an audit, which is not a random
  sample of the graded one.
- The counterfactual cuts nine signals. Fan-out, orchestration frequency, planning ratios,
  model diversity and CLI share are not cut at all, on either corpus. The declared coverage
  is a floor, and the script prints which signals it looked for and could not find.
- Corpora produced on the same team, on similar work, are not independent in the way this
  argument needs. If every runner is a backend engineer on one codebase, say so in the write-up
  rather than presenting the corpora as varied.
