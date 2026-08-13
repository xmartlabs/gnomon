import { NextResponse } from "next/server";
import { checkTeamToken, issueTokens, isLoopbackRedirect } from "@/lib/auth";
import { getDb, upsertPerson, uploadedMonths } from "@/lib/db";
import { uploadHistory } from "@/lib/history";

// In-memory failed-attempt throttle for the shared TEAM_TOKEN endpoint. Single
// container, so a module-scope map is sufficient; keyed by client IP.
const MAX_FAILS = 5;
const WINDOW_MS = 60_000;
// x-forwarded-for is client-supplied, so the key space is attacker-widenable —
// hard-cap the map rather than let it grow for the container's lifetime.
const MAX_TRACKED_IPS = 10_000;
const fails = new Map<string, { n: number; first: number }>();

/**
 * x-forwarded-for is client-supplied. Honoring it unconditionally lets an
 * attacker mint a fresh throttle bucket per request and brute-force the shared
 * TEAM_TOKEN unthrottled, so it counts only when the operator declares a proxy
 * in front (TRUST_PROXY=1). Direct deployments — the documented default — share
 * one bucket: a wrong-token flood can lock sign-in for 60s, which is the
 * cheaper failure than an unlimited guessing channel.
 */
function clientIp(req: Request): string {
  if (process.env.TRUST_PROXY !== "1") return "direct";
  const xff = req.headers.get("x-forwarded-for") ?? "";
  return xff.split(",")[0].trim() || req.headers.get("x-real-ip") || "unknown";
}

/** The live (non-expired) failure record for this IP, if any. */
function activeFails(ip: string, now: number) {
  const rec = fails.get(ip);
  return rec && now - rec.first <= WINDOW_MS ? rec : undefined;
}

function recordFail(ip: string, now: number): void {
  const rec = activeFails(ip, now);
  if (rec) {
    rec.n += 1;
    return;
  }
  if (fails.size >= MAX_TRACKED_IPS) {
    for (const [key, r] of fails) if (now - r.first > WINDOW_MS) fails.delete(key);
    // Still full means the whole window is live traffic: evict the oldest key
    // (Map iterates in insertion order) so the bound holds regardless.
    if (fails.size >= MAX_TRACKED_IPS) fails.delete(fails.keys().next().value!);
  }
  fails.set(ip, { n: 1, first: now });
}

export function _resetRateLimitForTests(): void {
  fails.clear();
}

export async function POST(req: Request): Promise<Response> {
  const ip = clientIp(req);
  const now = Date.now();

  // Shed throttled callers before reading or parsing the body — that traffic is
  // exactly what the throttle exists to stop paying for.
  if ((activeFails(ip, now)?.n ?? 0) >= MAX_FAILS) {
    // Never log the submitted token — only the outcome and source.
    console.warn(`[cli-auth] rate-limited failed auth from ${ip}`);
    return NextResponse.json({ error: "too many attempts, try again later" }, { status: 429 });
  }

  const form = new URLSearchParams(await req.text());
  const teamToken = form.get("team_token") ?? "";
  const name = (form.get("name") ?? "").trim();
  // Case is normalized by upsertPerson, which owns person identity.
  const email = (form.get("email") ?? "").trim();
  const redirectUri = form.get("redirect_uri") ?? "";
  // Coerce the request field here; the hard [1,12] cap stays in issueTokens.
  const requested = Number(form.get("count"));
  const count = Number.isFinite(requested) ? Math.trunc(requested) : 1;

  if (!isLoopbackRedirect(redirectUri)) {
    // Backstop only — the page refuses to render a form for a bad redirect_uri,
    // so a human never reaches this.
    return NextResponse.json(
      { error: "redirect_uri must be a http://127.0.0.1 or http://localhost URL" },
      { status: 400 }
    );
  }

  const backToForm = (error: string) => {
    const back = new URL("/cli-auth", req.url);
    back.searchParams.set("error", error);
    back.searchParams.set("redirect_uri", redirectUri);
    back.searchParams.set("count", String(count));
    return NextResponse.redirect(back, 303);
  };

  if (!checkTeamToken(teamToken)) {
    recordFail(ip, now);
    console.warn(`[cli-auth] invalid team token from ${ip}`);
    return backToForm("Invalid team token");
  }
  if (!name || !/.+@.+\..+/.test(email)) return backToForm("Name and a valid email are required");
  fails.delete(ip); // success clears the counter

  const db = getDb();
  const person = upsertPerson(db, email, name);
  const tokens = await issueTokens(person, count);

  const dest = new URL(redirectUri);
  dest.searchParams.set("tokens", JSON.stringify(tokens));
  // `uploaded` is the legacy alias; `uploaded_history` is the current contract
  // generation the CLI prefers (gnomon/upload/mirdash.py:_history_from_query).
  // Emitting only the alias makes the CLI fall back to its pre-contract planner.
  dest.searchParams.set("uploaded", JSON.stringify(uploadedMonths(db, person.id)));
  dest.searchParams.set(
    "uploaded_history",
    JSON.stringify({ outcome: "valid", months: uploadHistory(db, person.id) })
  );
  return NextResponse.redirect(dest, 302);
}
