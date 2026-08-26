/**
 * Colour is never the sole carrier of meaning — every trend renders a glyph
 * AND a number. Red only for a real decline; missing data is grey, never red.
 */
export function Trend({
  delta,
  against,
  size,
  format = String,
}: {
  delta: number | null;
  against?: string;
  size?: "lg";
  /** Formats the absolute magnitude — e.g. fmtTokens for a token delta. Defaults to the bare number. */
  format?: (abs: number) => string;
}) {
  const noData = delta === null;
  const dir = noData ? "none" : delta > 0 ? "up" : delta < 0 ? "down" : "flat";

  const map = {
    up: { glyph: "▲", color: "var(--positive)", text: `+${format(delta ?? 0)}` },
    down: { glyph: "▼", color: "var(--negative)", text: `−${format(Math.abs(delta ?? 0))}` },
    flat: { glyph: "=", color: "var(--neutral)", text: "0" },
    none: { glyph: "—", color: "var(--neutral)", text: "no data" },
  }[dir];

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "baseline",
        gap: "var(--space-2)",
        fontFamily: "var(--font-figure)",
        fontSize: size === "lg" ? "var(--size-body-lg)" : "var(--size-body-sm)",
        fontWeight: "var(--weight-medium)",
        color: map.color,
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden="true">{map.glyph}</span>
      <span>{map.text}</span>
      {against && (
        <span style={{ color: "var(--text-tertiary)", fontWeight: "var(--weight-regular)" }}>vs {against}</span>
      )}
    </span>
  );
}
