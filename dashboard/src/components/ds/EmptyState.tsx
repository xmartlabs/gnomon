/** Replaces the entire content region below the h1 — never show empty figures beside it. Always give a way out. */
export function EmptyState({
  label,
  title,
  titleAs: Title = "h2",
  body,
  action,
  width,
}: {
  label?: string;
  title: React.ReactNode;
  titleAs?: "h2" | "h3";
  body?: React.ReactNode;
  action?: React.ReactNode;
  width?: number;
}) {
  return (
    <div
      style={{
        maxWidth: width ?? 520,
        padding: "var(--space-14) 0",
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: "var(--space-5)",
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
      <Title style={{ margin: 0, font: "var(--type-title-lg)", letterSpacing: "var(--tracking-title)", textWrap: "pretty" }}>
        {title}
      </Title>
      {body && (
        <p style={{ margin: 0, font: "var(--type-body-lg)", color: "var(--text-secondary)", textWrap: "pretty" }}>
          {body}
        </p>
      )}
      {action && <div style={{ marginTop: "var(--space-3)" }}>{action}</div>}
    </div>
  );
}
