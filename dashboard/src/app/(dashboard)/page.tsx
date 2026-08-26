import { Suspense } from "react";
import { getDb } from "@/lib/db";
import { buildTeamOverview } from "@/lib/metrics";
import { coachEnabled } from "@/lib/coach";
import { fmtTokens, fmtUsd, fmtMonthLabel, fmtMonthShort } from "@/lib/format";
import { Metric } from "@/components/ds/Metric";
import { Trend } from "@/components/ds/Trend";
import { ColumnChart } from "@/components/ds/ColumnChart";
import { Divider } from "@/components/ds/Divider";
import { SectionLabel } from "@/components/ds/SectionLabel";
import { PillarBar } from "@/components/ds/PillarBar";
import { DonutChart } from "@/components/ds/DonutChart";
import { EmptyState } from "@/components/ds/EmptyState";
import Link from "next/link";
import { PeopleTable } from "@/components/PeopleTable";
import { TierSplit } from "@/components/TierSplit";
import { TeamCoaching } from "@/components/TeamCoaching";

export const dynamic = "force-dynamic"; // reads SQLite on every request

export default async function TeamDashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const { month } = await searchParams;
  const db = getDb();
  const o = buildTeamOverview(db, month);
  const coachOn = coachEnabled();
  const monthLabel = o.currentMonth ? fmtMonthLabel(o.currentMonth) : "—";

  const heading = (
    <h1 style={{ margin: "0 0 var(--space-8)", font: "var(--type-title-lg)", letterSpacing: "var(--tracking-title)" }}>
      Team · <span style={{ fontFamily: "var(--font-figure)", fontWeight: "var(--weight-medium)" }}>{monthLabel}</span>
    </h1>
  );

  // Fresh deploy: nobody has ever uploaded. Never show empty figures beside
  // the h1 — replace the whole content region, and always offer a way out.
  if (o.people.length === 0) {
    return (
      <div>
        {heading}
        <EmptyState
          label={monthLabel}
          title="Nobody has uploaded sessions yet."
          body={
            <span>
              Data shows up once someone runs{" "}
              <code style={{ fontFamily: "var(--font-figure)", fontSize: 14 }}>
                xl-ai-insights --mirdash-base=http://localhost:3000
              </code>{" "}
              pointed at this server.
            </span>
          }
        />
      </div>
    );
  }

  // A real month with uploads but nothing AQ-parseable in them.
  if (o.currentMonth !== null && o.coverage.withCurrentMonth === 0) {
    const backTo = o.availableMonths.find((m) => m !== o.currentMonth) ?? null;
    return (
      <div>
        {heading}
        <EmptyState
          label={monthLabel}
          title={`Nobody uploaded sessions in ${monthLabel}.`}
          body={
            <span>
              Data shows up once someone runs{" "}
              <code style={{ fontFamily: "var(--font-figure)", fontSize: 14 }}>gnomon push</code> pointed at this
              server.
            </span>
          }
          action={
            backTo && (
              <Link
                href={`/?month=${backTo}`}
                style={{ font: "var(--type-body)", color: "var(--accent)", borderBottom: "var(--rule-width) solid currentColor" }}
              >
                ← Back to {fmtMonthLabel(backTo)}
              </Link>
            )
          }
        />
      </div>
    );
  }

  const prevMonthShort =
    o.teamAqTrend.length > 1 ? fmtMonthShort(o.teamAqTrend[o.teamAqTrend.length - 2].monthKey) : undefined;

  return (
    <div>
      {heading}

      <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--space-10)", flexWrap: "wrap" }}>
        <Metric
          label="Team AQ"
          value={o.avgAq ?? "—"}
          unit="/100"
          size="xl"
          trailing={o.avgAqDelta !== null && <Trend delta={o.avgAqDelta} against={prevMonthShort} size="lg" />}
        />
        {o.teamAqTrend.length > 0 && (
          <div style={{ width: 210, flex: "none" }}>
            <ColumnChart
              height={96}
              data={o.teamAqTrend.map((t) => ({ label: fmtMonthShort(t.monthKey), value: t.aq }))}
              ariaLabel="Team AQ over the last few months"
            />
          </div>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: "var(--space-9)" }}>
          <Metric
            label="Tokens"
            value={fmtTokens(o.tokensCurrentMonth)}
            size="md"
            align="right"
            trailing={o.tokensDelta !== null && <Trend delta={o.tokensDelta} format={fmtTokens} />}
          />
          <Metric
            label="Cost"
            value={fmtUsd(o.costCurrentMonth)}
            size="md"
            align="right"
            trailing={o.costDelta !== null && <Trend delta={o.costDelta} format={fmtUsd} />}
          />
        </div>
      </div>

      <Divider weight="default" space={11} />

      <div
        style={
          coachOn
            ? { display: "grid", gridTemplateColumns: "1.15fr auto 1fr", gap: "var(--layout-column-gap)", alignItems: "start" }
            : undefined
        }
      >
        <section>
          <SectionLabel
            as="h2"
            size="lg"
            hint="Average pillar score among people who uploaded data this month. Breadth = how much machinery you move · Craft = how well · Efficiency = the return on each intervention · Savvy = judgment"
          >
            Four pillars
          </SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-7)" }}>
            {o.pillarAverages.map((p) => (
              <PillarBar key={p.name} name={p.name} weight={`${p.weight}%`} value={Math.round(p.avgScore)} max={p.weight} />
            ))}
          </div>
        </section>
        {coachOn && (
          <>
            <Divider orientation="vertical" />
            <section>
              <SectionLabel as="h2" size="lg">
                What to improve this month
              </SectionLabel>
              <Suspense fallback={null}>
                <TeamCoaching
                  db={db}
                  monthKey={o.currentMonth ?? ""}
                  pillarAverages={o.pillarAverages}
                  coverage={o.coverage}
                  avgAqDelta={o.avgAqDelta}
                />
              </Suspense>
            </section>
          </>
        )}
      </div>

      <Divider weight="default" space={11} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: "var(--layout-column-gap)", alignItems: "start" }}>
        <section>
          <SectionLabel as="h2" size="lg" hint="Token distribution by model this month. Hover a slice to see its percentage.">
            Most used models
          </SectionLabel>
          {o.modelMix.length > 0 ? (
            <DonutChart data={o.modelMix.map((m) => ({ label: m.model, value: Math.round(m.pct * 100) }))} size={176} />
          ) : (
            <p style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>No model data this month.</p>
          )}
        </section>
        <Divider orientation="vertical" />
        <section>
          <SectionLabel as="h2" size="lg">
            How the team breaks down
          </SectionLabel>
          <TierSplit counts={o.tierDistribution} uploaded={o.coverage.withCurrentMonth} />
        </section>
      </div>

      <h2 style={{ font: "var(--type-title-lg)", letterSpacing: "var(--tracking-title)", margin: "var(--space-13) 0 var(--space-7)" }}>
        People
      </h2>
      <PeopleTable rows={o.people} monthKey={o.currentMonth} />
    </div>
  );
}
