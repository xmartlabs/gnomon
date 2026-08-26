import type { Db } from "@/lib/db";
import type { PersonProfile } from "@/lib/metrics";
import { getPersonSuggestions } from "@/lib/coach";

/** Suggestions come first on the profile, on purpose — the tone is coaching, not ranking. */
export async function SuggestionsCard({ db, profile }: { db: Db; profile: PersonProfile }) {
  const items = await getPersonSuggestions(db, profile);
  if (!items) return null;

  return (
    <>
      {items.map((s, i) => (
        <p
          key={i}
          style={{
            margin: 0,
            paddingBottom: "var(--space-6)",
            marginBottom: "var(--space-6)",
            borderBottom: i === 0 ? "var(--rule-width) solid var(--rule-subtle)" : 0,
            font: "var(--type-title-sm)",
            textWrap: "pretty",
          }}
        >
          {s.text}
          <span className="sr-only"> — eje: {s.axis}</span>
        </p>
      ))}
    </>
  );
}
