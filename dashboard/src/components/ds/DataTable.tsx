"use client";

import { useState } from "react";

export type Column<T> = {
  key: string;
  header: string;
  align?: "right";
  figure?: boolean;
  muted?: boolean;
  wrap?: boolean;
  render?: (row: T) => React.ReactNode;
};

/**
 * Rule-only table: no outer border, no zebra striping. Actions are visible
 * at rest — a persistent "Ver perfil ›", never a reveal-on-hover affordance.
 * The whole row is the click target: pointer cursor, tabIndex, role="button".
 */
export function DataTable<T extends { id?: string | number }>({
  columns,
  rows,
  actionLabel = "Open",
  rowLabel,
  onRowClick,
}: {
  columns: Column<T>[];
  rows: T[];
  actionLabel?: string;
  rowLabel?: (row: T) => string;
  onRowClick?: (row: T) => void;
}) {
  const clickable = Boolean(onRowClick);
  const [hover, setHover] = useState(-1);

  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          {columns.map((c) => (
            <th
              key={c.key}
              scope="col"
              style={{
                textAlign: c.align === "right" ? "right" : "left",
                padding: "0 var(--space-5) var(--space-4) 0",
                borderBottom: "var(--rule-width) solid var(--rule-strong)",
                fontFamily: "var(--font-figure)",
                fontSize: "var(--size-label)",
                fontWeight: "var(--weight-medium)",
                letterSpacing: "var(--tracking-label)",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                whiteSpace: "nowrap",
              }}
            >
              {c.header}
            </th>
          ))}
          {clickable && <th aria-hidden="true" style={{ borderBottom: "var(--rule-width) solid var(--rule-strong)" }} />}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr
            key={r.id ?? i}
            tabIndex={clickable ? 0 : undefined}
            role={clickable ? "button" : undefined}
            aria-label={clickable ? rowLabel?.(r) : undefined}
            onClick={clickable ? () => onRowClick!(r) : undefined}
            onKeyDown={
              clickable
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onRowClick!(r);
                    }
                  }
                : undefined
            }
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(-1)}
            style={{
              cursor: clickable ? "pointer" : "default",
              background: clickable && hover === i ? "var(--surface-hover)" : "transparent",
              transition: "background var(--duration-fast) var(--ease-out)",
            }}
          >
            {columns.map((c) => (
              <td
                key={c.key}
                style={{
                  textAlign: c.align === "right" ? "right" : "left",
                  padding: "var(--space-5) var(--space-5) var(--space-5) 0",
                  borderBottom: "var(--rule-width) solid var(--rule-subtle)",
                  font: c.figure ? undefined : "var(--type-body)",
                  fontFamily: c.figure ? "var(--font-figure)" : "var(--font-ui)",
                  fontSize: c.figure ? "var(--size-metric-xs)" : c.muted ? "var(--size-body-sm)" : "var(--size-body)",
                  fontWeight: c.figure ? "var(--weight-medium)" : "var(--weight-regular)",
                  fontVariantNumeric: c.figure ? "tabular-nums" : undefined,
                  color: c.muted ? "var(--text-secondary)" : "var(--text-primary)",
                  whiteSpace: c.wrap ? "normal" : "nowrap",
                }}
              >
                {c.render ? c.render(r) : String((r as Record<string, unknown>)[c.key] ?? "")}
              </td>
            ))}
            {clickable && (
              <td style={{ padding: "var(--space-5) 0", textAlign: "right", borderBottom: "var(--rule-width) solid var(--rule-subtle)" }}>
                <span
                  style={{
                    font: "var(--type-body-sm)",
                    color: "var(--accent)",
                    borderBottom: "var(--rule-width) solid currentColor",
                    whiteSpace: "nowrap",
                  }}
                >
                  {actionLabel} ›
                </span>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
