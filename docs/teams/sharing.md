<span class="gn-label">Teams</span>

# Sharing a profile

<p class="gn-thesis">Sharing is opt-in. Running `xl-ai-insights` without `--local` uploads your `summary.json`, the counts and scores with no prompts or file contents, so you can follow your profile over time and your team can see it on a dashboard.</p>

## Share your profile

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights
```

It accepts the same source names and directory flags as a local run, plus the [sharing flags](../get-started/usage.md#sharing-runs):

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights claude
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --no-open
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --window=3
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --dry-run
```

To send your profile to your own team's server instead of the default one, see [Point the CLI at your dashboard](dashboard.md#point-the-cli-at-your-dashboard).

## What happens

1. gnomon runs the same local analysis to compute your metrics.
2. It opens your browser for a one-time sign-in. The page sends a token back to the CLI on `127.0.0.1:8799`.
3. It uploads `summary.json`, tied to your account through that sign-in. [Privacy](../project/privacy.md#what-is-uploaded) lists every field.
4. It opens your report page.

If the browser can't open, for example on a headless machine or in CI, or the sign-in takes longer than 120 seconds, the command prints a warning and stops. Nothing is uploaded. If you don't want to share at all, use `--local`.

## Which months are uploaded

With no flags, gnomon uploads the current month. When the previous month is missing on the server or was scored under another scoring contract, it rebuilds and uploads that month first.

- `--backfill[=N]` uploads each of the last N months (default 6, at most 12).
- `--force` re-uploads every month, up to the last 12, whatever the server already has.
- `--dry-run` prints the plan, and why each month is in it, without uploading anything.

Each month is scored over a trailing window of `--window=N` calendar months ending in that month. The default is 1, so a month is scored on that month alone.

Uploads larger than 900 KiB are refused before they are sent, because the server would reject them.

## Release check

Uploading to the default server requires the installed CLI to match the latest published release exactly. Before signing in, gnomon makes one request to GitHub Releases to check. If your version differs, including a newer build from `main`, it stops and prints the refresh command:

```bash
uvx --refresh --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights
```

Pass `--allow-stale-cli` to continue anyway. The check is skipped for `--local`, for `--help`, and when you upload to another server.

## Where the files go

A sharing run writes its files to a new temporary directory and keeps it after the run. It prints the path unless you pass `--quiet`. To keep the files somewhere specific, pass `--output-dir=PATH`, for example `--output-dir=.` for the current directory. Files with the same names there are overwritten.

The files include `narrative_input.md`, which holds excerpts from your transcripts. It is never uploaded; don't share it.
