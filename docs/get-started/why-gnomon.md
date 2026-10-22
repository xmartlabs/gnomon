<span class="gn-label">Get started</span>

# Why gnomon

<p class="gn-thesis">gnomon reads the AI coding-agent transcripts already on a developer's machine and turns a month of them into two readings: how they build, and how well they operate agents. It runs locally, has no dependencies, and every number it produces can be traced back to the code.</p>

## What you get

- **Two independent scores.** The [GStack scorecard](../metrics/gstack.md) describes how you build. The [Agentic Quotient (AQ)](../metrics/how-scoring-works.md) describes how well you operate agents. Neither feeds the other.
- **One profile across your tools.** Claude Code, Codex, Gemini CLI, Cursor, Google Antigravity (CLI and IDE), Pi and opencode are read and scored together. See [Supported tools](../sources/supported-tools.md).
- **No penalty for your tool.** When a tool cannot record a signal, that part of the score is left out and its weight goes to what can be measured. See [What each source measures](../sources/coverage.md).
- **Local by default.** `xl-ai-insights --local` makes no network calls. Sharing a profile is a separate command you choose to run. See [Privacy](../project/privacy.md).
- **No dependencies.** The CLI uses only the Python 3 standard library.
- **A versioned scoring contract.** Every score carries a contract ID, and scores are compared only when the IDs match. The [miraudit](../project/miraudit.md) skill lets you re-derive your own published number from your own transcripts.
- **A team dashboard you host.** One container and one volume give a team its AQ trends and per-person profiles. See [Self-hosted dashboard](../teams/dashboard.md).

## What gnomon tries to be

- **Local-first.** `--local` makes no network calls, and sharing is an explicit opt-in.
- **A read-only reader of transcripts you already have.** There is no instrumentation, wrapper or daemon. Cursor's database is opened read-only, and gnomon falls back to SQLite's `immutable` mode rather than touch a running editor's files.
- **Honest about what it can see.** Claude Code gives the fullest picture. Other tools give valid but thinner profiles, and a signal a tool cannot record is reported as not measured instead of guessed. [Steering leverage](../metrics/efficiency/steering-leverage.md) publishes its measurement but is not scored yet.
- **Versioned and reproducible.** A change to any formula, weight or target changes the contract ID, so old and new numbers never mix silently.

## What gnomon is not

- **Not a productivity ranking or a surveillance tool.** The score is a learning aid: each axis comes with a [rubric](../metrics/rubric.md) that names the next habit to build.
- **Not a code-quality or static-analysis tool.** Both scores come from how you work with agents in your transcripts. gnomon never grades the code itself. It reads `git log --numstat` line counts for churn, not file contents.
- **Not a cost tracker.** Token counts appear as context, and the [Token economy](../metrics/savvy/token-economy.md) axis measures how much of your tool use goes through the shell rather than MCP. It is not a billing ledger.
- **Not a real-time monitor.** It is a batch read of transcripts on disk, scored one calendar month at a time.
- **Not opinionated where there is no better answer.** The profile's "MCP vs CLI" and "Tool diversity" readings are described, not graded.

## Related projects

- [paxel-local](https://github.com/Photobombastic/paxel-local) by Max Schilling is the upstream gnomon is forked from. It ships the GStack scorecard. gnomon adds the Agentic Quotient and a Codex parser fix that drops injected wrapper messages and empty seed sessions.
- [gstack](https://github.com/garrytan/gstack) is the framework the three GStack build axes are grounded in. Those axes are unchanged from upstream.

## License

gnomon is MIT licensed. See [LICENSE](https://github.com/xmartlabs/gnomon/blob/main/LICENSE). The original paxel-local license is retained.

## Next

[Install gnomon and run it](install.md) on your own transcripts.
