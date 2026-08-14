import { fmtDelta } from "@/lib/format";

/** The sheet's side gutter — every band on both pages sits on it. */
export const GUTTER = "px-[72px]";
export const REPORT_NAME = "gnomon · the AQ report";

/** Chart/mix series order from the design system: ink → terracotta → parchment. */
const SERIES = ["var(--ink)", "var(--accent)", "var(--parch)"];
export const seriesColor = (i: number) => SERIES[i % SERIES.length];

export function Eyebrow({
  children,
  className = "",
  size = 11,
  tracking = ".18em",
  as: Tag = "div",
}: {
  children: React.ReactNode;
  className?: string;
  size?: number;
  tracking?: string;
  as?: "div" | "h3";
}) {
  return (
    <Tag
      className={`font-semibold text-ink-60 uppercase ${className}`}
      style={{ fontSize: size, letterSpacing: tracking }}
    >
      {children}
    </Tag>
  );
}

export function Section({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`${GUTTER} py-2 ${className}`}>{children}</section>;
}

export function SectionTitle({ children, note }: { children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="mt-[26px] mb-3.5 flex items-baseline justify-between">
      <h2 className="serif text-[22px] font-semibold" style={{ fontVariationSettings: "'opsz' 60" }}>
        {children}
      </h2>
      {note && <span className="text-xs text-ink-60">{note}</span>}
    </div>
  );
}

/** The page shell: 4px ink top rule, masthead band, 2px ink rule. */
export function Sheet({
  maxWidth,
  mastheadPad,
  masthead,
  children,
}: {
  maxWidth: number;
  mastheadPad: string;
  masthead: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto border-t-4 border-ink bg-paper" style={{ maxWidth }}>
      <div className={`flex items-baseline justify-between ${GUTTER} ${mastheadPad}`}>{masthead}</div>
      <div className={GUTTER}>
        <hr role="presentation" className="border-0 border-t-2 border-ink" />
      </div>
      {children}
    </main>
  );
}

export function Colophon({ right, pad = "pt-4.5 pb-[30px]" }: { right: React.ReactNode; pad?: string }) {
  return (
    <div
      className={`flex justify-between border-t border-hairline ${GUTTER} ${pad} text-[11.5px] tracking-[.04em] text-ink-60`}
    >
      <span>{REPORT_NAME} · self-hosted</span>
      <span className="num">{right}</span>
    </div>
  );
}

/**
 * The signature drop-stat: a giant Fraunces numeral with an italic "/ 100" and
 * whatever the page hangs beside it (tier badge, annotation).
 */
export function AqDisplay({
  value,
  size,
  ofSize,
  asidePad,
  children,
}: {
  value: number | string;
  /** A clamp() so a 3-digit score cannot push the sheet sideways on mobile. */
  size: string;
  ofSize: number;
  asidePad: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-4">
      <span
        className="serif num font-semibold tracking-[-0.04em]"
        style={{ fontSize: size, lineHeight: 0.92, fontVariationSettings: "'opsz' 144" }}
      >
        {value}
      </span>
      <span className={asidePad}>
        <div className="serif text-ink-60 italic" style={{ fontSize: ofSize }}>
          / 100
        </div>
        {children}
      </span>
    </div>
  );
}

/** The inked italic annotation under a drop-stat — underlined in its own tone. */
export function Annotation({
  tone,
  arrow,
  children,
  className = "",
}: {
  tone: string;
  arrow?: "up" | "down";
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`serif inline-block border-b pb-0.5 italic ${className}`}
      style={{ color: tone, borderColor: "currentColor" }}
    >
      {arrow && (
        <span aria-hidden className="mr-1.5 inline-block -translate-y-px">
          {arrow === "up" ? "↗" : "↘"}
        </span>
      )}
      {children}
    </div>
  );
}

const TIER_COLOR: Record<string, string> = {
  elite: "var(--accent)",
  advanced: "var(--ink)",
  proficient: "var(--ink-60)",
};

/** No pill — Fraunces small-caps with a leading dot in the tier's colour. */
export function TierBadge({ tier, size = 12 }: { tier: string | null; size?: number }) {
  if (!tier) return null;
  const color = TIER_COLOR[tier.toLowerCase()] ?? "var(--ink-60)";
  return (
    <span
      className="serif inline-flex items-center gap-[7px] font-semibold tracking-[.06em] uppercase"
      style={{ color, fontSize: size }}
    >
      <span aria-hidden className="size-[7px] flex-none rounded-full" style={{ background: "currentColor" }} />
      {tier}
    </span>
  );
}

/**
 * Moss for gains, burnt for losses. The visible glyphs are hidden from
 * assistive tech — a true minus sign is dropped by several screen readers, and
 * the placeholder is a dash with no meaning — so each carries a spoken twin.
 */
export function Delta({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <span className="font-semibold text-ink-60">
        <span aria-hidden>––</span>
        <span className="sr-only">no previous window</span>
      </span>
    );
  }
  if (value === 0) {
    return (
      <span className="font-semibold text-ink-60">
        <span aria-hidden>±0</span>
        <span className="sr-only">unchanged</span>
      </span>
    );
  }
  return (
    <span className="font-semibold" style={{ color: value > 0 ? "var(--gain)" : "var(--loss)" }}>
      <span aria-hidden>{fmtDelta(value)}</span>
      <span className="sr-only">
        {value > 0 ? "up" : "down"} {Math.abs(value)} points
      </span>
    </span>
  );
}

/** Swatch + label + right-aligned value, used by both the chart and mix legends. */
export function LegendRow({
  color,
  label,
  value,
  swatch = 14,
}: {
  color: string;
  label: string;
  value: React.ReactNode;
  swatch?: number;
}) {
  return (
    <div className="flex items-center gap-2.5 border-b border-hairline py-2 text-[13.5px] last:border-b-0">
      <span aria-hidden className="flex-none" style={{ width: swatch, height: swatch, background: color }} />
      <span className="min-w-0 truncate" title={label}>
        {label}
      </span>
      <span className="num ml-auto flex-none text-[12.5px] text-ink-60">{value}</span>
    </div>
  );
}
