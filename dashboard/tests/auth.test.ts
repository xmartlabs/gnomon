import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { SignJWT } from "jose";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  checkTeamToken,
  issueTokens,
  verifyToken,
  isLoopbackRedirect,
  _resetSecretForTests,
} from "@/lib/auth";
import { TEST_JWT_SECRET as JWT_SECRET } from "./helpers/env";

const SECRET = new TextEncoder().encode(JWT_SECRET);

/** Mint a token, varying only the field under test. */
const mint = (o: { alg?: string; sub?: string; exp?: string | number; secret?: Uint8Array } = {}) =>
  new SignJWT({ email: "a@b.c", name: "A" })
    .setProtectedHeader({ alg: o.alg ?? "HS256" })
    .setSubject(o.sub ?? "1")
    .setExpirationTime(o.exp ?? "2h")
    .sign(o.secret ?? SECRET);

describe("auth", () => {
  beforeEach(() => {
    process.env.TEAM_TOKEN = "sekret-team";
    process.env.JWT_SECRET = JWT_SECRET;
    _resetSecretForTests();
  });

  it("checkTeamToken matches exact token only", () => {
    expect(checkTeamToken("sekret-team")).toBe(true);
    expect(checkTeamToken("wrong")).toBe(false);
    expect(checkTeamToken("")).toBe(false);
  });

  it("checkTeamToken false when TEAM_TOKEN unset", () => {
    delete process.env.TEAM_TOKEN;
    expect(checkTeamToken("anything")).toBe(false);
  });

  it("issueTokens returns count tokens that verify back to the person", async () => {
    const tokens = await issueTokens({ id: 7, email: "ada@example.com", name: "Ada" }, 3);
    expect(tokens).toHaveLength(3);
    const claims = await verifyToken(tokens[0]);
    expect(claims).toEqual({ personId: 7, email: "ada@example.com", name: "Ada" });
  });

  it("issueTokens mints distinct credentials, one per planned upload", async () => {
    const tokens = await issueTokens({ id: 7, email: "ada@example.com", name: "Ada" }, 3);
    expect(new Set(tokens).size).toBe(3);
    for (const t of tokens) expect(await verifyToken(t)).not.toBeNull();
  });

  it("issueTokens clamps count to [1,12]", async () => {
    expect(await issueTokens({ id: 1, email: "a@b.c", name: "A" }, 0)).toHaveLength(1);
    expect(await issueTokens({ id: 1, email: "a@b.c", name: "A" }, 99)).toHaveLength(12);
  });

  it("verifyToken rejects garbage and wrong-secret tokens", async () => {
    expect(await verifyToken("not-a-jwt")).toBeNull();
    const wrong = await mint({ secret: new TextEncoder().encode("some-other-secret-at-least-32-byte!") });
    expect(await verifyToken(wrong)).toBeNull();
  });

  it.each(["HS384", "HS512"])("verifyToken rejects the %s algorithm", async (alg) => {
    expect(await verifyToken(await mint({ alg }))).toBeNull();
  });

  it.each(["0", "-3", "abc", "1.5"])("verifyToken rejects subject %j", async (sub) => {
    expect(await verifyToken(await mint({ sub }))).toBeNull();
  });

  it("verifyToken rejects expired tokens", async () => {
    expect(await verifyToken(await mint({ exp: Math.floor(Date.now() / 1000) - 60 }))).toBeNull();
  });

  it("isLoopbackRedirect only allows loopback http with explicit port", () => {
    expect(isLoopbackRedirect("http://127.0.0.1:8799/callback")).toBe(true);
    expect(isLoopbackRedirect("http://localhost:8799/callback")).toBe(true);
    expect(isLoopbackRedirect("http://localhost/callback")).toBe(false); // no port
    expect(isLoopbackRedirect("https://evil.com/callback")).toBe(false);
    expect(isLoopbackRedirect("http://127.0.0.1.evil.com/cb")).toBe(false);
    expect(isLoopbackRedirect("not a url")).toBe(false);
  });
});

describe("auth without JWT_SECRET", () => {
  let dir: string;

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "gnomon-auth-"));
    process.env.DATA_DIR = dir;
    delete process.env.JWT_SECRET;
    _resetSecretForTests();
  });

  afterEach(() => {
    delete process.env.DATA_DIR;
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("generates a secret on the data volume and reuses it across restarts", async () => {
    const [token] = await issueTokens({ id: 3, email: "a@b.c", name: "A" }, 1);
    const secretFile = path.join(dir, "jwt-secret");
    expect(fs.existsSync(secretFile)).toBe(true);

    // Simulate a process restart: the memo is gone, the file is not.
    _resetSecretForTests();
    expect(await verifyToken(token)).toEqual({ personId: 3, email: "a@b.c", name: "A" });
  });
});
