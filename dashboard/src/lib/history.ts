import type { Db } from "@/lib/db";
import { uploadsForPerson } from "@/lib/db";

/**
 * The `uploaded_history` payload the CLI's upload planner consumes.
 *
 * Shape and strictness are dictated by `_history_from_query` in
 * gnomon/upload/mirdash.py, which validates ALL-OR-NOTHING: one structurally
 * invalid month invalidates the entire history and silently drops the server
 * back to its pre-contract planner. So every field is emitted only when it is
 * known-good, and a malformed row is skipped rather than passed through.
 */
export type HistoryEntry = {
  monthKey: string;
  uploadedAt: number;
  scoreContractId?: string;
  coverage?: { flag: string; indexed: number; transcripts: number };
  totalSessions?: number;
};

const MONTH_KEY = /^\d{4}-(0[1-9]|1[0-2])$/;
const COVERAGE_FLAGS = new Set(["complete", "partial", "insufficient", "unknown"]);

const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v);

/** Coverage only when it passes the CLI's validator — else omit the optional key. */
function coverageOf(summary: any): HistoryEntry["coverage"] | undefined {
  const c = summary?.coverage;
  if (!c || typeof c !== "object") return undefined;
  if (!COVERAGE_FLAGS.has(c.flag) || !isInt(c.indexed) || !isInt(c.transcripts)) return undefined;
  return { flag: c.flag, indexed: c.indexed, transcripts: c.transcripts };
}

export function uploadHistory(db: Db, personId: number): HistoryEntry[] {
  return uploadsForPerson(db, personId)
    .filter((u) => MONTH_KEY.test(u.monthKey) && isInt(u.uploadedAt) && u.uploadedAt >= 0)
    .map(({ monthKey, uploadedAt, summary }) => {
      const entry: HistoryEntry = { monthKey, uploadedAt };
      // Without scoreContractId the planner sees prev_contract === null, which
      // never equals the active contract, so it re-uploads the previous month
      // on EVERY run (plan_upload's "contract-upgrade" branch).
      const contract = summary?.score_contract_id;
      if (typeof contract === "string" && contract) entry.scoreContractId = contract;
      const coverage = coverageOf(summary);
      if (coverage) entry.coverage = coverage;
      const sessions = summary?.context?.total_sessions;
      if (typeof sessions === "number" && !Number.isNaN(sessions)) {
        entry.totalSessions = Math.trunc(sessions);
      }
      return entry;
    });
}
