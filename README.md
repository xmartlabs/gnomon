<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/gnomon-mark-dark.svg">
    <img src=".github/assets/gnomon-mark-light.svg" alt="gnomon" width="64">
  </picture>
</p>
<h1 align="center">gnomon</h1>
<p align="center"><i>A local builder-profiler for AI-assisted coding.</i></p>
<p align="center">
  <sub><i>gnomon (γνώμων): the part of a sundial that casts the shadow — "the one that knows/judges." It measures by what you cast.</i></sub>
</p>

<p align="center">
  <a href="https://github.com/xmartlabs/gnomon/actions/workflows/ci.yml"><img src="https://github.com/xmartlabs/gnomon/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/xmartlabs/gnomon/releases/latest"><img src="https://img.shields.io/github/v/release/xmartlabs/gnomon?sort=semver&amp;label=release" alt="Latest release"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/xmartlabs/gnomon" alt="License"></a>
  <a href="#install-and-run"><img src="https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.8+"></a>
</p>

<p align="center">
  <a href="https://xmartlabs.github.io/gnomon/"><b>Documentation</b></a> ·
  <a href="https://xmartlabs.github.io/gnomon/get-started/install/">Install</a> ·
  <a href="https://xmartlabs.github.io/gnomon/metrics/how-scoring-works/">How scoring works</a> ·
  <a href="https://xmartlabs.github.io/gnomon/project/privacy/">Privacy</a>
</p>

gnomon reads the AI coding-agent transcripts already on your disk (Claude Code,
Codex, Gemini CLI, Cursor, Google Antigravity CLI and IDE, Pi and opencode) and
turns a month of them into two readings: a **GStack scorecard** for how you
build, and an **Agentic Quotient (AQ)** for how well you operate agents. The CLI
uses only the Python 3 standard library, and `--local` runs make no network
calls. Every weight, target and formula is public, and a tool that cannot record
a signal is never scored as zero for it.

## Install and run

You need Python 3.8+ and [uv](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@latest xl-ai-insights --local
```

gnomon finds every supported tool's transcripts, scores the current calendar
month, writes its outputs to the current directory and opens `profile.html`.
Nothing leaves your machine. To run from a checkout instead, see
[Install & quick start](https://xmartlabs.github.io/gnomon/get-started/install/).

| Output | What it holds |
|--------|---------------|
| `profile.html` | Your profile: the GStack scorecard, the AQ with its pillars and axes, and what to work on next |
| `report.md` / `stats.json` | Every computed metric, as text and as JSON |
| `summary.json` | The shareable subset, with no prompts, quotes or file paths. See [Usage & outputs](https://xmartlabs.github.io/gnomon/get-started/usage/#outputs) |

These files hold data derived from your transcripts; don't commit them.

## Share with your team (opt-in)

Run the same command without `--local` to upload `summary.json` and follow your
profile over time, or point it at a [self-hosted team dashboard](https://xmartlabs.github.io/gnomon/teams/dashboard/)
(one container, one volume). See [Sharing a profile](https://xmartlabs.github.io/gnomon/teams/sharing/) and
[Privacy](https://xmartlabs.github.io/gnomon/project/privacy/) for exactly what is sent.

## Documentation

The full documentation lives at **[xmartlabs.github.io/gnomon](https://xmartlabs.github.io/gnomon/)**:

- [How scoring works](https://xmartlabs.github.io/gnomon/metrics/how-scoring-works/): the AQ, its pillars and levels
- [What each source measures](https://xmartlabs.github.io/gnomon/sources/coverage/): which tool feeds which axis
- [Privacy](https://xmartlabs.github.io/gnomon/project/privacy/): what is uploaded and what never is
- [Self-hosted dashboard](https://xmartlabs.github.io/gnomon/teams/dashboard/): run your own team dashboard
- [Scoring reference](https://xmartlabs.github.io/gnomon/metrics/scoring-reference/): contract versions, payload fields and replay rules
- [miraudit](skills/miraudit/README.md): re-derive your published AQ from your own transcripts

## Contributing

```bash
python3 -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, the test
suites and how the scoring contract is versioned.

## License and credits

MIT — see [LICENSE](LICENSE).

Fork of [paxel-local](https://github.com/Photobombastic/paxel-local) (by Max
Schilling, original `LICENSE` retained), with two additions:

1. **Agentic Quotient (AQ)** — a 4-pillar score for how well you operate
   agents (separate from the gstack build scorecard).
2. **Codex parser fix** — drops injected wrappers (`environment_context`,
   `AGENTS.md`, the `whats 2+2?` boot probe) and empty seed-sessions that were
   inflating counts.

The gstack build axes are grounded in [gstack](https://github.com/garrytan/gstack)
and unchanged from upstream.
