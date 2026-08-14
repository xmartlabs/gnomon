import { LegendRow, seriesColor } from "./ui";

type Mix = { model: string; pct: number }[];

/**
 * Segments split by a 2px paper gap, never borders (design system §Bars).
 * `pct` is a 0..1 fraction (summary.py rounds turns/model_total to 3 places).
 */
export function ModelMixBar({ mix }: { mix: Mix }) {
  const shown = mix.filter((m) => m.pct > 0);
  if (!shown.length) return <div className="text-[13px] text-ink-60">No model data</div>;

  return (
    <div>
      {/* The bar restates the legend below it, so it carries no label of its own. */}
      <div aria-hidden className="mt-3 mb-3.5 flex h-3.5">
        {shown.map((m, i) => (
          <span
            key={m.model}
            className="border-l-2 border-paper first:border-l-0"
            style={{ width: `${m.pct * 100}%`, background: seriesColor(i) }}
          />
        ))}
      </div>
      <div className="text-[13px]">
        {shown.map((m, i) => (
          <LegendRow
            key={m.model}
            color={seriesColor(i)}
            label={m.model}
            value={`${Math.round(m.pct * 100)}%`}
            swatch={13}
          />
        ))}
      </div>
    </div>
  );
}
