import { getDb } from "@/lib/db";
import { buildTeamOverview } from "@/lib/metrics";
import { fmtTokens, fmtUsd, fmtDelta, splitUnit } from "@/lib/format";
import { PeopleTable } from "@/components/PeopleTable";
import { UsageChart } from "@/components/UsageChart";
import { AqDisplay, Annotation, Colophon, Eyebrow, GUTTER, Sheet } from "@/components/ui";

// Typeset to docs/design/mockups/team-overview.html ("The Ledger").
export const dynamic = "force-dynamic"; // reads SQLite on every request

export default function TeamOverviewPage() {
  const o = buildTeamOverview(getDb());
  const engineers = `${o.coverage.total} engineer${o.coverage.total === 1 ? "" : "s"}`;
  const tokens = splitUnit(fmtTokens(o.tokensCurrentMonth));

  return (
    <Sheet
      maxWidth={1440}
      mastheadPad="pt-[34px] pb-[22px]"
      masthead={
        <>
          <h1 className="flex items-baseline gap-4">
            <span
              className="serif text-[34px] font-semibold tracking-[-0.02em]"
              style={{ fontVariationSettings: "'opsz' 100" }}
            >
              gnomon<span className="text-accent">.</span>
            </span>
            <span className="text-xs font-semibold tracking-[.22em] text-ink-60 uppercase">
              Team Dashboard
            </span>
          </h1>
          <div className="num text-[13px] text-ink-60">
            <b className="font-semibold text-ink">{engineers}</b>
            <span className="mx-2.5 text-ink-30" aria-hidden>
              ·
            </span>
            current window <b className="font-semibold text-ink">{o.currentMonth ?? "—"}</b>
          </div>
        </>
      }
    >
      {o.people.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <div
            className={`grid grid-cols-1 gap-y-8 ${GUTTER} pt-[30px] pb-[34px] lg:grid-cols-[1.45fr_1fr_1fr_1fr] lg:gap-y-0`}
          >
            <div className="pr-12 lg:border-r lg:border-hairline">
              <Eyebrow className="mb-0.5">Team avg AQ</Eyebrow>
              <AqDisplay
                value={o.avgAq ?? "—"}
                size="clamp(84px, 18vw, 148px)"
                ofSize={19}
                asidePad="pt-[22px]"
              >
                {o.avgAqDelta !== null && (
                  <Annotation
                    className="mt-3 text-base"
                    tone={o.avgAqDelta === 0 ? "var(--ink-60)" : "var(--accent)"}
                    arrow={o.avgAqDelta === 0 ? undefined : o.avgAqDelta > 0 ? "up" : "down"}
                  >
                    {o.avgAqDelta === 0 ? "±0" : fmtDelta(o.avgAqDelta)} vs last month
                  </Annotation>
                )}
              </AqDisplay>
            </div>

            <StatColumn
              label="Ingest coverage"
              value={String(o.coverage.withCurrentMonth)}
              unit={`/${o.coverage.total}`}
              foot={`people with a ${o.currentMonth ?? "—"} upload`}
            />
            <StatColumn label="Tokens / mo" {...tokens} foot="across all models" />
            <StatColumn
              label="Est. cost / mo"
              value={fmtUsd(o.costCurrentMonth)}
              foot="list prices · approximate"
            />
          </div>

          <div className={`${GUTTER} py-2`}>
            <div className="mb-2.5 flex items-baseline justify-between">
              <h2 className="serif text-2xl font-semibold" style={{ fontVariationSettings: "'opsz' 60" }}>
                The people
              </h2>
              <span className="num text-xs text-ink-60">
                {/* Only claim a single window when everyone is actually in it. */}
                {o.coverage.withCurrentMonth === o.people.length
                  ? `Window ${o.currentMonth ?? "—"}`
                  : "Latest window per person"}{" "}
                · sorted by AQ
              </span>
            </div>
            <PeopleTable rows={o.people} monthKey={o.currentMonth} />
          </div>

          <div className={`mt-[22px] ${GUTTER}`}>
            <hr role="presentation" className="border-0 border-t border-hairline" />
          </div>

          {o.usageOverTime.length > 0 && (
            <div className={`${GUTTER} pt-5 pb-16`}>
              <UsageChart months={o.usageOverTime} />
            </div>
          )}
        </>
      )}

      <Colophon right={`Printed from window ${o.currentMonth ?? "—"}`} />
    </Sheet>
  );
}

function StatColumn({
  label,
  value,
  unit,
  foot,
}: {
  label: string;
  value: string;
  unit?: string;
  foot: string;
}) {
  return (
    <dl className="pt-1.5 lg:border-r lg:border-hairline lg:pl-10 lg:last:border-r-0">
      <dt>
        <Eyebrow className="mb-3.5">{label}</Eyebrow>
      </dt>
      <dd className="serif num text-[44px] leading-none font-semibold tracking-[-0.01em]">
        {value}
        {unit && <small className="text-[22px] font-medium tracking-normal text-ink-60">{unit}</small>}
      </dd>
      <dd className="mt-2.5 text-[12.5px] text-ink-60">{foot}</dd>
    </dl>
  );
}

/** design-system.md §Empty state — a ruled block, not a boxed card. */
function EmptyState() {
  return (
    <div className={`${GUTTER} py-16`}>
      <Eyebrow className="mb-3">No uploads yet</Eyebrow>
      <h2
        className="serif mb-3 max-w-[24ch] text-[34px] font-semibold"
        style={{ fontVariationSettings: "'opsz' 80" }}
      >
        Point the gnomon CLI at this dashboard.
      </h2>
      <p className="mb-6 max-w-[52ch] text-sm text-ink-60">
        Each engineer runs the CLI locally and signs in once. Only summary statistics are
        uploaded — prompts and file contents never leave their machine.
      </p>
      <code className="num block max-w-[62ch] border-y border-hairline py-3.5 text-sm break-all text-ink">
        xl-ai-insights --mirdash-base=http://localhost:3000
      </code>
    </div>
  );
}
