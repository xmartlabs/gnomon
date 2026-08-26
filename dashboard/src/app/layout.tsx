import "./globals.css";
import type { Metadata } from "next";
import { Fraunces, Archivo, IBM_Plex_Mono } from "next/font/google";

// Fraunces stays for /cli-auth, the one screen this redesign does not touch
// (out of scope per the design handoff). Archivo is shared: the new design
// system's --font-ui is the SAME family, just more weights, so one self-hosted
// instance serves both the legacy login page and the new dashboard.
const display = Fraunces({
  subsets: ["latin"], variable: "--font-display",
  axes: ["opsz"], style: ["normal", "italic"],
});
const body = Archivo({ subsets: ["latin"], variable: "--font-body", weight: ["400", "500", "600", "700"] });
// The new design system's figure font — every number, label and code span.
const mono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-mono-gn", weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "gnomon dashboard",
  description: "Self-hosted team dashboard for gnomon build profiles",
};

// Applies the saved/system theme before paint so there is no light-to-dark
// flash on load. Reads localStorage directly — this runs before React hydrates.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var saved = localStorage.getItem("gn-theme");
    var theme = saved === "light" || saved === "dark"
      ? saved
      : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: the inline script below sets data-theme on
    // <html> before React hydrates (that's the point — no flash of the wrong
    // theme), so the server-rendered markup never has this attribute and a
    // mismatch here is expected, not a bug.
    <html lang="en" suppressHydrationWarning className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
