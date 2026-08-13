import { describe, it, expect, beforeEach } from "vitest";
import { POST } from "@/app/api/gnomon/ingest/route";
import { issueTokens } from "@/lib/auth";
import { getDb, upsertPerson, uploadsForPerson } from "@/lib/db";
import { makeSummary } from "./fixtures/summary";
import { useTempDbEnv } from "./helpers/env";
import { postJson } from "./helpers/request";

const URL_ = "http://test/api/gnomon/ingest";
const req = (body: unknown, token?: string) => postJson(URL_, body, token);

/** A person with a fresh upload token — the state every non-401 case needs. */
async function authed() {
  const person = upsertPerson(getDb(), "ada@example.com", "Ada");
  const [token] = await issueTokens(person, 1);
  return { person, token };
}

describe("POST /api/gnomon/ingest", () => {
  beforeEach(useTempDbEnv);

  it("401 without token", async () => {
    expect((await POST(req(makeSummary()))).status).toBe(401);
  });

  it("401 with a malformed token", async () => {
    expect((await POST(req(makeSummary(), "garbage"))).status).toBe(401);
  });

  it("400 on invalid summary", async () => {
    const { token } = await authed();
    const res = await POST(req({ nope: true }, token));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toMatch(/context/);
  });

  it("400 on a body that is not valid JSON", async () => {
    const { token } = await authed();
    expect((await POST(req("{not json", token))).status).toBe(400);
  });

  it("200 with reportUrl on success", async () => {
    const { person, token } = await authed();
    const res = await POST(req(makeSummary(), token));
    expect(res.status).toBe(200);
    expect((await res.json()).reportUrl).toBe(`/p/${person.id}/2026-06`);
  });

  it("stores the raw request bytes verbatim", async () => {
    const { person, token } = await authed();
    const raw = JSON.stringify({ ...makeSummary(), _unknown_future_field: 42 });
    await POST(req(raw, token));
    const [stored] = uploadsForPerson(getDb(), person.id);
    expect(stored.summary._unknown_future_field).toBe(42);
  });

  it("413 when body exceeds the size cap", async () => {
    process.env.MAX_INGEST_BYTES = "1024";
    const { token } = await authed();
    const big = makeSummary({ context: { client_version: "x".repeat(4096) } });
    expect((await POST(req(big, token))).status).toBe(413);
    delete process.env.MAX_INGEST_BYTES;
  });
});
