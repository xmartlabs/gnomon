# gnomon

> A local builder-profiler for AI-assisted coding. Reads your agent transcripts on-device and grades **how you build** (gstack) and **how well you operate agents** (Agentic Quotient). Local mode keeps all data on your machine; the separate opt-in `xl-ai-insights` flow uploads the disclosed `summary.json` fields for AI-powered analysis and historical tracking.

_gnomon (γνώμων): the part of a sundial that casts the shadow — "the one that knows/judges." It measures by what you cast._

Fork of [paxel-local](https://github.com/Photobombastic/paxel-local) (by Max Schilling, original `LICENSE` retained), with two additions:

1. **Agentic Quotient (AQ)** — a 4-pillar score for how well you operate agents (separate from the gstack build scorecard).
2. **Codex parser fix** — drops injected wrappers (`environment_context`, `AGENTS.md`, the `whats 2+2?` boot probe) and empty seed-sessions that were inflating counts.

---

## Quick start

No dependencies — Python 3 stdlib only.

Releases are tagged `v0.2.0`, `v0.3.0`, etc. Use `@latest` to always get the most recent release, or pin to a specific tag like `@v0.3.0`.

```bash
# Recommended: install the latest release (no clone needed)
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --local

# Or pin a specific version
uvx --from git+https://github.com/xmartlabs/gnomon@v0.3.0 xl-ai-insights --local

# Or clone the repo and run directly
git clone https://github.com/xmartlabs/gnomon
cd gnomon
python3 paxel.py
```

All read detected local transcripts (Claude, Codex, Gemini, Cursor, …) and open your profile.

> **Cache note:** `uvx` caches packages. After a new release, run
> `uvx --refresh --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights`
> to pick up the new version for upload/network flows.

Restrict to one or more sources:

```bash
xl-ai-insights --local claude            # Claude Code only
xl-ai-insights --local claude codex      # Claude Code + Codex
xl-ai-insights --local --no-open         # don't auto-open profile.html
xl-ai-insights --local --summary         # also write summary.json
xl-ai-insights --local --output-dir=.    # write outputs to current directory
```

`xl-ai-insights --local` is 100% local — no network, no release check, no login, nothing leaves your machine.

> **Legacy:** `python3 paxel.py` still works from a repo checkout and behaves identically. It is a thin shim over `gnomon.cli.local`.

### Sharing your profile (opt-in)

To upload `summary.json` and view your evolution over time, run `xl-ai-insights` **without** `--local`:

```bash
# Run via uvx (latest release)
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights

# Once published to PyPI
uvx xl-ai-insights

# Alternative with pipx
pipx run xl-ai-insights
```

Upload/network flows require the installed CLI to match the published latest
release exactly. Local `main`/development builds may be newer than the published
tag, but they are still blocked before login/upload because the server flow only
trusts the published release. When a mismatch is confirmed, the command prints
the refresh command:

```bash
uvx --refresh --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights
```

If you intentionally need to continue with a non-published CLI, pass
`--allow-stale-cli`. Help and `--local` never perform this network freshness
check.

It accepts the same source arguments:

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights claude
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --no-open
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --output-dir=.
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --window=3
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --help
```

Each scored point is computed over a **trailing window of `--window=N` calendar
months** (default 1) ending at its anchor month, so a month is scored on that
month. Raise it with `--window=N` if you want a point smoothed over the N months
ending at its anchor. The window applies to normal monthly runs and to
`--backfill`/`--force`.

The **per-calendar-month evidence** block (`noticed_stats_monthly`) is
deliberately wider than the scoring window: it is shaped over a trailing
six-month read of the same transcripts, so re-running gnomon still corrects
earlier months rather than freezing each one at whatever it looked like the day
it was first uploaded. Only the scoring window is published as
`context.window_months`.

Every payload declares the corpus span it was actually built over in
`context.window_months`, derived from the dates the run covered rather than from
the flag that asked for them. A run bounded to whole calendar months declares
that count; a run with no bounds at all — a plain local run, which reads every
transcript still on disk — declares `null`, because its span is whatever survived
retention rather than anything the run chose. Recomputing a stored payload
against a newer formula only accepts payloads that declare the current one-month
window: a wider or unstated corpus produces roughly a different number of
sessions and tool calls than the scoring targets are calibrated for, so it is
refused instead of being pooled with genuine one-month scores.

## Scoring contract

Current runtime contract: **scoring inputs version 18**, **AQ version 18**, and
**GStack version 18** (`score_contract_id = 18:18:18`). Compare scores only when
the contract IDs match.

`Workflow` dispatch fan-out is sourced from the real dispatched-agent transcripts
under `.../subagents/workflows/wf_*/agent-*.jsonl`, one credit per distinct
dispatched agent, rather than from the `Workflow` tool_use call count (one call
can fan out to many agents). `Agent`/`Task` calls are unchanged: one call is
still one dispatched agent.

Compounding credits MCP knowledge-write persistence calls (mem0
`add_memory`/`update_memory`, engram `mem_save`/`mem_update`) in addition to
filesystem memory/ADR writes, deduped per distinct persisted target within a
session so target-less or repeat-target spam cannot saturate the axis. Reads,
deletions, and fetch-only knowledge servers (context7-class) still credit zero.

AQ is computed once over the requested scoring window; there is no recency blend.
The scoring window is a trailing `--window=N` calendar-month window (default 1).
`noticed_stats_monthly` is separate six-month evidence used to correct monthly
history; only the scoring window is published as `context.window_months`.

`behavior.actions_per_prompt` is top-level tool calls per human instruction:
`(volume.tool_calls_total - volume.sidechain_tool_calls) /
volume.total_instructions`. `total_instructions` includes typed prompts and bare
slash commands. `tool_calls_total` remains sidechain-inclusive because rate terms
and source aggregation use it; `sidechain_tool_calls` is a diagnostic value, not a
scored term.

Steering leverage publishes the measured `actions_per_prompt` but is withheld while
its band is unvalidated. `steering_leverage.state` is
`"withheld_unvalidated_band"`, `"unmeasured_sidechain_labels"`, or `"scored"`.
An unmeasured sidechain label drops the term rather than assigning zero; remaining
Efficiency weight is renormalized.

Rate terms require sufficient tool-call evidence. Terms below the evidence floor
are dropped and their weights renormalized. An axis that scores fewer than all of
its terms includes `partial_terms` with the scored-term count and surviving weight
share.

Replay recomputes stored inputs only when their counter definitions, top-level
`actions_per_prompt` basis, and declared scoring window are compatible. It refuses
incompatible payloads instead of guessing. Single-source replay is exact;
multi-source replay reports its exactness and source-profile replay status. Uploads
are checked before POST against the 900 KiB ingest limit and fail rather than being
truncated.

Rate terms (test runs, review skills, task planning, skills,
compounding writes) are scored **per tool call**, not per session. One session is
not one unit of work across tools: a batch of 2-minute one-shot CLI sessions
otherwise acts as pure denominator and collapses the rate of a habit you actually
practise. Only the unit changes — the targets were recalibrated to match, and
absolute volume still does not raise AQ, because both sides of the ratio grow
together.

What happens when you run it (without `--local`):

1. Runs the local analysis engine to compute your metrics.
2. Opens your browser to mirdash for a one-time browser login (loopback callback on `127.0.0.1:8799`).
3. Uploads `summary.json` (see below) — associated with your account via the login session.
4. Opens your report page in the browser.

By default, `xl-ai-insights` writes paxel outputs to a temporary directory and
keeps that directory after the run finishes. This applies to normal monthly
runs, `--backfill`, and `--force` on macOS, Linux, and Windows. The command
prints the temp path unless you pass `--quiet`. If you want the final files in a
specific location, pass `--output-dir=PATH` (for example `--output-dir=.` to
write into the current directory). Existing files with the same names are
overwritten in that destination. The artifacts may include
`narrative_input.md`, which contains local transcript excerpts; don't upload or
share it.

If the browser can't open (headless/CI) or the auth times out (120 s), the command prints a warning and exits cleanly — nothing is uploaded. If you don't want to share at all, use `--local`.

**What is uploaded — exactly.** `xl-ai-insights` uploads the same `summary.json` that `xl-ai-insights --local --summary` writes to disk:

- `context` — date range, list of detected sources, total session count
- `planning_ratio_explore_to_doing`
- `errors` — error recovery ratio + error rate per 100 tool calls
- `iteration_depth` — mean, median, p90, max, files hammered >15×
- `churn` — git churn total + tool-authored churn (Edit/Write)
- `orchestration` — fanout median + delegate action count
- `compounding_writes`
- `ecosystem` — distinct skills, total skill uses, distinct MCP servers, and raw
  custom skill and MCP server names
- `progression_monthly` — per-month counts (prompts, tools, sessions, active days, tool churn lines) plus the **names of AI models used that month** (top model + per-model turn counts, up to 3 models per month)
- `profile` — computed AQ/archetype/scorecard block used by the report UI
- `noticed_stats` — share-safe evidence used by the local "What we noticed" cards: counts and derived metrics for shipping, iteration, errors, models, rhythm, prompt lengths, agents, sessions, and top tools

**What is NOT uploaded:** Prompts and file contents are not uploaded. Verbatim
quotes, file paths, `narrative_input.md` contents, and `stats.json` are also
excluded. The payload does include raw custom skill and MCP server names; those
are user-chosen identifiers and may themselves contain a project, customer, or
environment name. Model names (for example `claude-opus-4` or `gpt-5.4`) are
also included. The mirdash server associates the upload with your account via
your login token; `xl-ai-insights` itself sends no email address.

### Overriding the mirdash URL

For `xl-ai-insights`, precedence (first match wins):

| Method | How |
|--------|-----|
| CLI flag | `--mirdash-base=https://your-server.example.com` |
| Env var | `GNOMON_MIRDASH_BASE=https://your-server.example.com` |
| Config file | `~/.config/gnomon/config.json` with `{"mirdash_base": "https://your-server.example.com"}` |
| Default | `https://mirdash.xmartlabs.com` |

The config file is optional and only needed to override the default. It lives outside the repo (`~/.config/gnomon/`) so it won't be committed.

```bash
# Dev / self-hosted override
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --mirdash-base=http://localhost:3000
```

Scope to a time window (for monthly / quarterly check-ins):

```bash
xl-ai-insights --local --last=30d --summary         # rolling last month
xl-ai-insights --local --last=90d                    # rolling last quarter (also Nw / Nm)
xl-ai-insights --local --since=2026-03-01 --until=2026-05-31   # explicit window (until-day inclusive)
```

Every metric follows the requested window — **including git churn**, whose
`git log --since/--until` range tracks the kept events, and **including AQ**.
Events without a timestamp are dropped in windowed runs because they cannot
honor explicit bounds; that includes Cursor JSONL-only sessions beyond their
single file-mtime timestamp.

### Sandbox / self-hosted / copied histories

Histories don't have to live in their default home-dir locations. gnomon honors the
same env vars the CLIs use (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) and accepts explicit
dir overrides — handy for transcripts mounted or `scp`'d from a sandbox, devcontainer,
or remote box:

```bash
xl-ai-insights --local --claude-dir=/mnt/sandbox-home/.claude     # root or .../projects both work
xl-ai-insights --local --codex-dir=~/backups/codex                # root or .../sessions both work
# also: --gemini-dir, --antigravity-dir, --pi-dir, --opencode-dir
```

Custom planning skills (idiosyncratic names) can be added to the Plan-ceremony detector
without a code change via a comma-separated env var — it extends the built-in needles:

```bash
GNOMON_PLAN_SKILL_NEEDLES="roadmap,my-planner" xl-ai-insights --local
```

### Outputs (written to the current directory by default, git-ignored)

| File | What |
|------|------|
| `profile.html` | Branded, shareable profile — scorecard + AQ + signature moves |
| `report.md` | Human-readable stats |
| `stats.json` | Machine-readable metrics (incl. the full `agentic` block) |
| `summary.json` (`--summary`) | Shareable subset: the 8 measured high-signal metrics + `progression_monthly` + computed `profile` + `noticed_stats` blocks — no prompts or verbatim quotes. Built for the [low-cost feedback loop](docs/metrics-evaluation.md) |
| `narrative_input.md` | Curated excerpts for an optional LLM narrative pass |

> These outputs contain **your** transcript-derived data. They're in `.gitignore` — don't commit them.

---

## Sources

Auto-detected from their default local locations:

| Source | Location | Notes |
|--------|----------|-------|
| Claude Code | `~/.claude/projects/**/*.jsonl` | Fullest signal coverage |
| Codex CLI (OpenAI/GPT) | `~/.codex/**/*.jsonl` | Injected wrappers + seed-sessions filtered; model read from `turn_context`; SKILL.md shell-reads counted as skill usage |
| Gemini CLI | `~/.gemini/**/*.json` | |
| Others (PI, opencode) | per-tool dirs | parsed where present |
| Cursor | `state.vscdb` + `~/.cursor/projects/.../agent-transcripts` | full (SQLite-first + JSONL, deduped) |
| Google Antigravity CLI (`antigravity`) | `~/.gemini/antigravity-cli/conversations/*.db` (SQLite + protobuf) | Fully scored offline — prompts, tool calls (incl. MCP `server::tool`), tokens, models+switches, skills (`SKILL.md` reads), errors — decoded from the protobuf step payloads (stdlib decoder, no deps). `--antigravity-dir=PATH` to point at copied history (disables the live IDE read). |
| Google Antigravity IDE (`antigravity-ide`) | encrypted `*.pb` → live language-server API | Scored as a **separate source**. Transcripts are encrypted, so gnomon reads the unencrypted usage index and, when the IDE was used in-window, pulls conversations from **every** running workspace language server (launches the app if needed; stdlib only, no extra dependency). Gives prompts, tool calls (incl. MCP), skills, thinking, real timestamps, errors. The server **masks model id and tokens**, so those axes are dropped (not scored 0). |

---

## What it measures

Two **independent** questions — the report frames both:

### 1. gstack scorecard — *how you build*
Three 0–10 axes (Execution / Planning / Engineering) grounded in [gstack](https://github.com/garrytan/gstack) and a described steering style. Counts are measured; scores are a transparent rubric. **Axes unchanged from upstream.**

### 2. Agentic Quotient (AQ) — *how you operate agents*
0–100, four pillars (each shown with its sub-axes):

| Pillar | Weight | Sub-axes |
|--------|--------|----------|
| **Breadth** | 30 | Orchestration · Skill fluency · Tool command (MCP+CLI) · Discipline |
| **Craft** | 35 | Verification · Grounding · Compounding |
| **Efficiency** | 20 | Steering leverage (withheld while unvalidated) · Recovery |
| **Savvy** | 15 | Model mix · Token economy |

**Level** (one honest ladder, driven by AQ — no flattery at the floor): Novice <25 · Apprentice 25–45 · Adequate 45–60 · Proficient 60–75 · Advanced 75–88 · **Elite 88–100**. This is also the profile headline; the quote names your thinnest pillar so the gap is visible.

> Orchestration now reads **coordination** (median agents coordinated per orchestrating session), not raw dispatch volume — a serial grinder firing one agent at a time can't max it.

`MCP vs CLI` and `Tool diversity` are **described, not graded** (like steering — no better/worse end). CLI-first is treated as token-efficient, not a gap.

---

## Cross-model fairness — read this

gnomon is multi-source, and metrics are provider-agnostic where possible:

- **Provider-agnostic where telemetry allows:** git churn, MCP/CLI tool command, grounding, recovery, steering leverage, and compounding (matches `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `memory/` / `docs/adr`). **Model mix** rewards diversity and observable lower-tier routing using explicit provider tier tables for Anthropic and OpenAI; unsupported or ambiguous linkage is N/A rather than guessed.
- **Codex parity fixes:** the active model is read from Codex's `turn_context` (so GPT usage shows up in Model mix instead of reading as model-less), `update_plan` counts as planning (TodoWrite), and shell reads of `skills/<name>/SKILL.md` count as skill usage — Codex has no first-class Skill tool, so that's how skills are actually consumed there.
- **Claude-Code-specific signals** (still under-read for Codex/Gemini): `attributionSkill` precision. **ToolSearch** is no longer scored — it is ~94% harness-forced `select:` tool-loading, so it is published as a raw diagnostic count on the Tool command axis but feeds neither Tool command nor Token economy. These reflect Claude Code's ecosystem, not universal capability.

**Bottom line:** scores are most complete for Claude Code. Codex/Gemini profiles are valid; ToolSearch no longer moves any axis, so its Claude-only nature no longer under-reads other sources. We surface this rather than hide it.

---

## Monthly progression

`stats.json["progression"]["monthly"]`, a **Progression** section in `report.md`, and a
**Your trajectory** chart in `profile.html`: per-month prompts, tool calls, sessions,
active days, tool-authored churn, and top model. When a plan's monthly limits cap any
single month's volume, the month-over-month slope is the honest signal — not lifetime
totals.

---

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Covers the CLI extractor, Codex injected-message filter, compounding-path matcher, and the full `compute_aq` pillar math.

---

## Privacy

All analysis runs on-device. For accurate code-churn it shells out to your local `git` (`git log --numstat`) on the repos it finds. `xl-ai-insights --local` makes zero network calls — nothing leaves your machine.

If you run `xl-ai-insights` (without `--local`) against the default public
mirdash, it first makes one outbound GET request to GitHub Releases to check the
latest stable CLI version. A custom `--mirdash-base` skips that public release
policy. After you authenticate, the command POSTs `summary.json` (described
above under "What is uploaded") to the selected mirdash. Prompts and file
contents remain excluded, while raw custom skill/MCP names and model names are
included as disclosed above. Running without `--local` is entirely opt-in.

### Cursor specifics

**No special run needed.** Cursor is auto-detected like every other source — `xl-ai-insights --local`
includes it, `xl-ai-insights --local cursor` restricts to it. You don't need to close Cursor first:
the SQLite store is opened read-only (`mode=ro`), nothing is written to it.

**Where it reads from** (two stores, merged and deduped):

| Store | Default location | Carries |
|-------|------------------|---------|
| `state.vscdb` (SQLite) | macOS `~/Library/Application Support/Cursor/User/globalStorage/` · Linux `~/.config/Cursor/User/globalStorage/` · Windows `%APPDATA%\Cursor\User\globalStorage\` | Event stream: per-event timestamps, tool error statuses |
| agent-transcripts JSONL | `~/.cursor/projects/**/agent-transcripts/` | Full tool inputs (edit old/new strings → churn), workspace path, subagent sidechains |

The same modern session exists in **both** with complementary data, so gnomon prefers the
SQLite copy and backfills workspace path + edit churn from its JSONL twin. JSONL-only
sessions (and subagent sidechains, which exist only as JSONL) are kept as-is.

The DB is opened with `mode=ro`; if Cursor is running and holds a write-ahead lock, gnomon
retries with `immutable=1` (still read-only) so an open editor never blanks out your SQLite data.

**GUI app vs. CLI (`cursor-agent`) — what each backend records.** The two entry points persist
to different stores, and the CLI's transcript is leaner:

| Signal | GUI app (`state.vscdb`) | CLI `cursor-agent` |
|--------|--------------------------|---------------------|
| Tokens (input/output) | ✅ `tokenCount` per turn | ❌ not persisted anywhere (handled only in-flight) |
| Model name | ✅ `modelConfig.modelName` | ✅ `~/.cursor/chats/*/<chatId>/store.db` → `lastUsedModel` |
| Session timestamp | ✅ `createdAt` per turn | ✅ `~/.cursor/chats/*/<chatId>/meta.json` → `createdAtMs` |
| Workspace / cwd | ✅ (+ slug) | ✅ inferred from absolute tool-input paths |
| Tools, prompts, errors, churn | ✅ | ✅ |
| MCP servers | ✅ | ✅ resolved via the `<slug>/mcps/*/SERVER_METADATA.json` sidecar |

The CLI transcript JSONL is lean (`role` + `content` + `turn_ended`), but its sibling
`~/.cursor/chats/<workspaceHash>/<chatId>/` store backfills the real model and session date,
so a CLI profile is scored on everything **except token economy and model mix** — tokens are
never written to disk, and model choice is flat-rate (one request per turn regardless of model).
(If the `chats` dir is absent — e.g. a copied/mounted `projects`
dir without it — the session falls back to file mtime and no model, as before.)

**Overrides:** `--cursor-dir=PATH` points at a copied/mounted `projects` dir (root or the
`projects` subdir both work). The `state.vscdb` path is fixed per platform — there's no
flag for it, so DB-backed sessions are only read from the local Cursor install.

**Known caveats:** CLI transcript JSONL carries no per-event timestamps (single file-mtime
stamp), token data, or model field. The chats sidecar may recover the model, but tokens remain
unavailable. If a `projects` dir is copied/synced to a new machine, mtimes reset and the monthly
timeline compresses; `ApplyPatch` churn counts raw patch lines (slight over-estimate). Workspace
slugs encode `.`/`-` ambiguously, so cwd is recovered from real tool-input paths.
