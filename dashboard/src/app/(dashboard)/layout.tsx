import { getDb, distinctMonthKeys } from "@/lib/db";
import { AppHeader } from "@/components/AppHeader";

// Shared chrome for the two screens this redesign covers (Team, Profile).
// Deliberately its own route group, NOT the root layout — /cli-auth sits
// outside it and keeps its own minimal page, out of scope for this design.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const months = distinctMonthKeys(getDb(), 3);

  // Two nested elements on purpose: `background` lives on the OUTER, full-
  // width one. Putting it on the same element as `maxWidth` would shrink the
  // painted area down to 1180px too, leaving the old /cli-auth cream body
  // color showing in the side gutters on any wider viewport.
  return (
    <div className="gn-app" style={{ background: "var(--surface-page)", color: "var(--text-primary)", minHeight: "100vh" }}>
      <div
        style={{
          maxWidth: "var(--layout-max)",
          margin: "0 auto",
          padding: "var(--space-8) var(--layout-gutter) var(--space-14)",
        }}
      >
        <AppHeader months={months} />
        {children}
      </div>
    </div>
  );
}
