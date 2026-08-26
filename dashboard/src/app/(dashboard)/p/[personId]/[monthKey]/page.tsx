import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";
import { getDb } from "@/lib/db";
import { buildPersonProfile, type PersonProfile } from "@/lib/metrics";
import { coachEnabled } from "@/lib/coach";
import { fmtMonthShort } from "@/lib/format";
import { SectionLabel } from "@/components/ds/SectionLabel";
import { Divider } from "@/components/ds/Divider";
import { Badge } from "@/components/ds/Badge";
import { ColumnChart } from "@/components/ds/ColumnChart";
import { PillarBar } from "@/components/ds/PillarBar";
import { Metric } from "@/components/ds/Metric";
import { SuggestionsCard } from "@/components/SuggestionsCard";

export const dynamic = "force-dynamic";

/** Beyond ~8 the columns become slivers; keep the most recent windows. */
const MAX_LEVEL_BARS = 8;

const PILLAR_ORDER = ["Breadth", "Craft", "Efficiency", "Savvy"];

export default async function PersonProfilePage({
  params,
}: {
  params: Promise<{ personId: string; monthKey: string }>;
}) {
  const { personId, monthKey } = await params;
  const id = Number(personId);
  const db = getDb();
  const p = Number.isSafeInteger(id) && id > 0 ? buildPersonProfile(db, id, monthKey) : null;
  if (!p) notFound();

  const coachOn = coachEnabled();
  const levels = p.levelOverTime.slice(-MAX_LEVEL_BARS);
  const pillarsByName = new Map(p.pillars.map((pillar) => [pillar.name, pillar]));

  return (
    <div>
      <nav aria-label="breadcrumb" style={{ marginBottom: "var(--space-9)" }}>
        <Link href="/" style={{ font: "var(--type-body)", color: "var(--accent)", borderBottom: "var(--rule-width) solid currentColor" }}>
          ← Team
        </Link>
      </nav>

      <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--space-10)", flexWrap: "wrap" }}>
        <div style={{ maxWidth: 460 }}>
          <h1 style={{ margin: 0, font: "var(--type-title-lg)", fontSize: 40, letterSpacing: "var(--tracking-title)" }}>{p.name}</h1>
          <div
            style={{
              fontFamily: "var(--font-figure)",
              fontSize: "var(--size-label-lg)",
              letterSpacing: "var(--tracking-label)",
              textTransform: "uppercase",
              color: "var(--text-tertiary)",
              margin: "var(--space-3) 0 var(--space-5)",
            }}
          >
            {p.email}
          </div>
          {p.archetype?.quote && (
            <p style={{ margin: 0, font: "var(--type-title-sm)", fontStyle: "italic", color: "var(--text-secondary)", textWrap: "pretty" }}>
              “{p.archetype.title ? `${p.archetype.title} — ${p.archetype.quote}` : p.archetype.quote}”
            </p>
          )}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "baseline", gap: "var(--space-6)" }}>
          <span style={{ font: "var(--type-metric-lg)", fontSize: 96, letterSpacing: "var(--tracking-metric)", fontVariantNumeric: "tabular-nums" }}>
            {p.aq}
          </span>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            <span style={{ font: "var(--type-body)", fontFamily: "var(--font-figure)", color: "var(--text-secondary)" }}>/100</span>
            <Badge tone={p.tier === "Elite" ? "accent" : "neutral"}>{p.tier}</Badge>
          </div>
        </div>
      </div>

      <Divider weight="default" space={10} />

      <div
        style={
          coachOn
            ? { display: "grid", gridTemplateColumns: "1fr auto 1.25fr", gap: "var(--layout-column-gap)", alignItems: "start" }
            : undefined
        }
      >
        {coachOn && (
          <>
            <section>
              <SectionLabel as="h2" size="lg" hint="Each suggestion comes from one specific rubric axis.">
                Suggestions
              </SectionLabel>
              <Suspense fallback={null}>
                <SuggestionsCard db={db} profile={p} />
              </Suspense>
            </section>
            <Divider orientation="vertical" />
          </>
        )}
        <section>
          <SectionLabel as="h2" size="lg" hint="The gstack scorecard judges how you build; AQ judges how you operate the machine.">
            Scorecard
          </SectionLabel>
          <Scorecard scorecard={p.scorecard} />
          {levels.length > 0 && (
            <>
              <Divider weight="subtle" space={8} />
              <SectionLabel as="h3">Level over time</SectionLabel>
              <ColumnChart
                height={110}
                data={levels.map((l) => ({ label: fmtMonthShort(l.monthKey), value: l.aq, emphasis: l.monthKey === p.monthKey }))}
                ariaLabel={`${p.name}'s AQ, last ${levels.length} months`}
              />
            </>
          )}
        </section>
      </div>

      <Divider weight="default" space={11} />

      {p.pillars.length > 0 && (
        <>
          <SectionLabel as="h2" size="lg">
            How they operate agents · four pillars
          </SectionLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "var(--space-10)" }}>
            {PILLAR_ORDER.filter((name) => pillarsByName.has(name)).map((name) => {
              const pillar = pillarsByName.get(name)!;
              return (
                <div key={name} style={{ borderTop: "var(--rule-width-strong) solid var(--rule-strong)", paddingTop: "var(--space-5)" }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-4)", marginBottom: "var(--space-6)" }}>
                    <span style={{ font: "var(--type-title-sm)" }}>{pillar.name}</span>
                    <span style={{ marginLeft: "auto", fontFamily: "var(--font-figure)", fontSize: "var(--size-metric-sm)", fontWeight: "var(--weight-medium)" }}>
                      {Math.round(pillar.score)}
                    </span>
                    <span style={{ fontFamily: "var(--font-figure)", fontSize: "var(--size-label)", color: "var(--text-tertiary)" }}>
                      /{pillar.weight}
                    </span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
                    {pillar.axes.map((axis) => (
                      <PillarBar key={axis.name} name={axis.name} value={Number(axis.score.toFixed(1))} max={10} size="sm" />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          <Divider weight="default" space={11} />
        </>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1.35fr auto 1fr", gap: "var(--layout-column-gap)", alignItems: "start" }}>
        <section>
          <SectionLabel as="h2" size="lg" hint="Deterministic counters: they don't judge, they just count.">
            Explore
          </SectionLabel>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "var(--space-8) var(--space-9)" }}>
            {p.explore.map((c) => (
              <div key={c.label}>
                <div style={{ font: "var(--type-metric-sm)", fontVariantNumeric: "tabular-nums" }}>
                  {c.value}
                  {c.unit && <small style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)" }}>{c.unit}</small>}
                </div>
                <div style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)", textWrap: "pretty" }}>{c.label.toLowerCase()}</div>
              </div>
            ))}
          </div>
        </section>
        <Divider orientation="vertical" />
        <section>
          <SectionLabel as="h2" size="lg">
            Usage this month
          </SectionLabel>
          <div style={{ display: "flex", gap: "var(--space-9)", marginBottom: "var(--space-8)" }}>
            <Metric value={p.usage.sessions.toLocaleString("en-US")} caption="sessions" size="sm" />
            <Metric value={p.usage.prompts.toLocaleString("en-US")} caption="prompts" size="sm" />
            <Metric value={String(p.usage.actionsPerPrompt)} caption="actions/prompt" size="sm" />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            {p.modelMix.map((m) => (
              <PillarBar key={m.model} name={m.model} value={Math.round(m.pct * 100)} size="sm" tone={m.pct < 0.3 ? "muted" : undefined} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function Scorecard({ scorecard }: { scorecard: PersonProfile["scorecard"] }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "var(--space-8)" }}>
      {scorecard.map((s) => (
        <div key={s.key}>
          <div style={{ font: "var(--type-metric-md)", letterSpacing: "var(--tracking-metric)" }}>{s.value ?? "—"}</div>
          <div style={{ font: "var(--type-body)", marginTop: "var(--space-1)", textTransform: "capitalize" }}>{s.key}</div>
          <div style={{ font: "var(--type-body-sm)", color: "var(--text-secondary)", textWrap: "pretty" }}>{s.gloss}</div>
        </div>
      ))}
    </div>
  );
}
