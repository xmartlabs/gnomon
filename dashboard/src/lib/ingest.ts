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
