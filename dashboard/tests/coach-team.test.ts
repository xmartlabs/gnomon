import { describe, it, expect, beforeEach, vi } from "vitest";
import Anthropic from "@anthropic-ai/sdk";
import { coachEnabled, getTeamInsight, type TeamInsightInput } from "@/lib/coach";
import { buildTeamOverview } from "@/lib/metrics";
import { upsertPerson } from "@/lib/db";
import { makeSummary } from "./fixtures/summary";
import { freshDb, putUpload, type TestDb } from "./helpers/env";

/** Stand in for one Messages API call without going near the network. */
function mockCreate(impl: () => unknown) {
  return vi
    .spyOn(Anthropic.Messages.prototype, "create")
    .mockImplementation(impl as never);
}

const toolReply = (name: string, input: unknown) => ({
  content: [{ type: "tool_use", name, input }],
});

const INSIGHT_INPUT = {
  headline: "Breadth is the team's weakest pillar.",
  body: "Only 2 of 6 people orchestrate subagents.",
  impact_estimate: "+5 AQ",
  secondary_headline: "4 profiles run long sessions with no checkpoints.",
  secondary_detail: "Lowers Efficiency without lowering work volume.",
};

function inputFor(db: TestDb, monthKey: string): TeamInsightInput {
  const o = buildTeamOverview(db, monthKey);
  return { monthKey, pillarAverages: o.pillarAverages, coverage: o.coverage, avgAqDelta: o.avgAqDelta };
}

describe("coach-team", () => {
  let db: TestDb;
  let input: TeamInsightInput;

  beforeEach(() => {
    vi.restoreAllMocks();
    db = freshDb();
    const p = upsertPerson(db, "ada@example.com", "Ada");
    putUpload(db, p.id, "2026-06", makeSummary());
    input = inputFor(db, "2026-06");
    process.env.LLM_API_KEY = "sk-test";
    delete process.env.LLM_MODEL;
  });

  it("is disabled without LLM_API_KEY, and never calls the API", async () => {
    delete process.env.LLM_API_KEY;
    const create = mockCreate(() => toolReply("team_insight", INSIGHT_INPUT));

    expect(coachEnabled()).toBe(false);
    expect(await getTeamInsight(db, input)).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });

  it("calls the API once, then serves every later view from cache", async () => {
    const create = mockCreate(() => toolReply("team_insight", INSIGHT_INPUT));

    const first = await getTeamInsight(db, input);
    const second = await getTeamInsight(db, input);
    expect(first).toEqual({
      headline: INSIGHT_INPUT.headline,
      body: INSIGHT_INPUT.body,
      impactEstimate: INSIGHT_INPUT.impact_estimate,
      secondary: { headline: INSIGHT_INPUT.secondary_headline, detail: INSIGHT_INPUT.secondary_detail },
    });
    expect(second).toEqual(first);
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("caches under coach-team:, never colliding with the per-person coach: prefix", async () => {
    mockCreate(() => toolReply("team_insight", INSIGHT_INPUT));
    await getTeamInsight(db, input);

    const row = db
      .prepare(`SELECT key FROM settings WHERE key LIKE 'coach-team:%'`)
      .get() as { key: string } | undefined;
    expect(row?.key.startsWith("coach-team:2026-06:")).toBe(true);
    expect(db.prepare(`SELECT 1 FROM settings WHERE key LIKE 'coach:%'`).get()).toBeUndefined();
  });

  it("a re-upload by ANY person for that month evicts and regenerates the team insight", async () => {
    const create = mockCreate(() => toolReply("team_insight", INSIGHT_INPUT));
    await getTeamInsight(db, input);

    const alan = upsertPerson(db, "alan@example.com", "Alan");
    putUpload(db, alan.id, "2026-06", makeSummary({ profile: { aq: { aq_0_100: 60, tier: "Proficient" } } }));
    create.mockImplementation((() =>
      toolReply("team_insight", { ...INSIGHT_INPUT, headline: "Craft is now the weakest pillar." })) as never);

    const after = inputFor(db, "2026-06");
    const second = await getTeamInsight(db, after);
    expect(second?.headline).toBe("Craft is now the weakest pillar.");
    expect(create).toHaveBeenCalledTimes(2);
  });

  it("leaves a different month's cached insight untouched", async () => {
    mockCreate(() => toolReply("team_insight", INSIGHT_INPUT));
    await getTeamInsight(db, input);

    const p = upsertPerson(db, "grace@example.com", "Grace");
    putUpload(db, p.id, "2026-05", makeSummary());

    expect(db.prepare(`SELECT 1 FROM settings WHERE key LIKE 'coach-team:2026-06:%'`).get()).toBeDefined();
  });

  it("advice generated before a re-upload is never served after it", async () => {
    const create = mockCreate(() => {
      const alan = upsertPerson(db, "alan@example.com", "Alan");
      putUpload(db, alan.id, "2026-06", makeSummary()); // ingest mid-flight
      return toolReply("team_insight", { ...INSIGHT_INPUT, headline: "advice about the OLD numbers" });
    });

    expect((await getTeamInsight(db, input))?.headline).toBe("advice about the OLD numbers");

    create.mockImplementation((() =>
      toolReply("team_insight", { ...INSIGHT_INPUT, headline: "advice about the NEW numbers" })) as never);
    const after = inputFor(db, "2026-06");
    expect((await getTeamInsight(db, after))?.headline).toBe("advice about the NEW numbers");
  });

  it("returns null on a missing or malformed tool_use block, and caches nothing", async () => {
    const create = mockCreate(() => ({ content: [] }));
    expect(await getTeamInsight(db, input)).toBeNull();

    create.mockImplementation((() => toolReply("team_insight", { headline: "only a headline" })) as never);
    expect(await getTeamInsight(db, input)).toBeNull();
    expect(create).toHaveBeenCalledTimes(2); // neither cached, so both retried
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

    await expect(getTeamInsight(db, input)).resolves.toBeNull();
  });

  it("honours an LLM_MODEL override", async () => {
    process.env.LLM_MODEL = "claude-opus-5";
    const create = mockCreate(() => toolReply("team_insight", INSIGHT_INPUT));
    await getTeamInsight(db, input);

    expect((create.mock.calls[0][0] as { model: string }).model).toBe("claude-opus-5");
  });
});
