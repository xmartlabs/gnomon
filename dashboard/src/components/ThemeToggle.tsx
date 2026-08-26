"use client";

import { useEffect, useState } from "react";
import { IconButton } from "@/components/ds/IconButton";

/**
 * The saved/system theme is already applied before paint by the inline
 * script in layout.tsx (no flash). This only mirrors that into local state so
 * the toggle can flip `data-theme` and persist the explicit choice.
 */
export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.getAttribute("data-theme") === "dark");
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
    localStorage.setItem("gn-theme", next ? "dark" : "light");
  };

  return (
    <IconButton ariaLabel={dark ? "Switch to light theme" : "Switch to dark theme"} bordered onClick={toggle}>
      {dark ? (
        <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
          <circle cx="10" cy="10" r="3.6" />
          <path d="M10 1.8v1.9M10 16.3v1.9M3.8 3.8l1.35 1.35M14.85 14.85l1.35 1.35M1.8 10h1.9M16.3 10h1.9M3.8 16.2l1.35-1.35M14.85 5.15L16.2 3.8" />
        </svg>
      ) : (
        <svg width="17" height="17" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" aria-hidden="true">
          <path d="M16.3 12.4A7 7 0 0 1 7.6 3.7a7 7 0 1 0 8.7 8.7z" />
        </svg>
      )}
    </IconButton>
  );
}
