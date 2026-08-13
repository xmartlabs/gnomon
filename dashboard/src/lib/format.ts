// Display formatting. Kept out of metrics.ts so the derivation layer stays
// numeric — the components decide how a number is typeset.

/**
 * Magnitude-aware token count. The dashboards deal in billions (the mockups
 * read "18.9B", "5.7B"), so a fixed M scale would print five-digit numerals.
 */
export function fmtTokens(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${Math.round(n / 1e3)}K`;
  return String(Math.round(n));
}

export function fmtUsd(n: number): string {
  return `$${Math.round(n).toLocaleString("en-US")}`;
}

/** Signed delta for the inked annotations: +4 / −4 (true minus sign). */
export function fmtDelta(n: number): string {
  return n < 0 ? `−${Math.abs(n)}` : `+${n}`;
}
