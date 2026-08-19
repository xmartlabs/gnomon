import type { Db } from "@/lib/db";
import type { PersonProfile } from "@/lib/metrics";
import { getCoachText } from "@/lib/coach";
import { Section } from "@/components/ui";

/**
 * The one 2px terracotta rule and the one Fraunces prose block in the system
 * (design-system.md §Coach card).
 *
 * Owns its <Section> so an unconfigured or failing coach renders NOTHING — a
 * wrapper supplied by the page would still emit its padding and leave a gap
 * where the feature would have been.
 */
export async function CoachCard({ db, profile }: { db: Db; profile: PersonProfile }) {
  const text = await getCoachText(db, profile);
  if (!text) return null;

  return (
    <Section className="mt-3">
      <div className="border-t-2 border-accent pt-4 pb-1">
        <div className="mb-2.5 flex items-center gap-2.5">
          <h3 className="text-[11px] font-semibold tracking-[.18em] text-accent uppercase">AI coach</h3>
          <span className="border border-hairline px-2 py-0.5 text-[10.5px] tracking-[.06em] text-ink-60">
            optional · LLM_API_KEY
          </span>
        </div>
        <p className="serif max-w-[70ch] text-[14.5px] leading-[1.65] text-ink">{text}</p>
      </div>
    </Section>
  );
}
