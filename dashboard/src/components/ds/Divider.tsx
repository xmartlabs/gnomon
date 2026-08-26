type Weight = "strong" | "default" | "subtle";

const COLOR: Record<Weight, string> = {
  strong: "var(--rule-strong)",
  default: "var(--rule-default)",
  subtle: "var(--rule-subtle)",
};

/** Hairline rule — the primary structural device. No cards, no boxes: grouping is a Divider plus whitespace. */
export function Divider({
  orientation = "horizontal",
  weight = "default",
  thick = false,
  space,
}: {
  orientation?: "horizontal" | "vertical";
  weight?: Weight;
  thick?: boolean;
  /** Spacing-scale step (1-14) for the vertical margin. Defaults to --space-11 (48px). */
  space?: number;
}) {
  const width = weight === "strong" && thick ? "var(--rule-width-strong)" : "var(--rule-width)";
  if (orientation === "vertical") {
    return (
      <div
        aria-hidden="true"
        style={{ width, alignSelf: "stretch", background: COLOR[weight], flex: "none" }}
      />
    );
  }
  return (
    <hr
      style={{
        border: 0,
        borderTop: `${width} solid ${COLOR[weight]}`,
        margin: space !== undefined ? `var(--space-${space}) 0` : "var(--space-11) 0",
      }}
    />
  );
}
