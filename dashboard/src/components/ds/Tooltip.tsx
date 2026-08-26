"use client";

import { useState } from "react";

type Side = "top" | "bottom" | "right";

const POSITION: Record<Side, React.CSSProperties> = {
  top: { bottom: "100%", left: "50%", transform: "translate(-50%, -6px)" },
  bottom: { top: "100%", left: "50%", transform: "translate(-50%, 6px)" },
  right: { left: "100%", top: "50%", transform: "translate(6px, -50%)" },
};

/**
 * Definitions live here, not in the native `title` attribute — unreachable by
 * keyboard, invisible on touch. The marker is a 24x24px hit area around a
 * 16px hairline-circle "i", open on hover AND focus.
 */
export function Tooltip({
  label,
  side = "top",
  width,
  children,
}: {
  label: string;
  side?: Side;
  width?: number;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <span
      style={{ position: "relative", display: "inline-flex", alignItems: "center" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children ?? (
        <span
          tabIndex={0}
          role="button"
          aria-label={label}
          aria-expanded={open}
          style={{
            minWidth: 24,
            minHeight: 24,
            flex: "none",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: "none",
            border: 0,
            padding: 0,
            cursor: "help",
          }}
        >
          <span
            aria-hidden="true"
            style={{
              width: 16,
              height: 16,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: "var(--font-figure)",
              fontSize: 10,
              lineHeight: 1,
              color: "var(--text-tertiary)",
              border: "var(--rule-width) solid var(--rule-default)",
              borderRadius: "var(--radius-full)",
            }}
          >
            i
          </span>
        </span>
      )}
      {open && (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            zIndex: 20,
            maxWidth: width ?? 260,
            width: "max-content",
            padding: "var(--space-4) var(--space-5)",
            background: "var(--surface-inverse)",
            color: "var(--text-inverse)",
            font: "var(--type-body-sm)",
            textAlign: "left",
            borderRadius: "var(--radius-sm)",
            boxShadow: "var(--shadow-overlay)",
            pointerEvents: "none",
            textWrap: "pretty",
            ...POSITION[side],
          }}
        >
          {label}
        </span>
      )}
    </span>
  );
}
