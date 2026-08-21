"use client";
import { useState } from "react";
import type { MonthUsage } from "@/lib/metrics";
import { fmtTokens, fmtUsd } from "@/lib/format";
import { Eyebrow, LegendRow, SectionTitle, seriesColor } from "./ui";

// Flat stacked fills on a 2px ink baseline with dashed hairline gridlines
// (design system §Bars). Hand-built rather than charted: the mockup's grammar
// is rules and flat fills, which a chart library would fight.

const CHART_H = 300;
const GRIDLINES = 3;
/** Beyond a year the columns collapse to slivers, so show the last 12 months. */
const MAX_MONTHS = 12;

// Gaps shrink with the viewport — fixed 96px tracks overflow the sheet once a
// team has ~11 months of history.
const COLUMNS = (n: number) => ({
  gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`,
  columnGap: "min(96px, 8%)",
  paddingInline: "min(48px, 4%)",
});

type Unit = "tokens" | "cost";

function niceStep(max: number): number {
  // The largest round step (1, 2, 2.5 or 5 × a power of ten) at or below
  // max/GRIDLINES — rounding UP would push the first line past the tallest bar
  // and leave the chart with a single stray gridline.
  const raw = max / GRIDLINES || 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const candidates = [1, 2, 2.5, 5, 10].map((m) => m * pow);
  return candidates.findLast((s) => s <= raw) ?? candidates[0];
}

export function UsageChart({ months: all }: { months: MonthUsage[] }) {
  const [unit, setUnit] = useState<Unit>("tokens");
  const months = all.slice(-MAX_MONTHS);
  const fmt = unit === "tokens" ? fmtTokens : fmtUsd;
  const valueOf = (m: { tokens: number; cost: number }) => (unit === "tokens" ? m.tokens : m.cost);

  const totals = months.map((m) => m.byModel.reduce((s, x) => s + valueOf(x), 0));
  const max = Math.max(...totals, 0);
  const step = niceStep(max);
  // Leave headroom for the total label that sits above the tallest stack.
  const scale = max > 0 ? (CHART_H - 42) / max : 0;

  // Ranked by total volume, not by arrival order: the series colours carry
  // meaning (ink → terracotta → parchment), so the heaviest model must land on
  // ink whichever order the payload happened to list the models in.
  const volume = new Map<string, number>();
  for (const m of months) {
    for (const x of m.byModel) volume.set(x.modelId, (volume.get(x.modelId) ?? 0) + x.tokens);
  }
  const order = [...volume.entries()].sort((a, b) => b[1] - a[1]).map(([id]) => id);
  const labelOf = new Map(months.flatMap((m) => m.byModel.map((x) => [x.modelId, x.model] as const)));
  const last = months.at(-1);

  return (
    <div>
      <SectionTitle
        note={
          <div className="inline-flex overflow-hidden rounded-[2px] border border-ink" role="group" aria-label="Chart unit">
            {(["tokens", "cost"] as Unit[]).map((u) => (
              <button
                key={u}
                type="button"
                aria-pressed={unit === u}
                onClick={() => setUnit(u)}
                className={`cursor-pointer px-[18px] py-2 text-xs font-semibold tracking-[.08em] uppercase ${
                  unit === u ? "bg-ink text-paper" : "text-ink-60"
                }`}
              >
                {u === "tokens" ? "Tokens" : "Cost"}
              </button>
            ))}
          </div>
        }
      >
        Company usage over time
      </SectionTitle>

      <div className="grid grid-cols-1 items-end gap-12 lg:grid-cols-[1fr_220px]">
        <div className="min-w-0">
          {/* The plot is decorative: the same numbers are in the sr-only table. */}
          <div
            aria-hidden
            className="relative grid items-end border-b-2 border-ink"
            style={{ height: CHART_H, ...COLUMNS(months.length) }}
          >
            {Array.from({ length: GRIDLINES + 2 }, (_, i) => step * (i + 1))
              .filter((v) => v <= max && v * scale < CHART_H)
              .map((v) => (
                <div
                  key={v}
                  className="absolute right-[min(48px,4%)] left-[min(48px,4%)] border-t border-dashed border-hairline"
                  style={{ bottom: v * scale }}
                >
                  <span className="num absolute top-[-8px] right-full mr-2.5 text-[11px] whitespace-nowrap text-ink-30">
                    {fmt(v)}
                  </span>
                </div>
              ))}

            {months.map((m, mi) => (
              <div key={m.monthKey} className="relative z-1 flex h-full flex-col justify-end">
                <div className="serif num mb-2 text-center text-[17px] font-semibold">{fmt(totals[mi])}</div>
                {order
                  .map((id, si) => ({ seg: m.byModel.find((x) => x.modelId === id), id, si }))
                  .filter(({ seg }) => seg && valueOf(seg) > 0)
                  .map(({ seg, id, si }, rendered) => (
                    <div
                      key={id}
                      className={rendered > 0 ? "w-full border-t-2 border-paper" : "w-full"}
                      style={{ height: valueOf(seg!) * scale, background: seriesColor(si) }}
                    />
                  ))}
              </div>
            ))}
          </div>

          <div className="grid pt-2.5" style={COLUMNS(months.length)}>
            {months.map((m) => (
              <div
                key={m.monthKey}
                className="num text-center text-xs font-semibold tracking-[.14em] text-ink-60 uppercase"
              >
                {m.monthKey}
              </div>
            ))}
          </div>

          <table className="sr-only">
            <caption>Company usage over time, by model, in {unit}</caption>
            <thead>
              <tr>
                <th scope="col">Window</th>
                {order.map((id) => (
                  <th key={id} scope="col">
                    {labelOf.get(id) ?? id}
                  </th>
                ))}
                <th scope="col">Total</th>
              </tr>
            </thead>
            <tbody>
              {months.map((m, mi) => (
                <tr key={m.monthKey}>
                  <th scope="row">{m.monthKey}</th>
                  {order.map((id) => {
                    const seg = m.byModel.find((x) => x.modelId === id);
                    return <td key={id}>{seg ? fmt(valueOf(seg)) : "—"}</td>;
                  })}
                  <td>{fmt(totals[mi])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="pb-[34px]">
          <Eyebrow className="mb-3.5">By model · {last?.monthKey ?? "—"}</Eyebrow>
          {order.map((id, i) => {
            const seg = last?.byModel.find((x) => x.modelId === id);
            return (
              <LegendRow
                key={id}
                color={seriesColor(i)}
                label={labelOf.get(id) ?? id}
                value={seg ? fmt(valueOf(seg)) : "—"}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
