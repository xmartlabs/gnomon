import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/**
 * Seed the database the seeded server will open. Playwright starts webServer
 * BEFORE globalSetup, so the build lives in the `test:e2e` script instead —
 * seeding is safe here because the DB is opened lazily on the first request.
 *
 * The empty server's DB is deliberately never created: the schema appears on
 * first request, which is exactly the state a fresh `docker compose up` is in.
 */
export default function globalSetup() {
  const cwd = process.cwd();
  const runDir = path.join(cwd, "test-results", "run");
  fs.mkdirSync(runDir, { recursive: true });

  execFileSync("pnpm", ["seed"], {
    cwd,
    stdio: "inherit",
    env: { ...process.env, GNOMON_DB_PATH: path.join(runDir, "seeded.db") },
  });
}
