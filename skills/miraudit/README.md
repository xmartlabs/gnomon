# miraudit

Audits a score that someone else's code computed about your work, and tells you whether it
reflects what you actually did.

It is built for gnomon / xl-ai-insights AQ reports, but the checks are written as shapes of
infidelity rather than as a list of that tool's known bugs, so they survive the formula
changing. It does not compute a score, propose formula changes, or rank anyone.

A run produces two files: `miraudit-<date>.json` and a human-readable
`miraudit-<date>.md` rendered from it. The JSON is what makes runs comparable. One person's
corpus is an anecdote; the same gap measured on five machines is a defect in the axis.

## What it checks

**Anchor.** Reproduces the published number locally before measuring anything. If the base
run does not reproduce it, the method is wrong before any finding is, and the run stops.
Prints a corpus fingerprint first, because counts compared across machines mean nothing
without one.

**Per-axis fidelity.** Takes each axis's declared signals, re-measures the underlying
behaviour from the transcript corpus, and reports the gap and its direction: faithful,
overestimates, or underestimates. Ground truth never comes from the tool's own aggregates.

**Structural shapes**, independent of any formula: terms silently renormalized away for
lack of evidence, saturated axes that no longer discriminate, denominators containing work
the person did not do, counters driven by the harness rather than by anyone's judgement,
and one counter feeding two pillars.

**A refutation gate.** Nothing is reported until it survives six attempts to kill it. Each
attempt exists because it killed a real finding that was about to be sent; the write-ups
are in `references/refutation.md`. Findings that die are recorded in `dismissed` with the
fact that killed them, so nobody reopens them.

## Install

**Copy the directory.** Verified.

```bash
git clone <repo> /tmp/miraudit-src
cp -r /tmp/miraudit-src/miraudit ~/.claude/skills/    # all your projects
# or
cp -r /tmp/miraudit-src/miraudit .claude/skills/      # this project only
```

**Via the skills CLI.** Not verified yet. Confirm how it discovers skills in a repository
before relying on it.

```bash
npx skills add OWNER/REPO -a claude-code
```

**As part of a plugin.** If it ships inside one, install the plugin and read the update
note below, which matters more than it looks.

### Why it is not a plugin here

The layout is already what a Claude Code plugin expects, so wrapping it needs one file:
a `.claude-plugin/plugin.json` manifest beside this `skills/` directory.

That wrapper was left out on purpose. A plugin buys marketplace distribution, versioning,
and the ability to bundle agents, hooks and commands alongside a skill. This is a skill on
its own, and a personal skill copied to `~/.claude/skills/` is already available in every
project, so the wrapper would add ceremony without adding reach. Wrapping it would also
mean turning its host repository into a plugin marketplace, which is a separate decision
for whoever owns that repository.

## Use

```
/miraudit
```

Or describe the symptom and let the agent pick it up: "my score dropped four points and I
did not change how I work."

The checks in `scripts/` also run standalone. Each one takes a read-only checkout of the
scoring tool and reads your transcript corpus:

```bash
python3 scripts/fidelity-audit.py --checkout /path/to/gnomon \
        --until 2026-08-06 --stats /path/to/anchored-run/stats.json
python3 scripts/verification-reality.py --checkout /path/to/gnomon \
        --until 2026-08-06 --repo /path/to/your/repo --ref main
```

`--until` is the report's own end date. Leave it out and the window ends now, which drifts
every day and includes the audit session itself, so the checks describe different days than
the report does.

`--stats` points at the anchored run's `stats.json`. Axis scores are read from there and
never baked into the scripts, so a header cannot go stale when an axis moves.

They import the scoring tool's own predicates on purpose. A denominator you define yourself
produces a number that is true and means nothing. That mistake is documented in
`references/refutation.md`.

## Updating

**If you installed it as a plugin, editing the source does not change what runs.** Plugins
execute from a version-pinned snapshot under
`~/.claude/plugins/cache/<org>/<plugin>/<version>/`, which is a copy, not a symlink. Diff
the file you edited against the cached one before you trust any test of your change. This
has burned real money more than once.

**Knowing when the skill has gone stale.** `references/known-state.md` pins the commit and
contract string it was validated against. Phase 0 compares your installed version to it and
says so when they differ. When they do, the fixtures in `scripts/` have to be re-run before
anyone quotes a finding: a check written against one contract and silently measuring
another is worse than no check.

## Scope

It reads the transcript corpus and a checkout of the scoring tool. It writes only inside its
own output directory, and never inside the audited repository. When code has to be modified
to prove something, it patches a throwaway copy.

It cannot see what it has no record of. Tests that run inside a git hook, checks that run in
CI, and commands you typed in your own terminal are all invisible to the corpus, so they are
invisible here too. It reports what the transcripts show and says which questions it did not
ask.

An empty findings list means the run worked and found nothing to report.
