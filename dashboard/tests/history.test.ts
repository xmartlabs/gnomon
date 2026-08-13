import { describe, it, expect } from "vitest";
import { upsertPerson, upsertUpload } from "@/lib/db";
import { uploadHistory } from "@/lib/history";
import { makeSummary } from "./fixtures/summary";
import { freshDb } from "./helpers/env";

function seed(db: ReturnType<typeof freshDb>, monthKey: string, summary: unknown) {
  const p = upsertPerson(db, "ada@example.com", "Ada");
  upsertUpload(db, {
    personId: p.id,
    monthKey,
    windowMonths: 6,
    summaryJson: JSON.stringify(summary),
  });
  return p.id;
}

describe("uploadHistory", () => {
  it("carries the planner metadata the CLI reads", () => {
    // Without scoreContractId, plan_upload's contract-upgrade branch re-uploads
    // the previous month on every single run.
    const db = freshDb();
    const id = seed(db, "2026-05", makeSummary());
    expect(uploadHistory(db, id)).toEqual([
      {
        monthKey: "2026-05",
        uploadedAt: expect.any(Number),
        scoreContractId: "aq-v11",
        coverage: { flag: "complete", indexed: 171, transcripts: 171 },
        totalSessions: 171,
      },
    ]);
  });

  it("omits optional keys rather than emitting invalid ones", () => {
    // _history_from_query rejects the WHOLE history on one malformed entry, so
    // a partial summary must degrade to the required pair only.
    const db = freshDb();
    const id = seed(db, "2026-05", { context: {} });
    expect(uploadHistory(db, id)).toEqual([
      { monthKey: "2026-05", uploadedAt: expect.any(Number) },
    ]);
  });

  it.each([
    ["a non-integer indexed", { flag: "complete", indexed: 1.5, transcripts: 3 }],
    ["a boolean transcripts", { flag: "complete", indexed: 1, transcripts: true }],
    ["an unlisted flag", { flag: "bogus", indexed: 1, transcripts: 3 }],
  ])("drops coverage with %s", (_label, coverage) => {
    const db = freshDb();
    const id = seed(db, "2026-05", makeSummary({ coverage }));
    expect(uploadHistory(db, id)[0].coverage).toBeUndefined();
  });

  it("skips rows whose month_key could not pass the CLI validator", () => {
    const db = freshDb();
    const id = seed(db, "2026-13", makeSummary());
    upsertUpload(db, {
      personId: id,
      monthKey: "2026-05",
      windowMonths: 6,
      summaryJson: JSON.stringify(makeSummary()),
    });
    expect(uploadHistory(db, id).map((e) => e.monthKey)).toEqual(["2026-05"]);
  });

  it("returns an empty history for a person with no uploads", () => {
    const db = freshDb();
    const p = upsertPerson(db, "new@example.com", "New");
    expect(uploadHistory(db, p.id)).toEqual([]);
  });
});
