import "./globals.css";
import type { Metadata } from "next";
import { Fraunces, Archivo } from "next/font/google";

const display = Fraunces({
  subsets: ["latin"], variable: "--font-display",
  axes: ["opsz"], style: ["normal", "italic"],
});
const body = Archivo({ subsets: ["latin"], variable: "--font-body", weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: "gnomon dashboard",
  description: "Self-hosted team dashboard for gnomon build profiles",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
