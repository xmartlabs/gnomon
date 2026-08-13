import { describe, it, expect, beforeEach } from "vitest";
import {
  upsertPerson, upsertUpload, uploadedMonths,
  listPeople, uploadsForPerson, latestUploads,
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
