# gnomon

> A local builder-profiler for AI-assisted coding. Reads your agent transcripts on-device and grades **how you build** (gstack) and **how well you operate agents** (Agentic Quotient). Everything runs locally — nothing leaves your machine. For AI-powered analysis and to track your evolution over time, run the separate opt-in command `xl-ai-insights`.

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
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --local

# Or pin a specific version
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@v0.3.0 xl-ai-insights --local

# Or clone the repo and run directly
git clone https://github.com/xmartlabs/gnomon
cd gnomon
python3 paxel.py
```

All read detected local transcripts (Claude, Codex, Gemini, Cursor, …) and open your profile.

Restrict to one or more sources:

```bash
xl-ai-insights --local claude            # Claude Code only
xl-ai-insights --local claude codex      # Claude Code + Codex
xl-ai-insights --local --no-open         # don't auto-open profile.html
xl-ai-insights --local --summary         # also write summary.json
xl-ai-insights --local --output-dir=.    # write outputs to current directory
```

`xl-ai-insights --local` is 100% local — no network, no login, nothing leaves your machine.

> **Legacy:** `python3 paxel.py` still works from a repo checkout and behaves identically. It is a thin shim over `gnomon.cli.local`.

### Sharing your profile (opt-in)

To upload `summary.json` and view your evolution over time, run `xl-ai-insights` **without** `--local`:

```bash
# Run via uvx (latest release)
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights

# Once published to PyPI
uvx xl-ai-insights

# Alternative with pipx
pipx run xl-ai-insights
```

It accepts the same source arguments:

```bash
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights claude
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --no-open
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --output-dir=.
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --window=3
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --help
```

Each scored point is computed over a **trailing window of `--window=N` calendar
months** (default 6) ending at its anchor month, so a single weak month doesn't
tank the score. `--window=1` scores each month on its own. The window applies to
normal monthly runs and to `--backfill`/`--force`.

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
- `ecosystem` — distinct skills, total skill uses, distinct MCP servers
- `progression_monthly` — per-month counts (prompts, tools, sessions, active days, tool churn lines) plus the **names of AI models used that month** (top model + per-model turn counts, up to 3 models per month)
- `profile` — computed AQ/archetype/scorecard block used by the report UI
- `noticed_stats` — share-safe evidence used by the local "What we noticed" cards: counts and derived metrics for shipping, iteration, errors, models, rhythm, prompt lengths, agents, sessions, and top tools

**What is NOT uploaded:** prompts, verbatim quotes, project names, file paths, `narrative_input.md` contents, and `stats.json`. The mirdash server associates the upload with your account via your login token; `xl-ai-insights` itself sends no email or PII. Note: model names (e.g. `claude-opus-4`, `gpt-5.4`) are included in `progression_monthly`, `profile`, and `noticed_stats`.

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
uvx --reinstall --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --mirdash-base=http://localhost:3000
```

Scope to a time window (for monthly / quarterly check-ins):

```bash
xl-ai-insights --local --last=30d --summary         # rolling last month
xl-ai-insights --local --last=90d                    # rolling last quarter (also Nw / Nm)
xl-ai-insights --local --since=2026-03-01 --until=2026-05-31   # explicit window (until-day inclusive)
```

Everything follows the window — **including git churn**, whose `git log --since/--until`
range tracks the kept events. Events without a timestamp are dropped in windowed runs
(they can't honor "this period only"); that includes Cursor JSONL-only sessions beyond
their single file-mtime timestamp.

### Sandbox / self-hosted / copied histories

Histories don't have to live in their default home-dir locations. gnomon honors the
same env vars the CLIs use (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) and accepts explicit
dir overrides — handy for transcripts mounted or `scp`'d from a sandbox, devcontainer,
or remote box:

```bash
xl-ai-insights --local --claude-dir=/mnt/sandbox-home/.claude     # root or .../projects both work
xl-ai-insights --local --codex-dir=~/backups/codex                # root or .../sessions both work
# also: --gemini-dir, --pi-dir, --opencode-dir
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
| Google Antigravity | `state.vscdb` (protobuf) | detected; conversation count + date range surfaced as metadata. Transcripts live **server-side**, so it can't be scored honestly |

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
| **Efficiency** | 20 | Steering leverage (sweet-spot) · Recovery |
| **Savvy** | 15 | Model mix · Token economy |

**Level** (one honest ladder, driven by AQ — no flattery at the floor): Novice <25 · Apprentice 25–45 · Adequate 45–60 · Proficient 60–75 · Advanced 75–88 · **Elite 88–100**. This is also the profile headline; the quote names your thinnest pillar so the gap is visible.

> Orchestration now reads **coordination** (median agents coordinated per orchestrating session), not raw dispatch volume — a serial grinder firing one agent at a time can't max it.

`MCP vs CLI` and `Tool diversity` are **described, not graded** (like steering — no better/worse end). CLI-first is treated as token-efficient, not a gap.

---

## Cross-model fairness — read this

gnomon is multi-source, and metrics are provider-agnostic where possible:

- **Provider-agnostic:** git churn, MCP/CLI tool command, grounding, recovery, steering leverage, compounding (matches `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `memory/` / `docs/adr`), and **Model mix** (rewards using >1 model and routing work off your default — no hard-coded model names).
- **Codex parity fixes:** the active model is read from Codex's `turn_context` (so GPT usage shows up in Model mix instead of reading as model-less), `update_plan` counts as planning (TodoWrite), and shell reads of `skills/<name>/SKILL.md` count as skill usage — Codex has no first-class Skill tool, so that's how skills are actually consumed there.
- **Claude-Code-specific signals** (still under-read for Codex/Gemini): `attributionSkill` precision and **ToolSearch** (part of Token economy). These reflect Claude Code's ecosystem, not universal capability.

**Bottom line:** scores are most complete for Claude Code. Codex/Gemini profiles are valid but slightly under-read on ToolSearch-style sub-axes. We surface this rather than hide it.

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

If you run `xl-ai-insights` (without `--local`), it makes one outbound network call: a POST of `summary.json` (described above under "What is uploaded") to mirdash after you authenticate. No prompts, no quotes, no project names are ever sent. Running `xl-ai-insights` without `--local` is entirely opt-in.

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
so a CLI profile is scored on everything **except token economy** — tokens are the one signal
the CLI never writes to disk. (If the `chats` dir is absent — e.g. a copied/mounted `projects`
dir without it — the session falls back to file mtime and no model, as before.)

**Overrides:** `--cursor-dir=PATH` points at a copied/mounted `projects` dir (root or the
`projects` subdir both work). The `state.vscdb` path is fixed per platform — there's no
flag for it, so DB-backed sessions are only read from the local Cursor install.

**Known caveats:** CLI transcripts carry no per-event timestamps (single file-mtime stamp) and
no tokens/model; if a `projects` dir is copied/synced to a new machine, mtimes reset and the
monthly timeline compresses; `ApplyPatch` churn counts raw patch lines (slight over-estimate).
Workspace slugs encode `.`/`-` ambiguously, so cwd is recovered from real tool-input paths.
