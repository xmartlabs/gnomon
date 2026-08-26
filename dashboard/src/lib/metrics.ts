// Read-time derivation over raw stored summary.json blobs. Numeric only —
// display formatting lives in lib/format.ts so the components own typography.
//
// Per-model monthly tokens are read EXACTLY from `noticed_stats_monthly`
// (summary.py `monthly_noticed_stats`), whose entries carry
// `token_usage.by_model` with per-model input/output/cache_read/cache_creation.
// Only when that block is absent (older summaries) do we fall back to
// APPROXIMATING the split by distributing the progression entry's tokens_total
// across models proportionally to invocation counts.
import type { Db } from "@/lib/db";
import { getPerson, listPeople, uploadsForPerson, distinctMonthKeys } from "@/lib/db";
import { costUsd, type TokenSplit } from "@/lib/pricing";

// Tolerate malformed known fields everywhere: coerce anything non-array to [].
function arr(v: unknown): any[] {
  return Array.isArray(v) ? v : [];
}
const toNum = (v: unknown): number => Number(v) || 0;

export type ModelUsage = { modelId: string; model: string; tokens: number; cost: number };
export type MonthUsage = { monthKey: string; byModel: ModelUsage[] };
export type AqPoint = { monthKey: string; aq: number };

export function monthEntry(summary: any, monthKey: string): any | null {
  return arr(summary?.progression_monthly).find((e: any) => e?.month === monthKey) ?? null;
}

export function monthTokensByModel(summary: any, monthKey: string): ModelUsage[] {
  // Preferred path: exact per-model tokens from noticed_stats_monthly.
  const noticed = arr(summary?.noticed_stats_monthly).find((e: any) => e?.month === monthKey);
  const byModel = noticed?.token_usage?.by_model;
  if (Array.isArray(byModel) && byModel.length) {
    return byModel.map((m: any) => {
      const t: TokenSplit = {
        input: toNum(m?.input),
        output: toNum(m?.output),
        cacheRead: toNum(m?.cache_read),
        cacheCreation: toNum(m?.cache_creation),
      };
      const modelId = String(m?.model_id ?? m?.model ?? "unknown");
      return {
        modelId,
        // Keep the display name: the chart and mix legends label with "Opus 4.8",
        // never the raw id. The id stays the aggregation key.
        model: String(m?.model ?? modelId),
        tokens: t.input + t.output + t.cacheRead + t.cacheCreation,
        cost: costUsd(t, modelId),
      };
    });
  }

  // Fallback: invocation-share approximation for legacy summaries.
  const e = monthEntry(summary, monthKey);
  if (!e) return [];
  const label = modelLabels(summary);
  const total = toNum(e.tokens_total);
  // Drop non-positive counts: a malformed payload with a negative count would
  // otherwise hand one model a negative token share (and a negative cost),
  // which is not a state a chart segment can represent.
  const models: [string, number][] = arr(e.models).filter(
    (m: any) => Array.isArray(m) && toNum(m[1]) > 0
  );
  const totalCalls = models.reduce((s, [, n]) => s + toNum(n), 0);

  if (totalCalls <= 0) {
    if (total <= 0) return [];
    const modelId = String(e.top_model ?? "unknown");
    return [{ modelId, model: label(modelId), tokens: total, cost: costUsd(splitOf(e, 1), modelId) }];
  }

  const split = models.map(([modelId, calls]) => {
    const share = toNum(calls) / totalCalls;
    return {
      modelId: String(modelId),
      model: label(String(modelId)),
      tokens: Math.round(total * share),
      cost: costUsd(splitOf(e, share), String(modelId)),
    };
  });
  // Rounding each share independently can drift off tokens_total; give the
  // remainder to the largest model so the parts still sum to the whole.
  const drift = total - split.reduce((s, m) => s + m.tokens, 0);
  if (drift !== 0) {
    const biggest = split.reduce((a, b) => (b.tokens > a.tokens ? b : a));
    biggest.tokens += drift;
  }
  return split;
}

/**
 * id -> display name ("claude-opus-4-8" -> "Opus 4.8"). The legacy
 * progression_monthly block carries raw ids only, but the same summary's
 * model_usage/token_usage blocks name them, so legends stay readable.
 */
function modelLabels(summary: any): (id: string) => string {
  const map = new Map<string, string>();
  for (const m of [...arr(summary?.profile?.model_usage), ...arr(summary?.token_usage?.by_model)]) {
    if (m?.model_id && typeof m.model === "string" && m.model) map.set(String(m.model_id), m.model);
  }
  return (id: string) => map.get(id) ?? id;
}

function splitOf(e: any, share: number): TokenSplit {
  return {
    input: toNum(e.tokens_input) * share,
    output: toNum(e.tokens_output) * share,
    cacheRead: toNum(e.tokens_cache_read) * share,
    cacheCreation: toNum(e.tokens_cache_creation) * share,
  };
}

/**
 * One usage record per month a person has data for, ascending.
 *
 * Each upload only covers a trailing `window_months` window, so the latest
 * upload alone TRUNCATES older months, while consecutive uploads OVERLAP on the
 * months both windows span. The rule: every person-month is owned by exactly
 * one upload — the most recent one that still covers it.
 */
export function monthlyUsage(uploads: { monthKey: string; summary: any }[]): MonthUsage[] {
  const owned = new Map<string, ModelUsage[]>();
  // Descending, first writer wins: the newest upload claims each month, and
  // months it no longer covers fall through to the older uploads that do.
  for (const up of [...uploads].reverse()) {
    for (const e of [...arr(up.summary?.noticed_stats_monthly), ...arr(up.summary?.progression_monthly)]) {
      const month = e?.month;
      if (!month || owned.has(month)) continue;
      owned.set(month, monthTokensByModel(up.summary, month));
    }
  }
  return [...owned.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([monthKey, byModel]) => ({ monthKey, byModel }));
}

export type PersonRow = {
  personId: number; name: string; monthKey: string;
  aq: number | null; tier: string | null; delta: number | null;
  trend: AqPoint[];
  topPillar: string | null;
  tokens: number | null; cost: number | null;
};

function aqOf(summary: any): number | null {
  const v = summary?.profile?.aq?.aq_0_100;
  return typeof v === "number" ? v : null;
}

/** AQ series (ascending) plus the value and month-over-month delta at monthKey. */
function aqAt(uploads: { monthKey: string; summary: any }[], monthKey: string) {
  // The sparkline skips AQ-less uploads, but the delta must not: it is defined
  // against the IMMEDIATELY PRECEDING upload. Reaching further back would
  // compare across a gap and report a change that spans more than one month.
  const trend = uploads
    .map((u) => ({ monthKey: u.monthKey, aq: aqOf(u.summary) }))
    .filter((t): t is AqPoint => t.aq !== null);
  const i = uploads.findIndex((u) => u.monthKey === monthKey);
  const aq = i >= 0 ? aqOf(uploads[i].summary) : null;
  const prev = i > 0 ? aqOf(uploads[i - 1].summary) : null;
  return {
    trend,
    aq,
    delta: aq !== null && prev !== null ? aq - prev : null,
  };
}

export function personRow(
  personId: number, name: string, monthKey: string,
  summaries: { monthKey: string; summary: any }[],
  usage?: MonthUsage
): PersonRow {
  const cur = summaries.find((s) => s.monthKey === monthKey)?.summary;
  const { trend, aq, delta } = aqAt(summaries, monthKey);

  // Top pillar = best score relative to its own weight, so a heavy pillar
  // doesn't win purely by carrying more points.
  const rank = (p: any) => toNum(p?.score) / (toNum(p?.weight) || 1);
  const best = arr(cur?.profile?.aq?.pillars).reduce(
    (a: any, b: any) => (a === null || rank(b) > rank(a) ? b : a),
    null
  );

  // Tokens and cost come from the SAME record, so the table's two numbers can
  // never disagree about which block the month was read from.
  const byModel = usage?.byModel ?? (cur ? monthTokensByModel(cur, monthKey) : null);

  return {
    personId, name, monthKey, aq,
    tier: cur?.profile?.aq?.tier ?? null,
    delta, trend,
    topPillar: best?.name ?? null,
    tokens: byModel ? byModel.reduce((s, m) => s + m.tokens, 0) : null,
    cost: byModel ? byModel.reduce((s, m) => s + m.cost, 0) : null,
  };
}

export type ModelShare = { modelId: string; model: string; tokens: number; pct: number };

export type TeamOverview = {
  people: PersonRow[];
  avgAq: number | null;
  avgAqDelta: number | null;
  currentMonth: string | null;
  coverage: { withCurrentMonth: number; total: number };
  tokensCurrentMonth: number;
  costCurrentMonth: number;
  /** vs the month immediately before the selected one; null when that's outside the tracked window. */
  tokensDelta: number | null;
  costDelta: number | null;
  usageOverTime: MonthUsage[];
  /** Every uploaded monthKey the month selector can offer, most recent first. */
  availableMonths: string[];
  pillarAverages: { name: string; weight: number; avgScore: number }[];
  tierDistribution: { tier: string; count: number }[];
  modelMix: ModelShare[];
  teamAqTrend: AqPoint[];
};

const TIER_ORDER = ["Elite", "Advanced", "Proficient", "Adequate", "Apprentice", "Novice"] as const;

/**
 * Team-wide average score per AQ pillar, across everyone COVERED for the
 * selected month (callers only pass pillar sets for people who actually have
 * an upload for that month, so this stays coverage-aware by construction).
 * Order is first-seen order across `pillarSets`, itself stable per the AQ
 * scoring contract — no pillar names hardcoded here.
 */
export function teamPillarAverages(
  pillarSets: PersonProfile["pillars"][]
): { name: string; weight: number; avgScore: number }[] {
  const acc = new Map<string, { weightSum: number; scoreSum: number; n: number }>();
  for (const pillars of pillarSets) {
    for (const p of pillars) {
      const e = acc.get(p.name) ?? { weightSum: 0, scoreSum: 0, n: 0 };
      e.weightSum += p.weight;
      e.scoreSum += p.score;
      e.n += 1;
      acc.set(p.name, e);
    }
  }
  return [...acc.entries()].map(([name, e]) => ({
    name,
    weight: Math.round(e.weightSum / e.n),
    avgScore: e.scoreSum / e.n,
  }));
}

/**
 * How many people land in each of the six real AQ tiers this month. Always
 * all six, including zero-count ones — a widget whose categories change shape
 * month to month reads as broken, and "Novice: 0" is itself information.
 */
export function tierDistribution(people: { tier: string | null }[]): { tier: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const p of people) {
    if (!p.tier) continue;
    counts.set(p.tier, (counts.get(p.tier) ?? 0) + 1);
  }
  return TIER_ORDER.map((tier) => ({ tier, count: counts.get(tier) ?? 0 }));
}

/**
 * One month's already-summed per-model totals, as shares of that month's
 * total tokens. Beyond `maxSeries` models by token share, the rest are folded
 * into one "Other" bucket so a chart never has to budget more series colors
 * than the design system's ink/accent/parch triad plus one muted overflow.
 */
export function teamModelMix(byModel: ModelUsage[], maxSeries = 3): ModelShare[] {
  const total = byModel.reduce((s, m) => s + m.tokens, 0);
  if (total <= 0) return [];
  const sorted = [...byModel].sort((a, b) => b.tokens - a.tokens);
  const top = sorted
    .slice(0, maxSeries)
    .map((m) => ({ modelId: m.modelId, model: m.model, tokens: m.tokens, pct: m.tokens / total }));
  const rest = sorted.slice(maxSeries);
  if (!rest.length) return top;
  const tokens = rest.reduce((s, m) => s + m.tokens, 0);
  return [...top, { modelId: "__other__", model: "Other", tokens, pct: tokens / total }];
}

/**
 * `month` pins every aggregate below to one specific calendar month instead
 * of "whatever's most recent". `people` (the Equipo table rows) is NOT
 * filtered by it — each row stays that person's own latest upload, same as
 * today, with the table's existing staleness label doing the "this row isn't
 * the selected month" work. Everything else needs each person's data AT
 * `month` specifically, which `rows` can't give (it only ever holds each
 * person's latest row) — so those are recomputed via buildPersonProfile.
 */
export function buildTeamOverview(db: Db, month?: string): TeamOverview {
  const people = listPeople(db);
  const rows: PersonRow[] = [];
  const upsByPerson = new Map<number, ReturnType<typeof uploadsForPerson>>();
  // month -> modelId -> totals. The id is the join key; the label rides along.
  // Deliberately window-spanning (every month ANY upload's window covers,
  // even months that upload didn't literally re-upload) — this is what
  // usageOverTime's monthly bars want. NOT reused for tokensCurrentMonth /
  // teamModelMix below, which need the narrower "this exact monthKey was
  // uploaded" scope instead — see the comment there for why.
  const agg = new Map<string, Map<string, ModelUsage>>();

  for (const p of people) {
    const ups = uploadsForPerson(db, p.id); // ascending by monthKey
    upsByPerson.set(p.id, ups);
    if (!ups.length) continue;
    const latestMonth = ups.at(-1)!.monthKey;
    const usage = monthlyUsage(ups);
    rows.push(personRow(p.id, p.name, latestMonth, ups, usage.find((u) => u.monthKey === latestMonth)));

    for (const { monthKey, byModel } of usage) {
      const models = agg.get(monthKey) ?? new Map<string, ModelUsage>();
      agg.set(monthKey, models);
      for (const m of byModel) {
        const cur = models.get(m.modelId);
        if (cur) {
          cur.tokens += m.tokens;
          cur.cost += m.cost;
        } else {
          models.set(m.modelId, { ...m });
        }
      }
    }
  }

  rows.sort((a, b) => (b.aq ?? -1) - (a.aq ?? -1));

  const avg = (xs: number[]) => (xs.length ? Math.round(xs.reduce((s, x) => s + x, 0) / xs.length) : null);

  const allMonths = distinctMonthKeys(db); // desc, every monthKey with a real upload
  const availableMonths = allMonths.slice(0, 3); // the month selector's options
  // An unknown `month` (stale bookmark, typo) falls back silently to latest —
  // this is not the empty-state's job, which is reserved for a valid month
  // that genuinely has zero AQ-parseable coverage.
  const selectedMonth = month && allMonths.includes(month) ? month : (allMonths[0] ?? null);

  // Computed once per month in `availableMonths` (not just `selectedMonth`),
  // so the 3-month team AQ trend below doesn't pay for a second pass.
  const coveredByMonth = new Map<string, PersonProfile[]>();
  for (const mk of availableMonths) {
    coveredByMonth.set(
      mk,
      people
        .map((p) => buildPersonProfile(db, p.id, mk))
        .filter((x): x is PersonProfile => x !== null)
    );
  }
  const covered = selectedMonth ? (coveredByMonth.get(selectedMonth) ?? []) : [];

  // tokensCurrentMonth/costCurrentMonth/teamModelMix must count each person
  // AT MOST ONCE, from their OWN upload literally labeled the target month —
  // not from `agg`, whose window-spanning months can otherwise double-count a
  // person whose upload for an OLDER month still claims usage data reaching
  // into the target month (a real scenario: a wide window legitimately
  // mentions more months than its own monthKey label). Computed for every
  // month in `availableMonths` so the cost/token Trend below has a same-shape
  // number to compare the selected month against.
  const exactByMonth = new Map<string, ModelUsage[]>();
  for (const mk of availableMonths) {
    const models = new Map<string, ModelUsage>();
    for (const p of people) {
      const exact = upsByPerson.get(p.id)?.find((u) => u.monthKey === mk);
      if (!exact) continue;
      for (const m of monthTokensByModel(exact.summary, mk)) {
        const cur = models.get(m.modelId);
        if (cur) {
          cur.tokens += m.tokens;
          cur.cost += m.cost;
        } else {
          models.set(m.modelId, { ...m });
        }
      }
    }
    exactByMonth.set(mk, [...models.values()]);
  }
  const monthByModel = selectedMonth ? (exactByMonth.get(selectedMonth) ?? []) : [];
  const sumTokens = (xs: ModelUsage[]) => xs.reduce((s, m) => s + m.tokens, 0);
  const sumCost = (xs: ModelUsage[]) => xs.reduce((s, m) => s + m.cost, 0);

  // The delta compares against whichever month sits immediately before the
  // selected one — null (renders "sin datos") when that's outside the last-3
  // window this function tracks, e.g. the oldest of the three is selected.
  const prevMonth = selectedMonth ? allMonths[allMonths.indexOf(selectedMonth) + 1] : undefined;
  const prevExact = prevMonth ? exactByMonth.get(prevMonth) : undefined;
  const tokensDelta = prevExact ? Math.round(sumTokens(monthByModel) - sumTokens(prevExact)) : null;
  const costDelta = prevExact ? Math.round(sumCost(monthByModel) - sumCost(prevExact)) : null;

  return {
    people: rows,
    // Scoped to the selected window, like the tokens/cost stats beside them:
    // the masthead labels this figure with `currentMonth`, so folding in a
    // person whose last upload doesn't cover it would make the headline
    // number silently wrong exactly when coverage is partial. `coverage` is
    // what tells the reader how many people the average stands on.
    avgAq: avg(covered.map((c) => c.aq)),
    avgAqDelta: avg(covered.map((c) => c.delta).filter((x): x is number => x !== null)),
    currentMonth: selectedMonth,
    coverage: { withCurrentMonth: covered.length, total: people.length },
    tokensCurrentMonth: sumTokens(monthByModel),
    costCurrentMonth: sumCost(monthByModel),
    tokensDelta,
    costDelta,
    usageOverTime: [...agg.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([monthKey, models]) => ({ monthKey, byModel: [...models.values()] })),
    availableMonths,
    pillarAverages: teamPillarAverages(covered.map((c) => c.pillars)),
    tierDistribution: tierDistribution(covered.map((c) => ({ tier: c.tier }))),
    modelMix: teamModelMix(monthByModel),
    teamAqTrend: [...availableMonths].reverse().map((mk) => ({
      monthKey: mk,
      aq: avg((coveredByMonth.get(mk) ?? []).map((c) => c.aq)) ?? 0,
    })),
  };
}

/** A stat tile: the numeral and the small unit are typeset differently. */
export type ExploreTile = { label: string; value: string; unit: string };

export type PersonProfile = {
  personId: number; name: string; email: string; monthKey: string;
  prevMonthKey: string | null; nextMonthKey: string | null;
  aq: number; tier: string; delta: number | null;
  levelOverTime: AqPoint[];
  pillars: { name: string; weight: number; score: number;
             axes: { name: string; weight: number; score: number }[] }[];
  // `value` is null when the summary carries no score for that key — printing
  // 0.0 would read as a real, very low score rather than missing data.
  scorecard: { key: "execution" | "planning" | "engineering"; value: number | null; gloss: string;
               trend: { monthKey: string; value: number }[] }[];
  explore: ExploreTile[];
  usage: { sessions: number; prompts: number; actionsPerPrompt: number };
  modelMix: { model: string; pct: number }[];
  archetype: { title: string; quote: string } | null;
};

const SCORE_KEYS = ["execution", "planning", "engineering"] as const;

function exploreTiles(s: any, e: any): ExploreTile[] {
  const tile = (label: string, value: any, unit = ""): ExploreTile => ({
    label,
    value: value == null ? "—" : String(value),
    unit: value == null ? "" : unit,
  });
  const pct = (label: string, v: any) =>
    tile(label, v == null ? null : Math.round(Number(v) * 100), "%");
  // Churn is millions of lines in practice; the mockup reads "8.2M lines".
  const churn = s?.churn?.git_churn_total;
  return [
    pct("Planning ratio", s?.planning_ratio_explore_to_doing),
    pct("Error recovery", s?.errors?.error_recovery_ratio),
    tile("Error rate", s?.errors?.error_rate_per_100_tools, "/100"),
    tile("Iter depth", s?.iteration_depth?.mean, "×"),
    tile("Git churn", churn == null ? null : (Number(churn) / 1e6).toFixed(1), "M lines"),
    tile("Fanout median", s?.orchestration?.fanout_median, " tasks"),
    tile("Compounding writes", s?.compounding_writes),
    tile("Active days", e?.active_days),
  ];
}

export function buildPersonProfile(db: Db, personId: number, monthKey: string): PersonProfile | null {
  const person = getPerson(db, personId);
  if (!person) return null;
  const ups = uploadsForPerson(db, personId);
  const idx = ups.findIndex((u) => u.monthKey === monthKey);
  if (idx < 0) return null;
  const s = ups[idx].summary;
  const { trend: levelOverTime, aq, delta } = aqAt(ups, monthKey);
  if (aq === null) return null;

  const scorecard = SCORE_KEYS.map((key) => ({
    key,
    value: Number.isFinite(Number(s?.profile?.scores?.[key]?.value))
      ? Number(s.profile.scores[key].value)
      : null,
    gloss: String(s?.profile?.scores?.[key]?.gloss ?? ""),
    trend: ups
      .map((u) => ({ monthKey: u.monthKey, value: Number(u.summary?.profile?.scores?.[key]?.value) }))
      .filter((t) => Number.isFinite(t.value)),
  }));

  const e = monthEntry(s, monthKey);
  const prompts = toNum(e?.prompts ?? s?.context?.total_prompts);
  const sessions = toNum(e?.sessions ?? s?.context?.total_sessions);
  const toolCalls = toNum(e?.tool_calls);

  return {
    personId, name: person.name, email: person.email, monthKey,
    prevMonthKey: idx > 0 ? ups[idx - 1].monthKey : null,
    nextMonthKey: idx < ups.length - 1 ? ups[idx + 1].monthKey : null,
    aq, tier: String(s?.profile?.aq?.tier ?? ""), delta, levelOverTime,
    pillars: arr(s?.profile?.aq?.pillars).map((p: any) => ({
      name: String(p?.name ?? ""), weight: toNum(p?.weight), score: toNum(p?.score),
      axes: arr(p?.axes).map((a: any) => ({
        name: String(a?.name ?? ""), weight: toNum(a?.weight), score: toNum(a?.score),
      })),
    })),
    scorecard,
    explore: exploreTiles(s, e),
    usage: {
      sessions, prompts,
      actionsPerPrompt: prompts > 0 ? Math.round(toolCalls / prompts) : 0,
    },
    modelMix: arr(s?.profile?.model_usage).map((m: any) => ({
      model: String(m?.model ?? m?.model_id ?? "?"),
      pct: toNum(m?.pct),
    })),
    archetype: s?.profile?.archetype ?? null,
  };
}
