import type { Db } from "@/lib/db";
import { getUpload, upsertUpload } from "@/lib/db";

export class IngestError extends Error {}

type Valid = { ok: true; monthKey: string; windowMonths: number };
type Invalid = { ok: false; error: string };

// The real CLI sends tz-aware ISO-8601 timestamps, NOT bare dates: parse_window
// (gnomon/sources/discovery.py) turns --since/--until into aware datetimes and
// the accumulator serializes them with .isoformat(), so context.date_range
// arrives as e.g. "2026-08-31T00:00:00-03:00". Both forms are accepted.
//
// The offset is deliberately ignored: these bounds are the operator's LOCAL
// calendar window, and the anchor month must be read the same way the CLI wrote
// it — converting to UTC first would shift an end-of-month bound into the next
// month for positive offsets.
//
// Still strict about the date itself — `Date.parse` accepts "June 30 2026" and
// rolls over impossible dates like 2026-06-31.
const ISO_DATE =
  /^(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

function parseIsoDate(s: unknown): Date | null {
  if (typeof s !== "string") return null;
  const m = ISO_DATE.exec(s);
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
    return {
      ok: false,
      error: "context.date_range must be [start, end] as YYYY-MM-DD or ISO-8601 timestamps",
    };
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

// gnomon/coverage.py COVERAGE_RANK. "unknown" is deliberately absent: it maps
// to null, which is INCOMPARABLE and never justifies rejecting an upload.
const COVERAGE_RANK: Record<string, number> = { insufficient: 0, partial: 1, complete: 2 };

function completeness(summary: any): { rank: number | null; sessions: number } {
  const flag = summary?.coverage?.flag;
  return {
    rank: typeof flag === "string" && flag in COVERAGE_RANK ? COVERAGE_RANK[flag] : null,
    sessions: Number(summary?.context?.total_sessions) || 0,
  };
}

/**
 * Mirror of mirdash's ingest anti-degradation guard (see _stamp_force_directive
 * in gnomon/upload/mirdash.py): a non-force upload must not replace a stored
 * month it loses to on completeness. Claude Code's shrinking transcript
 * retention means a later re-run legitimately sees FEWER sessions than the
 * stored row, and blindly overwriting silently destroys the better snapshot.
 */
function degrades(incoming: any, stored: any): boolean {
  const a = completeness(incoming);
  const b = completeness(stored);
  if (a.rank !== null && b.rank !== null && a.rank !== b.rank) return a.rank < b.rank;
  return a.sessions < b.sessions;
}

// `rawJson` is the original request text — stored verbatim so the bytes are
// preserved. `body` is the parsed copy used only for validation.
export function ingestSummary(
  db: Db,
  personId: number,
  body: any,
  rawJson?: string
): { reportUrl: string; stored: boolean } {
  const v = validateSummary(body);
  if (!v.ok) throw new IngestError(v.error);

  const reportUrl = `/p/${personId}/${v.monthKey}`;
  const existing = getUpload(db, personId, v.monthKey);
  // Top-level `force` (not nested under context) is the CLI's explicit override
  // — the same shape mirdash's schema whitelists.
  if (existing && body.force !== true && degrades(body, existing.summary)) {
    // Answer 200 with the report URL anyway, exactly as mirdash does.
    return { reportUrl, stored: false };
  }

  upsertUpload(db, {
    personId,
    monthKey: v.monthKey,
    windowMonths: v.windowMonths,
    summaryJson: rawJson ?? JSON.stringify(body),
  });
  return { reportUrl, stored: true };
}
