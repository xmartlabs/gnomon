# Self-hosted gnomon dashboard — design spec

**Date:** 2026-07-13
**Status:** approved (brainstorm session)

## Goal

Any company can run `docker compose up`, point the existing gnomon CLI at it
(`xl-ai-insights --mirdash-base=http://localhost:3000`), and get a
self-contained team dashboard: team ranking, aggregate cards, per-person
profiles, usage-over-time. Open source, zero external dependencies.

## Non-goals (v1)

- Roster metadata (team / segment / seniority columns) — excluded from v1.
- Multi-tenant / orgs. One deployment = one team.
- Replacing mirdash. This coexists with it (see Coexistence).

## Coexistence with mirdash

The gnomon CLI is **not modified**. It already resolves its base URL with this
precedence: `--mirdash-base=URL` flag → `GNOMON_MIRDASH_BASE` env →
`~/.config/gnomon/config.json` `mirdash_base` key → baked default
`https://mirdash.xmartlabs.com`.

- XL people keep using mirdash by default — nothing changes for them.
- Self-hosted users opt in by pointing the base URL at their own deployment.
- The dashboard implements the **same HTTP contract** mirdash exposes, so one
  CLI binary serves both backends. Contract changes must remain
  backward-compatible on both servers.

## Architecture

Monorepo — new `dashboard/` folder in this repo:

```
gnomon/
├── gnomon/            # CLI Python — unchanged
├── dashboard/         # Next.js app (UI + API routes)
│   ├── Dockerfile
│   └── ...
├── docker-compose.yml # 1 service: dashboard + SQLite volume
└── README.md          # new "Self-hosted dashboard" section
```

- **Stack:** Next.js (App Router) single container. SQLite via
  `better-sqlite3`, DB file on a mounted volume at `/data`.
- **Charts:** Recharts. Dark theme, mirdash-like visual language.
- **Image:** published to `ghcr.io/xmartlabs/gnomon-dashboard` on release tags;
  compose references the prebuilt image so users never build locally.

## CLI contract (server side)

The dashboard implements exactly the routes the CLI already calls:

### `GET /cli-auth?redirect_uri=http://127.0.0.1:PORT/callback&count=N`

Login page. User enters `TEAM_TOKEN` + name + email. On success the server:

1. Creates/finds the person by email.
2. Issues `N` JWTs (one per month upload the CLI plans to perform).
3. Redirects to `redirect_uri` with query params:
   - `tokens=<url-encoded JSON array of JWT strings>`
   - `uploaded=<url-encoded JSON array of {"monthKey":"YYYY-MM","uploadedAt":<int ms epoch>}>`
     for that person — same shape `_uploaded_from_query` parses.

### `POST /api/gnomon/ingest`

- Headers: `Authorization: Bearer <JWT>`, `Content-Type: application/json`.
- Body: the full `summary.json` dict for one month window.
- Behavior: upsert keyed on `(person, monthKey)` where `monthKey` is derived
  from the summary's date range anchor month; store raw JSON.
- Response `200`: `{"reportUrl": "/p/<personId>/<monthKey>"}` (relative URL —
  the CLI joins it against the base).
- Errors: `401` invalid/expired token, `400` malformed summary — plain-text or
  JSON message; the CLI surfaces the body verbatim.

## Auth model

- `TEAM_TOKEN`: shared team secret, set in `.env`. Gate for `/cli-auth` and
  any admin surface.
- `JWT_SECRET`: signing key for the short-lived upload JWTs. From `.env`, or
  auto-generated on first boot and persisted to `/data`.
- Identity = the email the user declares at login. No passwords, no OAuth in
  v1 (acceptable for a trusted-team tool; documented in README).

## Data model (SQLite)

```sql
people(id, email UNIQUE, name, created_at)
uploads(id, person_id, month_key, window_months, summary_json TEXT, uploaded_at,
        UNIQUE(person_id, month_key))
settings(key PRIMARY KEY, value)
```

Raw `summary_json` is the source of truth; all metrics are derived at read
time. This makes the dashboard schema-proof: new summary fields never require
a migration, and older dashboards ignore fields they don't know.

## UI views (v1)

1. **Team overview** (`/`)
   - Cards: team avg AQ, ingest coverage (people with current-month upload /
     total people), tokens/mo, est. cost/mo.
   - People table, sortable: name, AQ, tier badge, trend sparkline, delta,
     top pillar, tokens, cost.
   - Company usage over time: stacked monthly bars by model, tokens/cost
     toggle.
2. **Person profile** (`/p/<personId>/<monthKey>`)
   - AQ score + tier + delta, level-over-time bars.
   - 4 pillars (Breadth / Craft / Efficiency / Savvy) with sub-axes.
   - Scorecard: Execution / Planning / Engineering with trends.
   - Explore grid: planning ratio, error recovery, error rate, iteration
     depth, git churn, fanout median, compounding writes.
   - Usage: sessions, prompts, actions/prompt, model mix bar.
   - Prev/next month navigation.
3. **AI coach** (optional)
   - If `LLM_API_KEY` (Anthropic) is present in `.env`, generate a short
     coach paragraph per profile; cache in DB. Card hidden when unset.
     Off by default.

All numbers come from fields already present in `summary.json` (profile,
scorecard, metrics blocks, model usage, token_usage).

## Deploy / DX

```yaml
services:
  dashboard:
    image: ghcr.io/xmartlabs/gnomon-dashboard:latest
    ports: ["3000:3000"]
    env_file: .env        # TEAM_TOKEN required, LLM_API_KEY optional
    volumes: ["gnomon-data:/data"]
volumes:
  gnomon-data:
```

- `.env.example` with commented variables.
- GitHub Action: build + push image to ghcr on release tags.
- README quickstart: (1) `docker compose up -d`, (2) set `TEAM_TOKEN`,
  (3) run CLI with `--mirdash-base=http://<host>:3000`.

## Error handling

- Ingest validates JWT and minimal summary shape (`context.date_range`,
  `context.total_sessions`); returns 400/401 with a clear message the CLI
  already prints.
- Empty states in UI: no uploads yet → onboarding card with the exact CLI
  command to run.

## Testing

- Unit (vitest): auth token issue/verify, ingest validation + upsert,
  metric-derivation helpers.
- Fixtures: real `summary.json`-shaped payloads derived from this repo's
  sample outputs.
- Smoke e2e: compose build → POST fixture summaries → assert overview and
  profile pages render key numbers.
- Phase 2 (optional): contract test running the Python CLI against a local
  dashboard in CI.
