import Link from "next/link";
import { Suspense } from "react";
import { MonthSelect } from "@/components/MonthSelect";
import { ThemeToggle } from "@/components/ThemeToggle";

function Wordmark() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-4)" }}>
      <svg width="24" height="24" viewBox="0 0 64 64" aria-hidden="true">
        <path d="M32 8 L32 52 L8 52 Z" fill="var(--accent-mark-shadow)" />
        <path d="M32 8 L44 52 L32 52 Z" fill="var(--accent-mark)" />
      </svg>
      <span style={{ fontFamily: "var(--font-ui)", fontWeight: "var(--weight-semibold)", fontSize: 22, letterSpacing: "-0.03em", color: "var(--text-primary)" }}>
        gnomon
      </span>
    </span>
  );
}

/** Shared across both screens (app/(dashboard)/layout.tsx) — the wordmark always returns to the team screen. */
export function AppHeader({ months }: { months: string[] }) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-8)",
        paddingBottom: "var(--space-5)",
        borderBottom: "var(--rule-width) solid var(--rule-strong)",
        marginBottom: "var(--space-11)",
      }}
    >
      <Link href="/" aria-label="gnomon — back to the team dashboard" style={{ background: "none", border: 0, padding: 0, cursor: "pointer" }}>
        <Wordmark />
      </Link>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-6)" }}>
        <Suspense fallback={null}>
          <MonthSelect months={months} />
        </Suspense>
        <ThemeToggle />
      </div>
    </header>
  );
}
