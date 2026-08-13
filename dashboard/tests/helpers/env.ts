import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import Database from "better-sqlite3";
import { initSchema, _resetDbForTests } from "@/lib/db";
import { _resetSecretForTests } from "@/lib/auth";

export const TEST_JWT_SECRET = "test-jwt-secret-at-least-32-bytes!!";
export const TEST_TEAM_TOKEN = "sekret-team";

/**
 * Point the module singletons at a throwaway DB file and a known secret.
 * Route tests go through getDb(), so they need the env wiring rather than a
 * hand-built connection — call this in beforeEach.
 */
export function useTempDbEnv(): void {
  process.env.TEAM_TOKEN = TEST_TEAM_TOKEN;
  process.env.JWT_SECRET = TEST_JWT_SECRET;
  process.env.GNOMON_DB_PATH = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "gnomon-")), "t.db");
  _resetDbForTests();
  _resetSecretForTests();
}

/** In-memory DB with the schema applied — for libs that take a Db directly. */
export function freshDb() {
  const db = new Database(":memory:");
  initSchema(db);
  return db;
}
