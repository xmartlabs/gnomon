type Size = "xl" | "lg" | "md" | "sm";

const SIZE_FONT: Record<Size, string> = {
  xl: "var(--type-metric-xl)",
  lg: "var(--type-metric-lg)",
  md: "var(--type-metric-md)",
  sm: "var(--type-metric-sm)",
};

/**
 * One `xl` figure per screen — that figure is the screen's subject. Every
 * number carries its denominator and its comparison; a bare figure with no
 * scale does not ship (pair with `unit` and/or `trailing`).
 */
export function Metric({
  label,
  value,
  unit,
  caption,
  size = "md",
  align,
  tone,
  trailing,
}: {
  label?: string;
  value: React.ReactNode;
  unit?: string;
  caption?: string;
  size?: Size;
  align?: "right";
  tone?: "accent";
  trailing?: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        alignItems: align === "right" ? "flex-end" : "flex-start",
      }}
    >
      {label && (
        <span
          style={{
            fontFamily: "var(--font-figure)",
            fontSize: "var(--size-label)",
            fontWeight: "var(--weight-medium)",
            letterSpacing: "var(--tracking-label)",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
          }}
        >
          {label}
        </span>
      )}
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-4)" }}>
        <span
          style={{
            font: SIZE_FONT[size],
            letterSpacing: "var(--tracking-metric)",
            color: tone === "accent" ? "var(--accent)" : "var(--text-primary)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {value}
        </span>
        {unit && (
          <span style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)", fontFamily: "var(--font-figure)" }}>
            {unit}
          </span>
        )}
        {trailing}
      </div>
      {caption && <span style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{caption}</span>}
    </div>
  );
}
