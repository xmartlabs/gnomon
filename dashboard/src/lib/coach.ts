import Anthropic from "@anthropic-ai/sdk";
import type { Db } from "@/lib/db";
import type { PersonProfile } from "@/lib/metrics";

/**
 * The optional AI coach. Off unless the operator sets LLM_API_KEY, and it never
 * throws into the page — a coach outage must not take a profile down with it.
 *
 * Model note: the plan pinned Haiku 4.5 for a 3–4 sentence paragraph. Kept as
 * the default so the feature is cheap to leave on, but overridable with
 * LLM_MODEL for teams who want a stronger read.
 */
const DEFAULT_MODEL = "claude-haiku-4-5";
const MAX_TOKENS = 300;

export function coachEnabled(): boolean {
  return Boolean(process.env.LLM_API_KEY);
}

const cacheKey = (personId: number, monthKey: string) => `coach:${personId}:${monthKey}`;

function buildPrompt(prof: PersonProfile): string {
  const pillars = prof.pillars.map((p) => `${p.name} ${p.score.toFixed(0)}/${p.weight}`).join(", ");
  const scores = prof.scorecard
    .filter((s) => s.value !== null)
    .map((s) => `${s.key} ${s.value!.toFixed(1)}/10`)
    .join(", ");
  const explore = prof.explore
    .filter((t) => t.value !== "—")
    .map((t) => `${t.label} ${t.value}${t.unit}`)
    .join(", ");

  return [
    "You are a concise engineering coach reading one developer's monthly agent-usage report.",
    "In 3-4 sentences, name their strongest area and the single highest-leverage improvement.",
    "Cite the specific numbers you are reasoning from. No preamble, no headings, no bullet lists.",
    "",
    `AQ: ${prof.aq}/100 (${prof.tier}).`,
    pillars && `Pillars: ${pillars}.`,
    scores && `Scores: ${scores}.`,
    explore && `Signals: ${explore}.`,
  ]
    .filter(Boolean)
    .join("\n");
}

/**
 * Cached per (person, month) in `settings`. db.ts drops that key inside the
 * upload transaction, so a re-uploaded month regenerates instead of showing
 * advice about numbers that no longer exist.
 */
export async function getCoachText(db: Db, prof: PersonProfile): Promise<string | null> {
  if (!coachEnabled()) return null;

  const key = cacheKey(prof.personId, prof.monthKey);
  const cached = db.prepare(`SELECT value FROM settings WHERE key = ?`).get(key) as
    | { value: string }
    | undefined;
  if (cached) return cached.value;

  const client = new Anthropic({ apiKey: process.env.LLM_API_KEY, maxRetries: 1 });

  try {
    const message = await client.messages.create({
      model: process.env.LLM_MODEL || DEFAULT_MODEL,
      max_tokens: MAX_TOKENS,
      messages: [{ role: "user", content: buildPrompt(prof) }],
    });

    // A refusal returns 200 with no text block; treat it as "no coach today".
    const text = message.content.find((b) => b.type === "text")?.text?.trim();
    if (!text) return null;

    db.prepare(`INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)`).run(key, text);
    return text;
  } catch (err) {
    // Typed chain rather than a catch-all: a bad key is an operator problem
    // worth naming in the logs, a rate limit is transient and worth retrying
    // on the next render. Neither is worth failing the page over.
    if (err instanceof Anthropic.AuthenticationError) {
      console.error("[coach] LLM_API_KEY rejected — the coach card will stay hidden");
    } else if (err instanceof Anthropic.NotFoundError) {
      console.error(`[coach] unknown model ${process.env.LLM_MODEL || DEFAULT_MODEL}`);
    } else if (err instanceof Anthropic.RateLimitError) {
      console.warn("[coach] rate limited; will retry on the next view");
    } else if (err instanceof Anthropic.APIConnectionError) {
      console.warn("[coach] could not reach the API; will retry on the next view");
    } else {
      console.error("[coach] unexpected failure", err);
    }
    return null;
  }
}
