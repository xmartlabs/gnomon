import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { dataDir } from "@/lib/paths";

export type Db = Database.Database;

export function initSchema(db: Db): void {
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");
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

function dbFile(): string {
  const custom = process.env.GNOMON_DB_PATH;
  if (!custom) return path.join(dataDir(), "gnomon.db");
  fs.mkdirSync(path.dirname(custom), { recursive: true });
  return custom;
}

export function getDb(): Db {
  if (_db) return _db;
  const db = new Database(dbFile());
  initSchema(db);
  _db = db; // only cache after schema init succeeds, so a failure retries next call
  return _db;
}

/** Test-only: drop the singleton so the next getDb() honors a new GNOMON_DB_PATH. */
export function _resetDbForTests(): void {
  _db = null;
}

export function upsertPerson(db: Db, email: string, name: string) {
  const normEmail = email.toLowerCase().trim();
  db.prepare(
    `INSERT INTO people (email, name) VALUES (?, ?)
     ON CONFLICT(email) DO UPDATE SET name = excluded.name`
  ).run(normEmail, name.trim());
  return db.prepare(`SELECT id, email, name FROM people WHERE email = ?`)
    .get(normEmail) as { id: number; email: string; name: string };
}

export function upsertUpload(
  db: Db,
  args: { personId: number; monthKey: string; windowMonths: number; summaryJson: string }
): void {
  // Atomic: the upload and its stale-coach-cache eviction must commit together,
  // else a crash between them leaves new metrics beside stale coach text.
  db.transaction(() => {
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
  })();
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
    `SELECT month_key AS monthKey, window_months AS windowMonths,
            uploaded_at AS uploadedAt, summary_json AS summaryJson
     FROM uploads WHERE person_id = ? ORDER BY month_key`
  ).all(personId) as {
    monthKey: string; windowMonths: number; uploadedAt: number; summaryJson: string;
  }[];
  return rows.map((r) => ({
    monthKey: r.monthKey,
    windowMonths: r.windowMonths,
    uploadedAt: r.uploadedAt,
    summary: JSON.parse(r.summaryJson),
  }));
}

export function getUpload(db: Db, personId: number, monthKey: string) {
  const row = db.prepare(
    `SELECT window_months AS windowMonths, summary_json AS summaryJson
     FROM uploads WHERE person_id = ? AND month_key = ?`
  ).get(personId, monthKey) as { windowMonths: number; summaryJson: string } | undefined;
  return row && { windowMonths: row.windowMonths, summary: JSON.parse(row.summaryJson) };
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
