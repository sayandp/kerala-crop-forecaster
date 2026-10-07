// Server-only database access. DATABASE_URL_RO is the read-only role cropcast_ro; it is read
// here, in server components, and never exposed to the client (no NEXT_PUBLIC_ prefix).
import { neon } from "@neondatabase/serverless";

type Sql = ReturnType<typeof neon>;
let client: Sql | null | undefined;

function sql(): Sql | null {
  if (client === undefined) {
    const url = process.env.DATABASE_URL_RO;
    client = url ? neon(url) : null;
  }
  return client;
}

/**
 * Run a parameterised query (tagged template) and return typed rows.
 * Without a database (e.g. a CI build) or on error the fallback is returned, so pages render an
 * empty state and are filled on the next ISR regeneration.
 */
export async function rows<T>(run: (q: Sql) => Promise<unknown>, fallback: T[] = []): Promise<T[]> {
  const q = sql();
  if (!q) return fallback;
  try {
    return (await run(q)) as T[];
  } catch (err) {
    console.error("db query failed:", err instanceof Error ? err.message : "unknown error");
    return fallback;
  }
}
