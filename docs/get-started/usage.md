<span class="gn-label">Get started</span>

# Usage & outputs

<p class="gn-thesis">By default gnomon scores the current calendar month across every tool it finds. Flags choose which tools, which dates and where the files go; this page lists them and explains each output file.</p>

The examples use `xl-ai-insights`, the command installed by the [quick start](install.md). With `uvx`, prefix each one with `uvx --from git+https://github.com/xmartlabs/gnomon@latest`.

## Choose sources

Name one or more sources to score only those. With no names, gnomon reads every source it finds.

```bash
xl-ai-insights --local claude            # Claude Code only
xl-ai-insights --local claude codex      # Claude Code and Codex
```

Source names: `claude`, `codex`, `gemini`, `cursor`, `antigravity`, `antigravity-ide`, `pi`, `opencode`. See [Supported tools](../sources/supported-tools.md) for where each one is read from.

### Low-volume sources

A source counts only when it has at least 10 sessions in the scored window, so a tool you tried once does not skew the profile. Pass `--include-low-volume` to include smaller sources. A source still needs at least one session in the window.

## Choose a time window

With `--local` and no window flags, gnomon scores the current calendar month.

```bash
xl-ai-insights --local --last=30d                               # the last 30 days
xl-ai-insights --local --last=90d                               # the last 90 days (also Nw, Nm)
xl-ai-insights --local --since=2026-03-01 --until=2026-05-31    # explicit dates, end day included
xl-ai-insights --local --since=2026-01-01                       # from a date to now
```

- `--last=N` takes days (`30` or `30d`), weeks (`2w`) or 30-day months (`1m`), ends now, and overrides `--since` and `--until`.
- Every metric follows the window, including git churn and the AQ.
- Events without a timestamp are dropped from windowed runs, because they cannot be placed inside the bounds.
- Cursor sessions that exist only as JSONL files carry no event timestamps, so the file's modification time stands in for the whole session. A default run keeps them only when that time falls in the current month; pass `--since` to count older ones.

The AQ's targets are calibrated for one calendar month of work, so a score over a much longer window is not directly comparable with a monthly one. See [How scoring works](../metrics/how-scoring-works.md#what-gets-scored).

## Read transcripts from other places

gnomon honours the same environment variables as the tools themselves: `CLAUDE_CONFIG_DIR` for Claude Code and `CODEX_HOME` for Codex. To read history copied from a sandbox, a devcontainer or another machine, point gnomon at it with a `--<source>-dir` flag:

```bash
xl-ai-insights --local --claude-dir=/mnt/sandbox-home/.claude   # the root or its projects/ folder both work
xl-ai-insights --local --codex-dir=~/backups/codex              # the root or its sessions/ folder both work
```

The flags are `--claude-dir`, `--codex-dir`, `--gemini-dir`, `--cursor-dir`, `--antigravity-dir`, `--antigravity-ide-dir`, `--pi-dir` and `--opencode-dir`. A flag wins over the environment variable. Passing `--antigravity-dir` alone also skips the live Antigravity IDE read, so a copied history is not mixed with the running app's.

## Add your own planning skills

gnomon recognises common planning skills by name. If your team uses its own, add their names to the detector with a comma-separated environment variable. No code change is needed.

```bash
GNOMON_PLAN_SKILL_NEEDLES="roadmap,my-planner" xl-ai-insights --local
```

## Flag reference

### Local runs

| Flag | What it does |
|------|--------------|
| `--local` | Run the analysis only: no login, no upload, no network calls |
| `<source> ...` | Score only the named sources |
| `--since=YYYY-MM-DD` | Start of the window |
| `--until=YYYY-MM-DD` | End day of the window, included |
| `--last=N[d|w|m]` | Rolling window ending now |
| `--include-low-volume` | Include sources with fewer than 10 sessions in the window |
| `--<source>-dir=PATH` | Read a source's transcripts from `PATH` |
| `--output-dir=PATH` | Write the outputs to `PATH` (use `.` for the current directory) |
| `--no-open` | Don't open `profile.html` at the end |
| `--tools` | Print per-tool-call rates, to check the rate terms by hand |

### Sharing runs

These apply when you run `xl-ai-insights` without `--local`, which uploads your profile. See [Sharing a profile](../teams/sharing.md).

| Flag | What it does |
|------|--------------|
| `--window=N` | Score each uploaded month over the trailing N calendar months (default 1) |
| `--backfill[=N]` | Upload each of the last N months (default 6, at most 12) |
| `--force` | Re-upload every month, up to the last 12, ignoring what the server already has |
| `--dry-run` | Show what would be uploaded, and why, without uploading |
| `--mirdash-base=URL` | Upload to another server, such as your [self-hosted dashboard](../teams/dashboard.md#point-the-cli-at-your-dashboard) |
| `--allow-stale-cli` | Continue after a confirmed out-of-date CLI warning |
| `--console` | Show progress in the terminal instead of the browser |
| `--quiet` | Print only errors and the final report URL |
| `--verbose` | Also print the analysis engine's full output |
| `--no-open` | Don't open the report page at the end |
| `--output-dir=PATH` | Copy the final files into `PATH` |

`xl-ai-insights --help` prints the same list.

## Outputs

A local run writes these files to the current directory, or to `--output-dir`:

| File | What it holds |
|------|---------------|
| `profile.html` | Your profile: the GStack scorecard, the AQ with its pillars and axes, signature moves, growth edges, the trend, and a few of your own prompts quoted verbatim |
| `report.md` | The same statistics as readable text |
| `stats.json` | Every computed metric, including the full AQ breakdown. Never uploaded |
| `summary.json` | The shareable subset: counts and scores with no prompts, quotes or file paths. This is exactly what a sharing run uploads; see [Privacy](../project/privacy.md#what-is-uploaded) for every field |
| `narrative_input.md` | Short excerpts from your transcripts, prepared for an optional narrative written by a language model. Never uploaded |

`xl-ai-insights --local` always writes `summary.json`. `python3 paxel.py` writes it only with `--summary`.

These files hold data derived from your own transcripts. gnomon's repository ignores them in git; if you run gnomon inside another repository, don't commit them. `narrative_input.md` contains verbatim excerpts, so don't share it.

A sharing run writes the same files to a new temporary directory, keeps it after the run and prints its path unless you pass `--quiet`.
