export type ColumnDatum = { label: string; value: number; emphasis?: boolean };

export function ColumnChart({
  data,
  height = 96,
  gap,
  max,
  showValues = true,
  ariaLabel,
}: {
  data: ColumnDatum[];
  height?: number;
  gap?: string;
  max?: number;
  showValues?: boolean;
  ariaLabel?: string;
}) {
  const computedMax = max ?? Math.max(...data.map((d) => d.value), 1) * 1.12;

  return (
    <div
      role="img"
      aria-label={ariaLabel ?? data.map((d) => `${d.label} ${d.value}`).join(", ")}
      style={{ display: "flex", alignItems: "flex-end", gap: gap ?? "var(--space-5)", height }}
    >
      {data.map((d, i) => {
        const emphasised = d.emphasis ?? i === data.length - 1;
        return (
          <div
            key={d.label}
            style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-3)" }}
          >
            {showValues && (
              <span
                style={{
                  fontFamily: "var(--font-figure)",
                  fontSize: "var(--size-body-sm)",
                  fontWeight: "var(--weight-medium)",
                  fontVariantNumeric: "tabular-nums",
                  color: emphasised ? "var(--text-primary)" : "var(--text-secondary)",
                }}
              >
                {d.value}
              </span>
            )}
            <div
              style={{
                width: "100%",
                height: Math.max(2, Math.round((d.value / computedMax) * (height - 34))),
                background: emphasised ? "var(--chart-1)" : "var(--chart-4)",
              }}
            />
            <span
              style={{
                fontFamily: "var(--font-figure)",
                fontSize: "var(--size-label)",
                letterSpacing: "var(--tracking-label)",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
              }}
            >
              {d.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
