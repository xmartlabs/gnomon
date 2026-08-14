import { describe, it, expect, beforeEach } from "vitest";
import { POST } from "@/app/api/cli-auth/route";
import { _resetRateLimitForTests } from "@/lib/rate-limit";
import { verifyToken } from "@/lib/auth";
import { getDb, upsertPerson } from "@/lib/db";
import { useTempDbEnv, putUpload, TEST_TEAM_TOKEN } from "./helpers/env";
import { makeSummary } from "./fixtures/summary";
import { postForm } from "./helpers/request";

const CB = "http://127.0.0.1:8799/callback";
const ok = {
  team_token: TEST_TEAM_TOKEN,
  name: "Ada",
  email: "ada@example.com",
  redirect_uri: CB,
  count: "1",
};

const post = (fields: Record<string, string>) =>
  POST(postForm("http://test/api/cli-auth", fields));

/** The callback URL the CLI's loopback server would receive. */
const callbackOf = (res: Response) => new URL(res.headers.get("location")!);

describe("POST /api/cli-auth", () => {
  beforeEach(() => {
    useTempDbEnv();
    _resetRateLimitForTests();
  });

  it("redirects to callback with N valid tokens and uploaded months", async () => {
    const db = getDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    putUpload(db, p.id, "2026-05", {});

    const res = await post({ ...ok, count: "3" });
    expect(res.status).toBe(302);
    const loc = callbackOf(res);
    expect(loc.origin + loc.pathname).toBe(CB);
    const tokens = JSON.parse(loc.searchParams.get("tokens")!);
    expect(tokens).toHaveLength(3);
    expect((await verifyToken(tokens[0]))?.email).toBe("ada@example.com");
    const uploaded = JSON.parse(loc.searchParams.get("uploaded")!);
    expect(uploaded[0].monthKey).toBe("2026-05");
    expect(typeof uploaded[0].uploadedAt).toBe("number");
  });

  it("emits uploaded_history with the planner metadata", async () => {
    // gnomon/upload/mirdash.py:_history_from_query treats a missing
    // uploaded_history as "legacy" and falls back to the older upload planner;
    // a missing scoreContractId makes plan_upload re-upload every run.
    const db = getDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    putUpload(db, p.id, "2026-05", makeSummary());

    const history = JSON.parse(callbackOf(await post(ok)).searchParams.get("uploaded_history")!);
    expect(history.outcome).toBe("valid");
    expect(history.months).toEqual([
      {
        monthKey: "2026-05",
        uploadedAt: expect.any(Number),
        scoreContractId: "aq-v11",
        coverage: { flag: "complete", indexed: 171, transcripts: 171 },
        totalSessions: 171,
      },
    ]);
  });

  it("sends an empty uploaded list for a first-time person", async () => {
    const loc = callbackOf(await post(ok));
    expect(JSON.parse(loc.searchParams.get("uploaded")!)).toEqual([]);
    expect(JSON.parse(loc.searchParams.get("uploaded_history")!).months).toEqual([]);
  });

  it("rejects wrong team token with redirect back to form", async () => {
    const res = await post({ ...ok, team_token: "wrong" });
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toContain("/cli-auth?");
    expect(res.headers.get("location")).toContain("error=");
  });

  it("rejects non-loopback redirect_uri with 400", async () => {
    expect((await post({ ...ok, redirect_uri: "https://evil.com/cb" })).status).toBe(400);
  });

  it("rejects missing name/email with redirect back to form", async () => {
    expect((await post({ ...ok, name: "", email: "" })).status).toBe(303);
  });

  it("preserves redirect_uri and count when bouncing back to the form", async () => {
    const loc = callbackOf(await post({ ...ok, team_token: "wrong", count: "6" }));
    expect(loc.searchParams.get("redirect_uri")).toBe(CB);
    expect(loc.searchParams.get("count")).toBe("6");
  });

  it.each([
    ["not-a-number", 1],
    ["-3", 1],
    ["999", 12],
  ])("coerces count=%j to %i tokens", async (count, expected) => {
    const loc = callbackOf(await post({ ...ok, count }));
    expect(JSON.parse(loc.searchParams.get("tokens")!)).toHaveLength(expected);
  });

  it("cannot be un-throttled by rotating x-forwarded-for", async () => {
    // The header is client-supplied; honoring it by default would hand an
    // attacker a fresh bucket per request against the shared TEAM_TOKEN.
    const spoof = (i: number) =>
      POST(
        new Request("http://test/api/cli-auth", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-forwarded-for": `10.0.0.${i}`,
          },
          body: new URLSearchParams({ ...ok, team_token: "wrong" }).toString(),
        })
      );
    let last!: Response;
    for (let i = 1; i <= 6; i++) last = await spoof(i);
    expect(last.status).toBe(429);
  });

  it("throttles repeated wrong team tokens with 429", async () => {
    let last!: Response;
    for (let i = 0; i < 6; i++) last = await post({ ...ok, team_token: "wrong" });
    expect(last.status).toBe(429);
  });

  it("clears the throttle counter after a successful sign-in", async () => {
    for (let i = 0; i < 4; i++) await post({ ...ok, team_token: "wrong" });
    expect((await post(ok)).status).toBe(302);
    for (let i = 0; i < 4; i++) await post({ ...ok, team_token: "wrong" });
    expect((await post(ok)).status).toBe(302);
  });
});
