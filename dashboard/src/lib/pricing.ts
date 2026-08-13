export type TokenSplit = {
  input: number;
  output: number;
  cacheRead: number;
  cacheCreation: number;
};

type Price = { in: number; out: number; cacheRead: number; cacheWrite: number };

// Approximate list prices per MTok, USD — edit freely for your provider mix.
const FRONTIER: Price = { in: 15, out: 75, cacheRead: 1.5, cacheWrite: 18.75 };
const MID: Price = { in: 3, out: 15, cacheRead: 0.3, cacheWrite: 3.75 };

// Matched by substring on the model id, first hit wins.
const PRICES: [needle: string, p: Price][] = [
  ["opus", FRONTIER],
  ["fable", FRONTIER],
  ["sonnet", MID],
  ["haiku", { in: 0.8, out: 4, cacheRead: 0.08, cacheWrite: 1 }],
  ["gpt", { in: 2.5, out: 10, cacheRead: 0.25, cacheWrite: 0 }],
  ["gemini", { in: 1.25, out: 10, cacheRead: 0.125, cacheWrite: 0 }],
];
const DEFAULT = MID;

// The id set is tiny (a handful of models) but costUsd runs once per model per
// month per upload, so memoize the substring scan.
const resolved = new Map<string, Price>();

function priceFor(modelId: string): Price {
  const key = modelId || "";
  const hit = resolved.get(key);
  if (hit) return hit;
  const low = key.toLowerCase();
  const price = PRICES.find(([needle]) => low.includes(needle))?.[1] ?? DEFAULT;
  resolved.set(key, price);
  return price;
}

export function costUsd(tokens: TokenSplit, modelId: string): number {
  const p = priceFor(modelId);
  const M = 1_000_000;
  return (
    (tokens.input / M) * p.in +
    (tokens.output / M) * p.out +
    (tokens.cacheRead / M) * p.cacheRead +
    (tokens.cacheCreation / M) * p.cacheWrite
  );
}
