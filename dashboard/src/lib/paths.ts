import fs from "node:fs";

/**
 * The mounted data volume. Both the SQLite file and the JWT secret live here,
 * so the location is resolved in exactly one place — otherwise a deployment
 * that moves one of them silently splits them across directories.
 */
export function dataDir(): string {
  const dir = process.env.DATA_DIR ?? "/data";
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
