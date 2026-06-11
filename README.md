# gnomon

> A local builder-profiler for AI-assisted coding. Reads your agent transcripts on-device and grades **how you build** (gstack) and **how well you operate agents** (Agentic Quotient). Nothing leaves your machine.

_gnomon (γνώμων): the part of a sundial that casts the shadow — "the one that knows/judges." It measures by what you cast._

Fork of [paxel-local](https://github.com/Photobombastic/paxel-local) (by Max Schilling, original `LICENSE` retained), with two additions:

1. **Agentic Quotient (AQ)** — a 4-pillar score for how well you operate agents (separate from the gstack build scorecard).
2. **Codex parser fix** — drops injected wrappers (`environment_context`, `AGENTS.md`, the `whats 2+2?` boot probe) and empty seed-sessions that were inflating counts.

---

## Quick start

No dependencies — Python 3 stdlib only.

```bash
# Option A: run directly (no install)
python3 <(curl -sL https://raw.githubusercontent.com/xmartlabs/gnomon/main/paxel.py)

# Option B: clone the repo
git clone https://github.com/xmartlabs/gnomon
cd gnomon
python3 paxel.py
```

Both read all detected local transcripts (Claude, Codex, Gemini, Cursor, …) and open your profile. Option A writes outputs to the current directory; Option B writes them to the repo directory.

Restrict to one or more sources:

```bash
python3 paxel.py claude            # Claude Code only
python3 paxel.py claude codex      # Claude Code + Codex
python3 paxel.py --no-open         # don't auto-open profile.html (headless / CI)
python3 paxel.py --summary         # also write summary.json — the shareable subset
```

Scope to a time window (for monthly / quarterly check-ins):

```bash
python3 paxel.py --last=30d --summary              # rolling last month
python3 paxel.py --last=90d                        # rolling last quarter (also Nw / Nm)
python3 paxel.py --since=2026-03-01 --until=2026-05-31   # explicit window (until-day inclusive)
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
python3 paxel.py --claude-dir=/mnt/sandbox-home/.claude     # root or .../projects both work
python3 paxel.py --codex-dir=~/backups/codex                # root or .../sessions both work
# also: --gemini-dir, --pi-dir, --opencode-dir
```

### Outputs (written to the repo dir, git-ignored)

| File | What |
|------|------|
| `profile.html` | Branded, shareable profile — scorecard + AQ + signature moves |
| `report.md` | Human-readable stats |
| `stats.json` | Machine-readable metrics (incl. the full `agentic` block) |
| `summary.json` (`--summary`) | Shareable subset: the 8 measured high-signal metrics + monthly progression — no prompts, no quotes, no rubric scores. Built for the [low-cost feedback loop](docs/metrics-evaluation.md) |
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

Everything runs on-device. For accurate code-churn it shells out to your local `git` (`git log --numstat`) on the repos it finds. No network calls, no uploads.

### Cursor specifics

**No special run needed.** Cursor is auto-detected like every other source — `python3 paxel.py`
includes it, `python3 paxel.py cursor` restricts to it. You don't need to close Cursor first:
the SQLite store is opened read-only (`mode=ro`), nothing is written to it.

**Where it reads from** (two stores, merged and deduped):

| Store | Default location | Carries |
|-------|------------------|---------|
| `state.vscdb` (SQLite) | macOS `~/Library/Application Support/Cursor/User/globalStorage/` · Linux `~/.config/Cursor/User/globalStorage/` · Windows `%APPDATA%\Cursor\User\globalStorage\` | Event stream: per-event timestamps, tool error statuses |
| agent-transcripts JSONL | `~/.cursor/projects/**/agent-transcripts/` | Full tool inputs (edit old/new strings → churn), workspace path, subagent sidechains |

The same modern session exists in **both** with complementary data, so gnomon prefers the
SQLite copy and backfills workspace path + edit churn from its JSONL twin. JSONL-only
sessions (and subagent sidechains, which exist only as JSONL) are kept as-is.

**Overrides:** `--cursor-dir=PATH` points at a copied/mounted `projects` dir (root or the
`projects` subdir both work). The `state.vscdb` path is fixed per platform — there's no
flag for it, so DB-backed sessions are only read from the local Cursor install.

**Known caveats** (from upstream): workspace slugs with dashes may mis-parse; JSONL-only
sessions get a single file-mtime timestamp; `ApplyPatch` churn counts raw patch lines
(slight over-estimate).
