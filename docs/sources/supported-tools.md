<span class="gn-label">Sources</span>

# Supported tools

<p class="gn-thesis">gnomon reads the transcripts each AI coding tool already keeps on disk. It finds them in their default locations, opens them read-only and scores all of them together as one profile.</p>

Each source has a name you can pass on the command line to score only that tool, and a `--<name>-dir` flag to read a copy kept somewhere else. See [Usage](../get-started/usage.md#read-transcripts-from-other-places).

| Tool | Name | Default location |
|------|------|------------------|
| Claude Code | `claude` | `~/.claude/projects/**/*.jsonl`, or `$CLAUDE_CONFIG_DIR/projects` |
| Codex CLI | `codex` | `~/.codex/sessions/**/*.jsonl`, or `$CODEX_HOME/sessions` |
| Gemini CLI | `gemini` | `~/.gemini/tmp/**/*.json` |
| Cursor | `cursor` | `state.vscdb` in Cursor's global storage, plus `~/.cursor/projects/**/agent-transcripts/` |
| Google Antigravity CLI | `antigravity` | `~/.gemini/antigravity-cli/conversations/*.db` |
| Google Antigravity IDE | `antigravity-ide` | `~/.gemini/antigravity-ide/conversations/*.db`, or the running IDE |
| Pi | `pi` | `~/.pi/agent/sessions/**/*.jsonl` |
| opencode | `opencode` | `~/.local/share/opencode/opencode.db`, plus older `storage/session/*/*.json` files |

Not every tool records every signal. Claude Code records the most. When a tool cannot record something, that part of the score is left out instead of scored as zero. [What each source measures](coverage.md) shows exactly what each tool covers.

## Claude Code

The fullest source. It records skills, subagents, plan mode, models, thinking and every tool call.

## Codex CLI

gnomon removes the messages Codex injects as if you had typed them (environment context, user instructions, `AGENTS.md` notices and the `whats 2+2?` start-up probe), and drops sessions that hold nothing else. The model is read from each turn's `turn_context`. Codex has no skill tool, so a shell command that reads a `SKILL.md` file counts as using that skill, and a spawned thread counts as delegation.

## Gemini CLI

Read from the JSON session files under `~/.gemini/tmp`.

## Pi and opencode

Read from their own session stores. For opencode, gnomon reads the SQLite database and any older JSON session files that were not migrated into it.

## Cursor

Cursor is found like any other source. You don't need to close it first: its database is opened read-only, and when Cursor holds a lock on it gnomon retries in SQLite's `immutable` mode, which also never writes.

gnomon reads two stores and merges them:

| Store | Default location | Carries |
|-------|------------------|---------|
| `state.vscdb` (SQLite) | macOS `~/Library/Application Support/Cursor/User/globalStorage/` · Linux `~/.config/Cursor/User/globalStorage/` · Windows `%APPDATA%\Cursor\User\globalStorage\` | The event stream: per-event timestamps and tool error statuses |
| Agent transcripts (JSONL) | `~/.cursor/projects/**/agent-transcripts/` | Full tool inputs (for edit churn), the workspace path and subagent sidechains |

The same session usually exists in both. gnomon prefers the SQLite copy and fills in the workspace path and edit churn from its JSONL twin. Sessions found only as JSONL, including every subagent sidechain, are kept as they are.

### The app and the CLI record different things

| Signal | Cursor app (`state.vscdb`) | Cursor CLI (`cursor-agent`) |
|--------|----------------------------|-----------------------------|
| Tokens | Yes, per turn | No, never written to disk |
| Model name | Yes | Yes, from `~/.cursor/chats/<hash>/<chatId>/store.db` |
| Session time | Yes, per turn | Yes, from `~/.cursor/chats/<hash>/<chatId>/meta.json` |
| Workspace | Yes | Inferred from absolute paths in tool inputs |
| Tools, prompts, errors, churn | Yes | Yes |
| MCP servers | Yes | Yes, from each server's `SERVER_METADATA.json` |

Cursor does not score [Model mix](../metrics/savvy/model-mix.md) for either entry point. Cursor bills a flat request per turn whatever the model, so choosing a cheaper model saves nothing and the axis would not mean the same thing. [Token economy](../metrics/savvy/token-economy.md) is still scored: it compares shell and MCP calls, which Cursor records, not tokens.

If the CLI's `chats` folder is missing, for example in a copied `projects` folder, the session falls back to the file's modification time and has no model.

### Overrides and caveats

- `--cursor-dir=PATH` points at a copied `projects` folder (the folder or its parent both work). The `state.vscdb` path is fixed per platform and has no flag, so database sessions are read only from the local Cursor install.
- CLI transcripts carry no per-event timestamps, so the whole session takes the file's modification time. Copying or syncing a `projects` folder to a new machine resets those times and compresses the monthly timeline.
- `ApplyPatch` churn counts raw patch lines, a slight overestimate.
- Workspace folder names encode `.` and `-` ambiguously, so the working directory is recovered from real paths in tool inputs.

## Google Antigravity

Antigravity's CLI and IDE are scored as two separate sources.

**CLI.** Each conversation is a SQLite file whose steps are stored as protobuf. gnomon decodes them with the standard library and scores prompts, tool calls (including MCP calls), tokens, models, skills read from `SKILL.md` files, and errors. `--antigravity-dir=PATH` points at a copied history and turns off the live IDE read.

**IDE.** Newer versions keep conversation databases under `~/.gemini/antigravity-ide/conversations/`, which gnomon reads like the CLI's. Older versions encrypt their transcripts. For those, gnomon reads the unencrypted usage index and, when the IDE was used in the scored window, asks every running workspace's language server for its conversations, launching the app if needed. This gives prompts, tool calls (including MCP), skills, thinking, timestamps and errors. The language server hides the model and token counts, so [Model mix](../metrics/savvy/model-mix.md) is not scored for the IDE.
