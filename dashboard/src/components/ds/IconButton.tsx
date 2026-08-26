"use client";

import { useState } from "react";

export function IconButton({
  size = "md",
  bordered,
  pressed,
  disabled,
  ariaLabel,
  onClick,
  children,
}: {
  size?: "sm" | "md" | "lg";
  bordered?: boolean;
  pressed?: boolean;
  disabled?: boolean;
  ariaLabel: string;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  const box = size === "sm" ? 32 : size === "lg" ? 48 : 40;
  const [hover, setHover] = useState(false);

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      title={ariaLabel}
      aria-pressed={pressed}
      style={{
        width: box,
        height: box,
        flex: "none",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: pressed ? "var(--surface-active)" : hover ? "var(--surface-hover)" : "transparent",
        color: disabled ? "var(--text-tertiary)" : "var(--text-secondary)",
        border: bordered ? "var(--rule-width) solid var(--rule-default)" : "var(--rule-width) solid transparent",
        borderRadius: "var(--radius-sm)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        transition: "var(--transition-control)",
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {children}
    </button>
  );
}
