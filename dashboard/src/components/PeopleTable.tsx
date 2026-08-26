"use client";

import { useRouter } from "next/navigation";
import { DataTable, type Column } from "@/components/ds/DataTable";
import { Badge } from "@/components/ds/Badge";
import { Trend } from "@/components/ds/Trend";
import type { PersonRow } from "@/lib/metrics";

/** Elite is the only tier that reads as "solid accent" — every tier below it is neutral, not a ranked rainbow. */
const isTopTier = (tier: string | null) => tier === "Elite";

export function PeopleTable({ rows, monthKey }: { rows: PersonRow[]; monthKey: string | null }) {
  const router = useRouter();

  const columns: Column<PersonRow>[] = [
    {
      key: "name",
      header: "Name",
      render: (r) => (
        <>
          {r.name}
          {monthKey && r.monthKey !== monthKey && (
            <span style={{ marginLeft: "var(--space-3)", fontFamily: "var(--font-figure)", fontSize: "var(--size-label)", color: "var(--text-tertiary)" }}>
              <span aria-hidden>· {r.monthKey}</span>
              <span className="sr-only">last upload {r.monthKey}, not the current window</span>
            </span>
          )}
        </>
      ),
    },
    { key: "aq", header: "AQ", figure: true, render: (r) => r.aq ?? "—" },
    { key: "tier", header: "Tier", render: (r) => (r.tier ? <Badge tone={isTopTier(r.tier) ? "accent" : "neutral"}>{r.tier}</Badge> : null) },
    { key: "trend", header: "Trend", render: (r) => <Trend delta={r.delta} /> },
    { key: "topPillar", header: "Top pillar", render: (r) => r.topPillar ?? "—" },
    { key: "monthKey", header: "Last upload", muted: true },
  ];

  return (
    <DataTable
      columns={columns}
      rows={rows.map((r) => ({ ...r, id: r.personId }))}
      actionLabel="View profile"
      rowLabel={(r) => `Open ${r.name}'s profile`}
      onRowClick={(r) => router.push(`/p/${r.personId}/${r.monthKey}`)}
    />
  );
}
