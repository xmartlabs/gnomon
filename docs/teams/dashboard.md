<span class="gn-label">Teams</span>

# Self-hosted dashboard

<p class="gn-thesis">The team dashboard collects the profiles your teammates share and shows the team's AQ, its trend and each person's profile. You run it yourself: one container and one volume, and the data stays on your server.</p>

## Run it

```bash
git clone https://github.com/xmartlabs/gnomon && cd gnomon
cp .env.example .env          # set TEAM_TOKEN (openssl rand -hex 24)
docker compose up -d          # the dashboard runs at http://localhost:3000
```

The container refuses to start without `TEAM_TOKEN`, so a misconfigured deploy fails loudly instead of accepting uploads from anyone.

To deploy to your own Linux VM with a GitHub Actions workflow, follow [Deploying to a Linux VM](#deploying-to-a-linux-vm) below.

## Point the CLI at your dashboard

Each teammate runs a [sharing run](sharing.md) against your server:

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@latest \
  xl-ai-insights --mirdash-base=http://localhost:3000
```

They sign in with the shared `TEAM_TOKEN` plus their name and email. The CLI chooses its server in this order, and the first match wins:

| Method | How |
|--------|-----|
| Flag | `--mirdash-base=https://your-server.example.com` |
| Environment variable | `GNOMON_MIRDASH_BASE=https://your-server.example.com` |
| Config file | `~/.config/gnomon/config.json` containing `{"mirdash_base": "https://your-server.example.com"}` |
| Default | `https://mirdash.xmartlabs.com` |

The config file lives outside the repository, so it is never committed. Without any of these, the CLI keeps using the default server, so a self-hosted dashboard is entirely opt-in.

Only `summary.json` is uploaded; prompts and file contents never leave each machine. See [Privacy](../project/privacy.md#what-is-uploaded).

## Settings

`.env.example` at the root of the repository lists every setting:

| Variable | Required | What it does |
|----------|----------|--------------|
| `TEAM_TOKEN` | Yes | Shared secret your team enters on the sign-in page. The container won't start without it |
| `JWT_SECRET` | No | Signing secret for the short-lived upload tokens. When unset, one is generated on first boot and kept in the data volume. Set it only if you run more than one replica |
| `TRUST_PROXY` | No | Set to `1` only when a reverse proxy sits in front of the container and the port is unreachable any other way. Left unset, sign-in throttling can't be bypassed by faking `x-forwarded-for` |
| `LLM_API_KEY` | No | An Anthropic API key. Turns on the AI coach: short written suggestions on each profile and for the team. Without it the coach is hidden, and a coach failure never breaks a page |
| `LLM_MODEL` | No | The coach's model. Defaults to `claude-haiku-4-5` |
| `MAX_INGEST_BYTES` | No | Largest accepted upload, in bytes. Defaults to 900 KiB, the same limit the CLI applies before sending |

## What the dashboard shows

Everything is computed when a page loads, from the raw `summary.json` uploads, so a newer CLI never needs a server migration. Each upload belongs to one person and one month. The calculations live in [`dashboard/src/lib/metrics.ts`](https://github.com/xmartlabs/gnomon/blob/main/dashboard/src/lib/metrics.ts). For what the scores mean, see [How scoring works](../metrics/how-scoring-works.md).

### Team page

A month selector offers the three most recent months with uploads. Every team figure is for the selected month and counts only the people who uploaded that month. The tier distribution says how many people that is.

- **Team AQ and its change.** The average AQ of the people who uploaded, rounded. The change is the average of each person's change from their previous upload.
- **Team trend.** The team AQ for each of the three months in the selector.
- **Tokens and cost.** Total tokens for the month, and an estimated cost, each with the change from the previous month. Each person counts once, from their upload for that exact month.
- **Pillar averages.** The average score of each AQ pillar, shown against the pillar's weight.
- **Model mix.** Each model's share of the month's tokens. The three largest models are shown and the rest are grouped as "Other".
- **Tier distribution.** How many people are at each of the six AQ levels, from Novice to Elite. Levels with nobody in them are still shown.
- **People table.** One row per person from their latest upload: AQ, level, change from the previous upload, an AQ sparkline, their strongest pillar, tokens and cost. The strongest pillar is the one with the highest score relative to its weight, so a heavy pillar doesn't win just by carrying more points.

Cost is an estimate, not a bill. Tokens are priced per model from approximate list prices in [`dashboard/src/lib/pricing.ts`](https://github.com/xmartlabs/gnomon/blob/main/dashboard/src/lib/pricing.ts): input, output, cache reads and cache writes each have their own price per million tokens. The price is picked by matching the model name (`opus`, `sonnet`, `haiku`, `gpt`, `gemini`), and an unknown model gets the mid-tier price. Edit that file to match what your team actually pays.

### Person page

One person's profile for one month, with links to their previous and next months:

- **AQ and level**, the change from the previous upload, and the level over time.
- **GStack scorecard**: the three build axes, each with its trend.
- **AQ breakdown**: every pillar and its axes with their scores.
- **Counters**: planning ratio, error recovery, errors per 100 tool calls, average iteration depth, git churn, median fan-out, compounding writes and active days. These are plain counts from the upload. They don't judge.
- **Usage**: sessions, prompts and tool calls per prompt for the month.
- **Model mix**: each model's share of the person's turns.
- **Archetype**, and AI coaching suggestions when `LLM_API_KEY` is set.

The dashboard pages have no login of their own: `TEAM_TOKEN` guards uploads and sign-in, not reading. Keep the dashboard on a private network or behind an authenticating proxy, as the deploy guide below explains.

## Deploying to a Linux VM

This guide is maintained next to the deploy code, in [`dashboard/deploy/README.md`](https://github.com/xmartlabs/gnomon/blob/main/dashboard/deploy/README.md).

--8<-- "dashboard/deploy/README.md:2"
