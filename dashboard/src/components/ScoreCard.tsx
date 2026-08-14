import type { PersonProfile } from "@/lib/metrics";
import { drift, polylinePoints } from "./Sparkline";
import { Eyebrow } from "./ui";

type Score = PersonProfile["scorecard"][number];

/** Execution / Planning / Engineering, each with its own trend polyline. */
export function ScoreCard({ score }: { score: Score }) {
  const values = score.trend.map((t) => t.value);
  const { stroke, word } = drift(values);

  return (
    <div className="px-8 sm:border-r sm:border-hairline sm:first:pl-0 sm:last:border-r-0 sm:last:pr-0">
      <div className="border-t-2 border-ink pt-3">
        <Eyebrow as="h3">{score.key}</Eyebrow>
        <div className="serif num mt-2 text-[38px] leading-none font-semibold">
          {score.value === null ? (
            <span className="text-ink-30">
              <span aria-hidden>—</span>
              <span className="sr-only">not reported</span>
            </span>
          ) : (
            <>
              {score.value.toFixed(1)}
              <small className="text-[17px] font-medium text-ink-60">/10</small>
            </>
          )}
        </div>
        <div className="mt-2 mb-3.5 min-h-[34px] text-[12.5px] text-ink-60">{score.gloss}</div>
        {values.length > 1 ? (
          <>
            <svg width="100%" height="34" viewBox="0 0 200 34" preserveAspectRatio="none" aria-hidden>
              <polyline
                points={polylinePoints(values, { width: 200, height: 34, pad: 4 })}
                fill="none"
                stroke={stroke}
                strokeWidth={1.6}
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <span className="sr-only">
              {word} over {values.length} windows
            </span>
          </>
        ) : (
          <div className="h-[34px]" aria-hidden />
        )}
      </div>
    </div>
  );
}
