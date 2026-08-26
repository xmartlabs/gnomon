import { Tooltip } from "./Tooltip";

/**
 * Replaces card headers, so it is the one thing allowed to carry the heading
 * outline. Default tag is `div` — pass `as="h2"`/`as="h3"` for any label that
 * titles a real section (headings must still run h1 → h2 → h3 in order).
 */
export function SectionLabel({
  as: Tag = "div",
  size,
  hint,
  tight = false,
  trailing,
  children,
}: {
  as?: "div" | "h2" | "h3" | "h4";
  size?: "lg";
  hint?: string;
  tight?: boolean;
  trailing?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Tag
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-4)",
        margin: 0,
        marginBottom: tight ? "var(--space-4)" : "var(--space-6)",
        font: "inherit",
        fontWeight: "inherit",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-figure)",
          fontSize: size === "lg" ? "var(--size-label-lg)" : "var(--size-label)",
          fontWeight: "var(--weight-medium)",
          letterSpacing: "var(--tracking-label)",
          textTransform: "uppercase",
          color: size === "lg" ? "var(--text-secondary)" : "var(--text-tertiary)",
        }}
      >
        {children}
      </span>
      {hint && <Tooltip label={hint} />}
      {trailing && <span style={{ marginLeft: "auto" }}>{trailing}</span>}
    </Tag>
  );
}
