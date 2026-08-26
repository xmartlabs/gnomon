"use client";

import { useState } from "react";

export type DonutDatum = { label: string; value: number; color?: string };

const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];

/**
 * Legend shows names only, no percentages — the resting state stays quiet;
 * numbers live in the hover. Hover/focus on a slice OR its legend row
 * offsets the slice 4px along its mid-angle and opens a centred tooltip.
 */
export function DonutChart({
  data,
  size = 176,
  thickness,
  legend = true,
  ariaLabel,
}: {
  data: DonutDatum[];
  size?: number;
  thickness?: number;
  legend?: boolean;
  ariaLabel?: string;
}) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const [active, setActive] = useState(-1);
  const r = 46;
  const inner = thickness ? 46 - thickness : 0;

  let acc = 0;
  const slices = data.map((d, i) => {
    const a0 = (acc / total) * Math.PI * 2 - Math.PI / 2;
    acc += d.value;
    const a1 = (acc / total) * Math.PI * 2 - Math.PI / 2;
    const mid = (a0 + a1) / 2;
    // Rounded to 2dp: Math.cos/sin can differ in their last bit between a
    // server render and client hydration for the same input, which turns
    // into a byte-different `d` string and a hydration mismatch React "won't
    // patch up" — rounding collapses that noise below anything that matters
    // at this chart's size.
    const p = (a: number, rad: number): [number, number] => [
      Math.round((50 + rad * Math.cos(a)) * 100) / 100,
      Math.round((50 + rad * Math.sin(a)) * 100) / 100,
    ];
    const o0 = p(a0, r);
    const o1 = p(a1, r);
    const large = d.value / total > 0.5 ? 1 : 0;
    let path: string;
    if (inner > 0) {
      const i1 = p(a1, inner);
      const i0 = p(a0, inner);
      path =
        `M${o0[0]} ${o0[1]} A${r} ${r} 0 ${large} 1 ${o1[0]} ${o1[1]} ` +
        `L${i1[0]} ${i1[1]} A${inner} ${inner} 0 ${large} 0 ${i0[0]} ${i0[1]} Z`;
    } else {
      path = `M50 50 L${o0[0]} ${o0[1]} A${r} ${r} 0 ${large} 1 ${o1[0]} ${o1[1]} Z`;
    }
    const pct = Math.round((d.value / total) * 100);
    return {
      path,
      color: d.color ?? PALETTE[i % PALETTE.length],
      label: d.label,
      pct,
      dx: Math.round(Math.cos(mid) * 4 * 100) / 100,
      dy: Math.round(Math.sin(mid) * 4 * 100) / 100,
    };
  });

  const shown = active >= 0 ? slices[active] : null;

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "var(--space-9)" }}>
      <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
        <svg
          viewBox="0 0 100 100"
          style={{ width: "100%", height: "100%", overflow: "visible" }}
          role="group"
          aria-label={ariaLabel ?? data.map((d) => `${d.label} ${Math.round((d.value / total) * 100)}%`).join(", ")}
        >
          {slices.map((s, i) => (
            <path
              key={s.label}
              d={s.path}
              fill={s.color}
              stroke="var(--surface-page)"
              strokeWidth={0.8}
              tabIndex={0}
              focusable="true"
              aria-label={`${s.label}: ${s.pct}%`}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(-1)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(-1)}
              style={{
                cursor: "pointer",
                transform: active === i ? `translate(${s.dx}px,${s.dy}px)` : "none",
                transformOrigin: "50px 50px",
                transition: "transform var(--duration-fast) var(--ease-out)",
              }}
            />
          ))}
        </svg>
        {shown && (
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              transform: "translate(-50%,-50%)",
              pointerEvents: "none",
              background: "var(--surface-raised)",
              border: "var(--rule-width) solid var(--rule-strong)",
              padding: "var(--space-2) var(--space-4)",
              whiteSpace: "nowrap",
              boxShadow: "var(--shadow-overlay)",
            }}
          >
            <span style={{ font: "var(--type-body-sm)" }}>{shown.label}</span>{" "}
            <span style={{ fontFamily: "var(--font-figure)", fontWeight: "var(--weight-medium)" }}>{shown.pct}%</span>
          </div>
        )}
      </div>
      {legend && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)", flex: "none" }}>
          {slices.map((s, i) => (
            <div
              key={s.label}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(-1)}
              style={{ display: "flex", alignItems: "center", gap: "var(--space-4)", font: "var(--type-body)" }}
            >
              <i style={{ width: 10, height: 10, background: s.color, flex: "none" }} />
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
