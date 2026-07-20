# Self-Hosted Gnomon Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single-container, open-source team dashboard that the existing gnomon CLI can upload to via `--mirdash-base`, showing team ranking, aggregate cards, per-person profiles, and usage-over-time.

**Architecture:** Next.js (App Router) serves both the UI and the CLI-facing HTTP contract (`GET /cli-auth`, `POST /api/gnomon/ingest`). SQLite (better-sqlite3) on a mounted `/data` volume stores raw `summary.json` uploads keyed on `(person, monthKey)`; all metrics are derived at read time. Docker image published to ghcr; `docker-compose.yml` at repo root runs it.

**Tech Stack:** Next.js 15 (App Router, TypeScript), better-sqlite3, jose (JWT HS256), Recharts, Tailwind CSS 4, Vitest. Node 22.

**Spec:** `docs/specs/2026-07-13-self-hosted-dashboard-design.md`

## Global Constraints

- The Python CLI (`gnomon/`) is **not modified**. The server must match the contract in `gnomon/upload/mirdash.py` and `gnomon/upload/auth.py` exactly.
- Coexists with mirdash: same contract, opt-in via `--mirdash-base` / `GNOMON_MIRDASH_BASE` / config key `mirdash_base`. Default CLI behavior (XL's mirdash) untouched.
- One container, one volume. No external services required. `LLM_API_KEY` optional, coach off without it.
- `TEAM_TOKEN` env var is required at boot; server refuses to start without it.
- `redirect_uri` on `/cli-auth` MUST be validated to loopback (`http://127.0.0.1:*` or `http://localhost:*`) — never redirect tokens elsewhere.
- Raw `summary_json` stored verbatim; derive on read; unknown fields tolerated everywhere (`?.` + fallbacks).
- All work on branch `feat/self-hosted-dashboard`. Commit after every task.
- Run all dashboard commands from `dashboard/` unless stated otherwise.

## summary.json fields the dashboard reads (reference)

From `gnomon/output/summary.py` (`build_summary`) — the upload body shape:

```jsonc
{
  "context": { "date_range": ["YYYY-MM-DD","YYYY-MM-DD"], "total_sessions": 171,
               "total_prompts": 1167, "sources": ["claude"], "client_version": "0.3.0",
               "window_months": 6 },   // window_months injected by CLI before upload
  "planning_ratio_explore_to_doing": 0.82,
  "errors": { "error_recovery_ratio": 0.98, "error_rate_per_100_tools": 2.6 },
  "iteration_depth": { "mean": 2.3, "median": 2, "p90": 5, "max": 89, "files_over_15x": 3 },
  "churn": { "git_churn_total": 8159072, "tool_churn_edit_write": 104990,
             "active_hours": 120, "actions_per_prompt": 14 },
  "orchestration": { "fanout_median": 3.5, "delegate_actions": 42 },
  "compounding_writes": 91,
  "ecosystem": { "skills_distinct": 12, "mcp_servers_distinct": 4, "...": "..." },
  "progression_monthly": [ { "month": "2026-06", "prompts": 1077, "sessions": 157,
      "tool_calls": 15472, "active_days": 14, "tool_churn_lines": 104990,
      "models": [["claude-opus-4-8", 24849], ["claude-fable-5", 1794]],
      "top_model": "claude-opus-4-8", "tokens_input": 9643595, "tokens_output": 21017872,
      "tokens_cache_read": 5575354211, "tokens_cache_creation": 117107983,
      "tokens_total": 5723123661 } ],
  "profile": {
    "aq": { "aq_0_100": 93, "tier": "Elite",
            "pillars": [ { "name": "Breadth", "weight": 30, "score": 27.0,
                           "axes": [ { "name": "...", "weight": 10, "score": 8.5 } ] } ] },
    "archetype": { "title": "...", "quote": "..." },
    "scores": { "execution": { "value": 8.5, "gloss": "...", "subs": [...] },
                "planning":  { "value": 10.0, "...": "..." },
                "engineering": { "value": 8.6, "...": "..." } },
    "model_usage": [ { "model_id": "claude-opus-4-8", "model": "Opus 4.8",
                       "count": 24849, "pct": 0.8, "tokens_input": 0, "...": 0 } ]
  },
  "token_usage": { "total_input": 0, "total_output": 0, "total_cache_read": 0,
                   "total_cache_creation": 0,
                   "by_model": [ { "model_id": "...", "model": "...", "input": 0,
                                   "output": 0, "cache_read": 0, "cache_creation": 0 } ] }
}
```

**monthKey derivation:** month (`YYYY-MM`) of `context.date_range[1]` (the window's end/anchor month — CLI sets `--until` to the anchor month's last day).

**Usage-over-time note:** per-month tokens come from the `progression_monthly` entry whose `month` equals the row's monthKey. Per-model split for a month is **approximated** by distributing `tokens_total` proportionally to model invocation counts in `models` (exact per-model monthly tokens are not in the payload). Cost applies the pricing map to that split.

---

### Task 1: Scaffold the dashboard app

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/next.config.ts`
- Create: `dashboard/vitest.config.ts`
- Create: `dashboard/src/app/layout.tsx`
- Create: `dashboard/src/app/globals.css`
- Create: `dashboard/src/app/page.tsx` (placeholder, replaced in Task 8)
- Create: `dashboard/.gitignore`
- Create: `dashboard/tests/smoke.test.ts`

**Interfaces:**
- Produces: a Next.js app that builds (`npm run build`) and tests (`npm test`), with Tailwind 4 and the theme CSS variables later tasks use (`--bg-base`, `--bg-surface`, `--bg-elev`, `--text-primary`, `--text-secondary`, `--text-muted`, `--border`, `--accent`, `--purple`).

- [ ] **Step 1: Create package.json**

```json
{
  "name": "gnomon-dashboard",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "better-sqlite3": "^12.11.0",
    "jose": "^6.2.0",
    "next": "^16.2.0",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "react-is": "^19.2.0",
    "recharts": "^3.9.0"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.1.0",
    "@types/better-sqlite3": "^7.6.12",
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "postcss": "^8.5.0",
    "tailwindcss": "^4.1.0",
    "typescript": "^5.7.0",
    "vitest": "^4.1.0"
  }
}
```

> **Dep notes (validated 2026-07-20):** current major lines are Next 16.2.x, better-sqlite3 12.x, jose 6.x, recharts 3.x, vitest 4.x. Next 16 needs Node ≥20.9 (we use 22, OK) and React 18.2+/19 (we use 19.2). `recharts` v3 requires a matching `react-is`; `@tailwindcss/postcss` needs a direct `postcss` dep. Review each major's migration notes on install; jose 6 and vitest 4 have breaking changes vs the previously-pinned 5/3 lines.

- [ ] **Step 2: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Create next.config.ts**

better-sqlite3 is a native module — it must stay external to the bundler, and `standalone` output is what the Dockerfile copies.

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["better-sqlite3"],
};

export default nextConfig;
```

- [ ] **Step 4: Create postcss config and globals.css**

`dashboard/postcss.config.mjs`:

```js
export default { plugins: { "@tailwindcss/postcss": {} } };
```

`dashboard/src/app/globals.css`:

```css
@import "tailwindcss";

:root {
  --bg-base: #1a1f27;
  --bg-surface: #222831;
  --bg-elev: #2a3038;
  --text-primary: #f0f0f0;
  --text-secondary: #c7cacf;
  --text-muted: #85888f;
  --border: rgba(255, 255, 255, 0.078);
  --accent: #ee1a64;
  --purple: #5d5fee;
}

body {
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, sans-serif;
}
```

(Same palette as the CLI auth success page in `gnomon/upload/auth.py` — one visual language across CLI and dashboard.)

- [ ] **Step 5: Create layout and placeholder page**

`dashboard/src/app/layout.tsx`:

```tsx
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "gnomon dashboard",
  description: "Self-hosted team dashboard for gnomon build profiles",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
```

`dashboard/src/app/page.tsx` (placeholder):

```tsx
export default function Home() {
  return <main className="p-8">gnomon dashboard</main>;
}
```

- [ ] **Step 6: Create vitest.config.ts and smoke test**

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
});
```

`dashboard/tests/smoke.test.ts`:

```ts
import { describe, it, expect } from "vitest";

describe("smoke", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 7: Create dashboard/.gitignore**

```
node_modules/
.next/
*.db
.env
```

- [ ] **Step 8: Install and verify**

Run: `cd dashboard && npm install && npm test && npm run build`
Expected: smoke test PASS, build succeeds.

- [ ] **Step 9: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): scaffold Next.js app with Tailwind and Vitest"
```

---

### Task 2: SQLite layer

**Files:**
- Create: `dashboard/src/lib/db.ts`
- Test: `dashboard/tests/db.test.ts`

**Interfaces:**
- Produces:
  - `getDb(): Database` — singleton; opens `${DATA_DIR ?? "/data"}/gnomon.db`, honors `GNOMON_DB_PATH` override (tests use `:memory:` semantics via a temp file), runs schema idempotently.
  - `upsertPerson(db, email: string, name: string): { id: number; email: string; name: string }`
  - `upsertUpload(db, args: { personId: number; monthKey: string; windowMonths: number; summaryJson: string }): void`
  - `uploadedMonths(db, personId: number): { monthKey: string; uploadedAt: number }[]` (uploadedAt = ms epoch)
  - `listPeople(db): { id: number; email: string; name: string }[]`
  - `uploadsForPerson(db, personId: number): { monthKey: string; windowMonths: number; summary: any }[]` (sorted ascending by monthKey)
  - `latestUploads(db): { personId: number; email: string; name: string; monthKey: string; summary: any }[]` — each person's most recent upload.

- [ ] **Step 1: Write failing tests**

`dashboard/tests/db.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import {
  initSchema, upsertPerson, upsertUpload, uploadedMonths,
  listPeople, uploadsForPerson, latestUploads,
} from "@/lib/db";

function freshDb() {
  const db = new Database(":memory:");
  initSchema(db);
  return db;
}

describe("db", () => {
  let db: ReturnType<typeof freshDb>;
  beforeEach(() => { db = freshDb(); });

  it("upsertPerson is idempotent on email and updates name", () => {
    const a = upsertPerson(db, "ada@example.com", "Ada");
    const b = upsertPerson(db, "ada@example.com", "Ada Lovelace");
    expect(b.id).toBe(a.id);
    expect(listPeople(db)).toHaveLength(1);
    expect(listPeople(db)[0].name).toBe("Ada Lovelace");
  });

  it("upsertUpload replaces same (person, monthKey)", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":1}' });
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":2}' });
    const ups = uploadsForPerson(db, p.id);
    expect(ups).toHaveLength(1);
    expect(ups[0].summary.v).toBe(2);
  });

  it("upsertUpload invalidates the stale coach cache for that person-month", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":1}' });
    db.prepare(`INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)`)
      .run(`coach:${p.id}:2026-06`, "old coaching text");
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":2}' });
    const cached = db.prepare(`SELECT value FROM settings WHERE key = ?`).get(`coach:${p.id}:2026-06`);
    expect(cached).toBeUndefined();
  });

  it("uploadedMonths returns monthKey + ms epoch uploadedAt", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    upsertUpload(db, { personId: p.id, monthKey: "2026-05", windowMonths: 6, summaryJson: "{}" });
    const months = uploadedMonths(db, p.id);
    expect(months[0].monthKey).toBe("2026-05");
    expect(months[0].uploadedAt).toBeGreaterThan(1_700_000_000_000);
  });

  it("latestUploads returns one row per person, most recent month", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    upsertUpload(db, { personId: p.id, monthKey: "2026-05", windowMonths: 6, summaryJson: '{"m":"05"}' });
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"m":"06"}' });
    const rows = latestUploads(db);
    expect(rows).toHaveLength(1);
    expect(rows[0].monthKey).toBe("2026-06");
    expect(rows[0].summary.m).toBe("06");
  });
});
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `npm test -- tests/db.test.ts`
Expected: FAIL — module `@/lib/db` not found.

- [ ] **Step 3: Implement db.ts**

```ts
import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";

export type Db = Database.Database;

export function initSchema(db: Db): void {
  db.pragma("journal_mode = WAL");
  db.exec(`
    CREATE TABLE IF NOT EXISTS people (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      created_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
    );
    CREATE TABLE IF NOT EXISTS uploads (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      person_id INTEGER NOT NULL REFERENCES people(id),
      month_key TEXT NOT NULL,
      window_months INTEGER NOT NULL,
      summary_json TEXT NOT NULL,
      uploaded_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000),
      UNIQUE (person_id, month_key)
    );
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);
}

let _db: Db | null = null;

export function getDb(): Db {
  if (_db) return _db;
  const dir = process.env.DATA_DIR ?? "/data";
  const file = process.env.GNOMON_DB_PATH ?? path.join(dir, "gnomon.db");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  _db = new Database(file);
  initSchema(_db);
  return _db;
}

export function upsertPerson(db: Db, email: string, name: string) {
  db.prepare(
    `INSERT INTO people (email, name) VALUES (?, ?)
     ON CONFLICT(email) DO UPDATE SET name = excluded.name`
  ).run(email.toLowerCase().trim(), name.trim());
  return db.prepare(`SELECT id, email, name FROM people WHERE email = ?`)
    .get(email.toLowerCase().trim()) as { id: number; email: string; name: string };
}

export function upsertUpload(
  db: Db,
  args: { personId: number; monthKey: string; windowMonths: number; summaryJson: string }
): void {
  db.prepare(
    `INSERT INTO uploads (person_id, month_key, window_months, summary_json)
     VALUES (@personId, @monthKey, @windowMonths, @summaryJson)
     ON CONFLICT(person_id, month_key) DO UPDATE SET
       window_months = excluded.window_months,
       summary_json = excluded.summary_json,
       uploaded_at = unixepoch() * 1000`
  ).run(args);
  // Re-uploading a month supersedes its metrics, so any cached AI-coach text
  // for that (person, month) is stale — drop it so it regenerates on next view.
  db.prepare(`DELETE FROM settings WHERE key = ?`)
    .run(`coach:${args.personId}:${args.monthKey}`);
}

export function uploadedMonths(db: Db, personId: number) {
  return db.prepare(
    `SELECT month_key AS monthKey, uploaded_at AS uploadedAt
     FROM uploads WHERE person_id = ? ORDER BY month_key`
  ).all(personId) as { monthKey: string; uploadedAt: number }[];
}

export function listPeople(db: Db) {
  return db.prepare(`SELECT id, email, name FROM people ORDER BY name`)
    .all() as { id: number; email: string; name: string }[];
}

export function uploadsForPerson(db: Db, personId: number) {
  const rows = db.prepare(
    `SELECT month_key AS monthKey, window_months AS windowMonths, summary_json AS summaryJson
     FROM uploads WHERE person_id = ? ORDER BY month_key`
  ).all(personId) as { monthKey: string; windowMonths: number; summaryJson: string }[];
  return rows.map((r) => ({ monthKey: r.monthKey, windowMonths: r.windowMonths, summary: JSON.parse(r.summaryJson) }));
}

export function latestUploads(db: Db) {
  const rows = db.prepare(
    `SELECT u.person_id AS personId, p.email, p.name, u.month_key AS monthKey, u.summary_json AS summaryJson
     FROM uploads u
     JOIN people p ON p.id = u.person_id
     WHERE u.month_key = (SELECT MAX(month_key) FROM uploads WHERE person_id = u.person_id)`
  ).all() as { personId: number; email: string; name: string; monthKey: string; summaryJson: string }[];
  return rows.map((r) => ({ personId: r.personId, email: r.email, name: r.name, monthKey: r.monthKey, summary: JSON.parse(r.summaryJson) }));
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `npm test -- tests/db.test.ts`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/db.ts dashboard/tests/db.test.ts
git commit -m "feat(dashboard): SQLite layer with people/uploads upserts"
```

---

### Task 3: Auth lib (team token + JWT)

**Files:**
- Create: `dashboard/src/lib/auth.ts`
- Test: `dashboard/tests/auth.test.ts`

**Interfaces:**
- Produces:
  - `checkTeamToken(input: string): boolean` — constant-time compare against `process.env.TEAM_TOKEN`; false when env unset.
  - `issueTokens(person: { id: number; email: string; name: string }, count: number): Promise<string[]>` — `count` clamped to `[1, 12]` (mirdash `_MAX_BACKFILL`), HS256 JWTs, `exp` 2h, claims `{ sub: String(id), email, name }`.
  - `verifyToken(token: string): Promise<{ personId: number; email: string; name: string } | null>` — null on any failure; verification is **pinned to HS256** (`algorithms: ["HS256"]`) and `sub` must be a positive integer.
  - `isLoopbackRedirect(uri: string): boolean` — true only for `http://127.0.0.1:PORT/...` or `http://localhost:PORT/...`, **explicit port required**.
- JWT secret: `process.env.JWT_SECRET`, else generated once and persisted at `${DATA_DIR ?? "/data"}/jwt-secret` (tests set `JWT_SECRET`).

- [ ] **Step 1: Write failing tests**

`dashboard/tests/auth.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import { SignJWT } from "jose";
import { checkTeamToken, issueTokens, verifyToken, isLoopbackRedirect } from "@/lib/auth";

describe("auth", () => {
  beforeEach(() => {
    process.env.TEAM_TOKEN = "sekret-team";
    process.env.JWT_SECRET = "test-jwt-secret-at-least-32-bytes!!";
  });

  it("checkTeamToken matches exact token only", () => {
    expect(checkTeamToken("sekret-team")).toBe(true);
    expect(checkTeamToken("wrong")).toBe(false);
    expect(checkTeamToken("")).toBe(false);
  });

  it("checkTeamToken false when TEAM_TOKEN unset", () => {
    delete process.env.TEAM_TOKEN;
    expect(checkTeamToken("anything")).toBe(false);
  });

  it("issueTokens returns count tokens that verify back to the person", async () => {
    const tokens = await issueTokens({ id: 7, email: "ada@example.com", name: "Ada" }, 3);
    expect(tokens).toHaveLength(3);
    const claims = await verifyToken(tokens[0]);
    expect(claims).toEqual({ personId: 7, email: "ada@example.com", name: "Ada" });
  });

  it("issueTokens clamps count to [1,12]", async () => {
    expect(await issueTokens({ id: 1, email: "a@b.c", name: "A" }, 0)).toHaveLength(1);
    expect(await issueTokens({ id: 1, email: "a@b.c", name: "A" }, 99)).toHaveLength(12);
  });

  it("verifyToken rejects garbage and wrong-secret tokens", async () => {
    expect(await verifyToken("not-a-jwt")).toBeNull();
    // Correctly-formed HS256 token signed with a DIFFERENT secret.
    const wrong = await new SignJWT({ email: "a@b.c", name: "A" })
      .setProtectedHeader({ alg: "HS256" })
      .setSubject("1")
      .setExpirationTime("2h")
      .sign(new TextEncoder().encode("some-other-secret-at-least-32-byte!"));
    expect(await verifyToken(wrong)).toBeNull();
  });

  it("verifyToken rejects non-HS256 algorithms", async () => {
    const secret = new TextEncoder().encode(process.env.JWT_SECRET!);
    for (const alg of ["HS384", "HS512"]) {
      const t = await new SignJWT({ email: "a@b.c", name: "A" })
        .setProtectedHeader({ alg })
        .setSubject("1")
        .setExpirationTime("2h")
        .sign(secret);
      expect(await verifyToken(t)).toBeNull();
    }
  });

  it("verifyToken rejects non-positive-integer subjects", async () => {
    const secret = new TextEncoder().encode(process.env.JWT_SECRET!);
    for (const sub of ["0", "-3", "abc", "1.5"]) {
      const t = await new SignJWT({ email: "a@b.c", name: "A" })
        .setProtectedHeader({ alg: "HS256" })
        .setSubject(sub)
        .setExpirationTime("2h")
        .sign(secret);
      expect(await verifyToken(t)).toBeNull();
    }
  });

  it("isLoopbackRedirect only allows loopback http with explicit port", () => {
    expect(isLoopbackRedirect("http://127.0.0.1:8799/callback")).toBe(true);
    expect(isLoopbackRedirect("http://localhost:8799/callback")).toBe(true);
    expect(isLoopbackRedirect("http://localhost/callback")).toBe(false); // no port
    expect(isLoopbackRedirect("https://evil.com/callback")).toBe(false);
    expect(isLoopbackRedirect("http://127.0.0.1.evil.com/cb")).toBe(false);
    expect(isLoopbackRedirect("not a url")).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests, verify fail**

Run: `npm test -- tests/auth.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement auth.ts**

```ts
import { SignJWT, jwtVerify } from "jose";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const MAX_TOKENS = 12; // mirror _MAX_BACKFILL in gnomon/upload/mirdash.py

export function checkTeamToken(input: string): boolean {
  const expected = process.env.TEAM_TOKEN ?? "";
  if (!expected || !input) return false;
  // Hash both to fixed-length digests so the compare is constant-time
  // regardless of input length (no early length-based return leak).
  const a = crypto.createHash("sha256").update(input).digest();
  const b = crypto.createHash("sha256").update(expected).digest();
  return crypto.timingSafeEqual(a, b);
}

function jwtSecret(): Uint8Array {
  const env = process.env.JWT_SECRET;
  if (env) return new TextEncoder().encode(env);
  const dir = process.env.DATA_DIR ?? "/data";
  const file = path.join(dir, "jwt-secret");
  try {
    return new TextEncoder().encode(fs.readFileSync(file, "utf-8").trim());
  } catch {
    const secret = crypto.randomBytes(32).toString("hex");
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(file, secret, { mode: 0o600 });
    return new TextEncoder().encode(secret);
  }
}

export async function issueTokens(
  person: { id: number; email: string; name: string },
  count: number
): Promise<string[]> {
  const n = Math.max(1, Math.min(MAX_TOKENS, Math.floor(count) || 1));
  const secret = jwtSecret();
  const tokens: string[] = [];
  for (let i = 0; i < n; i++) {
    tokens.push(
      await new SignJWT({ email: person.email, name: person.name })
        .setProtectedHeader({ alg: "HS256" })
        .setSubject(String(person.id))
        .setIssuedAt()
        .setExpirationTime("2h")
        .sign(secret)
    );
  }
  return tokens;
}

export async function verifyToken(
  token: string
): Promise<{ personId: number; email: string; name: string } | null> {
  try {
    // Pin the accepted algorithm to HS256 — without this, jose accepts any
    // alg the token header declares, defeating the HS256 contract.
    const { payload } = await jwtVerify(token, jwtSecret(), { algorithms: ["HS256"] });
    if (typeof payload.email !== "string") return null;
    const personId = Number(payload.sub);
    if (!Number.isInteger(personId) || personId <= 0) return null;
    return {
      personId,
      email: payload.email,
      name: typeof payload.name === "string" ? payload.name : "",
    };
  } catch {
    return null;
  }
}

export function isLoopbackRedirect(uri: string): boolean {
  try {
    const u = new URL(uri);
    // Require an explicit port so a bare `http://localhost/callback` (which the
    // CLI never sends) is rejected — narrows the redirect surface.
    return (
      u.protocol === "http:" &&
      (u.hostname === "127.0.0.1" || u.hostname === "localhost") &&
      u.port !== ""
    );
  } catch {
    return false;
  }
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `npm test -- tests/auth.test.ts`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/auth.ts dashboard/tests/auth.test.ts
git commit -m "feat(dashboard): team-token check, JWT issue/verify, loopback redirect guard"
```

---

### Task 4: Ingest validation + monthKey derivation

**Files:**
- Create: `dashboard/src/lib/ingest.ts`
- Test: `dashboard/tests/ingest.test.ts`
- Create: `dashboard/tests/fixtures/summary.ts` (builder for summary fixtures)

**Interfaces:**
- Consumes: `upsertUpload`, `Db` from `@/lib/db`.
- Produces:
  - `validateSummary(body: unknown): { ok: true; monthKey: string; windowMonths: number } | { ok: false; error: string }` — requires `context.date_range` as `[string, string]` with **both** values strict `YYYY-MM-DD` calendar dates and `start <= end`, plus `context.total_sessions > 0`; monthKey = `date_range[1].slice(0, 7)` (derived only after strict validation); windowMonths = `context.window_months ?? 6`.
  - `ingestSummary(db: Db, personId: number, body: any, rawJson?: string): { reportUrl: string }` — validates the parsed `body`, stores `rawJson` **verbatim** when provided (falls back to `JSON.stringify(body)`), returns `{ reportUrl: "/p/<personId>/<monthKey>" }`; throws `IngestError` (with `.message`) on invalid body.
  - Fixture: `makeSummary(overrides?)` returning a minimal-but-complete summary object (context, profile.aq with 4 pillars, profile.scores, progression_monthly, token_usage, metric blocks) that both ingest and metrics tests reuse.

- [ ] **Step 1: Write the fixture builder**

`dashboard/tests/fixtures/summary.ts`:

```ts
export function makeSummary(overrides: Record<string, any> = {}) {
  const base = {
    context: {
      date_range: ["2026-01-01", "2026-06-30"],
      total_sessions: 171,
      total_prompts: 1167,
      sources: ["claude"],
      client_version: "0.3.0",
      window_months: 6,
    },
    planning_ratio_explore_to_doing: 0.82,
    errors: { error_recovery_ratio: 0.98, error_rate_per_100_tools: 2.6 },
    iteration_depth: { mean: 2.3, median: 2, p90: 5, max: 89, files_over_15x: 3 },
    churn: { git_churn_total: 8159072, tool_churn_edit_write: 104990, active_hours: 120, actions_per_prompt: 14 },
    orchestration: { fanout_median: 3.5, delegate_actions: 42 },
    compounding_writes: 91,
    ecosystem: { skills_distinct: 12, mcp_servers_distinct: 4 },
    progression_monthly: [
      { month: "2026-05", prompts: 500, sessions: 80, tool_calls: 7000, active_days: 12,
        models: [["claude-opus-4-8", 4000]], top_model: "claude-opus-4-8",
        tokens_input: 1e6, tokens_output: 2e6, tokens_cache_read: 5e8, tokens_cache_creation: 1e7,
        tokens_total: 513_000_000 },
      { month: "2026-06", prompts: 1077, sessions: 157, tool_calls: 15472, active_days: 14,
        models: [["claude-opus-4-8", 24849], ["claude-fable-5", 1794]], top_model: "claude-opus-4-8",
        tokens_input: 9_643_595, tokens_output: 21_017_872, tokens_cache_read: 5_575_354_211,
        tokens_cache_creation: 117_107_983, tokens_total: 5_723_123_661 },
    ],
    // Exact per-model monthly tokens (summary.py `monthly_noticed_stats`). Newer
    // summaries carry this; metrics prefer it over the invocation-share estimate.
    noticed_stats_monthly: [
      { month: "2026-05", range_start: "2026-05-01", range_end: "2026-05-31",
        token_usage: { total_input: 1e6, total_output: 2e6, total_cache_read: 5e8, total_cache_creation: 1e7,
          by_model: [
            { model_id: "claude-opus-4-8", model: "Opus 4.8", input: 1e6, output: 2e6, cache_read: 5e8, cache_creation: 1e7 },
          ] } },
      { month: "2026-06", range_start: "2026-06-01", range_end: "2026-06-30",
        token_usage: { total_input: 9_643_595, total_output: 21_017_872, total_cache_read: 5_575_354_211, total_cache_creation: 117_107_983,
          by_model: [
            { model_id: "claude-opus-4-8", model: "Opus 4.8", input: 9_000_000, output: 20_000_000, cache_read: 5.5e9, cache_creation: 1.1e8 },
            { model_id: "claude-fable-5", model: "Fable 5", input: 643_595, output: 1_017_872, cache_read: 75_354_211, cache_creation: 7_107_983 },
          ] } },
    ],
    profile: {
      aq: {
        aq_0_100: 93, tier: "Elite",
        pillars: [
          { name: "Breadth", weight: 30, score: 27.0, axes: [{ name: "Discipline", weight: 10, score: 1.2, signals: {} }] },
          { name: "Craft", weight: 35, score: 33.0, axes: [] },
          { name: "Efficiency", weight: 20, score: 18.0, axes: [] },
          { name: "Savvy", weight: 15, score: 15.0, axes: [] },
        ],
      },
      archetype: { title: "Blueprint, then bulldozer", quote: "Plan wide, then grind narrow" },
      scores: {
        execution: { value: 8.5, gloss: "How much you ship, how fast", subs: [] },
        planning: { value: 10.0, gloss: "Think before you build", subs: [] },
        engineering: { value: 8.6, gloss: "How clean your work is", subs: [] },
      },
      model_usage: [
        { model_id: "claude-opus-4-8", model: "Opus 4.8", count: 24849, pct: 0.8,
          tokens_input: 9_000_000, tokens_output: 20_000_000, tokens_cache_read: 5e9, tokens_cache_creation: 1e8 },
        { model_id: "claude-fable-5", model: "Fable 5", count: 1794, pct: 0.2,
          tokens_input: 600_000, tokens_output: 1_000_000, tokens_cache_read: 5e8, tokens_cache_creation: 1e7 },
      ],
    },
    token_usage: {
      total_input: 9_643_595, total_output: 21_017_872,
      total_cache_read: 5_575_354_211, total_cache_creation: 117_107_983,
      by_model: [
        { model_id: "claude-opus-4-8", model: "Opus 4.8", input: 9_000_000, output: 20_000_000,
          cache_read: 5e9, cache_creation: 1e8 },
      ],
    },
  };
  return deepMerge(base, overrides);
}

function deepMerge(base: any, over: any): any {
  if (Array.isArray(over) || typeof over !== "object" || over === null) return over;
  const out = { ...base };
  for (const k of Object.keys(over)) {
    out[k] = k in base ? deepMerge(base[k], over[k]) : over[k];
  }
  return out;
}
```

- [ ] **Step 2: Write failing tests**

`dashboard/tests/ingest.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import Database from "better-sqlite3";
import { initSchema, upsertPerson, uploadsForPerson } from "@/lib/db";
import { validateSummary, ingestSummary, IngestError } from "@/lib/ingest";
import { makeSummary } from "./fixtures/summary";

describe("validateSummary", () => {
  it("accepts a valid summary and derives monthKey from date_range end", () => {
    const r = validateSummary(makeSummary());
    expect(r).toEqual({ ok: true, monthKey: "2026-06", windowMonths: 6 });
  });

  it("rejects missing date_range, zero sessions, non-object bodies", () => {
    expect(validateSummary(null).ok).toBe(false);
    expect(validateSummary({}).ok).toBe(false);
    expect(validateSummary(makeSummary({ context: { total_sessions: 0 } })).ok).toBe(false);
    expect(validateSummary(makeSummary({ context: { date_range: ["bad", "worse"] } })).ok).toBe(false);
  });

  it("rejects non-strict and impossible calendar dates and reversed ranges", () => {
    // Date.parse would accept these; strict validation must not.
    expect(validateSummary(makeSummary({ context: { date_range: ["2026-01-01", "June 30 2026"] } })).ok).toBe(false);
    expect(validateSummary(makeSummary({ context: { date_range: ["2026-01-01", "2026-06-31"] } })).ok).toBe(false); // no June 31
    expect(validateSummary(makeSummary({ context: { date_range: ["2026-6-3", "2026-06-30"] } })).ok).toBe(false); // not zero-padded
    expect(validateSummary(makeSummary({ context: { date_range: ["2026-06-30", "2026-01-01"] } })).ok).toBe(false); // start > end
  });

  it("defaults window_months to 6 when absent", () => {
    const s = makeSummary();
    delete s.context.window_months;
    const r = validateSummary(s);
    expect(r).toEqual({ ok: true, monthKey: "2026-06", windowMonths: 6 });
  });
});

describe("ingestSummary", () => {
  it("stores upload and returns relative reportUrl", () => {
    const db = new Database(":memory:");
    initSchema(db);
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const { reportUrl } = ingestSummary(db, p.id, makeSummary());
    expect(reportUrl).toBe(`/p/${p.id}/2026-06`);
    expect(uploadsForPerson(db, p.id)).toHaveLength(1);
  });

  it("throws IngestError on invalid body", () => {
    const db = new Database(":memory:");
    initSchema(db);
    expect(() => ingestSummary(db, 1, {})).toThrow(IngestError);
  });
});
```

- [ ] **Step 3: Run tests, verify fail**

Run: `npm test -- tests/ingest.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement ingest.ts**

```ts
import type { Db } from "@/lib/db";
import { upsertUpload } from "@/lib/db";

export class IngestError extends Error {}

type Valid = { ok: true; monthKey: string; windowMonths: number };
type Invalid = { ok: false; error: string };

// Strict `YYYY-MM-DD` calendar-date check — `Date.parse` alone accepts
// "June 30 2026" and rolls over impossible dates like 2026-06-31.
function parseIsoDate(s: unknown): Date | null {
  if (typeof s !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const [, y, mo, d] = m.map(Number);
  const dt = new Date(Date.UTC(y, mo - 1, d));
  // Reject rollovers: the round-trip must equal the input components.
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) {
    return null;
  }
  return dt;
}

export function validateSummary(body: unknown): Valid | Invalid {
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return { ok: false, error: "body must be a JSON object (summary.json)" };
  }
  const ctx = (body as any).context;
  if (typeof ctx !== "object" || ctx === null) {
    return { ok: false, error: "missing context block" };
  }
  const dr = ctx.date_range;
  if (!Array.isArray(dr) || dr.length < 2) {
    return { ok: false, error: "context.date_range must be [start, end]" };
  }
  const start = parseIsoDate(dr[0]);
  const end = parseIsoDate(dr[1]);
  if (!start || !end) {
    return { ok: false, error: "context.date_range must be [start, end] as YYYY-MM-DD dates" };
  }
  if (start.getTime() > end.getTime()) {
    return { ok: false, error: "context.date_range start must be <= end" };
  }
  if (!(Number(ctx.total_sessions) > 0)) {
    return { ok: false, error: "context.total_sessions must be > 0" };
  }
  const windowMonths = Number(ctx.window_months) >= 1 ? Number(ctx.window_months) : 6;
  // monthKey derived only after strict validation, from the validated end date.
  return { ok: true, monthKey: (dr[1] as string).slice(0, 7), windowMonths };
}

// `rawJson` is the original request text — stored verbatim so the bytes are
// preserved. `body` is the parsed copy used only for validation.
export function ingestSummary(
  db: Db,
  personId: number,
  body: any,
  rawJson?: string
): { reportUrl: string } {
  const v = validateSummary(body);
  if (!v.ok) throw new IngestError(v.error);
  upsertUpload(db, {
    personId,
    monthKey: v.monthKey,
    windowMonths: v.windowMonths,
    summaryJson: rawJson ?? JSON.stringify(body),
  });
  return { reportUrl: `/p/${personId}/${v.monthKey}` };
}
```

- [ ] **Step 5: Run tests, verify pass**

Run: `npm test -- tests/ingest.test.ts`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/ingest.ts dashboard/tests/ingest.test.ts dashboard/tests/fixtures/summary.ts
git commit -m "feat(dashboard): summary validation, monthKey derivation, ingest upsert"
```

---

### Task 5: `POST /api/gnomon/ingest` route

**Files:**
- Create: `dashboard/src/app/api/gnomon/ingest/route.ts`
- Test: `dashboard/tests/ingest-route.test.ts`

**Interfaces:**
- Consumes: `verifyToken` (Task 3), `ingestSummary`/`IngestError` (Task 4), `getDb` (Task 2).
- Produces: route handler `POST(req: Request): Promise<Response>` —
  - `401` `{"error": "..."}` when Authorization header missing/invalid;
  - `413` `{"error": "payload too large"}` when the body exceeds `MAX_INGEST_BYTES` (default 5 MiB);
  - `400` `{"error": "..."}` on invalid JSON or failed validation;
  - `200` `{"reportUrl": "/p/<id>/<monthKey>"}` on success.
  - Reads the raw request text **once**, stores it verbatim, and validates a parsed copy.
  - Matches CLI expectations in `gnomon/upload/mirdash.py:_upload_summary` (reads `data["reportUrl"]`; on HTTPError prints response body).

- [ ] **Step 1: Write failing tests** (invoke the handler directly with `Request` objects; inject a test DB via `GNOMON_DB_PATH` pointing at a temp file)

`dashboard/tests/ingest-route.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { POST } from "@/app/api/gnomon/ingest/route";
import { issueTokens } from "@/lib/auth";
import { getDb, upsertPerson } from "@/lib/db";
import { makeSummary } from "./fixtures/summary";

function req(body: any, token?: string) {
  return new Request("http://test/api/gnomon/ingest", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

describe("POST /api/gnomon/ingest", () => {
  beforeEach(() => {
    process.env.JWT_SECRET = "test-jwt-secret-at-least-32-bytes!!";
    process.env.GNOMON_DB_PATH = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "gnomon-")), "t.db");
  });

  it("401 without token", async () => {
    const res = await POST(req(makeSummary()));
    expect(res.status).toBe(401);
  });

  it("400 on invalid summary", async () => {
    const db = getDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const [token] = await issueTokens(p, 1);
    const res = await POST(req({ nope: true }, token));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toMatch(/context/);
  });

  it("200 with reportUrl on success", async () => {
    const db = getDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const [token] = await issueTokens(p, 1);
    const res = await POST(req(makeSummary(), token));
    expect(res.status).toBe(200);
    expect((await res.json()).reportUrl).toBe(`/p/${p.id}/2026-06`);
  });

  it("413 when body exceeds the size cap", async () => {
    process.env.MAX_INGEST_BYTES = "1024";
    const db = getDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const [token] = await issueTokens(p, 1);
    const big = makeSummary({ context: { client_version: "x".repeat(4096) } });
    const res = await POST(req(big, token));
    expect(res.status).toBe(413);
    delete process.env.MAX_INGEST_BYTES;
  });
});
```

Note: `getDb()` is a singleton — add `export function _resetDbForTests()` in `db.ts` setting `_db = null`, and call it in `beforeEach` after setting `GNOMON_DB_PATH`:

```ts
// add to db.ts
export function _resetDbForTests(): void { _db = null; }
```

```ts
// in beforeEach, after setting GNOMON_DB_PATH:
_resetDbForTests();
```

- [ ] **Step 2: Run tests, verify fail**

Run: `npm test -- tests/ingest-route.test.ts`
Expected: FAIL — route module not found.

- [ ] **Step 3: Implement route.ts**

```ts
import { NextResponse } from "next/server";
import { verifyToken } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { ingestSummary, IngestError } from "@/lib/ingest";

// Cap the accepted body so a valid token can't exhaust memory/disk with a
// giant upload. Real summaries are well under this. Read at call time so the
// env override is honored per-request (and testable).
function maxBodyBytes(): number {
  return Number(process.env.MAX_INGEST_BYTES) || 5 * 1024 * 1024;
}

export async function POST(req: Request): Promise<Response> {
  const auth = req.headers.get("authorization") ?? "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  const claims = token ? await verifyToken(token) : null;
  if (!claims) {
    return NextResponse.json({ error: "invalid or missing token" }, { status: 401 });
  }

  const cap = maxBodyBytes();
  // Reject early on a declared oversize length.
  const declared = Number(req.headers.get("content-length"));
  if (declared > cap) {
    return NextResponse.json({ error: "payload too large" }, { status: 413 });
  }

  // Read the raw text ONCE so we can both validate a parsed copy and store the
  // original bytes verbatim. Enforce the byte cap on the actual body too.
  const raw = await req.text();
  if (Buffer.byteLength(raw, "utf8") > cap) {
    return NextResponse.json({ error: "payload too large" }, { status: 413 });
  }

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "body must be valid JSON" }, { status: 400 });
  }

  try {
    const result = ingestSummary(getDb(), claims.personId, body, raw);
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof IngestError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    throw err;
  }
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `npm test -- tests/ingest-route.test.ts`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/app/api/gnomon/ingest/route.ts dashboard/tests/ingest-route.test.ts dashboard/src/lib/db.ts
git commit -m "feat(dashboard): /api/gnomon/ingest route matching CLI contract"
```

---

### Task 6: `/cli-auth` login page + callback redirect

**Files:**
- Create: `dashboard/src/app/cli-auth/page.tsx` (form UI, server component)
- Create: `dashboard/src/app/api/cli-auth/route.ts` (form POST handler)
- Test: `dashboard/tests/cli-auth-route.test.ts`

**Interfaces:**
- Consumes: `checkTeamToken`, `issueTokens`, `isLoopbackRedirect` (Task 3); `getDb`, `upsertPerson`, `uploadedMonths` (Task 2).
- Produces: `POST /api/cli-auth` accepting `application/x-www-form-urlencoded` fields `team_token`, `name`, `email`, `redirect_uri`, `count`. On success: `302` redirect to `redirect_uri` + `?tokens=<urlencoded JSON array>&uploaded=<urlencoded JSON array>` — the exact query shape `gnomon/upload/auth.py:_tokens_from_query` and `_uploaded_from_query` parse. On failure: `303` back to `/cli-auth?error=...&redirect_uri=...&count=...`. Failed team-token attempts are throttled per client IP (`429` after 5 fails/60s); failed-auth logging records only the outcome and IP, **never** the submitted token.
- CLI flow reference: CLI opens `{base}/cli-auth?redirect_uri=http://127.0.0.1:PORT/callback&count=N` in a browser and waits on the localhost callback.

- [ ] **Step 1: Write failing tests**

`dashboard/tests/cli-auth-route.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { POST, _resetRateLimitForTests } from "@/app/api/cli-auth/route";
import { verifyToken } from "@/lib/auth";
import { getDb, upsertPerson, upsertUpload, _resetDbForTests } from "@/lib/db";

function formReq(fields: Record<string, string>) {
  return new Request("http://test/api/cli-auth", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(fields).toString(),
  });
}

const CB = "http://127.0.0.1:8799/callback";

describe("POST /api/cli-auth", () => {
  beforeEach(() => {
    process.env.TEAM_TOKEN = "sekret-team";
    process.env.JWT_SECRET = "test-jwt-secret-at-least-32-bytes!!";
    process.env.GNOMON_DB_PATH = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "gnomon-")), "t.db");
    _resetDbForTests();
    _resetRateLimitForTests();
  });

  it("redirects to callback with N valid tokens and uploaded months", async () => {
    const db = getDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    upsertUpload(db, { personId: p.id, monthKey: "2026-05", windowMonths: 6, summaryJson: "{}" });

    const res = await POST(formReq({
      team_token: "sekret-team", name: "Ada", email: "ada@example.com",
      redirect_uri: CB, count: "3",
    }));
    expect(res.status).toBe(302);
    const loc = new URL(res.headers.get("location")!);
    expect(loc.origin + loc.pathname).toBe(CB);
    const tokens = JSON.parse(loc.searchParams.get("tokens")!);
    expect(tokens).toHaveLength(3);
    expect((await verifyToken(tokens[0]))?.email).toBe("ada@example.com");
    const uploaded = JSON.parse(loc.searchParams.get("uploaded")!);
    expect(uploaded[0].monthKey).toBe("2026-05");
    expect(typeof uploaded[0].uploadedAt).toBe("number");
  });

  it("rejects wrong team token with redirect back to form", async () => {
    const res = await POST(formReq({
      team_token: "wrong", name: "Ada", email: "ada@example.com",
      redirect_uri: CB, count: "1",
    }));
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toContain("/cli-auth?");
    expect(res.headers.get("location")).toContain("error=");
  });

  it("rejects non-loopback redirect_uri with 400", async () => {
    const res = await POST(formReq({
      team_token: "sekret-team", name: "Ada", email: "ada@example.com",
      redirect_uri: "https://evil.com/cb", count: "1",
    }));
    expect(res.status).toBe(400);
  });

  it("rejects missing name/email with redirect back to form", async () => {
    const res = await POST(formReq({
      team_token: "sekret-team", name: "", email: "",
      redirect_uri: CB, count: "1",
    }));
    expect(res.status).toBe(303);
  });

  it("throttles repeated wrong team tokens with 429", async () => {
    const bad = () => POST(formReq({
      team_token: "wrong", name: "Ada", email: "ada@example.com",
      redirect_uri: CB, count: "1",
    }));
    // Distinct source so the module-scope counter isn't polluted by prior tests
    // — the loopback redirect keeps the same IP header ("unknown") across calls.
    let last!: Response;
    for (let i = 0; i < 6; i++) last = await bad();
    expect(last.status).toBe(429);
  });
});
```

> Note: `_resetRateLimitForTests` clears the module-scope failed-attempt map between tests (all requests share the `"unknown"` IP header under a loopback callback).

- [ ] **Step 2: Run tests, verify fail**

Run: `npm test -- tests/cli-auth-route.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement api/cli-auth/route.ts**

```ts
import { NextResponse } from "next/server";
import { checkTeamToken, issueTokens, isLoopbackRedirect } from "@/lib/auth";
import { getDb, upsertPerson, uploadedMonths } from "@/lib/db";

// In-memory failed-attempt throttle for the shared TEAM_TOKEN endpoint. Single
// container, so a module-scope map is sufficient; keyed by client IP.
const MAX_FAILS = 5;
const WINDOW_MS = 60_000;
const fails = new Map<string, { n: number; first: number }>();

function clientIp(req: Request): string {
  const xff = req.headers.get("x-forwarded-for") ?? "";
  return xff.split(",")[0].trim() || req.headers.get("x-real-ip") || "unknown";
}

// `now` is injectable so tests don't depend on the wall clock.
function isRateLimited(ip: string, now: number): boolean {
  const rec = fails.get(ip);
  if (!rec) return false;
  if (now - rec.first > WINDOW_MS) { fails.delete(ip); return false; }
  return rec.n >= MAX_FAILS;
}
function recordFail(ip: string, now: number): void {
  const rec = fails.get(ip);
  if (!rec || now - rec.first > WINDOW_MS) fails.set(ip, { n: 1, first: now });
  else rec.n += 1;
}

export function _resetRateLimitForTests(): void { fails.clear(); }

export async function POST(req: Request): Promise<Response> {
  const form = new URLSearchParams(await req.text());
  const teamToken = form.get("team_token") ?? "";
  const name = (form.get("name") ?? "").trim();
  const email = (form.get("email") ?? "").trim().toLowerCase();
  const redirectUri = form.get("redirect_uri") ?? "";
  const count = Number(form.get("count") ?? "1");
  const ip = clientIp(req);
  const now = Date.now();

  if (!isLoopbackRedirect(redirectUri)) {
    return NextResponse.json(
      { error: "redirect_uri must be a http://127.0.0.1 or http://localhost URL" },
      { status: 400 }
    );
  }

  if (isRateLimited(ip, now)) {
    // Never log the submitted token — only the outcome and source.
    console.warn(`[cli-auth] rate-limited failed auth from ${ip}`);
    return NextResponse.json({ error: "too many attempts, try again later" }, { status: 429 });
  }

  const backToForm = (error: string) => {
    const back = new URL("/cli-auth", req.url);
    back.searchParams.set("error", error);
    back.searchParams.set("redirect_uri", redirectUri);
    back.searchParams.set("count", String(count));
    return NextResponse.redirect(back, 303);
  };

  if (!checkTeamToken(teamToken)) {
    recordFail(ip, now);
    console.warn(`[cli-auth] invalid team token from ${ip}`);
    return backToForm("Invalid team token");
  }
  if (!name || !/.+@.+\..+/.test(email)) return backToForm("Name and a valid email are required");
  fails.delete(ip); // success clears the counter

  const db = getDb();
  const person = upsertPerson(db, email, name);
  const tokens = await issueTokens(person, count);
  const uploaded = uploadedMonths(db, person.id);

  const dest = new URL(redirectUri);
  dest.searchParams.set("tokens", JSON.stringify(tokens));
  dest.searchParams.set("uploaded", JSON.stringify(uploaded));
  return NextResponse.redirect(dest, 302);
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `npm test -- tests/cli-auth-route.test.ts`
Expected: 5 PASS.

- [ ] **Step 5: Implement the form page** (no test — static server component; covered by smoke e2e in Task 11)

`dashboard/src/app/cli-auth/page.tsx`:

```tsx
export default async function CliAuthPage({
  searchParams,
}: {
  searchParams: Promise<{ redirect_uri?: string; count?: string; error?: string }>;
}) {
  const { redirect_uri = "", count = "1", error } = await searchParams;
  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border p-8"
           style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
        <div className="flex items-center gap-2 mb-6 text-sm font-semibold"
             style={{ color: "var(--text-secondary)" }}>
          <span className="inline-block w-2.5 h-2.5 rounded-full"
                style={{ background: "linear-gradient(135deg, var(--accent), var(--purple))" }} />
          gnomon dashboard · CLI sign-in
        </div>
        <h1 className="text-2xl font-bold mb-2">Authorize upload</h1>
        <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
          Enter your team token to let the CLI upload your build profile.
          Only summary statistics are uploaded — prompts and file contents stay on your machine.
        </p>
        {error && (
          <p className="text-sm mb-4 rounded-lg px-3 py-2"
             style={{ background: "rgba(238,26,100,.12)", color: "var(--accent)" }}>
            {error}
          </p>
        )}
        <form method="POST" action="/api/cli-auth" className="flex flex-col gap-3">
          <input type="hidden" name="redirect_uri" value={redirect_uri} />
          <input type="hidden" name="count" value={count} />
          <Field name="name" label="Name" type="text" placeholder="Ada Lovelace" />
          <Field name="email" label="Email" type="email" placeholder="ada@company.com" />
          <Field name="team_token" label="Team token" type="password" placeholder="••••••••" />
          <button type="submit"
                  className="mt-2 rounded-xl px-4 py-2.5 font-semibold text-white"
                  style={{ background: "var(--accent)" }}>
            Authorize
          </button>
        </form>
      </div>
    </main>
  );
}

function Field({ name, label, type, placeholder }: {
  name: string; label: string; type: string; placeholder: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm" style={{ color: "var(--text-secondary)" }}>
      {label}
      <input name={name} type={type} required placeholder={placeholder}
             className="rounded-lg border px-3 py-2 text-base outline-none"
             style={{ background: "var(--bg-elev)", borderColor: "var(--border)", color: "var(--text-primary)" }} />
    </label>
  );
}
```

- [ ] **Step 6: Verify build + full test suite**

Run: `npm run build && npm test`
Expected: build OK, all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/app/cli-auth dashboard/src/app/api/cli-auth dashboard/tests/cli-auth-route.test.ts
git commit -m "feat(dashboard): /cli-auth login flow issuing CLI tokens + uploaded state"
```

---

### Task 7: Metrics derivation lib

**Files:**
- Create: `dashboard/src/lib/pricing.ts`
- Create: `dashboard/src/lib/metrics.ts`
- Test: `dashboard/tests/metrics.test.ts`

**Interfaces:**
- Consumes: `latestUploads`, `uploadsForPerson`, `listPeople`, `Db` (Task 2); fixture `makeSummary` (Task 4).
- Produces (all pure functions over summaries — no DB access except the two `build*` entry points):
  - `pricing.ts`: `costUsd(tokens: { input: number; output: number; cacheRead: number; cacheCreation: number }, modelId: string): number` — per-MTok pricing map keyed by substring match (`opus`, `sonnet`, `haiku`, `fable`, `gpt`, `gemini`, default), e.g. opus `{in: 15, out: 75, cacheRead: 1.5, cacheWrite: 18.75}`; unknown models use default `{in: 3, out: 15, cacheRead: 0.3, cacheWrite: 3.75}`. Exact table lives in the file with a comment "approximate list prices — edit freely".
  - `monthEntry(summary: any, monthKey: string): any | null` — the `progression_monthly` entry with `month === monthKey`.
  - `monthTokensByModel(summary, monthKey): { modelId: string; tokens: number; cost: number }[]` — reads **exact** per-model tokens from `noticed_stats_monthly[monthKey].token_usage.by_model` (input/output/cache_read/cache_creation) and prices each via `costUsd`. Falls back to the invocation-share approximation over `progression_monthly` only when the exact block is absent (older summaries).
  - `personRow(personId, name, monthKey, summaries: {monthKey: string; summary: any}[]): PersonRow` where

    ```ts
    type PersonRow = {
      personId: number; name: string; monthKey: string;
      aq: number | null; tier: string | null;
      delta: number | null;              // aq - previous upload's aq
      trend: { monthKey: string; aq: number }[]; // all uploads, ascending
      topPillar: string | null;          // pillar with highest score/weight ratio
      tokens: number | null;             // monthEntry(monthKey).tokens_total
      cost: number | null;
    };
    ```
  - `buildTeamOverview(db: Db): TeamOverview` where

    ```ts
    type TeamOverview = {
      people: PersonRow[];                       // sorted by aq desc, nulls last
      avgAq: number | null;
      coverage: { withCurrentMonth: number; total: number }; // current = max monthKey seen
      tokensCurrentMonth: number;
      costCurrentMonth: number;
      usageOverTime: { monthKey: string; byModel: { model: string; tokens: number; cost: number }[] }[];
    };
    ```
  - `buildPersonProfile(db: Db, personId: number, monthKey: string): PersonProfile | null` where

    ```ts
    type PersonProfile = {
      personId: number; name: string; email: string; monthKey: string;
      prevMonthKey: string | null; nextMonthKey: string | null;
      aq: number; tier: string; delta: number | null;
      levelOverTime: { monthKey: string; aq: number }[];
      pillars: { name: string; weight: number; score: number;
                 axes: { name: string; weight: number; score: number }[] }[];
      scorecard: { key: "execution" | "planning" | "engineering"; value: number; gloss: string;
                   trend: { monthKey: string; value: number }[] }[];
      explore: { label: string; value: string }[];   // formatted metric strings
      usage: { sessions: number; prompts: number; actionsPerPrompt: number };
      modelMix: { model: string; pct: number }[];
      archetype: { title: string; quote: string } | null;
    };
    ```
  - `fmtTokens(n: number): string` (e.g. `5723M`), `fmtUsd(n: number): string` (e.g. `$39,360`).

- [ ] **Step 1: Write failing tests**

`dashboard/tests/metrics.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import Database from "better-sqlite3";
import { initSchema, upsertPerson, upsertUpload } from "@/lib/db";
import {
  monthEntry, monthTokensByModel, personRow,
  buildTeamOverview, buildPersonProfile, fmtTokens, fmtUsd,
} from "@/lib/metrics";
import { costUsd } from "@/lib/pricing";
import { makeSummary } from "./fixtures/summary";

function seed(db: any) {
  const p = upsertPerson(db, "ada@example.com", "Ada");
  const may = makeSummary({
    context: { date_range: ["2025-12-01", "2026-05-31"] },
    profile: { aq: { aq_0_100: 79, tier: "Advanced" } },
  });
  const jun = makeSummary(); // 2026-06, aq 93
  upsertUpload(db, { personId: p.id, monthKey: "2026-05", windowMonths: 6, summaryJson: JSON.stringify(may) });
  upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: JSON.stringify(jun) });
  return p;
}

describe("metrics", () => {
  let db: any;
  beforeEach(() => { db = new Database(":memory:"); initSchema(db); });

  it("monthEntry finds the progression entry for the anchor month", () => {
    expect(monthEntry(makeSummary(), "2026-06")?.sessions).toBe(157);
    expect(monthEntry(makeSummary(), "2019-01")).toBeNull();
  });

  it("monthTokensByModel reads exact per-model tokens from noticed_stats_monthly", () => {
    const split = monthTokensByModel(makeSummary(), "2026-06");
    const total = split.reduce((s, m) => s + m.tokens, 0);
    expect(total).toBe(5_723_123_661); // exact, not approximated
    expect(split[0].tokens).toBeGreaterThan(split[1].tokens); // opus > fable
    expect(split[0].cost).toBeGreaterThan(0);
  });

  it("monthTokensByModel falls back to invocation-share when noticed block absent", () => {
    const legacy = makeSummary();
    delete legacy.noticed_stats_monthly; // simulate an older summary
    const split = monthTokensByModel(legacy, "2026-06");
    const total = split.reduce((s, m) => s + m.tokens, 0);
    expect(total).toBeCloseTo(5_723_123_661, -2);
    expect(split[0].tokens).toBeGreaterThan(split[1].tokens);
  });

  it("personRow computes aq, delta vs previous month, trend, tokens", () => {
    const p = seed(db);
    const overview = buildTeamOverview(db);
    const row = overview.people[0];
    expect(row.aq).toBe(93);
    expect(row.delta).toBe(14);
    expect(row.trend.map((t) => t.aq)).toEqual([79, 93]);
    expect(row.tokens).toBe(5_723_123_661);
  });

  it("buildTeamOverview aggregates avg, coverage, usage over time", () => {
    seed(db);
    const o = buildTeamOverview(db);
    expect(o.avgAq).toBe(93);
    expect(o.coverage).toEqual({ withCurrentMonth: 1, total: 1 });
    expect(o.usageOverTime.map((u) => u.monthKey)).toEqual(["2026-05", "2026-06"]);
  });

  it("usageOverTime keeps months only an OLDER window covered (no truncation)", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    // Older upload's window uniquely covers 2026-01; newer upload's window does not.
    const jan = makeSummary({
      context: { date_range: ["2025-08-01", "2026-01-31"] },
      noticed_stats_monthly: [
        { month: "2026-01", token_usage: { by_model: [
          { model_id: "claude-opus-4-8", input: 1e6, output: 1e6, cache_read: 0, cache_creation: 0 } ] } },
      ],
      progression_monthly: [{ month: "2026-01", models: [["claude-opus-4-8", 100]], tokens_total: 2e6 }],
    });
    upsertUpload(db, { personId: p.id, monthKey: "2026-01", windowMonths: 6, summaryJson: JSON.stringify(jan) });
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: JSON.stringify(makeSummary()) });
    const o = buildTeamOverview(db);
    expect(o.usageOverTime.map((u) => u.monthKey)).toContain("2026-01");
  });

  it("usageOverTime counts each person-month once across overlapping windows", () => {
    // Two uploads whose windows both cover 2026-06 must not double-count it.
    const p = upsertPerson(db, "ada@example.com", "Ada");
    upsertUpload(db, { personId: p.id, monthKey: "2026-05", windowMonths: 6, summaryJson: JSON.stringify(makeSummary()) });
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: JSON.stringify(makeSummary()) });
    const o = buildTeamOverview(db);
    const jun = o.usageOverTime.find((u) => u.monthKey === "2026-06")!;
    const tokens = jun.byModel.reduce((s, m) => s + m.tokens, 0);
    expect(tokens).toBe(5_723_123_661); // single window's total, not doubled
  });

  it("buildPersonProfile returns profile view or null", () => {
    const p = seed(db);
    const prof = buildPersonProfile(db, p.id, "2026-06");
    expect(prof?.aq).toBe(93);
    expect(prof?.prevMonthKey).toBe("2026-05");
    expect(prof?.nextMonthKey).toBeNull();
    expect(prof?.pillars.map((x) => x.name)).toEqual(["Breadth", "Craft", "Efficiency", "Savvy"]);
    expect(prof?.scorecard.find((s) => s.key === "planning")?.value).toBe(10.0);
    expect(buildPersonProfile(db, 999, "2026-06")).toBeNull();
  });

  it("formatters", () => {
    expect(fmtTokens(5_723_123_661)).toBe("5723M");
    expect(fmtUsd(39360.4)).toBe("$39,360");
    expect(costUsd({ input: 1_000_000, output: 0, cacheRead: 0, cacheCreation: 0 }, "claude-opus-4-8")).toBeCloseTo(15);
  });
});
```

- [ ] **Step 2: Run tests, verify fail**

Run: `npm test -- tests/metrics.test.ts`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement pricing.ts**

```ts
// Approximate list prices per MTok, USD — edit freely for your provider mix.
// Matched by substring on the model id, first hit wins.
const PRICES: [needle: string, p: { in: number; out: number; cacheRead: number; cacheWrite: number }][] = [
  ["opus",   { in: 15,  out: 75,  cacheRead: 1.5,  cacheWrite: 18.75 }],
  ["fable",  { in: 15,  out: 75,  cacheRead: 1.5,  cacheWrite: 18.75 }],
  ["sonnet", { in: 3,   out: 15,  cacheRead: 0.3,  cacheWrite: 3.75 }],
  ["haiku",  { in: 0.8, out: 4,   cacheRead: 0.08, cacheWrite: 1 }],
  ["gpt",    { in: 2.5, out: 10,  cacheRead: 0.25, cacheWrite: 0 }],
  ["gemini", { in: 1.25, out: 10, cacheRead: 0.125, cacheWrite: 0 }],
];
const DEFAULT = { in: 3, out: 15, cacheRead: 0.3, cacheWrite: 3.75 };

export function priceFor(modelId: string) {
  const low = (modelId || "").toLowerCase();
  for (const [needle, p] of PRICES) if (low.includes(needle)) return p;
  return DEFAULT;
}

export function costUsd(
  tokens: { input: number; output: number; cacheRead: number; cacheCreation: number },
  modelId: string
): number {
  const p = priceFor(modelId);
  const M = 1_000_000;
  return (
    (tokens.input / M) * p.in +
    (tokens.output / M) * p.out +
    (tokens.cacheRead / M) * p.cacheRead +
    (tokens.cacheCreation / M) * p.cacheWrite
  );
}
```

- [ ] **Step 4: Implement metrics.ts**

```ts
// Read-time derivation over raw stored summary.json blobs.
//
// Per-model monthly tokens are read EXACTLY from `noticed_stats_monthly`
// (summary.py `monthly_noticed_stats`), whose entries carry
// `token_usage.by_model` with per-model input/output/cache_read/cache_creation.
// Only when that block is absent (older summaries) do we fall back to
// APPROXIMATING the split by distributing the progression entry's tokens_total
// across models proportionally to invocation counts.
import type { Db } from "@/lib/db";
import { latestUploads, listPeople, uploadsForPerson } from "@/lib/db";
import { costUsd } from "@/lib/pricing";

// Tolerate malformed known fields everywhere: coerce anything non-array to [].
function arr<T = any>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

export function monthEntry(summary: any, monthKey: string): any | null {
  const list = summary?.progression_monthly;
  if (!Array.isArray(list)) return null;
  return list.find((e: any) => e?.month === monthKey) ?? null;
}

// Exact per-month token block, when present.
function noticedMonth(summary: any, monthKey: string): any | null {
  const list = summary?.noticed_stats_monthly;
  if (!Array.isArray(list)) return null;
  return list.find((e: any) => e?.month === monthKey) ?? null;
}

export function monthTokensByModel(summary: any, monthKey: string) {
  // Preferred path: exact per-model tokens from noticed_stats_monthly.
  const byModel = noticedMonth(summary, monthKey)?.token_usage?.by_model;
  if (Array.isArray(byModel) && byModel.length) {
    return byModel.map((m: any) => {
      const t = {
        input: Number(m?.input) || 0,
        output: Number(m?.output) || 0,
        cacheRead: Number(m?.cache_read) || 0,
        cacheCreation: Number(m?.cache_creation) || 0,
      };
      const modelId = String(m?.model_id ?? m?.model ?? "unknown");
      return {
        modelId,
        tokens: t.input + t.output + t.cacheRead + t.cacheCreation,
        cost: costUsd(t, modelId),
      };
    });
  }

  // Fallback: invocation-share approximation for legacy summaries.
  const e = monthEntry(summary, monthKey);
  if (!e) return [];
  const models: [string, number][] = Array.isArray(e.models) ? e.models : [];
  const totalCalls = models.reduce((s, [, n]) => s + n, 0);
  if (totalCalls <= 0) {
    const t = Number(e.tokens_total) || 0;
    return t > 0 ? [{ modelId: e.top_model ?? "unknown", tokens: t, cost: costUsd(splitOf(e, 1), e.top_model ?? "") }] : [];
  }
  return models.map(([modelId, calls]) => {
    const share = calls / totalCalls;
    return {
      modelId,
      tokens: Math.round((Number(e.tokens_total) || 0) * share),
      cost: costUsd(splitOf(e, share), modelId),
    };
  });
}

function splitOf(e: any, share: number) {
  return {
    input: (Number(e.tokens_input) || 0) * share,
    output: (Number(e.tokens_output) || 0) * share,
    cacheRead: (Number(e.tokens_cache_read) || 0) * share,
    cacheCreation: (Number(e.tokens_cache_creation) || 0) * share,
  };
}

export type PersonRow = {
  personId: number; name: string; monthKey: string;
  aq: number | null; tier: string | null; delta: number | null;
  trend: { monthKey: string; aq: number }[];
  topPillar: string | null;
  tokens: number | null; cost: number | null;
};

function aqOf(summary: any): number | null {
  const v = summary?.profile?.aq?.aq_0_100;
  return typeof v === "number" ? v : null;
}

export function personRow(
  personId: number, name: string, monthKey: string,
  summaries: { monthKey: string; summary: any }[]
): PersonRow {
  const cur = summaries.find((s) => s.monthKey === monthKey)?.summary;
  const trend = summaries
    .map((s) => ({ monthKey: s.monthKey, aq: aqOf(s.summary) }))
    .filter((t): t is { monthKey: string; aq: number } => t.aq !== null);
  const idx = trend.findIndex((t) => t.monthKey === monthKey);
  const aq = idx >= 0 ? trend[idx].aq : null;
  const delta = idx > 0 ? trend[idx].aq - trend[idx - 1].aq : null;

  const pillars = cur?.profile?.aq?.pillars;
  let topPillar: string | null = null;
  if (Array.isArray(pillars) && pillars.length) {
    const best = [...pillars].sort(
      (a, b) => (b.score / (b.weight || 1)) - (a.score / (a.weight || 1))
    )[0];
    topPillar = best?.name ?? null;
  }

  const e = cur ? monthEntry(cur, monthKey) : null;
  const tokens = e ? Number(e.tokens_total) || 0 : null;
  const cost = cur
    ? monthTokensByModel(cur, monthKey).reduce((s, m) => s + m.cost, 0)
    : null;

  return { personId, name, monthKey, aq, tier: cur?.profile?.aq?.tier ?? null, delta, trend, topPillar, tokens, cost };
}

export type TeamOverview = {
  people: PersonRow[];
  avgAq: number | null;
  coverage: { withCurrentMonth: number; total: number };
  tokensCurrentMonth: number;
  costCurrentMonth: number;
  usageOverTime: { monthKey: string; byModel: { model: string; tokens: number; cost: number }[] }[];
};

export function buildTeamOverview(db: Db): TeamOverview {
  const people = listPeople(db);
  const latest = latestUploads(db);
  const currentMonth = latest.length ? latest.map((l) => l.monthKey).sort().at(-1)! : null;

  const rows: PersonRow[] = [];
  const usageAgg = new Map<string, Map<string, { tokens: number; cost: number }>>();

  for (const p of people) {
    const ups = uploadsForPerson(db, p.id); // ascending by monthKey
    if (!ups.length) continue;
    const lastMonth = ups.at(-1)!.monthKey;
    rows.push(personRow(p.id, p.name, lastMonth, ups));

    // Usage over time: a single summary only covers a trailing `window_months`
    // window, so the latest upload alone TRUNCATES older months. Iterate ALL of
    // the person's uploads and record each month once — the most recent upload
    // that still covers a month wins (ups is ascending, so later writes clobber
    // earlier ones for the same month). This dedups the overlap between windows.
    const personMonth = new Map<string, { model: string; tokens: number; cost: number }[]>();
    for (const up of ups) {
      const months = new Set<string>([
        ...(Array.isArray(up.summary?.noticed_stats_monthly)
          ? up.summary.noticed_stats_monthly.map((e: any) => e?.month) : []),
        ...(Array.isArray(up.summary?.progression_monthly)
          ? up.summary.progression_monthly.map((e: any) => e?.month) : []),
      ].filter(Boolean));
      for (const month of months) {
        personMonth.set(
          month,
          monthTokensByModel(up.summary, month).map((m) => ({ model: m.modelId, tokens: m.tokens, cost: m.cost }))
        );
      }
    }

    // Merge this person's deduped per-month totals into the team aggregate.
    for (const [month, list] of personMonth) {
      for (const m of list) {
        const byModel = usageAgg.get(month) ?? new Map();
        const cur = byModel.get(m.model) ?? { tokens: 0, cost: 0 };
        cur.tokens += m.tokens;
        cur.cost += m.cost;
        byModel.set(m.model, cur);
        usageAgg.set(month, byModel);
      }
    }
  }

  rows.sort((a, b) => (b.aq ?? -1) - (a.aq ?? -1));

  const aqs = rows.map((r) => r.aq).filter((x): x is number => x !== null);
  const avgAq = aqs.length ? Math.round(aqs.reduce((s, x) => s + x, 0) / aqs.length) : null;
  const withCurrent = currentMonth ? rows.filter((r) => r.monthKey === currentMonth).length : 0;
  const currentRows = currentMonth ? rows.filter((r) => r.monthKey === currentMonth) : [];

  return {
    people: rows,
    avgAq,
    coverage: { withCurrentMonth: withCurrent, total: people.length },
    tokensCurrentMonth: currentRows.reduce((s, r) => s + (r.tokens ?? 0), 0),
    costCurrentMonth: currentRows.reduce((s, r) => s + (r.cost ?? 0), 0),
    usageOverTime: [...usageAgg.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([monthKey, byModel]) => ({
        monthKey,
        byModel: [...byModel.entries()].map(([model, v]) => ({ model, ...v })),
      })),
  };
}

export type PersonProfile = {
  personId: number; name: string; email: string; monthKey: string;
  prevMonthKey: string | null; nextMonthKey: string | null;
  aq: number; tier: string; delta: number | null;
  levelOverTime: { monthKey: string; aq: number }[];
  pillars: { name: string; weight: number; score: number;
             axes: { name: string; weight: number; score: number }[] }[];
  scorecard: { key: "execution" | "planning" | "engineering"; value: number; gloss: string;
               trend: { monthKey: string; value: number }[] }[];
  explore: { label: string; value: string }[];
  usage: { sessions: number; prompts: number; actionsPerPrompt: number };
  modelMix: { model: string; pct: number }[];
  archetype: { title: string; quote: string } | null;
};

const SCORE_KEYS = ["execution", "planning", "engineering"] as const;

export function buildPersonProfile(db: Db, personId: number, monthKey: string): PersonProfile | null {
  const person = listPeople(db).find((p) => p.id === personId);
  if (!person) return null;
  const ups = uploadsForPerson(db, personId);
  const idx = ups.findIndex((u) => u.monthKey === monthKey);
  if (idx < 0) return null;
  const s = ups[idx].summary;
  const aq = aqOf(s);
  if (aq === null) return null;

  const levelOverTime = ups
    .map((u) => ({ monthKey: u.monthKey, aq: aqOf(u.summary) }))
    .filter((t): t is { monthKey: string; aq: number } => t.aq !== null);
  const li = levelOverTime.findIndex((t) => t.monthKey === monthKey);
  const delta = li > 0 ? levelOverTime[li].aq - levelOverTime[li - 1].aq : null;

  const scorecard = SCORE_KEYS.map((key) => ({
    key,
    value: Number(s?.profile?.scores?.[key]?.value) || 0,
    gloss: String(s?.profile?.scores?.[key]?.gloss ?? ""),
    trend: ups
      .map((u) => ({ monthKey: u.monthKey, value: Number(u.summary?.profile?.scores?.[key]?.value) }))
      .filter((t) => Number.isFinite(t.value)),
  }));

  const pct = (x: any) => (x == null ? "—" : `${Math.round(Number(x) * 100)}%`);
  const num = (x: any, unit = "") => (x == null ? "—" : `${x}${unit}`);
  const explore = [
    { label: "Planning ratio", value: pct(s?.planning_ratio_explore_to_doing) },
    { label: "Error recovery", value: pct(s?.errors?.error_recovery_ratio) },
    { label: "Error rate", value: num(s?.errors?.error_rate_per_100_tools, " /100 tools") },
    { label: "Iter depth", value: num(s?.iteration_depth?.mean, "×") },
    { label: "Git churn", value: num(s?.churn?.git_churn_total, " lines") },
    { label: "Fanout median", value: num(s?.orchestration?.fanout_median, " tasks") },
    { label: "Compounding writes", value: num(s?.compounding_writes, " ops") },
  ];

  const e = monthEntry(s, monthKey);
  const prompts = Number(e?.prompts ?? s?.context?.total_prompts) || 0;
  const sessions = Number(e?.sessions ?? s?.context?.total_sessions) || 0;
  const toolCalls = Number(e?.tool_calls) || 0;

  return {
    personId, name: person.name, email: person.email, monthKey,
    prevMonthKey: idx > 0 ? ups[idx - 1].monthKey : null,
    nextMonthKey: idx < ups.length - 1 ? ups[idx + 1].monthKey : null,
    aq, tier: String(s?.profile?.aq?.tier ?? ""), delta, levelOverTime,
    pillars: arr(s?.profile?.aq?.pillars).map((p: any) => ({
      name: String(p?.name ?? ""), weight: Number(p?.weight) || 0, score: Number(p?.score) || 0,
      axes: arr(p?.axes).map((a: any) => ({
        name: String(a?.name ?? ""), weight: Number(a?.weight) || 0, score: Number(a?.score) || 0,
      })),
    })),
    scorecard, explore,
    usage: {
      sessions, prompts,
      actionsPerPrompt: prompts > 0 ? Math.round(toolCalls / prompts) : 0,
    },
    modelMix: arr(s?.profile?.model_usage).map((m: any) => ({
      model: String(m?.model ?? m?.model_id ?? "?"),
      pct: Number(m?.pct) || 0,
    })),
    archetype: s?.profile?.archetype ?? null,
  };
}

export function fmtTokens(n: number): string {
  return `${Math.round(n / 1_000_000)}M`;
}

export function fmtUsd(n: number): string {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}
```

- [ ] **Step 5: Run tests, verify pass**

Run: `npm test -- tests/metrics.test.ts`
Expected: all PASS. If the delta test fails because `makeSummary` deep-merges `profile.aq` without replacing pillars, that's fine — only `aq_0_100`/`tier` are overridden; pillars stay from base.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/pricing.ts dashboard/src/lib/metrics.ts dashboard/tests/metrics.test.ts
git commit -m "feat(dashboard): read-time metric derivation, pricing map, view models"
```

---

### Task 8: Team overview page

**Files:**
- Create: `dashboard/src/components/Card.tsx`
- Create: `dashboard/src/components/PeopleTable.tsx`
- Create: `dashboard/src/components/UsageChart.tsx` (client component, Recharts)
- Create: `dashboard/src/components/Sparkline.tsx` (inline SVG, no lib)
- Modify: `dashboard/src/app/page.tsx` (replace placeholder)

**Interfaces:**
- Consumes: `buildTeamOverview`, `fmtTokens`, `fmtUsd`, `TeamOverview`, `PersonRow` (Task 7); `getDb` (Task 2).
- Produces: `/` server-rendered page. `export const dynamic = "force-dynamic"` (reads DB per request).

- [ ] **Step 1: Sparkline component**

`dashboard/src/components/Sparkline.tsx`:

```tsx
export function Sparkline({ points, width = 90, height = 28 }: {
  points: number[]; width?: number; height?: number;
}) {
  if (points.length < 2) return <div style={{ width, height }} />;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - 3 - ((p - min) / span) * (height - 6)).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} className="block rounded"
         style={{ background: "var(--bg-base)" }}>
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} />
    </svg>
  );
}
```

- [ ] **Step 2: Card component**

`dashboard/src/components/Card.tsx`:

```tsx
export function Card({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border p-6"
         style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
      <div className="text-xs font-semibold tracking-widest uppercase mb-3"
           style={{ color: "var(--text-muted)" }}>{title}</div>
      <div className="text-4xl font-bold">{value}</div>
      {sub && <div className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>{sub}</div>}
    </div>
  );
}
```

- [ ] **Step 3: PeopleTable component**

`dashboard/src/components/PeopleTable.tsx`:

The design spec requires a **sortable** people table, so this is a client component with clickable column headers (default sort: AQ desc, matching the server order).

```tsx
"use client";
import Link from "next/link";
import { useState } from "react";
import type { PersonRow } from "@/lib/metrics";
import { fmtTokens, fmtUsd } from "@/lib/metrics";
import { Sparkline } from "./Sparkline";

type SortKey = "name" | "aq" | "tier" | "delta" | "topPillar" | "tokens" | "cost";
const COLS: { key: SortKey | null; label: string }[] = [
  { key: "name", label: "Name" }, { key: "aq", label: "AQ" }, { key: "tier", label: "Tier" },
  { key: null, label: "Trend" }, { key: "delta", label: "Delta" }, { key: "topPillar", label: "Top pillar" },
  { key: "tokens", label: "Tokens" }, { key: "cost", label: "Cost" },
];

// Nulls always sort last regardless of direction.
function cmp(a: PersonRow, b: PersonRow, key: SortKey, dir: 1 | -1): number {
  const av = a[key] as string | number | null;
  const bv = b[key] as string | number | null;
  if (av === null && bv === null) return 0;
  if (av === null) return 1;
  if (bv === null) return -1;
  if (typeof av === "string" && typeof bv === "string") return dir * av.localeCompare(bv);
  return dir * ((av as number) - (bv as number));
}

export function PeopleTable({ people }: { people: PersonRow[] }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "aq", dir: -1 });
  const rows = [...people].sort((a, b) => cmp(a, b, sort.key, sort.dir));
  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: -1 }));

  return (
    <div className="rounded-2xl border overflow-x-auto"
         style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            {COLS.map((c) => (
              <th key={c.label} className="text-left px-4 py-3 font-semibold">
                {c.key ? (
                  <button type="button" onClick={() => onSort(c.key!)}
                          className="uppercase tracking-widest hover:text-white">
                    {c.label}{sort.key === c.key ? (sort.dir === -1 ? " ↓" : " ↑") : ""}
                  </button>
                ) : c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.personId} className="border-t" style={{ borderColor: "var(--border)" }}>
              <td className="px-4 py-3 font-semibold">
                <Link href={`/p/${p.personId}/${p.monthKey}`} className="hover:underline">
                  {p.name}
                </Link>
              </td>
              <td className="px-4 py-3 text-lg font-bold">{p.aq ?? "—"}</td>
              <td className="px-4 py-3">
                {p.tier && (
                  <span className="rounded-full border px-2.5 py-0.5 text-xs font-semibold"
                        style={{ color: "var(--accent)", borderColor: "var(--accent)" }}>
                    {p.tier.toUpperCase()}
                  </span>
                )}
              </td>
              <td className="px-4 py-3"><Sparkline points={p.trend.map((t) => t.aq)} /></td>
              <td className="px-4 py-3" style={{ color: "var(--accent)" }}>
                {p.delta === null ? "—" : `${p.delta >= 0 ? "+" : ""}${p.delta} pts`}
              </td>
              <td className="px-4 py-3">{p.topPillar ?? "—"}</td>
              <td className="px-4 py-3 font-mono">{p.tokens === null ? "—" : fmtTokens(p.tokens)}</td>
              <td className="px-4 py-3 font-mono">{p.cost === null ? "—" : fmtUsd(p.cost)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: UsageChart client component**

`dashboard/src/components/UsageChart.tsx`:

```tsx
"use client";
import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

const COLORS = ["#ee1a64", "#5d5fee", "#22c55e", "#eab308", "#94a3b8", "#f472b6", "#38bdf8", "#fb923c"];

export function UsageChart({ data }: {
  data: { monthKey: string; byModel: { model: string; tokens: number; cost: number }[] }[];
}) {
  const [mode, setMode] = useState<"tokens" | "cost">("tokens");
  const models = [...new Set(data.flatMap((d) => d.byModel.map((m) => m.model)))];
  const rows = data.map((d) => {
    const row: Record<string, number | string> = { month: d.monthKey };
    for (const m of d.byModel) {
      row[m.model] = mode === "tokens" ? Math.round(m.tokens / 1_000_000) : Math.round(m.cost);
    }
    return row;
  });
  return (
    <div className="rounded-2xl border p-6"
         style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold tracking-widest uppercase"
            style={{ color: "var(--text-muted)" }}>
          Company usage over time
        </h2>
        <div className="flex rounded-full border text-xs font-semibold overflow-hidden"
             style={{ borderColor: "var(--border)" }}>
          {(["tokens", "cost"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)}
                    className="px-3 py-1 capitalize"
                    style={mode === m ? { background: "var(--accent)", color: "white" } : { color: "var(--text-muted)" }}>
              {m}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={rows}>
          <XAxis dataKey="month" stroke="var(--text-muted)" fontSize={12} />
          <YAxis stroke="var(--text-muted)" fontSize={12}
                 tickFormatter={(v) => (mode === "tokens" ? `${v}M` : `$${v}`)} />
          <Tooltip contentStyle={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {models.map((m, i) => (
            <Bar key={m} dataKey={m} stackId="usage" fill={COLORS[i % COLORS.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 5: Overview page**

`dashboard/src/app/page.tsx` (replace placeholder):

```tsx
import { getDb } from "@/lib/db";
import { buildTeamOverview, fmtTokens, fmtUsd } from "@/lib/metrics";
import { Card } from "@/components/Card";
import { PeopleTable } from "@/components/PeopleTable";
import { UsageChart } from "@/components/UsageChart";

export const dynamic = "force-dynamic";

export default function Home() {
  const o = buildTeamOverview(getDb());

  if (o.people.length === 0) {
    return (
      <main className="min-h-screen flex items-center justify-center p-6">
        <div className="max-w-lg rounded-2xl border p-8 text-center"
             style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
          <h1 className="text-2xl font-bold mb-3">No uploads yet</h1>
          <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
            Point the gnomon CLI at this dashboard to see your team here:
          </p>
          <pre className="rounded-lg p-4 text-left text-xs overflow-x-auto"
               style={{ background: "var(--bg-elev)" }}>
{`uvx --from git+https://github.com/xmartlabs/gnomon@latest \\
  xl-ai-insights --mirdash-base=${process.env.PUBLIC_URL ?? "http://localhost:3000"}`}
          </pre>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl p-6 flex flex-col gap-6">
      <h1 className="text-lg font-bold tracking-widest uppercase"
          style={{ color: "var(--text-muted)" }}>gnomon · team dashboard</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card title="Team avg AQ" value={o.avgAq === null ? "—" : `${o.avgAq}`} sub="/100" />
        <Card title="Ingest coverage"
              value={o.coverage.total ? `${Math.round((o.coverage.withCurrentMonth / o.coverage.total) * 100)}%` : "—"}
              sub={`${o.coverage.withCurrentMonth} / ${o.coverage.total} people`} />
        <Card title="Tokens/mo" value={fmtTokens(o.tokensCurrentMonth)} />
        <Card title="Est. cost/mo" value={fmtUsd(o.costCurrentMonth)} sub="approx. list prices" />
      </div>
      <UsageChart data={o.usageOverTime} />
      <section>
        <h2 className="text-sm font-semibold tracking-widest uppercase mb-3"
            style={{ color: "var(--text-muted)" }}>People</h2>
        <PeopleTable people={o.people} />
      </section>
    </main>
  );
}
```

- [ ] **Step 6: Verify build + manual smoke**

Run: `npm run build && npm test`
Expected: build OK, tests PASS.

Manual check: `TEAM_TOKEN=dev JWT_SECRET=devsecret-32-bytes-minimum-please DATA_DIR=/tmp/gnomon-dev npm run dev` → open `http://localhost:3000` → empty-state card renders with the CLI command.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components dashboard/src/app/page.tsx
git commit -m "feat(dashboard): team overview — cards, people table, usage chart"
```

---

### Task 9: Person profile page

**Files:**
- Create: `dashboard/src/app/p/[personId]/[monthKey]/page.tsx`
- Create: `dashboard/src/components/PillarBar.tsx`
- Create: `dashboard/src/components/ScoreCard.tsx`
- Create: `dashboard/src/components/ModelMixBar.tsx`

**Interfaces:**
- Consumes: `buildPersonProfile`, `fmtTokens` (Task 7); `getDb` (Task 2); `Sparkline` (Task 8).
- Produces: `/p/<personId>/<monthKey>` server-rendered page (+ `LevelBars` for level-over-time, per design spec); `notFound()` when profile is null.

- [ ] **Step 1: PillarBar component**

`dashboard/src/components/PillarBar.tsx`:

```tsx
export function PillarBar({ name, score, weight, axes }: {
  name: string; score: number; weight: number;
  axes: { name: string; weight: number; score: number }[];
}) {
  const pct = weight > 0 ? Math.min(100, (score / weight) * 100) : 0;
  return (
    <div className="rounded-2xl border p-5"
         style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
      <div className="flex justify-between text-sm font-semibold mb-2">
        <span>{name}</span>
        <span>{score.toFixed(0)}<span style={{ color: "var(--text-muted)" }}>/{weight}</span></span>
      </div>
      <div className="h-1.5 rounded-full" style={{ background: "var(--bg-elev)" }}>
        <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, background: "var(--accent)" }} />
      </div>
      {axes.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 text-xs" style={{ color: "var(--text-muted)" }}>
          {axes.map((a) => (
            <li key={a.name} className="flex justify-between">
              <span>{a.name}</span>
              <span>{a.score.toFixed(1)}/{a.weight}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: ScoreCard component**

`dashboard/src/components/ScoreCard.tsx`:

```tsx
import { Sparkline } from "./Sparkline";

export function ScoreCard({ label, value, gloss, trend }: {
  label: string; value: number; gloss: string; trend: number[];
}) {
  return (
    <div className="rounded-2xl border p-5"
         style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
      <div className="text-xs font-semibold tracking-widest uppercase mb-2"
           style={{ color: "var(--text-muted)" }}>{label}</div>
      <div className="text-3xl font-bold mb-1">
        {value.toFixed(1)}<span className="text-base font-normal" style={{ color: "var(--text-muted)" }}>/10</span>
      </div>
      <div className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>{gloss}</div>
      <Sparkline points={trend} width={180} height={40} />
    </div>
  );
}
```

- [ ] **Step 3: ModelMixBar component**

`dashboard/src/components/ModelMixBar.tsx`:

```tsx
const COLORS = ["#ee1a64", "#5d5fee", "#22c55e", "#eab308", "#94a3b8", "#f472b6"];

export function ModelMixBar({ mix }: { mix: { model: string; pct: number }[] }) {
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden mb-2" style={{ background: "var(--bg-elev)" }}>
        {mix.map((m, i) => (
          <div key={m.model} style={{ width: `${m.pct * 100}%`, background: COLORS[i % COLORS.length] }} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs" style={{ color: "var(--text-secondary)" }}>
        {mix.map((m, i) => (
          <span key={m.model} className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
            {m.model} {Math.round(m.pct * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3b: LevelBars component**

The design spec calls for **level-over-time bars** on the profile (not a sparkline). One bar per uploaded month, height ∝ AQ, most recent highlighted.

`dashboard/src/components/LevelBars.tsx`:

```tsx
export function LevelBars({ points }: { points: { monthKey: string; aq: number }[] }) {
  if (!points.length) {
    return <p className="text-sm" style={{ color: "var(--text-muted)" }}>No history yet.</p>;
  }
  const max = Math.max(100, ...points.map((p) => p.aq));
  return (
    <div className="flex items-end gap-2" style={{ height: 80 }}>
      {points.map((p, i) => {
        const isLast = i === points.length - 1;
        return (
          <div key={p.monthKey} className="flex-1 flex flex-col items-center gap-1 justify-end">
            <span className="text-xs font-semibold">{p.aq}</span>
            <div className="w-full rounded-t"
                 style={{
                   height: `${Math.max(4, (p.aq / max) * 56)}px`,
                   background: isLast ? "var(--accent)" : "var(--purple)",
                   opacity: isLast ? 1 : 0.55,
                 }} />
            <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>{p.monthKey.slice(2)}</span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Profile page**

`dashboard/src/app/p/[personId]/[monthKey]/page.tsx`:

```tsx
import Link from "next/link";
import { notFound } from "next/navigation";
import { getDb } from "@/lib/db";
import { buildPersonProfile } from "@/lib/metrics";
import { PillarBar } from "@/components/PillarBar";
import { ScoreCard } from "@/components/ScoreCard";
import { ModelMixBar } from "@/components/ModelMixBar";
import { LevelBars } from "@/components/LevelBars";

export const dynamic = "force-dynamic";

export default async function ProfilePage({
  params,
}: {
  params: Promise<{ personId: string; monthKey: string }>;
}) {
  const { personId, monthKey } = await params;
  const prof = buildPersonProfile(getDb(), Number(personId), monthKey);
  if (!prof) notFound();

  return (
    <main className="mx-auto max-w-6xl p-6 flex flex-col gap-6">
      <nav className="flex items-center justify-between">
        <Link href="/" className="text-sm hover:underline" style={{ color: "var(--text-muted)" }}>
          ← Team
        </Link>
        <div className="flex items-center gap-3 text-sm">
          {prof.prevMonthKey ? (
            <Link href={`/p/${prof.personId}/${prof.prevMonthKey}`} className="hover:underline">‹</Link>
          ) : <span style={{ color: "var(--text-muted)" }}>‹</span>}
          <span className="font-semibold">{prof.monthKey}</span>
          {prof.nextMonthKey ? (
            <Link href={`/p/${prof.personId}/${prof.nextMonthKey}`} className="hover:underline">›</Link>
          ) : <span style={{ color: "var(--text-muted)" }}>›</span>}
        </div>
      </nav>

      <header className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold">{prof.name}</h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>{prof.email}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-5xl font-bold">{prof.aq}<span className="text-xl" style={{ color: "var(--text-muted)" }}>/100</span></div>
          <div className="flex flex-col gap-1 items-start">
            <span className="rounded-full border px-3 py-0.5 text-xs font-semibold"
                  style={{ color: "var(--accent)", borderColor: "var(--accent)" }}>
              {prof.tier.toUpperCase()}
            </span>
            {prof.delta !== null && (
              <span className="text-xs" style={{ color: "var(--accent)" }}>
                {prof.delta >= 0 ? "↗ +" : "↘ "}{prof.delta} pts
              </span>
            )}
          </div>
        </div>
      </header>

      {prof.archetype && (
        <p className="text-sm italic" style={{ color: "var(--text-secondary)" }}>
          {prof.archetype.title} — “{prof.archetype.quote}”
        </p>
      )}

      <section className="rounded-2xl border p-5"
               style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
        <h2 className="text-xs font-semibold tracking-widest uppercase mb-3"
            style={{ color: "var(--text-muted)" }}>Level over time</h2>
        <LevelBars points={prof.levelOverTime} />
      </section>

      <section>
        <h2 className="text-xs font-semibold tracking-widest uppercase mb-3"
            style={{ color: "var(--text-muted)" }}>How you operate agents</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {prof.pillars.map((p) => <PillarBar key={p.name} {...p} />)}
        </div>
      </section>

      <section>
        <h2 className="text-xs font-semibold tracking-widest uppercase mb-3"
            style={{ color: "var(--text-muted)" }}>Scorecard</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {prof.scorecard.map((s) => (
            <ScoreCard key={s.key} label={s.key} value={s.value} gloss={s.gloss}
                       trend={s.trend.map((t) => t.value)} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-xs font-semibold tracking-widest uppercase mb-3"
            style={{ color: "var(--text-muted)" }}>Explore</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {prof.explore.map((m) => (
            <div key={m.label} className="rounded-2xl border p-4"
                 style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
              <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-muted)" }}>
                {m.label}
              </div>
              <div className="text-xl font-bold">{m.value}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border p-5 flex flex-col gap-4"
               style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
        <div className="grid grid-cols-3 gap-4 text-center">
          {[["Sessions", prof.usage.sessions], ["Prompts", prof.usage.prompts],
            ["Actions / prompt", prof.usage.actionsPerPrompt]].map(([label, v]) => (
            <div key={label as string}>
              <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>{label}</div>
              <div className="text-2xl font-bold">{v}</div>
            </div>
          ))}
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-muted)" }}>
            Model mix
          </div>
          <ModelMixBar mix={prof.modelMix} />
        </div>
      </section>
    </main>
  );
}
```

- [ ] **Step 5: Verify build + tests**

Run: `npm run build && npm test`
Expected: build OK, all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/app/p dashboard/src/components/PillarBar.tsx dashboard/src/components/ScoreCard.tsx dashboard/src/components/ModelMixBar.tsx dashboard/src/components/LevelBars.tsx
git commit -m "feat(dashboard): person profile page — AQ, pillars, scorecard, explore, usage"
```

---

### Task 10: AI coach (optional feature)

**Files:**
- Create: `dashboard/src/lib/coach.ts`
- Create: `dashboard/src/components/CoachCard.tsx`
- Modify: `dashboard/src/app/p/[personId]/[monthKey]/page.tsx` (insert `<CoachSection>` after archetype)
- Test: `dashboard/tests/coach.test.ts`

**Interfaces:**
- Consumes: `settings` table via `Db` (Task 2), `PersonProfile` (Task 7).
- Produces:
  - `coachEnabled(): boolean` — true iff `process.env.LLM_API_KEY` set.
  - `getCoachText(db: Db, prof: PersonProfile): Promise<string | null>` — returns cached text from `settings` key `coach:<personId>:<monthKey>`, else calls Anthropic Messages API (model `claude-haiku-4-5-20251001`, max_tokens 300) with a compact prompt built from the profile numbers, caches, returns; returns null when disabled or on API error (never throws into the page).

- [ ] **Step 1: Write failing tests** (mock `fetch`; test cache hit, disabled state, API failure → null)

`dashboard/tests/coach.test.ts`:

```ts
import { describe, it, expect, beforeEach, vi } from "vitest";
import Database from "better-sqlite3";
import { initSchema } from "@/lib/db";
import { coachEnabled, getCoachText } from "@/lib/coach";

const prof: any = {
  personId: 1, monthKey: "2026-06", name: "Ada", aq: 93, tier: "Elite",
  pillars: [{ name: "Breadth", weight: 30, score: 27, axes: [] }],
  scorecard: [{ key: "execution", value: 8.5, gloss: "", trend: [] }],
  explore: [], usage: { sessions: 1, prompts: 1, actionsPerPrompt: 1 }, modelMix: [],
  levelOverTime: [], delta: null, prevMonthKey: null, nextMonthKey: null,
  email: "ada@example.com", archetype: null,
};

describe("coach", () => {
  let db: any;
  beforeEach(() => {
    db = new Database(":memory:");
    initSchema(db);
    vi.restoreAllMocks();
  });

  it("disabled without LLM_API_KEY", async () => {
    delete process.env.LLM_API_KEY;
    expect(coachEnabled()).toBe(false);
    expect(await getCoachText(db, prof)).toBeNull();
  });

  it("calls API once, then serves from cache", async () => {
    process.env.LLM_API_KEY = "sk-test";
    const mock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ content: [{ type: "text", text: "Focus on Breadth." }] }), { status: 200 })
    );
    expect(await getCoachText(db, prof)).toBe("Focus on Breadth.");
    expect(await getCoachText(db, prof)).toBe("Focus on Breadth.");
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it("returns null on API error", async () => {
    process.env.LLM_API_KEY = "sk-test";
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("boom", { status: 500 }));
    expect(await getCoachText(db, prof)).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests, verify fail**

Run: `npm test -- tests/coach.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement coach.ts**

```ts
import type { Db } from "@/lib/db";
import type { PersonProfile } from "@/lib/metrics";

export function coachEnabled(): boolean {
  return Boolean(process.env.LLM_API_KEY);
}

export async function getCoachText(db: Db, prof: PersonProfile): Promise<string | null> {
  if (!coachEnabled()) return null;
  const key = `coach:${prof.personId}:${prof.monthKey}`;
  const cached = db.prepare(`SELECT value FROM settings WHERE key = ?`).get(key) as
    | { value: string }
    | undefined;
  if (cached) return cached.value;

  const pillars = prof.pillars
    .map((p) => `${p.name} ${p.score.toFixed(0)}/${p.weight}`)
    .join(", ");
  const scores = prof.scorecard.map((s) => `${s.key} ${s.value.toFixed(1)}/10`).join(", ");
  const prompt =
    `You are a concise engineering coach. In 3-4 sentences, tell this developer their ` +
    `strongest area and the single highest-leverage improvement. No preamble.\n` +
    `AQ: ${prof.aq}/100 (${prof.tier}). Pillars: ${pillars}. Scores: ${scores}.`;

  try {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": process.env.LLM_API_KEY!,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 300,
        messages: [{ role: "user", content: prompt }],
      }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    const text = data?.content?.find((b: any) => b.type === "text")?.text;
    if (typeof text !== "string" || !text.trim()) return null;
    db.prepare(`INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)`).run(key, text.trim());
    return text.trim();
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `npm test -- tests/coach.test.ts`
Expected: 3 PASS.

- [ ] **Step 5: CoachCard + wire into profile page**

`dashboard/src/components/CoachCard.tsx`:

```tsx
export function CoachCard({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border p-5"
         style={{ background: "var(--bg-surface)", borderColor: "var(--purple)" }}>
      <div className="text-xs font-semibold tracking-widest uppercase mb-2"
           style={{ color: "var(--purple)" }}>✦ AI coach</div>
      <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>{text}</p>
    </div>
  );
}
```

In `dashboard/src/app/p/[personId]/[monthKey]/page.tsx`, add imports and render after the archetype paragraph:

```tsx
import { getCoachText } from "@/lib/coach";
import { CoachCard } from "@/components/CoachCard";
// inside the component, after computing prof:
const coach = await getCoachText(getDb(), prof);
// in JSX, after the archetype <p>:
{coach && <CoachCard text={coach} />}
```

- [ ] **Step 6: Verify build + full suite**

Run: `npm run build && npm test`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/lib/coach.ts dashboard/src/components/CoachCard.tsx dashboard/src/app/p dashboard/tests/coach.test.ts
git commit -m "feat(dashboard): optional AI coach with DB cache, off without LLM_API_KEY"
```

---

### Task 11: Docker image, compose, env, smoke e2e

**Files:**
- Create: `dashboard/Dockerfile`
- Create: `dashboard/.dockerignore`
- Create: `docker-compose.yml` (repo root)
- Create: `.env.example` (repo root)
- Create: `dashboard/scripts/smoke-e2e.sh`

**Interfaces:**
- Consumes: everything above.
- Produces: `docker compose up` serves the dashboard on `:3000` with persisted volume; smoke script exercises cli-auth → ingest → overview → profile against a running container.

- [ ] **Step 1: Dockerfile** (multi-stage, standalone output; better-sqlite3 native build needs python3/make/g++ in the builder only)

```dockerfile
FROM node:22-bookworm-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production DATA_DIR=/data PORT=3000 HOSTNAME=0.0.0.0
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/scripts/docker-entrypoint.sh ./docker-entrypoint.sh
RUN mkdir -p /data && chown node:node /data
USER node
VOLUME /data
EXPOSE 3000
# TEAM_TOKEN is enforced at container start by the entrypoint (Step 5), NOT at
# build time — the builder has no runtime secrets.
ENTRYPOINT ["./docker-entrypoint.sh"]
```

Note: create an empty `dashboard/public/.gitkeep` so the `COPY` doesn't fail if no public assets exist yet. The entrypoint script is created in Step 5.

- [ ] **Step 2: dashboard/.dockerignore**

```
node_modules
.next
*.db
.env
```

- [ ] **Step 3: docker-compose.yml (repo root)**

```yaml
services:
  dashboard:
    image: ghcr.io/xmartlabs/gnomon-dashboard:latest
    build: ./dashboard
    ports:
      - "3000:3000"
    env_file: .env
    volumes:
      - gnomon-data:/data
    restart: unless-stopped

volumes:
  gnomon-data:
```

(`build:` present so `docker compose up --build` works from a clone before the ghcr image exists; plain `docker compose up` pulls the published image.)

- [ ] **Step 4: .env.example (repo root)**

```bash
# REQUIRED — shared secret your team enters on the /cli-auth page.
# Generate one: openssl rand -hex 24
TEAM_TOKEN=change-me

# OPTIONAL — JWT signing secret. Auto-generated and persisted in the data
# volume when unset. Set it explicitly if you run replicas.
# JWT_SECRET=

# OPTIONAL — Anthropic API key. Enables the AI coach card on profiles.
# LLM_API_KEY=

# OPTIONAL — public base URL shown in onboarding copy.
# PUBLIC_URL=https://gnomon.your-company.com
```

- [ ] **Step 5: TEAM_TOKEN boot guard (container entrypoint)**

The guard MUST NOT live in `layout.tsx`: module-scope code there is evaluated during `npm run build`, which runs in the Docker builder **without** runtime secrets — a build-time throw would break the image build, and it is not a reliable process-start check anyway. Enforce it in a build-safe startup wrapper that runs only when the container starts.

`dashboard/scripts/docker-entrypoint.sh`:

```sh
#!/usr/bin/env sh
set -e
if [ -z "${TEAM_TOKEN:-}" ]; then
  echo "FATAL: TEAM_TOKEN env var is required — set it in .env (see .env.example)" >&2
  exit 1
fi
exec node server.js
```

This runs at container start (not build), and a missing `TEAM_TOKEN` makes the container exit non-zero immediately. `chmod +x dashboard/scripts/docker-entrypoint.sh`.

Update the Dockerfile runner stage (Step 1) to use it instead of `CMD ["node", "server.js"]`:

```dockerfile
COPY --from=builder /app/scripts/docker-entrypoint.sh ./docker-entrypoint.sh
ENTRYPOINT ["./docker-entrypoint.sh"]
```

**Verify both properties:**

```bash
# a) image builds with NO runtime secrets present
cd dashboard && docker build -t gnomon-dashboard:local .   # must succeed

# b) container exits immediately (non-zero) when TEAM_TOKEN is absent
docker run --rm gnomon-dashboard:local; echo "exit=$?"      # exit=1, logs the FATAL line
```

- [ ] **Step 6: Smoke e2e script**

`dashboard/scripts/smoke-e2e.sh`:

```bash
#!/usr/bin/env bash
# Smoke test against a running dashboard (default http://localhost:3000).
# Usage: BASE=http://localhost:3000 TEAM_TOKEN=dev ./scripts/smoke-e2e.sh
set -euo pipefail
BASE="${BASE:-http://localhost:3000}"
TEAM_TOKEN="${TEAM_TOKEN:-dev}"

echo "1. cli-auth page renders"
curl -fsS "$BASE/cli-auth?redirect_uri=http://127.0.0.1:9/callback&count=1" | grep -q "Authorize upload"

echo "2. login issues tokens"
LOC=$(curl -fsS -o /dev/null -w '%{redirect_url}' -X POST "$BASE/api/cli-auth" \
  --data-urlencode "team_token=$TEAM_TOKEN" \
  --data-urlencode "name=Smoke Tester" \
  --data-urlencode "email=smoke@example.com" \
  --data-urlencode "redirect_uri=http://127.0.0.1:9/callback" \
  --data-urlencode "count=1")
TOKEN=$(python3 -c "
import sys, json, urllib.parse
q = urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[1]).query)
print(json.loads(q['tokens'][0])[0])" "$LOC")
[ -n "$TOKEN" ]

echo "3. ingest accepts a summary"
SUMMARY=$(python3 - <<'EOF'
import json
print(json.dumps({
  "context": {"date_range": ["2026-01-01", "2026-06-30"], "total_sessions": 10,
              "total_prompts": 100, "window_months": 6},
  "profile": {"aq": {"aq_0_100": 88, "tier": "Advanced", "pillars": []},
              "scores": {"execution": {"value": 8, "gloss": "", "subs": []},
                         "planning": {"value": 9, "gloss": "", "subs": []},
                         "engineering": {"value": 7, "gloss": "", "subs": []}},
              "model_usage": []},
  "progression_monthly": [{"month": "2026-06", "prompts": 100, "sessions": 10,
    "tool_calls": 500, "models": [["claude-opus-4-8", 500]], "tokens_total": 1000000,
    "tokens_input": 100000, "tokens_output": 200000,
    "tokens_cache_read": 600000, "tokens_cache_creation": 100000}],
  "token_usage": {"total_input": 0, "total_output": 0, "total_cache_read": 0,
                  "total_cache_creation": 0, "by_model": []}
}))
EOF
)
REPORT_URL=$(curl -fsS -X POST "$BASE/api/gnomon/ingest" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$SUMMARY" | python3 -c "import sys, json; print(json.load(sys.stdin)['reportUrl'])")

echo "4. overview shows the person"
curl -fsS "$BASE/" | grep -q "Smoke Tester"

echo "5. profile page renders"
curl -fsS "$BASE$REPORT_URL" | grep -q "Smoke Tester"

echo "SMOKE OK"
```

Run: `chmod +x dashboard/scripts/smoke-e2e.sh`

- [ ] **Step 7: Build and run the smoke test**

```bash
cd dashboard && docker build -t gnomon-dashboard:local .
docker run -d --rm --name gnomon-smoke -p 3000:3000 \
  -e TEAM_TOKEN=dev -e JWT_SECRET=devsecret-32-bytes-minimum-please \
  gnomon-dashboard:local
sleep 3
TEAM_TOKEN=dev ./scripts/smoke-e2e.sh
docker stop gnomon-smoke
```

Expected: `SMOKE OK`.

- [ ] **Step 8: End-to-end with the real CLI (manual verification)**

With the container still running:

```bash
cd .. && python3 -m gnomon.cli.insights --mirdash-base=http://localhost:3000 --backfill=2
```

Browser opens `/cli-auth` → enter `dev` token + name/email → CLI uploads → prints report URL → open it, verify profile renders with your real data.

- [ ] **Step 9: Commit**

```bash
git add dashboard/Dockerfile dashboard/.dockerignore dashboard/public/.gitkeep dashboard/scripts docker-compose.yml .env.example
git commit -m "feat(dashboard): Dockerfile, compose, env template, TEAM_TOKEN entrypoint guard, smoke e2e"
```

---

### Task 12: CI image publish + README

**Files:**
- Create: `.github/workflows/dashboard-image.yml`
- Modify: `README.md` (add "Self-hosted dashboard" section after "Sharing your profile")

**Interfaces:**
- Consumes: Dockerfile (Task 11).
- Produces: ghcr image on release tags; user-facing docs.

- [ ] **Step 1: GitHub Action**

`.github/workflows/dashboard-image.yml`:

```yaml
name: dashboard-image

on:
  push:
    tags: ["v*"]
  workflow_dispatch:

jobs:
  # Tests gate the publish — an image never ships on a red suite.
  dashboard-tests:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: dashboard } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: dashboard/package-lock.json }
      - run: npm ci
      - run: npm test
      - run: npm run build

  publish:
    needs: [dashboard-tests, dashboard-contract]  # tests + real CLI contract must pass
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/${{ github.repository_owner }}/gnomon-dashboard
          tags: |
            type=semver,pattern={{version}}
            type=raw,value=latest
      - uses: docker/build-push-action@v6
        with:
          context: ./dashboard
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

Both jobs live in **the same workflow** so the `needs:` gate applies on every tag push. Also add the `dashboard-tests` job to the repo's PR CI workflow (following its conventions) so the suite runs on pull requests too, not only on tags.

- [ ] **Step 2b: Real Python CLI contract test (v1 — the primary constraint, not deferred)**

Exact CLI compatibility is the plan's top global constraint, so it must be exercised against the **real** `gnomon/upload/auth.py` + `mirdash.py` code — not re-implemented in TypeScript unit tests. Add a pytest that drives the actual CLI modules against a running dashboard container.

`tests/dashboard_contract_test.py` (repo-root test suite):

```python
import os, urllib.request, urllib.parse, urllib.error
import pytest
# REAL CLI modules — the contract must hold against these, not a reimplementation.
from gnomon.upload.auth import _tokens_from_query          # auth.py
from gnomon.upload.mirdash import _uploaded_from_query, _upload_summary  # mirdash.py

BASE = os.environ.get("DASHBOARD_BASE", "http://localhost:3000")
TEAM_TOKEN = os.environ.get("TEAM_TOKEN", "dev")

def _post_login(count=2):
    """Submit what the CLI's browser step submits, capture the redirect, and
    parse it with the REAL CLI query parsers so any query-shape drift fails."""
    cb = "http://127.0.0.1:9/callback"
    data = urllib.parse.urlencode({
        "team_token": TEAM_TOKEN, "name": "Contract Bot",
        "email": "contract@example.com", "redirect_uri": cb, "count": str(count),
    }).encode()
    req = urllib.request.Request(f"{BASE}/api/cli-auth", data=data, method="POST")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None  # keep the Location header
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(req)
        pytest.fail("expected a 302 redirect")
    except urllib.error.HTTPError as e:
        assert e.code == 302
        loc = e.headers["Location"]

    # Both parsers take a parse_qs() result dict (exactly as the CLI feeds them).
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    return _tokens_from_query(parsed), _uploaded_from_query(parsed)

def test_auth_callback_shape_matches_cli_parsers():
    tokens, uploaded = _post_login(count=2)
    assert isinstance(tokens, list) and len(tokens) == 2
    assert all(isinstance(t, str) and t for t in tokens)
    assert isinstance(uploaded, list)  # possibly empty on first run

def test_real_uploader_ingests_summary():
    tokens, _ = _post_login(count=1)
    summary = {
        "context": {"date_range": ["2026-01-01", "2026-06-30"], "total_sessions": 10,
                    "total_prompts": 100, "window_months": 6},
        "profile": {"aq": {"aq_0_100": 88, "tier": "Advanced", "pillars": []},
                    "scores": {}, "model_usage": []},
        "progression_monthly": [{"month": "2026-06", "models": [["claude-opus-4-8", 500]],
                                 "tokens_total": 1_000_000}],
    }
    # Drive the REAL uploader: bearer header, JSON body, and reportUrl parsing
    # all come from mirdash._upload_summary itself.
    report_url = _upload_summary(BASE, tokens[0], summary)
    assert isinstance(report_url, str) and report_url.startswith("/p/")
```

> This imports the CLI's own `_tokens_from_query`, `_uploaded_from_query`, and `_upload_summary` — so a contract drift (query keys, bearer scheme, `reportUrl` key, 302 status) fails here rather than silently in production. Confirm the `_upload_summary(base, token, summary)` signature against `gnomon/upload/mirdash.py` when wiring this up (it returns the `reportUrl` string or raises).

Add this job **to `dashboard-image.yml`** (same workflow as `dashboard-tests`/`publish`, so the `publish` gate above resolves) — it boots the container and runs the suite:

```yaml
  dashboard-contract:
    needs: dashboard-tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e . pytest
      - run: docker build -t gnomon-dashboard:ci ./dashboard
      - run: docker run -d --rm --name dash -p 3000:3000 -e TEAM_TOKEN=dev -e JWT_SECRET=ci-secret-32-bytes-minimum-please gnomon-dashboard:ci
      - run: |
          for i in $(seq 1 30); do curl -fsS http://localhost:3000/ >/dev/null && break; sleep 1; done
      - run: TEAM_TOKEN=dev DASHBOARD_BASE=http://localhost:3000 pytest tests/dashboard_contract_test.py -v
      - run: docker stop dash
```

Make `publish` also `needs: [dashboard-tests, dashboard-contract]` so a contract break blocks the image too.

- [ ] **Step 3: README section**

Append to `README.md` after the "Sharing your profile (opt-in)" section:

```markdown
### Self-hosted team dashboard

Don't have (or want) mirdash? Run your own dashboard — one container, one volume:

```bash
git clone https://github.com/xmartlabs/gnomon && cd gnomon
cp .env.example .env          # set TEAM_TOKEN (openssl rand -hex 24)
docker compose up -d          # dashboard at http://localhost:3000
```

Then point the CLI at it:

```bash
uvx --from git+https://github.com/xmartlabs/gnomon@latest \
  xl-ai-insights --mirdash-base=http://localhost:3000
```

Or persist it: `echo '{"mirdash_base": "http://localhost:3000"}' > ~/.config/gnomon/config.json`.

Each teammate signs in with the shared `TEAM_TOKEN` plus their name/email; the
dashboard shows the team ranking, per-person AQ profiles, and usage over time.
Only `summary.json` statistics are uploaded — prompts and file contents never
leave each machine. Set `LLM_API_KEY` (Anthropic) in `.env` to enable the
optional AI-coach card.

This coexists with mirdash: without `--mirdash-base`, the CLI keeps its default
behavior.
```

- [ ] **Step 4: Verify**

Run: `cd dashboard && npm test && npm run build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/dashboard-image.yml tests/dashboard_contract_test.py README.md
git commit -m "ci(dashboard): gated ghcr publish, real CLI contract test, document self-hosting"
```

---

## Self-review notes

- Spec coverage: CLI contract (Tasks 3–6), data model (Task 2), team overview + usage chart (Tasks 7–8), person profile (Task 9), AI coach (Task 10), deploy/DX + smoke e2e (Task 11), ghcr publish + real CLI contract test + README (Task 12). Roster explicitly out of scope. Coexistence handled by not touching `gnomon/` and documenting `--mirdash-base`.
- Per-model monthly tokens are read **exactly** from `noticed_stats_monthly[].token_usage.by_model`; the invocation-share split is a fallback for older summaries lacking that block (documented in `metrics.ts` header).
- Phase-2 candidates (not in this plan): cost pricing config via `settings`, roster metadata.

## Validation notes (2026-07-20)

Plan reviewed with Codex against the real CLI sources. Fixes folded in:
- **Deps bumped to current majors:** Next 16.2, better-sqlite3 12, jose 6, recharts 3 (+`react-is`), vitest 4, added `postcss` and `@types/react-dom` (Task 1).
- **TEAM_TOKEN guard moved out of `layout.tsx`** into a container entrypoint — the build no longer needs the secret and a missing token exits the container non-zero (Task 11).
- **Exact per-model monthly tokens** from `noticed_stats_monthly`, approximation only as legacy fallback; **usage-over-time no longer truncates** older months (iterates all uploads, dedups per person-month) (Task 7).
- **Strict `YYYY-MM-DD` date validation** (both ends, start ≤ end) and **verbatim raw-JSON storage** (Task 4/5).
- **Security:** JWT verification pinned to HS256 + positive-integer `sub`; constant-time team-token compare via fixed-length digests; loopback redirect requires explicit port; ingest body size cap (413); per-IP throttle on the shared team-token endpoint (429) with token-free audit logging (Tasks 3, 5, 6).
- **CI:** image publish gated on `dashboard-tests` **and** a real Python CLI contract test that drives `_tokens_from_query`/`_uploaded_from_query`/`_upload_summary` against a running container (Task 12).
- Array-shape guards on `pillars`/`axes`/`model_usage` for malformed-field tolerance (Task 7).
