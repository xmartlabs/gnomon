"use client";
import Link from "next/link";
import { useState } from "react";
import type { PersonRow } from "@/lib/metrics";
import { fmtTokens, fmtUsd } from "@/lib/format";
import { Sparkline } from "./Sparkline";
import { Delta, TierBadge } from "./ui";

type SortKey = "name" | "aq" | "tier" | "delta" | "topPillar" | "tokens" | "cost";

const COLS: { key: SortKey | null; label: string; width: string; right?: boolean }[] = [
  { key: "name", label: "Name", width: "24%" },
  { key: "aq", label: "AQ", width: "7%" },
  { key: "tier", label: "Tier", width: "13%" },
  { key: null, label: "Trend", width: "13%" },
  { key: "delta", label: "Delta", width: "9%" },
  { key: "topPillar", label: "Top pillar", width: "14%" },
  { key: "tokens", label: "Tokens", width: "10%", right: true },
  { key: "cost", label: "Cost", width: "10%", right: true },
];

/** Text columns default to A→Z, numeric ones to highest-first. */
const ASC_BY_DEFAULT: SortKey[] = ["name", "tier", "topPillar"];

/** Nulls always sort last, whichever direction the column is pointing. */
function compare(a: PersonRow, b: PersonRow, key: SortKey, asc: boolean): number {
  const x = a[key];
  const y = b[key];
  if (x === null || x === undefined) return y === null || y === undefined ? 0 : 1;
  if (y === null || y === undefined) return -1;
  const cmp = typeof x === "string" ? x.localeCompare(String(y)) : Number(x) - Number(y);
  return asc ? cmp : -cmp;
}

export function PeopleTable({ rows, monthKey }: { rows: PersonRow[]; monthKey: string | null }) {
  // Matches the server order, so the first paint never reshuffles.
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: "aq", asc: false });
  const sorted = [...rows].sort((a, b) => compare(a, b, sort.key, sort.asc));

  const toggle = (key: SortKey) =>
    setSort((s) => ({ key, asc: s.key === key ? !s.asc : ASC_BY_DEFAULT.includes(key) }));

  const activeLabel = COLS.find((c) => c.key === sort.key)?.label ?? "";

  return (
    // The 8 columns have a min-content floor; let the table scroll inside its
    // own box rather than pushing the whole page sideways.
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse">
        <caption className="sr-only">
          Engineers ranked by AQ{monthKey ? `, window ${monthKey}` : ""}. Tokens and cost are for
          the person’s latest uploaded window.
        </caption>
        <thead>
          <tr>
            {COLS.map((c) => (
              <th
                key={c.label}
                scope="col"
                style={{ width: c.width }}
                aria-sort={
                  c.key ? (sort.key === c.key ? (sort.asc ? "ascending" : "descending") : "none") : undefined
                }
                className={`border-b-2 border-ink pb-2.5 text-[10.5px] font-semibold tracking-[.16em] whitespace-nowrap text-ink-60 uppercase
                  ${c.right ? "pl-3.5 text-right" : "pr-3.5 text-left"}`}
              >
                {c.key ? (
                  <button
                    type="button"
                    onClick={() => toggle(c.key!)}
                    className="cursor-pointer tracking-[.16em] uppercase hover:text-ink"
                  >
                    {c.label}
                    {sort.key === c.key && (
                      <span aria-hidden className="ml-1 text-accent">
                        {sort.asc ? "▲" : "▼"}
                      </span>
                    )}
                  </button>
                ) : (
                  c.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.personId}
              className="border-b border-hairline text-[14.5px] last:border-b-0 [&>*]:py-[17px] [&>*]:pr-3.5"
            >
              <th scope="row" className="text-left font-normal">
                <Link
                  href={`/p/${r.personId}/${r.monthKey}`}
                  className="serif text-[17.5px] font-semibold tracking-[-0.005em] hover:text-accent"
                >
                  {r.name}
                </Link>
              </th>
              <td className="serif num text-[22px] font-semibold">{r.aq ?? "—"}</td>
              <td>
                <TierBadge tier={r.tier} />
              </td>
              <td>
                <Sparkline points={r.trend.map((t) => t.aq)} label={`${r.name} AQ trend`} />
              </td>
              <td className="num">
                <Delta value={r.delta} />
              </td>
              <td>
                <span className="serif text-[15px] italic">{r.topPillar ?? "—"}</span>
              </td>
              <td className="num pr-0 pl-3.5 text-right">
                {r.tokens === null ? "—" : fmtTokens(r.tokens)}
              </td>
              <td className="num pr-0 pl-3.5 text-right">{r.cost === null ? "—" : fmtUsd(r.cost)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div aria-live="polite" className="sr-only">
        Sorted by {activeLabel}, {sort.asc ? "ascending" : "descending"}
      </div>
    </div>
  );
}
