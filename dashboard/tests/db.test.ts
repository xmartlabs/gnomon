import { describe, it, expect, beforeEach } from "vitest";
import {
  upsertPerson, upsertUpload, uploadedMonths,
  listPeople, uploadsForPerson, latestUploads, distinctMonthKeys,
} from "@/lib/db";
import { freshDb } from "./helpers/env";

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
    const other = upsertPerson(db, "alan@example.com", "Alan");
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":1}' });

    const put = (key: string) =>
      db.prepare(`INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)`).run(key, "old text");
    const has = (key: string) =>
      db.prepare(`SELECT 1 FROM settings WHERE key = ?`).get(key) !== undefined;

    put(`coach:${p.id}:2026-06`);              // pre-hash format, written by older builds
    put(`coach:${p.id}:2026-06:deadbeefcafe`); // current format: stamped with the prompt hash
    put(`coach:${p.id}:2026-05:deadbeefcafe`); // a month this upload does not supersede
    put(`coach:${other.id}:2026-06:deadbeef`); // someone else's identical month

    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":2}' });

    expect(has(`coach:${p.id}:2026-06`)).toBe(false);
    expect(has(`coach:${p.id}:2026-06:deadbeefcafe`)).toBe(false);
    // The prefix delete must not reach past its own (person, month).
    expect(has(`coach:${p.id}:2026-05:deadbeefcafe`)).toBe(true);
    expect(has(`coach:${other.id}:2026-06:deadbeef`)).toBe(true);
  });

  it("upsertUpload invalidates the team insight for the uploaded monthKey, by anyone", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const other = upsertPerson(db, "alan@example.com", "Alan");
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":1}' });

    const put = (key: string) =>
      db.prepare(`INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)`).run(key, "old text");
    const has = (key: string) =>
      db.prepare(`SELECT 1 FROM settings WHERE key = ?`).get(key) !== undefined;

    put(`coach-team:2026-06:deadbeefcafe`); // the team block this month, not tied to any one person
    put(`coach-team:2026-05:deadbeefcafe`); // a different month — must survive

    // A DIFFERENT person uploading the same month still invalidates the team block.
    upsertUpload(db, { personId: other.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":1}' });

    expect(has(`coach-team:2026-06:deadbeefcafe`)).toBe(false);
    expect(has(`coach-team:2026-05:deadbeefcafe`)).toBe(true);
  });

  it("upsertUpload invalidates the stale suggestions cache for that person-month", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const other = upsertPerson(db, "alan@example.com", "Alan");
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":1}' });

    const put = (key: string) =>
      db.prepare(`INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)`).run(key, "old text");
    const has = (key: string) =>
      db.prepare(`SELECT 1 FROM settings WHERE key = ?`).get(key) !== undefined;

    put(`coach-suggestions:${p.id}:2026-06:deadbeefcafe`);
    put(`coach-suggestions:${p.id}:2026-05:deadbeefcafe`);      // a month this upload does not supersede
    put(`coach-suggestions:${other.id}:2026-06:deadbeef`);      // someone else's identical month

    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: '{"v":2}' });

    expect(has(`coach-suggestions:${p.id}:2026-06:deadbeefcafe`)).toBe(false);
    expect(has(`coach-suggestions:${p.id}:2026-05:deadbeefcafe`)).toBe(true);
    expect(has(`coach-suggestions:${other.id}:2026-06:deadbeef`)).toBe(true);
  });

  it("distinctMonthKeys returns every uploaded monthKey once, most recent first", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const other = upsertPerson(db, "alan@example.com", "Alan");
    upsertUpload(db, { personId: p.id, monthKey: "2026-04", windowMonths: 6, summaryJson: "{}" });
    upsertUpload(db, { personId: p.id, monthKey: "2026-06", windowMonths: 6, summaryJson: "{}" });
    upsertUpload(db, { personId: other.id, monthKey: "2026-06", windowMonths: 6, summaryJson: "{}" });
    upsertUpload(db, { personId: other.id, monthKey: "2026-05", windowMonths: 6, summaryJson: "{}" });

    expect(distinctMonthKeys(db)).toEqual(["2026-06", "2026-05", "2026-04"]);
    expect(distinctMonthKeys(db, 2)).toEqual(["2026-06", "2026-05"]);
  });

  it("distinctMonthKeys returns an empty array for an empty database", () => {
    expect(distinctMonthKeys(db)).toEqual([]);
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
