/**
 * Region check on /try and the job pages (UI-SPEC §7; PRE-A §7): Meta's Model API
 * isn't offered in some territories, so Safe Cut doesn't offer them uploads either.
 * Compliance with Meta's controls, not circumvention (AGENTS rule 7). The landing
 * page and the demo stay open everywhere.
 */
import { NextResponse, type NextRequest } from "next/server";
import { isRestricted, loadTerritories } from "./lib/region";

const territories = loadTerritories(process.env.SAFECUT_BLOCKED_TERRITORIES);

export function proxy(request: NextRequest) {
  // Vercel's edge headers; `request.geo` no longer exists in Next 15+.
  const country = request.headers.get("x-vercel-ip-country");
  const region = request.headers.get("x-vercel-ip-country-region");
  if (!isRestricted(country, region, territories)) return NextResponse.next();
  return NextResponse.rewrite(new URL("/unavailable", request.url));
}

export const config = {
  matcher: ["/try", "/jobs/:path*"],
};
