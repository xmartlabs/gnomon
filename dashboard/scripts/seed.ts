// Deterministic fake team — no randomness, so runs are reproducible and the
// Playwright gate can assert exact numbers. Reuses the test fixture so seed data
// and unit tests never drift apart.
import { getDb, upsertPerson, upsertUpload } from "../src/lib/db";
import { makeSummary } from "../tests/fixtures/summary";

// `top` is the pillar this person leads on, so the table's Top pillar column
// shows four different answers rather than whatever the fixture happens to rank
// first for everyone.
const PEOPLE = [
  { email: "ada@example.com", name: "Ada Lovelace", scale: 1.0, top: "Craft", aq: { "2026-05": 79, "2026-06": 93 } },
  { email: "alan@example.com", name: "Alan Turing", scale: 0.86, top: "Efficiency", aq: { "2026-05": 88, "2026-06": 85 } },
  { email: "grace@example.com", name: "Grace Hopper", scale: 0.8, top: "Breadth", aq: { "2026-04": 70, "2026-05": 74, "2026-06": 81 } },
  { email: "kat@example.com", name: "Katherine J.", scale: 0.65, top: "Savvy", aq: { "2026-06": 66 } },
];

// Weights come from the AQ model; the leader fills ~97% of its weight and the
// rest sit lower, so `topPillar` (score relative to weight) is unambiguous.
const PILLARS = [
  { name: "Breadth", weight: 30, axes: ["Tool range", "Skill use", "MCP reach"] },
  { name: "Craft", weight: 35, axes: ["Verification", "Error recovery", "Iteration"] },
  { name: "Efficiency", weight: 20, axes: ["Actions/prompt", "Fanout"] },
  { name: "Savvy", weight: 15, axes: ["Planning", "Compounding"] },
];

function pillarsFor(top: string, aq: number) {
  return PILLARS.map((p) => {
    const fill = p.name === top ? 0.97 : 0.62 + (aq / 100) * 0.2;
    return {
      name: p.name,
      weight: p.weight,
      score: Math.round(p.weight * fill * 10) / 10,
      axes: p.axes.map((name, i) => ({
        name,
        weight: 10,
        score: Math.round((fill * 10 - i * 0.4) * 10) / 10,
      })),
    };
  });
}

const MODELS = [
  { model_id: "claude-opus-4-8", model: "Opus 4.8", share: 0.6 },
  { model_id: "claude-fable-5", model: "Fable 5", share: 0.28 },
  { model_id: "claude-haiku-4-5", model: "Haiku 4.5", share: 0.12 },
];

const tierFor = (aq: number) => (aq >= 90 ? "Elite" : aq >= 80 ? "Advanced" : "Proficient");

function monthsEndingAt(monthKey: string, count: number): string[] {
  const [y, m] = monthKey.split("-").map(Number);
  return Array.from({ length: count }, (_, i) => {
    const d = new Date(Date.UTC(y, m - 1 - (count - 1 - i), 1));
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  });
}

/** Per-month blocks so the usage chart has a real series, not one repeated bar. */
function monthlyBlocks(monthKey: string, scale: number) {
  const months = monthsEndingAt(monthKey, 3);
  const noticed = [];
  const progression = [];
  for (const [i, month] of months.entries()) {
    // Gentle month-over-month growth, deterministic per person.
    const grow = (base: number) => Math.round(base * scale * (1 + i * 0.09));
    const total = grow(4.2e9);
    noticed.push({
      month,
      token_usage: {
        // Proportions taken from a real summary: cache reads dominate and
        // output is a fraction of a percent. Inventing a fat output share
        // would inflate estimated cost by more than an order of magnitude.
        by_model: MODELS.map((m) => ({
          model_id: m.model_id,
          model: m.model,
          input: Math.round(total * m.share * 0.0017),
          output: Math.round(total * m.share * 0.0037),
          cache_read: Math.round(total * m.share * 0.974),
          cache_creation: Math.round(total * m.share * 0.0206),
        })),
      },
    });
    progression.push({
      month,
      prompts: grow(900),
      sessions: grow(130),
      tool_calls: grow(13000),
      active_days: 12 + i,
      models: MODELS.map((m) => [m.model_id, Math.round(20000 * m.share)] as [string, number]),
      top_model: MODELS[0].model_id,
      tokens_total: total,
    });
  }
  return { noticed, progression };
}

function summaryFor(monthKey: string, aq: number, scale: number, top: string) {
  const { noticed, progression } = monthlyBlocks(monthKey, scale);
  const latest = progression.at(-1)!;
  return makeSummary({
    context: {
      // Tz-aware ISO timestamps, exactly what the real CLI uploads.
      date_range: [`${monthKey}-01T00:00:00-03:00`, `${monthKey}-28T00:00:00-03:00`],
      total_sessions: latest.sessions,
      total_prompts: latest.prompts,
    },
    noticed_stats_monthly: noticed,
    progression_monthly: progression,
    profile: {
      // Scores track AQ so the scorecard trend lines actually move month over
      // month instead of drawing a flat rule.
      scores: {
        execution: { value: Math.round(aq * 0.098 * 10) / 10, gloss: "How much you ship, how fast" },
        planning: { value: Math.round(aq * 0.105 * 10) / 10, gloss: "Think before you build" },
        engineering: { value: Math.round(aq * 0.092 * 10) / 10, gloss: "How clean your work is" },
      },
      aq: { aq_0_100: aq, tier: tierFor(aq), pillars: pillarsFor(top, aq) },
      model_usage: MODELS.map((m) => ({ model_id: m.model_id, model: m.model, pct: m.share })),
    },
  });
}

function main() {
  const db = getDb();
  for (const p of PEOPLE) {
    const person = upsertPerson(db, p.email, p.name);
    for (const [monthKey, aq] of Object.entries(p.aq)) {
      upsertUpload(db, {
        personId: person.id,
        monthKey,
        windowMonths: 6,
        summaryJson: JSON.stringify(summaryFor(monthKey, aq, p.scale, p.top)),
      });
    }
  }
  console.log(`Seeded ${PEOPLE.length} people.`);
}

main();
