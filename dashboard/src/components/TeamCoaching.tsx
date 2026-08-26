import type { Db } from "@/lib/db";
import { getTeamInsight, type TeamInsightInput } from "@/lib/coach";
import { Divider } from "@/components/ds/Divider";

/**
 * "What to improve this month" — the product's tone is coaching, not ranking.
 * Self-contained: renders nothing when the coach is unconfigured or the call
 * fails, so an absent insight leaves no heading with nothing under it (the
 * page decides whether to show the whole coaching COLUMN before this ever
 * resolves — see app/(dashboard)/page.tsx).
 */
export async function TeamCoaching({ db, ...input }: { db: Db } & TeamInsightInput) {
  const insight = await getTeamInsight(db, input);
  if (!insight) return null;

  return (
    <div>
      <h3 style={{ margin: 0, font: "var(--type-title-md)", letterSpacing: "var(--tracking-title)", textWrap: "pretty" }}>
        {insight.headline}
      </h3>
      <p style={{ margin: "var(--space-4) 0 var(--space-8)", font: "var(--type-body)", color: "var(--text-secondary)", textWrap: "pretty" }}>
        {insight.body}{" "}
        <span style={{ color: "var(--accent)", fontFamily: "var(--font-figure)", fontWeight: "var(--weight-medium)" }}>
          {insight.impactEstimate}
        </span>
      </p>
      <Divider weight="subtle" space={0} />
      <h4 style={{ margin: "var(--space-6) 0 var(--space-2)", font: "var(--type-title-sm)", textWrap: "pretty" }}>
        {insight.secondary.headline}
      </h4>
      <p style={{ margin: 0, font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{insight.secondary.detail}</p>
    </div>
  );
}
