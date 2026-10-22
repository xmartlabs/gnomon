<span class="gn-label">Project</span>

# Privacy

<p class="gn-thesis">gnomon runs on your machine. A local run makes no network calls at all, and sharing uploads one file of counts and scores that you can read before you send it. Your prompts and your code never leave the machine.</p>

## Local runs

All analysis runs on your machine. gnomon reads your agent transcripts read-only, and for accurate code churn it runs your local `git` (`git log --numstat`) on the repositories it finds in them.

`xl-ai-insights --local` makes no network calls, and nothing leaves your machine. For older versions of the Google Antigravity IDE, gnomon reads conversations from the IDE's language server, which runs on your own machine. See [Supported tools](../sources/supported-tools.md#google-antigravity).

## Sharing runs

Running `xl-ai-insights` without `--local` is opt-in, and it does two things over the network:

1. When you upload to the default server, it first makes one GET request to GitHub Releases to check that your CLI is the latest release. Uploading to another server with `--mirdash-base` skips this check.
2. After you sign in, it POSTs `summary.json` to the server you chose.

The server ties the upload to your account through your sign-in. `xl-ai-insights` itself sends no email address. See [Sharing a profile](../teams/sharing.md) for the full flow.

## What is uploaded

A sharing run uploads exactly the `summary.json` that `xl-ai-insights --local` writes to disk, so you can open the file and read it first. It holds:

- `context`: the date range, the detected sources, total sessions and prompts, the CLI version and the scoring window.
- Behaviour counters: `planning_ratio_explore_to_doing`, `errors` (recovery ratio and errors per 100 tool calls), `iteration_depth` (mean, median, p90, max and files edited more than 15 times), `churn` (git and tool-authored line counts, active hours, actions per prompt), `orchestration` (fan-out and delegation counts) and `compounding_writes`.
- `ecosystem`: how many skills and MCP servers you used, and the names of your most-used skills and MCP servers with their call counts.
- `progression_monthly` and `noticed_stats_monthly`: per-month counts (prompts, tool calls, sessions, active days, churn, tokens) and the names of the models you used, up to three per month in `progression_monthly`.
- `profile`: the computed AQ, GStack scorecard, archetype and readings that the report page shows.
- `scoring_inputs_by_source`, `profiles_by_source`, `source_usage` and `source_usage_monthly`: the same counters split by tool, so the server can recompute the score under a newer formula. These include names of skills, tools, MCP servers, subagent types and models, with their counts.
- `token_usage`: input, output and cached token totals, per model.
- `coverage`, version and contract IDs, and timing figures for the run.

## What is not uploaded

- Your prompts and the agent's replies.
- File contents and file paths.
- Verbatim quotes from your sessions. `profile.html` shows a few of your prompts, but it stays on your machine.
- `stats.json` and `narrative_input.md`.

## Names you should know about

The upload does include names. Skill names, MCP server names and subagent names are chosen by you or your team, and they may contain a project, customer or environment name. Model names such as `claude-opus-4` or `gpt-5.4` are included too. If a name is sensitive, run `--local` and read `summary.json` before you share.
