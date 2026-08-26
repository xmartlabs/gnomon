"use client";

import { useState } from "react";

type Option = string | { value: string; label: string };

export function Select({
  id,
  name,
  label,
  value,
  options,
  variant,
  disabled,
  onChange,
}: {
  id?: string;
  name?: string;
  label?: string;
  value: string;
  options: Option[];
  variant?: "inline";
  disabled?: boolean;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
}) {
  const selectId = id ?? `sel-${name ?? "field"}`;
  const [focus, setFocus] = useState(false);
  const inline = variant === "inline";

  const control = (
    <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      <select
        id={selectId}
        name={name}
        value={value}
        onChange={onChange}
        disabled={disabled}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{
          appearance: "none",
          WebkitAppearance: "none",
          height: inline ? "auto" : "var(--control-md)",
          padding: inline ? "2px var(--space-7) 3px var(--space-1)" : "0 var(--space-8) 0 var(--space-5)",
          font: "var(--type-body)",
          fontFamily: "var(--font-ui)",
          color: "var(--text-primary)",
          background: inline ? "transparent" : "var(--surface-raised)",
          border: inline ? 0 : `var(--rule-width) solid ${focus ? "var(--accent)" : "var(--rule-default)"}`,
          borderBottom: `var(--rule-width) solid ${focus ? "var(--accent)" : inline ? "var(--rule-strong)" : "var(--rule-default)"}`,
          borderRadius: inline ? 0 : "var(--radius-sm)",
          cursor: "pointer",
          outline: "none",
          transition: "var(--transition-control)",
        }}
      >
        {options.map((o) => {
          const val = typeof o === "string" ? o : o.value;
          const lab = typeof o === "string" ? o : o.label;
          return (
            <option key={val} value={val}>
              {lab}
            </option>
          );
        })}
      </select>
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          right: inline ? 4 : 12,
          pointerEvents: "none",
          fontSize: 9,
          color: "var(--text-decorative)",
          lineHeight: 1,
        }}
      >
        ▼
      </span>
    </div>
  );

  if (!label) return control;

  return (
    <label
      htmlFor={selectId}
      style={{ display: "flex", alignItems: "center", gap: "var(--space-4)", font: "var(--type-body-sm)", color: "var(--text-secondary)" }}
    >
      <span>{label}</span>
      {control}
    </label>
  );
}
