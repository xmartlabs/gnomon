import { describe, it, expect, beforeEach, vi } from "vitest";
import Anthropic from "@anthropic-ai/sdk";
import { coachEnabled, getCoachText } from "@/lib/coach";
import { buildPersonProfile } from "@/lib/metrics";
import { upsertPerson } from "@/lib/db";
import { makeSummary } from "./fixtures/summary";
import { freshDb, putUpload, type TestDb } from "./helpers/env";

/** Stand in for one Messages API call without going near the network. */
function mockCreate(impl: () => unknown) {
  return vi
    .spyOn(Anthropic.Messages.prototype, "create")
    .mockImplementation(impl as never);
}

const textReply = (text: string) => ({ content: [{ type: "text", text }] });

describe("coach", () => {
  let db: TestDb;
  let prof: NonNullable<ReturnType<typeof buildPersonProfile>>;

  beforeEach(() => {
    vi.restoreAllMocks();
    db = freshDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    putUpload(db, p.id, "2026-06", makeSummary());
    prof = buildPersonProfile(db, p.id, "2026-06")!;
    process.env.LLM_API_KEY = "sk-test";
    delete process.env.LLM_MODEL;
  });

  it("is disabled without LLM_API_KEY, and never calls the API", async () => {
    delete process.env.LLM_API_KEY;
    const create = mockCreate(() => textReply("should not happen"));

    expect(coachEnabled()).toBe(false);
    expect(await getCoachText(db, prof)).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });

  it("calls the API once, then serves every later view from cache", async () => {
    const create = mockCreate(() => textReply("Focus on Breadth."));

    expect(await getCoachText(db, prof)).toBe("Focus on Breadth.");
    expect(await getCoachText(db, prof)).toBe("Focus on Breadth.");
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("prompts with the numbers the advice is supposed to cite", async () => {
    const create = mockCreate(() => textReply("ok"));
    await getCoachText(db, prof);

    const prompt = (create.mock.calls[0][0] as { messages: { content: string }[] }).messages[0].content;
    expect(prompt).toContain("AQ: 93/100 (Elite)");
    expect(prompt).toContain("Breadth 27/30");
    expect(prompt).toContain("planning 10.0/10");
  });

  it("re-uploading the month drops the cached advice", async () => {
    // db.upsertUpload evicts coach:<person>:<month> inside the upload
    // transaction, so stale advice can never outlive the numbers it describes.
    const create = mockCreate(() => textReply("first take"));
    await getCoachText(db, prof);

    putUpload(db, prof.personId, "2026-06", makeSummary({ context: { total_sessions: 999 } }));
    create.mockImplementation((() => textReply("second take")) as never);

    expect(await getCoachText(db, prof)).toBe("second take");
    expect(create).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["an auth failure", new Anthropic.AuthenticationError(401, {}, "bad key", new Headers())],
    ["a rate limit", new Anthropic.RateLimitError(429, {}, "slow down", new Headers())],
    ["an unknown model", new Anthropic.NotFoundError(404, {}, "no such model", new Headers())],
    ["an unexpected error", new Error("boom")],
  ])("returns null on %s rather than throwing into the page", async (_label, error) => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
    mockCreate(() => {
      throw error;
    });

    await expect(getCoachText(db, prof)).resolves.toBeNull();
  });

  it("returns null when the reply carries no text block, and caches nothing", async () => {
    // e.g. a refusal: HTTP 200, no text content.
    const create = mockCreate(() => ({ content: [] }));

    expect(await getCoachText(db, prof)).toBeNull();
    expect(await getCoachText(db, prof)).toBeNull();
    expect(create).toHaveBeenCalledTimes(2); // not cached, so it retries later
  });

  it("honours an LLM_MODEL override", async () => {
    process.env.LLM_MODEL = "claude-opus-5";
    const create = mockCreate(() => textReply("ok"));
    await getCoachText(db, prof);

    expect((create.mock.calls[0][0] as { model: string }).model).toBe("claude-opus-5");
  });
});
