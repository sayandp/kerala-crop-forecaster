import { revalidatePath } from "next/cache";
import { timingSafeEqual } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";

/** On-demand ISR: the daily pipeline POSTs here after notify (header x-revalidate-secret). */
export async function POST(req: NextRequest) {
  const secret = process.env.REVALIDATE_SECRET;
  const given = req.headers.get("x-revalidate-secret") ?? "";
  if (!secret || given.length !== secret.length || !timingSafeEqual(Buffer.from(given), Buffer.from(secret))) {
    return NextResponse.json({ revalidated: false }, { status: 401 });
  }
  revalidatePath("/[lang]", "layout");
  return NextResponse.json({ revalidated: true, at: new Date().toISOString() });
}
