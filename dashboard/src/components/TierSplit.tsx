// gnomon/scoring/aq.py's real thresholds — kept in sync with the CLI's own tier cutoffs.
const RANGE: Record<string, string> = {
  Elite: "88+",
  Advanced: "75–87",
  Proficient: "60–74",
  Adequate: "45–59",
  Apprentice: "25–44",
  Novice: "<25",
};

export function TierSplit({
  counts,
  uploaded,
}: {
  counts: { tier: string; count: number }[];
  uploaded: number;
}) {
  // Only the tiers someone actually landed in this month — an all-zero row
  // for a tier nobody is near reads as noise, not information, in this
  // compact list (unlike the team-pillar bars, which always show all four).
  const shown = counts.filter((c) => c.count > 0);
  const modeTier = shown.reduce((a, b) => (b.count > a.count ? b : a), shown[0])?.tier ?? "—";

  return (
    <div>
      {shown.map((t, i) => (
        <div
          key={t.tier}
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: "var(--space-5)",
            padding: "var(--space-5) 0",
            borderBottom: i < shown.length - 1 ? "var(--rule-width) solid var(--rule-subtle)" : 0,
          }}
        >
          <span style={{ font: "var(--type-title-sm)" }}>{t.tier}</span>
          <span style={{ fontFamily: "var(--font-figure)", fontSize: "var(--size-label)", letterSpacing: "var(--tracking-label)", color: "var(--text-tertiary)" }}>
            {RANGE[t.tier] ?? ""}
          </span>
          <span style={{ marginLeft: "auto", fontFamily: "var(--font-figure)", fontSize: "var(--size-metric-sm)", fontWeight: "var(--weight-medium)" }}>
            {t.count}
          </span>
        </div>
      ))}
      <p style={{ margin: "var(--space-5) 0 0", font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>
        Average tier: {modeTier} · {uploaded} {uploaded === 1 ? "person" : "people"} uploaded this month
      </p>
    </div>
  );
}
