import type { PersonProfile } from "@/lib/metrics";

type Pillar = PersonProfile["pillars"][number];

/** One of four ruled columns: name + score/weight, a terracotta track, then axes. */
export function PillarBar({ pillar }: { pillar: Pillar }) {
  const pct = pillar.weight > 0 ? Math.min(100, (pillar.score / pillar.weight) * 100) : 0;
  return (
    <div className="lg:border-r lg:border-hairline lg:px-[26px] lg:first:pl-0 lg:last:border-r-0 lg:last:pr-0">
      <div className="flex items-baseline justify-between border-t-2 border-ink pt-3">
        <h3 className="serif text-base font-semibold">{pillar.name}</h3>
        <span className="serif num text-[18px] font-semibold">
          {Math.round(pillar.score)}
          <small className="text-xs font-medium text-ink-60">/{pillar.weight}</small>
        </span>
      </div>
      {/* The fill restates the score/weight above it, so it is decorative. */}
      <div aria-hidden className="mt-3 h-1 bg-paper-2">
        <div className="h-1 bg-accent" style={{ width: `${pct}%` }} />
      </div>
      {pillar.axes.length > 0 && (
        <div className="mt-3.5">
          {pillar.axes.map((a) => (
            <div
              key={a.name}
              className="flex justify-between border-b border-hairline py-1.5 text-[12.5px] text-ink-60 last:border-b-0"
            >
              <span>{a.name}</span>
              <span className="num text-ink">
                {a.score.toFixed(1)}
                <span className="sr-only"> out of 10</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
