"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Select } from "@/components/ds/Select";
import { fmtMonthLabel } from "@/lib/format";

/**
 * Global header control — selecting a month always routes to the team
 * screen for it (matches the design's own onMonth handler, which resets
 * `view` to 'team' unconditionally, even when opened from a profile page).
 */
export function MonthSelect({ months }: { months: string[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  if (months.length <= 1) return null; // nothing to switch between

  const selected = searchParams.get("month");
  const value = selected && months.includes(selected) ? selected : months[0];

  return (
    <Select
      label="Month"
      variant="inline"
      value={value}
      options={months.map((m) => ({ value: m, label: fmtMonthLabel(m) }))}
      onChange={(e) => router.push(`/?month=${e.target.value}`)}
    />
  );
}
