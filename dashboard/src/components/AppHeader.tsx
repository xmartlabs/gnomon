import Link from "next/link";
import { Suspense } from "react";
import { MonthSelect } from "@/components/MonthSelect";
import { ThemeToggle } from "@/components/ThemeToggle";

function Wordmark() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-4)" }}>
      <i
        aria-hidden="true"
        style={{
          width: 0,
          height: 0,
          borderLeft: "7px solid transparent",
          borderRight: "7px solid transparent",
          borderBottom: "16px solid var(--accent-mark)",
        }}
      />
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
