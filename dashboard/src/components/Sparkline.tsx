// 1.8px polyline with an end dot — terracotta when the series rose, ink-60 when
// it fell, ink-30 when flat (design system §Sparkline).

type Box = { width: number; height: number; pad?: number };

/** Direction of a series, and how the design system paints it. */
export function drift(values: number[]) {
  const d = values.length > 1 ? values[values.length - 1] - values[0] : 0;
  return {
    delta: d,
    stroke: d > 0 ? "var(--accent)" : d < 0 ? "var(--ink-60)" : "var(--ink-30)",
    word: d > 0 ? "rising" : d < 0 ? "falling" : "flat",
  };
}

/** Series → `points` attribute, scaled to the box and inverted for SVG's y-down. */
export function polylinePoints(values: number[], { width, height, pad = 2 }: Box): string {
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const step = (width - pad * 2) / (values.length - 1);
  return values
    .map((v, i) => {
      const y = height - pad - ((v - min) / span) * (height - pad * 2);
      return `${(pad + i * step).toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function Sparkline({ points, label }: { points: number[]; label: string }) {
  const width = 96;
  const height = 26;
  if (points.length < 2) {
    return <span className="sr-only">{label}: no trend data</span>;
  }

  const { stroke, word } = drift(points);
  const coords = polylinePoints(points, { width, height });
  const [lastX, lastY] = coords.split(" ").at(-1)!.split(",");

  return (
    <svg
      className="block"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${label}: ${points[0]} to ${points[points.length - 1]} over ${points.length} windows, ${word}`}
    >
      <polyline
        points={coords}
        fill="none"
        stroke={stroke}
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r={2.4} fill={stroke} />
    </svg>
  );
}
