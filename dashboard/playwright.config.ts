import { defineConfig } from "@playwright/test";
import path from "node:path";

// Two apps, because the empty state is only reachable with an empty database
// and the rest of the suite needs a seeded one.
export const SEEDED = "http://127.0.0.1:3210";
export const EMPTY = "http://127.0.0.1:3211";

const RUN_DIR = path.join(process.cwd(), "test-results", "run");
const env = (db: string, port: string) => ({
  GNOMON_DB_PATH: path.join(RUN_DIR, db),
  DATA_DIR: RUN_DIR,
  TEAM_TOKEN: "e2e-team-token",
  JWT_SECRET: "e2e-jwt-secret-at-least-32-bytes!",
  PORT: port,
});

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results/artifacts",
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      // The standalone server is what the Docker image runs, so the suite
      // exercises the same entrypoint rather than `next start`.
      command: "node .next/standalone/server.js",
      url: SEEDED,
      timeout: 60_000,
      reuseExistingServer: false,
      env: env("seeded.db", "3210"),
    },
    {
      command: "node .next/standalone/server.js",
      url: EMPTY,
      timeout: 60_000,
      reuseExistingServer: false,
      env: env("empty.db", "3211"),
    },
  ],
});
