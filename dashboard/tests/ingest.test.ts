import { describe, it, expect } from "vitest";
import { upsertPerson, uploadsForPerson } from "@/lib/db";
import { validateSummary, ingestSummary, IngestError } from "@/lib/ingest";
import { makeSummary } from "./fixtures/summary";
import { freshDb } from "./helpers/env";

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
    const db = freshDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const { reportUrl } = ingestSummary(db, p.id, makeSummary());
    expect(reportUrl).toBe(`/p/${p.id}/2026-06`);
    expect(uploadsForPerson(db, p.id)).toHaveLength(1);
  });

  it("throws IngestError on invalid body", () => {
    const db = freshDb();
    expect(() => ingestSummary(db, 1, {})).toThrow(IngestError);
  });

  it("stores rawJson verbatim when provided", () => {
    const db = freshDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const summary = makeSummary();
    // Raw bytes carry a field the parsed copy never round-trips identically.
    const raw = JSON.stringify({ ...summary, _raw_marker: "kept" });
    ingestSummary(db, p.id, summary, raw);
    const [stored] = uploadsForPerson(db, p.id);
    expect(stored.summary._raw_marker).toBe("kept");
  });

  it("re-ingesting the same month upserts instead of duplicating", () => {
    const db = freshDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    ingestSummary(db, p.id, makeSummary());
    ingestSummary(db, p.id, makeSummary({ context: { total_sessions: 999 } }));
    const rows = uploadsForPerson(db, p.id);
    expect(rows).toHaveLength(1);
    expect(rows[0].summary.context.total_sessions).toBe(999);
  });
});
