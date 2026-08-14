import Link from "next/link";
import { notFound } from "next/navigation";
import { getDb } from "@/lib/db";
import { buildPersonProfile } from "@/lib/metrics";
import { fmtDelta } from "@/lib/format";
import { PillarBar } from "@/components/PillarBar";
import { ScoreCard } from "@/components/ScoreCard";
import { ModelMixBar } from "@/components/ModelMixBar";
import {
  AqDisplay, Annotation, Colophon, REPORT_NAME, Section, SectionTitle, Sheet, TierBadge,
} from "@/components/ui";

// Typeset to docs/design/mockups/person-profile.html ("The Ledger").
export const dynamic = "force-dynamic";

/** Beyond a year the columns become slivers; keep the most recent windows. */
const MAX_LEVEL_BARS = 12;

export default async function PersonProfilePage({
  params,
}: {
  params: Promise<{ personId: string; monthKey: string }>;
}) {
  const { personId, monthKey } = await params;
  const id = Number(personId);
  const p = Number.isSafeInteger(id) && id > 0 ? buildPersonProfile(getDb(), id, monthKey) : null;
  if (!p) notFound();

  const levels = p.levelOverTime.slice(-MAX_LEVEL_BARS);

  return (
    <Sheet
      maxWidth={1200}
      mastheadPad="pt-[22px] pb-[18px]"
      masthead={
        <>
          <Link href="/" className="text-[13px] text-ink-60 hover:text-accent">
            ← The people
          </Link>
          <div className="flex items-center gap-4 text-[13px]">
            <MonthLink personId={p.personId} monthKey={p.prevMonthKey} dir="Previous" glyph="‹" />
            <span className="serif num font-semibold">{p.monthKey}</span>
            <MonthLink personId={p.personId} monthKey={p.nextMonthKey} dir="Next" glyph="›" />
          </div>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-8 px-[72px] pt-6 pb-5 lg:grid-cols-[1.5fr_1fr] lg:gap-0">
        <div className="min-w-0">
          <div className="serif text-[15px] font-semibold text-ink-60">{REPORT_NAME}</div>
          <h1
            className="serif my-1.5 text-[52px] leading-none font-semibold tracking-[-0.02em] break-words"
            style={{ fontVariationSettings: "'opsz' 110" }}
          >
            {p.name}
          </h1>
          <div className="num text-[13px] break-all text-ink-60">{p.email}</div>
          {p.archetype?.title && (
            <div className="serif mt-4 max-w-[34ch] text-[17px] italic">
              <b className="font-semibold text-accent not-italic">{p.archetype.title}</b>
              {p.archetype.quote && <> — “{p.archetype.quote}”</>}
            </div>
          )}
        </div>

        <div className="lg:border-l lg:border-hairline lg:pl-11">
          <AqDisplay value={p.aq} size="clamp(72px, 16vw, 120px)" ofSize={17} asidePad="pt-4">
            <div className="mt-2.5">
              <TierBadge tier={p.tier} size={13} />
            </div>
            {p.delta !== null && p.delta !== 0 && (
              <Annotation
                className="mt-2 text-[15px]"
                tone={p.delta > 0 ? "var(--gain)" : "var(--loss)"}
                arrow={p.delta > 0 ? "up" : "down"}
              >
                {fmtDelta(p.delta)} pts
                {p.levelOverTime.at(-2) && ` vs ${p.levelOverTime.at(-2)!.monthKey}`}
              </Annotation>
            )}
          </AqDisplay>
        </div>
      </div>

      {/* A first upload still gets the section — one bar is the person's whole
          history, and hiding it drops required context from new profiles. */}
      {levels.length > 0 && (
        <Section>
          <SectionTitle note={`${levels.length} window${levels.length === 1 ? "" : "s"}`}>
            Level over time
          </SectionTitle>
          <LevelBars points={levels} current={p.monthKey} />
        </Section>
      )}

      {p.pillars.length > 0 && (
        <Section>
          <SectionTitle note="four pillars">How you operate agents</SectionTitle>
          <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4 lg:gap-0">
            {p.pillars.map((pillar) => (
              <PillarBar key={pillar.name} pillar={pillar} />
            ))}
          </div>
        </Section>
      )}

      <Section>
        <SectionTitle>Scorecard</SectionTitle>
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-3 sm:gap-0">
          {p.scorecard.map((s) => (
            <ScoreCard key={s.key} score={s} />
          ))}
        </div>
      </Section>

      <Section>
        <SectionTitle>Explore</SectionTitle>
        <dl className="grid grid-cols-1 border-t border-l border-hairline min-[420px]:grid-cols-2 sm:grid-cols-4">
          {p.explore.map((t) => (
            <div key={t.label} className="border-r border-b border-hairline px-[18px] py-4">
              <dt className="mb-2 text-[10.5px] font-semibold tracking-[.14em] text-ink-60 uppercase">
                {t.label}
              </dt>
              <dd className="serif num text-[26px] font-semibold">
                {t.value}
                {t.unit && <small className="text-[13px] font-medium text-ink-60">{t.unit}</small>}
              </dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section>
        <SectionTitle>Usage</SectionTitle>
        <div className="grid grid-cols-1 gap-14 lg:grid-cols-2">
          <dl className="grid grid-cols-1 border-t-2 border-ink sm:grid-cols-3">
            <UsageCell label="Sessions" value={p.usage.sessions.toLocaleString("en-US")} />
            <UsageCell label="Prompts" value={p.usage.prompts.toLocaleString("en-US")} />
            <UsageCell label="Actions / prompt" value={String(p.usage.actionsPerPrompt)} />
          </dl>
          <div>
            <div className="border-t-2 border-ink pt-3 text-[10.5px] font-semibold tracking-[.14em] text-ink-60 uppercase">
              Model mix
            </div>
            <ModelMixBar mix={p.modelMix} />
          </div>
        </div>
      </Section>

      <Colophon right={`Window ${p.monthKey} · ${p.name}`} pad="mt-[26px] pt-4.5 pb-10" />
    </Sheet>
  );
}

function MonthLink({
  personId,
  monthKey,
  dir,
  glyph,
}: {
  personId: number;
  monthKey: string | null;
  dir: string;
  glyph: string;
}) {
  if (!monthKey) {
    return (
      <span className="serif text-[18px] text-ink-30" aria-hidden>
        {glyph}
      </span>
    );
  }
  return (
    <Link
      href={`/p/${personId}/${monthKey}`}
      aria-label={`${dir} window, ${monthKey}`}
      className="serif text-[18px] hover:text-accent"
    >
      <span aria-hidden>{glyph}</span>
    </Link>
  );
}

function UsageCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="py-3.5">
      <dt className="text-[10.5px] font-semibold tracking-[.14em] text-ink-60 uppercase">{label}</dt>
      <dd className="serif num mt-1.5 text-[clamp(22px,3.5vw,32px)] font-semibold">{value}</dd>
    </div>
  );
}

/** Most recent window inked, older ones parchment (design system §Bars). */
function LevelBars({ points, current }: { points: { monthKey: string; aq: number }[]; current: string }) {
  // AQ is an absolute 0–100 score, so the bars are read against 100 rather than
  // against the person's own best month — normalising to the max would make a
  // 70→74 drift look like the difference between empty and full.
  const cols = {
    gridTemplateColumns: `repeat(${points.length}, minmax(0, 140px))`,
    gap: "min(56px, 5%)",
  };
  return (
    <>
      <div className="grid h-[150px] items-end border-b-2 border-ink" style={cols}>
        {points.map((pt) => (
          <div key={pt.monthKey} className="flex h-full flex-col items-center justify-end">
            <span className="serif num mb-2 text-[18px] font-semibold">
              {pt.aq}
              {pt.monthKey === current && <span className="sr-only"> (current window)</span>}
            </span>
            <div
              aria-hidden
              className="w-full"
              style={{
                height: `${Math.min(100, Math.max(4, pt.aq))}%`,
                background: pt.monthKey === current ? "var(--ink)" : "var(--parch)",
              }}
            />
          </div>
        ))}
      </div>
      <div className="grid pt-2.5" style={cols}>
        {points.map((pt) => (
          <div
            key={pt.monthKey}
            className="num text-center text-[11px] font-semibold tracking-[.14em] text-ink-60 uppercase"
          >
            {pt.monthKey}
          </div>
        ))}
      </div>
    </>
  );
}
