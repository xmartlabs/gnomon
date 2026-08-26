// In-memory failed-attempt throttle for the shared TEAM_TOKEN endpoint. Single
// container, so a module-scope map is sufficient; keyed by client IP.
//
// This lives in lib/ rather than beside the route because a Next.js route
// module may only export route handlers — the webpack build rejects
// `_resetRateLimitForTests` as "not a valid Route export field" (Turbopack does
// not check, which is why it went unnoticed).

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
export function clientIp(req: Request): string {
  if (process.env.TRUST_PROXY !== "1") return "direct";
  const xff = req.headers.get("x-forwarded-for") ?? "";
  return xff.split(",")[0].trim() || req.headers.get("x-real-ip") || "unknown";
}

/** The live (non-expired) failure record for this IP, if any. */
function activeFails(ip: string, now: number) {
  const rec = fails.get(ip);
  return rec && now - rec.first <= WINDOW_MS ? rec : undefined;
}

export function isRateLimited(ip: string, now: number): boolean {
  return (activeFails(ip, now)?.n ?? 0) >= MAX_FAILS;
}

export function recordFail(ip: string, now: number): void {
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

/** A successful sign-in clears the caller's counter. */
export function clearFails(ip: string): void {
  fails.delete(ip);
}

export function _resetRateLimitForTests(): void {
  fails.clear();
}
