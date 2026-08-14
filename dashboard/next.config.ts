import type { NextConfig } from "next";

// NOTE: `pnpm build` passes --webpack deliberately. Next 16 defaults to
// Turbopack, which (a) emits no .next/standalone, which the Docker image is
// built around, and (b) skips route-export validation, so an illegal export
// from a route module only fails once you try the webpack path.
const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["better-sqlite3"],
};

export default nextConfig;
