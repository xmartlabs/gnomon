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
git clone https://github.com/nicoache1/gnomon
cd gnomon
python3 paxel.py            # reads all detected local transcripts; writes + opens your profile
```

Restrict to one or more sources:

```bash
python3 paxel.py claude            # Claude Code only
python3 paxel.py claude codex      # Claude Code + Codex
python3 paxel.py --no-open         # don't auto-open profile.html (headless / CI)
```

### Outputs (written to the repo dir, git-ignored)

| File | What |
|------|------|
| `profile.html` | Branded, shareable profile — scorecard + AQ + signature moves |
| `report.md` | Human-readable stats |
| `stats.json` | Machine-readable metrics (incl. the full `agentic` block) |
| `narrative_input.md` | Curated excerpts for an optional LLM narrative pass |

> These outputs contain **your** transcript-derived data. They're in `.gitignore` — don't commit them.

---

## Sources

Auto-detected from their default local locations:

| Source | Location | Notes |
|--------|----------|-------|
| Claude Code | `~/.claude/projects/**/*.jsonl` | Fullest signal coverage |
| Codex CLI (OpenAI/GPT) | `~/.codex/**/*.jsonl` | Injected wrappers + seed-sessions filtered |
| Gemini CLI | `~/.gemini/**/*.json` | |
| Others (PI, opencode) | per-tool dirs | parsed where present |

---

## What it measures

Two **independent** questions — the report frames both:

### 1. gstack scorecard — *how you build*
Three 0–10 axes (Execution / Planning / Engineering) grounded in [gstack](https://github.com/garrytan/gstack), plus an archetype (Architect, Quality Guardian, …) and a described steering style. Counts are measured; scores are a transparent rubric. **Unchanged from upstream.**

### 2. Agentic Quotient (AQ) — *how you operate agents*
0–100, four pillars (each shown with its sub-axes):

| Pillar | Weight | Sub-axes |
|--------|--------|----------|
| **Breadth** | 30 | Orchestration · Skill fluency · Tool command (MCP+CLI) · Discipline |
| **Craft** | 35 | Verification · Grounding · Compounding |
| **Efficiency** | 20 | Steering leverage (sweet-spot) · Recovery |
| **Savvy** | 15 | Model mix · Token economy |

Tiers: Operator <40 · Power User 40–60 · Orchestrator 60–80 · **Systems Builder 80–100**.

`MCP vs CLI` and `Tool diversity` are **described, not graded** (like steering — no better/worse end). CLI-first is treated as token-efficient, not a gap.

---

## Cross-model fairness — read this

gnomon is multi-source, and metrics are provider-agnostic where possible:

- **Provider-agnostic:** git churn, MCP/CLI tool command, grounding, recovery, steering leverage, compounding (matches `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `memory/` / `docs/adr`), and **Model mix** (rewards using >1 model and routing work off your default — no hard-coded model names).
- **Claude-Code-specific signals** (read 0 for Codex/Gemini, so those users score lower on these): the **skills** system (Skill fluency, and review/meta-skill detection in Craft) and **ToolSearch** (part of Token economy). These reflect Claude Code's ecosystem, not universal capability.

**Bottom line:** scores are most complete for Claude Code. Codex/Gemini profiles are valid but under-read on skill/ToolSearch sub-axes. We surface this rather than hide it.

---

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Covers the CLI extractor, Codex injected-message filter, compounding-path matcher, and the full `compute_aq` pillar math.

---

## Privacy

Everything runs on-device. For accurate code-churn it shells out to your local `git` (`git log --numstat`) on the repos it finds. No network calls, no uploads.
