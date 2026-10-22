<span class="gn-label">Get started</span>

# Install & quick start

<p class="gn-thesis">gnomon is a command-line tool that needs nothing but Python 3. One command reads the agent transcripts on your machine, scores the current month and opens your profile.</p>

## Before you start

- **Python 3.8 or newer.** The CLI uses only the standard library, so there is nothing else to install.
- **[uv](https://docs.astral.sh/uv/)**, for the `uvx` commands below. Without uv, run gnomon [from a checkout](#run-from-a-checkout) with git.
- **Transcripts from at least one [supported tool](../sources/supported-tools.md)** in their default locations, or a copy of them you can point gnomon at.

## Quick start

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --local
```

gnomon finds every supported tool's transcripts, scores the current calendar month, writes its [outputs](usage.md#outputs) to the current directory and opens `profile.html` in your browser.

With `--local`, nothing leaves your machine: there is no login, no upload and no release check. To share your profile or send it to a team dashboard, see [Sharing a profile](../teams/sharing.md).

## Pin a release

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@v0.4.0 xl-ai-insights --local
```

Releases are tagged `vX.Y.Z`. The `latest` tag always points at the most recent stable release.

## Run from a checkout

```bash
git clone https://github.com/xmartlabs/gnomon
cd gnomon
python3 paxel.py
```

`paxel.py` is the legacy entry point. It runs the same local analysis as `xl-ai-insights --local`, with three differences: it writes its files next to `paxel.py` instead of the current directory, it writes `summary.json` only when you pass `--summary`, and it never offers the Claude Code retention setting described below.

## Update

`uvx` caches packages. After a new release, refresh the cache:

```bash
uvx --refresh --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights
```

`--local` runs work with any version. Sharing to the default server requires the latest release; see [Sharing a profile](../teams/sharing.md#release-check).

## Claude Code transcript retention

Claude Code deletes transcripts older than 30 days unless you change its `cleanupPeriodDays` setting, and gnomon can only score history that still exists. On an interactive run that finds Claude Code history, gnomon offers to add `"cleanupPeriodDays": 180` to `~/.claude/settings.json`.

- It asks first, and the default answer is no.
- It never asks when the setting is already present, when input is not a terminal, or when you pass `--quiet` or `--dry-run`.
- Before writing, it backs up the existing file and prints the command to undo the change.
- It changes how long Claude Code keeps transcripts. It does not change gnomon's scoring window.

## Next

- [Usage & outputs](usage.md): choose sources and time windows, and read what each output file holds.
- [How scoring works](../metrics/how-scoring-works.md): what the AQ measures and how it is computed.
