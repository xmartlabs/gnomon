import { SignJWT, jwtVerify } from "jose";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { dataDir } from "@/lib/paths";

const MAX_TOKENS = 12; // mirror _MAX_BACKFILL in gnomon/upload/mirdash.py

export function checkTeamToken(input: string): boolean {
  const expected = process.env.TEAM_TOKEN ?? "";
  if (!expected || !input) return false;
  // Hash both to fixed-length digests so the compare is constant-time
  // regardless of input length (no early length-based return leak).
  const a = crypto.createHash("sha256").update(input).digest();
  const b = crypto.createHash("sha256").update(expected).digest();
  return crypto.timingSafeEqual(a, b);
}

let _key: crypto.KeyObject | null = null;

/** Test-only: drop the memoized key after mutating JWT_SECRET or DATA_DIR. */
export function _resetSecretForTests(): void {
  _key = null;
}

// Generated once and kept on the data volume, so tokens issued before a restart
// still verify after it.
function persistedSecret(): string {
  const file = path.join(dataDir(), "jwt-secret");
  if (!fs.existsSync(file)) {
    try {
      fs.writeFileSync(file, crypto.randomBytes(32).toString("hex"), { mode: 0o600, flag: "wx" });
    } catch {
      // A concurrent boot created it first — adopt theirs rather than overwrite,
      // else tokens it already issued would stop verifying.
    }
  }
  return fs.readFileSync(file, "utf-8").trim();
}

// Imported once as a KeyObject: passing raw bytes makes jose re-run
// crypto.subtle.importKey on every sign and verify.
function jwtKey(): crypto.KeyObject {
  if (!_key) {
    _key = crypto.createSecretKey(Buffer.from(process.env.JWT_SECRET ?? persistedSecret(), "utf8"));
  }
  return _key;
}

export async function issueTokens(
  person: { id: number; email: string; name: string },
  count: number
): Promise<string[]> {
  const n = Number.isFinite(count) ? Math.min(MAX_TOKENS, Math.max(1, Math.floor(count))) : 1;
  const key = jwtKey();
  // The CLI zips these against its planned month windows (one credential per
  // upload), so each gets its own jti — without it all n are the same byte
  // string, since the claims and second-resolution iat/exp are identical.
  return Promise.all(
    Array.from({ length: n }, () =>
      new SignJWT({ email: person.email, name: person.name })
        .setProtectedHeader({ alg: "HS256" })
        .setSubject(String(person.id))
        .setJti(crypto.randomUUID())
        .setIssuedAt()
        .setExpirationTime("2h")
        .sign(key)
    )
  );
}

export async function verifyToken(
  token: string
): Promise<{ personId: number; email: string; name: string } | null> {
  try {
    // Pin the accepted algorithm to HS256 — without this, jose accepts any
    // alg the token header declares, defeating the HS256 contract.
    const { payload } = await jwtVerify(token, jwtKey(), { algorithms: ["HS256"] });
    if (typeof payload.email !== "string") return null;
    // Number("") and Number(" 1 ") are permissive, so require a bare run of
    // digits before converting.
    if (typeof payload.sub !== "string" || !/^\d+$/.test(payload.sub)) return null;
    const personId = Number(payload.sub);
    if (personId <= 0 || !Number.isSafeInteger(personId)) return null;
    return {
      personId,
      email: payload.email,
      name: typeof payload.name === "string" ? payload.name : "",
    };
  } catch {
    return null;
  }
}

export function isLoopbackRedirect(uri: string): boolean {
  const u = URL.parse(uri);
  // Require an explicit port so a bare `http://localhost/callback` (which the
  // CLI never sends) is rejected — narrows the redirect surface.
  return (
    u !== null &&
    u.protocol === "http:" &&
    (u.hostname === "127.0.0.1" || u.hostname === "localhost") &&
    u.port !== ""
  );
}
