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

/**
 * Split a formatted figure into numeral and unit so a stat column can typeset
 * them at different sizes. Slicing the last character would mangle a unitless
 * value ("950" -> "95" + "0").
 */
export function splitUnit(s: string): { value: string; unit: string } {
  const m = /^([^A-Za-z]*)([A-Za-z]*)$/.exec(s);
  return m ? { value: m[1], unit: m[2] } : { value: s, unit: "" };
}

/** Signed delta for the inked annotations: +4 / −4 (true minus sign). */
export function fmtDelta(n: number): string {
  return n < 0 ? `−${Math.abs(n)}` : `+${n}`;
}

const MONTHS_EN = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** "2026-08" -> "August 2026" — the dashboard's content language is English. */
export function fmtMonthLabel(monthKey: string): string {
  const [y, m] = monthKey.split("-").map(Number);
  const name = MONTHS_EN[(m ?? 1) - 1] ?? monthKey;
  return `${name} ${y}`;
}

/** "2026-08" -> "aug" — the three-month history chart's column labels. */
export function fmtMonthShort(monthKey: string): string {
  return fmtMonthLabel(monthKey).slice(0, 3).toLowerCase();
}
