import { NextResponse } from "next/server";
import { verifyToken } from "@/lib/auth";
import { getDb } from "@/lib/db";
import { ingestSummary, IngestError } from "@/lib/ingest";

export async function POST(req: Request): Promise<Response> {
  const auth = req.headers.get("authorization") ?? "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  const claims = token ? await verifyToken(token) : null;
  if (!claims) {
    return NextResponse.json({ error: "invalid or missing token" }, { status: 401 });
  }

  // Matches the CLI's own pre-POST refusal (_INGEST_MAX_BYTES in
  // gnomon/upload/mirdash.py) so a non-gnomon client cannot persist a payload
  // the contract says the server rejects. Read per-request so the env override
  // stays testable.
  const cap = Number(process.env.MAX_INGEST_BYTES) || 900 * 1024;
  const tooLarge = () => NextResponse.json({ error: "payload too large" }, { status: 413 });
  if (Number(req.headers.get("content-length")) > cap) return tooLarge();

  // Read the raw text ONCE so we can both validate a parsed copy and store the
  // original bytes verbatim. Enforce the byte cap on the actual body too.
  // TODO(task-11): a chunked body with no content-length is still fully
  // buffered before this check — cap request size at the proxy/server layer.
  const raw = await req.text();
  if (Buffer.byteLength(raw, "utf8") > cap) return tooLarge();

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "body must be valid JSON" }, { status: 400 });
  }

  try {
    const { reportUrl, stored } = ingestSummary(getDb(), claims.personId, body, raw);
    if (!stored) {
      console.info(`[ingest] kept stored month for person ${claims.personId} — upload was less complete`);
    }
    return NextResponse.json({ reportUrl });
  } catch (err) {
    if (err instanceof IngestError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    throw err;
  }
}
