export function PillarBar({
  name,
  weight,
  value,
  max = 100,
  size,
  tone,
  reference,
}: {
  name: string;
  /** Display string next to the name, e.g. "30%" — the pillar's rubric weight, not its score. */
  weight?: string;
  value: number;
  max?: number;
  size?: "sm" | "lg";
  tone?: "muted";
  /** Team-average marker rendered as a strong tick over the track. */
  reference?: number | null;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const height = size === "sm" ? 6 : size === "lg" ? 10 : 8;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-4)" }}>
        <span style={{ font: size === "sm" ? "var(--type-body-sm)" : "var(--type-title-sm)" }}>{name}</span>
        {weight && (
          <span
            style={{
              fontFamily: "var(--font-figure)",
              fontSize: "var(--size-label)",
              letterSpacing: "var(--tracking-label)",
              color: "var(--text-tertiary)",
            }}
          >
            {weight}
          </span>
        )}
        <span
          style={{
            marginLeft: "auto",
            fontFamily: "var(--font-figure)",
            fontSize: size === "sm" ? "var(--size-body)" : "var(--size-metric-sm)",
            fontWeight: "var(--weight-medium)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {value}
        </span>
        {max !== 100 && (
          <span style={{ fontFamily: "var(--font-figure)", fontSize: "var(--size-label)", color: "var(--text-tertiary)" }}>
            /{max}
          </span>
        )}
      </div>
      <div
        role="img"
        aria-label={`${name}: ${value} of ${max}`}
        style={{ height, background: "var(--chart-track)", position: "relative" }}
      >
        <span
          style={{
            position: "absolute",
            inset: "0 auto 0 0",
            width: `${pct}%`,
            background: tone === "muted" ? "var(--chart-3)" : "var(--chart-1)",
          }}
        />
        {reference != null && (
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              top: -2,
              bottom: -2,
              left: `${Math.max(0, Math.min(100, (reference / max) * 100))}%`,
              width: "var(--rule-width-strong)",
              background: "var(--rule-strong)",
            }}
          />
        )}
      </div>
    </div>
  );
}
