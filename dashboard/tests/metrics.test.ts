import { describe, it, expect, beforeEach } from "vitest";
import { upsertPerson } from "@/lib/db";
import {
  monthEntry, monthTokensByModel, monthlyUsage,
  buildTeamOverview, buildPersonProfile,
  teamPillarAverages, tierDistribution, teamModelMix,
} from "@/lib/metrics";
import { fmtTokens, fmtUsd, fmtDelta } from "@/lib/format";
import { costUsd } from "@/lib/pricing";
import { makeSummary, TOTAL_TOKENS } from "./fixtures/summary";
import { freshDb, putUpload as put, type TestDb } from "./helpers/env";

function seed(db: TestDb) {
  const p = upsertPerson(db, "ada@example.com", "Ada");
  const may = makeSummary({
    context: { date_range: ["2025-12-01", "2026-05-31"] },
    profile: { aq: { aq_0_100: 79, tier: "Advanced" } },
  });
  put(db, p.id, "2026-05", may);
  put(db, p.id, "2026-06", makeSummary()); // 2026-06, aq 93
  return p;
}

describe("metrics", () => {
  let db: TestDb;
  beforeEach(() => {
    db = freshDb();
  });

  it("monthEntry finds the progression entry for the anchor month", () => {
    expect(monthEntry(makeSummary(), "2026-06")?.sessions).toBe(157);
    expect(monthEntry(makeSummary(), "2019-01")).toBeNull();
  });

  it("monthTokensByModel reads exact per-model tokens from noticed_stats_monthly", () => {
    const split = monthTokensByModel(makeSummary(), "2026-06");
    const total = split.reduce((s, m) => s + m.tokens, 0);
    expect(total).toBe(TOTAL_TOKENS); // exact, not approximated
    expect(split[0].tokens).toBeGreaterThan(split[1].tokens); // opus > fable
    expect(split[0].cost).toBeGreaterThan(0);
  });

  it("monthTokensByModel falls back to invocation-share when noticed block absent", () => {
    const legacy = makeSummary();
    delete legacy.noticed_stats_monthly; // simulate an older summary
    const split = monthTokensByModel(legacy, "2026-06");
    // The rounded shares must still sum to tokens_total exactly.
    expect(split.reduce((s, m) => s + m.tokens, 0)).toBe(TOTAL_TOKENS);
    expect(split[0].tokens).toBeGreaterThan(split[1].tokens);
    // Legacy blocks carry raw ids; the label comes from the summary's own
    // model_usage so legends don't print "claude-opus-4-8".
    expect(split[0].model).toBe("Opus 4.8");
  });

  it("fallback never emits negative tokens from a malformed count", () => {
    const legacy = makeSummary({
      progression_monthly: [
        { month: "2026-06", tokens_total: 100, tokens_input: 100,
          models: [["claude-opus-4-8", -1], ["claude-sonnet-4", 2]] },
      ],
    });
    delete legacy.noticed_stats_monthly;
    const split = monthTokensByModel(legacy, "2026-06");
    expect(split.every((m) => m.tokens >= 0 && m.cost >= 0)).toBe(true);
    expect(split.reduce((s, m) => s + m.tokens, 0)).toBe(100);
  });

  it("personRow computes aq, delta vs previous month, trend, tokens", () => {
    seed(db);
    const row = buildTeamOverview(db).people[0];
    expect(row.aq).toBe(93);
    expect(row.delta).toBe(14);
    expect(row.trend.map((t) => t.aq)).toEqual([79, 93]);
    expect(row.tokens).toBe(TOTAL_TOKENS);
  });

  it("buildTeamOverview aggregates avg, coverage, usage over time", () => {
    seed(db);
    const o = buildTeamOverview(db);
    expect(o.avgAq).toBe(93);
    expect(o.coverage).toEqual({ withCurrentMonth: 1, total: 1 });
    expect(o.usageOverTime.map((u) => u.monthKey)).toEqual(["2026-05", "2026-06"]);
  });

  it("usageOverTime keeps months only an OLDER window covered (no truncation)", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    // Older upload's window uniquely covers 2026-01; newer upload's window does not.
    const jan = makeSummary({
      context: { date_range: ["2025-08-01", "2026-01-31"] },
      noticed_stats_monthly: [
        { month: "2026-01", token_usage: { by_model: [
          { model_id: "claude-opus-4-8", input: 1e6, output: 1e6, cache_read: 0, cache_creation: 0 } ] } },
      ],
      progression_monthly: [{ month: "2026-01", models: [["claude-opus-4-8", 100]], tokens_total: 2e6 }],
    });
    put(db, p.id, "2026-01", jan);
    put(db, p.id, "2026-06", makeSummary());
    expect(buildTeamOverview(db).usageOverTime.map((u) => u.monthKey)).toContain("2026-01");
  });

  it("usageOverTime counts each person-month once across overlapping windows", () => {
    // Two uploads whose windows both cover 2026-06 must not double-count it.
    const p = upsertPerson(db, "ada@example.com", "Ada");
    put(db, p.id, "2026-05", makeSummary());
    put(db, p.id, "2026-06", makeSummary());
    const jun = buildTeamOverview(db).usageOverTime.find((u) => u.monthKey === "2026-06")!;
    const tokens = jun.byModel.reduce((s, m) => s + m.tokens, 0);
    expect(tokens).toBe(TOTAL_TOKENS); // single window's total, not doubled
  });

  it("aggregates usage across people rather than overwriting", () => {
    const ada = upsertPerson(db, "ada@example.com", "Ada");
    const alan = upsertPerson(db, "alan@example.com", "Alan");
    put(db, ada.id, "2026-06", makeSummary());
    put(db, alan.id, "2026-06", makeSummary());
    const jun = buildTeamOverview(db).usageOverTime.find((u) => u.monthKey === "2026-06")!;
    expect(jun.byModel.reduce((s, m) => s + m.tokens, 0)).toBe(2 * TOTAL_TOKENS);
  });

  it("reports coverage against the newest month anyone uploaded", () => {
    const ada = upsertPerson(db, "ada@example.com", "Ada");
    const alan = upsertPerson(db, "alan@example.com", "Alan");
    put(db, ada.id, "2026-06", makeSummary());
    put(db, alan.id, "2026-05", makeSummary()); // stale — never uploaded June
    const o = buildTeamOverview(db);
    expect(o.coverage).toEqual({ withCurrentMonth: 1, total: 2 });
    expect(o.tokensCurrentMonth).toBe(TOTAL_TOKENS); // stale person excluded
  });

  it("counts a person with no uploads in the coverage denominator only", () => {
    const ada = upsertPerson(db, "ada@example.com", "Ada");
    upsertPerson(db, "ghost@example.com", "Ghost");
    put(db, ada.id, "2026-06", makeSummary());
    const o = buildTeamOverview(db);
    expect(o.people).toHaveLength(1);
    expect(o.coverage).toEqual({ withCurrentMonth: 1, total: 2 });
  });

  it("returns an empty overview for an empty database", () => {
    expect(buildTeamOverview(db)).toEqual({
      people: [], avgAq: null, avgAqDelta: null, currentMonth: null,
      coverage: { withCurrentMonth: 0, total: 0 },
      tokensCurrentMonth: 0, costCurrentMonth: 0, tokensDelta: null, costDelta: null, usageOverTime: [],
      availableMonths: [], pillarAverages: [], modelMix: [], teamAqTrend: [],
      tierDistribution: [
        { tier: "Elite", count: 0 }, { tier: "Advanced", count: 0 },
        { tier: "Proficient", count: 0 }, { tier: "Adequate", count: 0 },
        { tier: "Apprentice", count: 0 }, { tier: "Novice", count: 0 },
      ],
    });
  });

  it("exposes the current window and the team delta the drop-stat prints", () => {
    seed(db); // Ada: 79 in May, 93 in June
    const o = buildTeamOverview(db);
    expect(o.currentMonth).toBe("2026-06");
    expect(o.avgAqDelta).toBe(14);
  });

  it("scopes the headline average to the current window, not stale rows", () => {
    // The masthead labels this figure with currentMonth, so someone who stopped
    // uploading three months ago must not drag the headline number.
    const ada = upsertPerson(db, "ada@example.com", "Ada");
    const alan = upsertPerson(db, "alan@example.com", "Alan");
    const aq = (n: number) => makeSummary({ profile: { aq: { aq_0_100: n } } });
    put(db, ada.id, "2026-05", aq(80));
    put(db, ada.id, "2026-06", aq(90));
    put(db, alan.id, "2026-04", aq(100));
    put(db, alan.id, "2026-05", aq(80)); // stale: never uploaded June
    const o = buildTeamOverview(db);
    expect(o.currentMonth).toBe("2026-06");
    expect(o.avgAq).toBe(90); // Ada only — not round((90+80)/2) = 85
    expect(o.avgAqDelta).toBe(10); // not round((10 + -20)/2) = -5
    expect(o.coverage).toEqual({ withCurrentMonth: 1, total: 2 });
  });

  it("reports no delta when the preceding upload carries no AQ", () => {
    // Reaching further back would report a change spanning more than one month.
    const p = upsertPerson(db, "ada@example.com", "Ada");
    put(db, p.id, "2026-04", makeSummary({ profile: { aq: { aq_0_100: 80 } } }));
    const noAq = makeSummary();
    delete noAq.profile.aq.aq_0_100;
    put(db, p.id, "2026-05", noAq);
    put(db, p.id, "2026-06", makeSummary({ profile: { aq: { aq_0_100: 90 } } }));
    const row = buildTeamOverview(db).people[0];
    expect(row.aq).toBe(90);
    expect(row.delta).toBeNull();
    expect(row.trend.map((t) => t.aq)).toEqual([80, 90]); // sparkline still skips it
  });

  it("keeps the display model name for chart legends", () => {
    seed(db);
    const jun = buildTeamOverview(db).usageOverTime.find((u) => u.monthKey === "2026-06")!;
    expect(jun.byModel.map((m) => m.model)).toEqual(["Opus 4.8", "Fable 5"]);
    expect(jun.byModel[0].modelId).toBe("claude-opus-4-8");
  });

  it("monthlyUsage gives each month to the newest upload that still covers it", () => {
    const older = {
      monthKey: "2026-01",
      summary: makeSummary({
        noticed_stats_monthly: [
          { month: "2026-01", token_usage: { by_model: [
            { model_id: "claude-opus-4-8", model: "Opus 4.8", input: 5, output: 0, cache_read: 0, cache_creation: 0 } ] } },
          { month: "2026-06", token_usage: { by_model: [
            { model_id: "claude-opus-4-8", model: "Opus 4.8", input: 999, output: 0, cache_read: 0, cache_creation: 0 } ] } },
        ],
        progression_monthly: [],
      }),
    };
    const newer = { monthKey: "2026-06", summary: makeSummary() };
    const usage = monthlyUsage([older, newer]);
    expect(usage.map((u) => u.monthKey)).toEqual(["2026-01", "2026-05", "2026-06"]);
    // 2026-06 is covered by both; the newer upload owns it, so the older
    // upload's stale 999 must not appear.
    const jun = usage.find((u) => u.monthKey === "2026-06")!;
    expect(jun.byModel.reduce((s, m) => s + m.tokens, 0)).toBe(TOTAL_TOKENS);
  });

  it("buildPersonProfile returns profile view or null", () => {
    const p = seed(db);
    const prof = buildPersonProfile(db, p.id, "2026-06");
    expect(prof?.aq).toBe(93);
    expect(prof?.prevMonthKey).toBe("2026-05");
    expect(prof?.nextMonthKey).toBeNull();
    expect(prof?.pillars.map((x) => x.name)).toEqual(["Breadth", "Craft", "Efficiency", "Savvy"]);
    expect(prof?.scorecard.find((s) => s.key === "planning")?.value).toBe(10.0);
    expect(buildPersonProfile(db, 999, "2026-06")).toBeNull();
  });

  it("buildPersonProfile links both neighbours from a middle month", () => {
    const p = seed(db);
    put(db, p.id, "2026-07", makeSummary());
    const prof = buildPersonProfile(db, p.id, "2026-06");
    expect(prof?.prevMonthKey).toBe("2026-05");
    expect(prof?.nextMonthKey).toBe("2026-07");
  });

  it("buildPersonProfile is null for a month the person never uploaded", () => {
    const p = seed(db);
    expect(buildPersonProfile(db, p.id, "2026-01")).toBeNull();
  });

  it("reports a missing score as null, not as a real 0.0", () => {
    const p = upsertPerson(db, "ada@example.com", "Ada");
    const noScores = makeSummary();
    delete noScores.profile.scores;
    put(db, p.id, "2026-06", noScores);
    const scorecard = buildPersonProfile(db, p.id, "2026-06")!.scorecard;
    expect(scorecard.map((s) => s.value)).toEqual([null, null, null]);
  });

  it("survives a summary stripped of every optional block", () => {
    // Unknown/missing fields must never throw — the store is schema-proof by
    // design and old clients keep uploading.
    const p = upsertPerson(db, "ada@example.com", "Ada");
    put(db, p.id, "2026-06", {
      context: { date_range: ["2026-01-01", "2026-06-30"], total_sessions: 1 },
      profile: { aq: { aq_0_100: 50 } },
    });
    const prof = buildPersonProfile(db, p.id, "2026-06");
    expect(prof?.aq).toBe(50);
    expect(prof?.pillars).toEqual([]);
    expect(prof?.modelMix).toEqual([]);
    expect(prof?.usage).toEqual({ sessions: 1, prompts: 0, actionsPerPrompt: 0 });
    // Missing metrics show the em-dash with no dangling unit.
    expect(prof?.explore.every((t) => t.value === "—" && t.unit === "")).toBe(true);
    expect(() => buildTeamOverview(db)).not.toThrow();
  });

  it("explore tiles split numeral from unit so the tile can typeset them", () => {
    const p = seed(db);
    const explore = buildPersonProfile(db, p.id, "2026-06")!.explore;
    expect(explore.map((t) => t.label)).toEqual([
      "Planning ratio", "Error recovery", "Error rate", "Iter depth",
      "Git churn", "Fanout median", "Compounding writes", "Active days",
    ]);
    expect(explore[0]).toEqual({ label: "Planning ratio", value: "82", unit: "%" });
    // Raw churn is 8159072 — the mockup reads "8.2M lines", not "8159072 lines".
    expect(explore[4]).toEqual({ label: "Git churn", value: "8.2", unit: "M lines" });
    expect(explore[7]).toEqual({ label: "Active days", value: "14", unit: "" });
  });

  it("formatters use the magnitude the mockups typeset", () => {
    expect(fmtTokens(TOTAL_TOKENS)).toBe("5.7B");
    expect(fmtTokens(8_159_072)).toBe("8.2M");
    expect(fmtTokens(4_200)).toBe("4K");
    expect(fmtDelta(4)).toBe("+4");
    expect(fmtDelta(-4)).toBe("\u22124");
    expect(fmtUsd(39360.4)).toBe("$39,360");
    expect(costUsd({ input: 1_000_000, output: 0, cacheRead: 0, cacheCreation: 0 }, "claude-opus-4-8")).toBeCloseTo(15);
  });

  it("prices unknown models with the default table instead of zero", () => {
    expect(costUsd({ input: 1_000_000, output: 0, cacheRead: 0, cacheCreation: 0 }, "who-knows-5")).toBeCloseTo(3);
  });

  describe("teamPillarAverages", () => {
    it("averages by pillar name across people, weight rounded", () => {
      const sets = [
        [{ name: "Breadth", weight: 30, score: 20, axes: [] }, { name: "Craft", weight: 35, score: 30, axes: [] }],
        [{ name: "Breadth", weight: 31, score: 24, axes: [] }, { name: "Craft", weight: 35, score: 34, axes: [] }],
      ];
      expect(teamPillarAverages(sets)).toEqual([
        { name: "Breadth", weight: 31, avgScore: 22 }, // (20+24)/2, (30+31)/2 rounded
        { name: "Craft", weight: 35, avgScore: 32 },
      ]);
    });

    it("is coverage-aware by construction: only pass pillar sets from covered people", () => {
      // A person with no pillar data for the month simply contributes an empty
      // array — the caller decides who's "covered", this function never fetches.
      const sets = [[{ name: "Breadth", weight: 30, score: 20, axes: [] }], []];
      expect(teamPillarAverages(sets)).toEqual([{ name: "Breadth", weight: 30, avgScore: 20 }]);
    });

    it("returns an empty array for no covered people", () => {
      expect(teamPillarAverages([])).toEqual([]);
    });
  });

  describe("tierDistribution", () => {
    it("returns all six tiers, including zero-count ones, in Elite→Novice order", () => {
      const people = [{ tier: "Advanced" }, { tier: "Advanced" }, { tier: "Novice" }];
      expect(tierDistribution(people)).toEqual([
        { tier: "Elite", count: 0 }, { tier: "Advanced", count: 2 },
        { tier: "Proficient", count: 0 }, { tier: "Adequate", count: 0 },
        { tier: "Apprentice", count: 0 }, { tier: "Novice", count: 1 },
      ]);
    });

    it("ignores null tiers without counting them as a seventh bucket", () => {
      const dist = tierDistribution([{ tier: null }, { tier: "Elite" }]);
      expect(dist.reduce((s, t) => s + t.count, 0)).toBe(1);
      expect(dist.find((t) => t.tier === "Elite")?.count).toBe(1);
    });
  });

  describe("teamModelMix", () => {
    it("returns exact shares with no Otros bucket at exactly maxSeries models", () => {
      const byModel = [
        { modelId: "opus", model: "Opus 4.8", tokens: 60, cost: 0 },
        { modelId: "fable", model: "Fable 5", tokens: 30, cost: 0 },
        { modelId: "haiku", model: "Haiku 4.5", tokens: 10, cost: 0 },
      ];
      const mix = teamModelMix(byModel);
      expect(mix).toHaveLength(3);
      expect(mix.find((m) => m.modelId === "opus")?.pct).toBeCloseTo(0.6);
      expect(mix.some((m) => m.modelId === "__other__")).toBe(false);
    });

    it("buckets everything past maxSeries into one Otros entry", () => {
      const byModel = [
        { modelId: "opus", model: "Opus 4.8", tokens: 40, cost: 0 },
        { modelId: "fable", model: "Fable 5", tokens: 30, cost: 0 },
        { modelId: "haiku", model: "Haiku 4.5", tokens: 20, cost: 0 },
        { modelId: "gpt", model: "GPT-5", tokens: 10, cost: 0 },
      ];
      const mix = teamModelMix(byModel);
      expect(mix.map((m) => m.modelId)).toEqual(["opus", "fable", "haiku", "__other__"]);
      const otros = mix.find((m) => m.modelId === "__other__")!;
      expect(otros.model).toBe("Other");
      expect(otros.tokens).toBe(10);
      expect(otros.pct).toBeCloseTo(0.1);
    });

    it("returns an empty array when the month has zero tokens", () => {
      expect(teamModelMix([])).toEqual([]);
    });
  });

  describe("buildTeamOverview month param", () => {
    it("with no month, behaves exactly as before (latest month, per-person latest row)", () => {
      seed(db);
      const withoutMonth = buildTeamOverview(db);
      const withLatest = buildTeamOverview(db, "2026-06");
      expect(withoutMonth).toEqual(withLatest);
    });

    it("pins every aggregate to a past month while `people` stays each person's own latest", () => {
      const ada = upsertPerson(db, "ada@example.com", "Ada");
      put(db, ada.id, "2026-05", makeSummary({ profile: { aq: { aq_0_100: 70, tier: "Proficient" } } }));
      put(db, ada.id, "2026-06", makeSummary({ profile: { aq: { aq_0_100: 90, tier: "Elite" } } }));
      const o = buildTeamOverview(db, "2026-05");
      expect(o.currentMonth).toBe("2026-05");
      expect(o.avgAq).toBe(70);
      expect(o.coverage).toEqual({ withCurrentMonth: 1, total: 1 });
      // The Equipo table row is unaffected — still Ada's own latest, June.
      expect(o.people[0].monthKey).toBe("2026-06");
      expect(o.people[0].aq).toBe(90);
    });

    it("falls back to latest on an unknown month, without throwing", () => {
      seed(db);
      const o = buildTeamOverview(db, "1999-01");
      expect(o.currentMonth).toBe("2026-06");
    });

    it("reports zero coverage for a real month with uploads but no AQ-parseable summary", () => {
      const p = upsertPerson(db, "ada@example.com", "Ada");
      put(db, p.id, "2026-06", {
        context: { date_range: ["2026-01-01", "2026-06-30"], total_sessions: 1 },
      });
      const o = buildTeamOverview(db, "2026-06");
      expect(o.coverage).toEqual({ withCurrentMonth: 0, total: 1 });
      expect(o.avgAq).toBeNull();
    });

    it("compares tokens/cost against the exact prior month, not a window-spanning total", () => {
      const ada = upsertPerson(db, "ada@example.com", "Ada");
      const summary = makeSummary();
      put(db, ada.id, "2026-05", summary);
      put(db, ada.id, "2026-06", summary);
      const o = buildTeamOverview(db, "2026-06");

      // Each upload's own monthKey is read from ITS OWN entry inside the same
      // shared fixture blob, so the two months are not necessarily equal —
      // the point is that the delta must match exactly that per-month
      // difference (`agg`'s window-spanning sum would instead double-count
      // and diverge from this).
      const juneTokens = monthTokensByModel(summary, "2026-06").reduce((s, m) => s + m.tokens, 0);
      const mayTokens = monthTokensByModel(summary, "2026-05").reduce((s, m) => s + m.tokens, 0);
      expect(o.tokensDelta).toBe(juneTokens - mayTokens);
      expect(o.tokensCurrentMonth).toBe(juneTokens);
    });

    it("reports no tokens/cost delta when the prior month falls outside the tracked window", () => {
      const p = upsertPerson(db, "ada@example.com", "Ada");
      put(db, p.id, "2026-06", makeSummary());
      const o = buildTeamOverview(db, "2026-06");
      expect(o.tokensDelta).toBeNull();
      expect(o.costDelta).toBeNull();
    });
  });
});
