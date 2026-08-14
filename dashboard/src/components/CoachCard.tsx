import type { Db } from "@/lib/db";
import type { PersonProfile } from "@/lib/metrics";
import { getCoachText } from "@/lib/coach";

/**
 * The one 2px terracotta rule and the one Fraunces prose block in the system
 * (design-system.md §Coach card). Rendered only when the coach produced text —
 * an unconfigured or failing coach leaves no trace on the page.
 */
export async function CoachCard({ db, profile }: { db: Db; profile: PersonProfile }) {
  const text = await getCoachText(db, profile);
  if (!text) return null;

  return (
    <div className="border-t-2 border-accent pt-4 pb-1">
      <div className="mb-2.5 flex items-center gap-2.5">
        <h3 className="text-[11px] font-semibold tracking-[.18em] text-accent uppercase">AI coach</h3>
        <span className="border border-hairline px-2 py-0.5 text-[10.5px] tracking-[.06em] text-ink-60">
          optional · LLM_API_KEY
        </span>
      </div>
      <p className="serif max-w-[70ch] text-[14.5px] leading-[1.65] text-ink">{text}</p>
    </div>
  );
}
