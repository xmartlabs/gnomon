"use client";

import { useState } from "react";

type Variant = "primary" | "secondary" | "ghost" | "link";
type Size = "sm" | "md" | "lg";

const SIZES: Record<Size, React.CSSProperties> = {
  sm: { height: "var(--control-sm)", padding: "0 var(--space-5)", fontSize: "var(--size-body-sm)" },
  md: { height: "var(--control-md)", padding: "0 var(--space-6)", fontSize: "var(--size-body)" },
  lg: { height: "var(--control-lg)", padding: "0 var(--space-7)", fontSize: "var(--size-body-lg)" },
};

const VARIANTS: Record<
  Variant,
  {
    background: string;
    color: string;
    border: string;
    borderBottom?: string;
    padding?: string;
    height?: string;
    hover: React.CSSProperties;
    active: React.CSSProperties;
  }
> = {
  primary: {
    background: "var(--accent)",
    color: "var(--accent-on)",
    border: "var(--rule-width) solid var(--accent)",
    hover: { background: "var(--accent-hover)", borderColor: "var(--accent-hover)" },
    active: { background: "var(--accent-pressed)", borderColor: "var(--accent-pressed)" },
  },
  secondary: {
    background: "var(--surface-raised)",
    color: "var(--text-primary)",
    border: "var(--rule-width) solid var(--rule-strong)",
    hover: { background: "var(--surface-hover)" },
    active: { background: "var(--surface-active)" },
  },
  ghost: {
    background: "transparent",
    color: "var(--text-primary)",
    border: "var(--rule-width) solid transparent",
    hover: { background: "var(--surface-hover)" },
    active: { background: "var(--surface-active)" },
  },
  link: {
    background: "transparent",
    color: "var(--accent)",
    border: "0",
    padding: "0",
    height: "auto",
    borderBottom: "var(--rule-width) solid currentColor",
    hover: { color: "var(--accent-hover)" },
    active: { color: "var(--accent-pressed)" },
  },
};

export function Button({
  variant = "primary",
  size = "md",
  type = "button",
  disabled,
  fullWidth,
  ariaLabel,
  iconLeft,
  iconRight,
  onClick,
  children,
}: {
  variant?: Variant;
  size?: Size;
  type?: "button" | "submit";
  disabled?: boolean;
  fullWidth?: boolean;
  ariaLabel?: string;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  onClick?: () => void;
  children: React.ReactNode;
}) {
  const v = VARIANTS[variant];
  const [hover, setHover] = useState(false);
  const [active, setActive] = useState(false);

  const style: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "var(--space-4)",
    fontFamily: "var(--font-ui)",
    fontWeight: "var(--weight-medium)",
    letterSpacing: 0,
    borderRadius: "var(--radius-sm)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.4 : 1,
    transition: "var(--transition-control)",
    width: fullWidth ? "100%" : undefined,
    whiteSpace: "nowrap",
    ...SIZES[size],
    background: v.background,
    color: v.color,
    border: v.border,
    borderBottom: v.borderBottom,
    padding: v.padding,
    height: v.height,
    ...(!disabled && hover ? v.hover : null),
    ...(!disabled && active ? v.active : null),
  };

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      aria-label={ariaLabel}
      style={style}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => {
        setHover(false);
        setActive(false);
      }}
      onMouseDown={() => setActive(true)}
      onMouseUp={() => setActive(false)}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
