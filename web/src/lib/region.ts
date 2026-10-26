import { z } from "zod";

/**
 * Meta's Geographic Use Policy §3 restricted territories (PRE-A API-NOTES §7, read
 * 2026-10-26). Config, not copy: the pages link the policy instead of listing it.
 * `SAFECUT_BLOCKED_TERRITORIES` (JSON, same shape) overrides it without a code change.
 */
export interface Territories {
  countries: readonly string[];
  /** Country → ISO 3166-2 region parts that are restricted when the whole country isn't. */
  regions: Readonly<Record<string, readonly string[]>>;
}

export const DEFAULT_TERRITORIES: Territories = {
  countries: ["AF", "BY", "KH", "CN", "HK", "MO", "CU", "ER", "ET", "HT", "IR", "IQ", "LY", "MM", "NI", "KP", "PK", "RU", "SO", "SY", "VE", "EH"],
  // Crimea (43), Sevastopol (40), Donetsk (14), Luhansk (09).
  regions: { UA: ["43", "40", "14", "09"] },
};

const code = z.string().trim().min(1).toUpperCase();
const territoriesSchema = z.object({ countries: z.array(code), regions: z.record(code, z.array(code)) });

export function loadTerritories(raw: string | undefined): Territories {
  if (!raw?.trim()) return DEFAULT_TERRITORIES;
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    json = undefined;
  }
  const parsed = territoriesSchema.safeParse(json);
  if (!parsed.success) throw new Error("SAFECUT_BLOCKED_TERRITORIES must be {countries: string[], regions: {CC: string[]}}");
  return parsed.data;
}

/**
 * Whether the edge location is restricted. With no country (local dev, a missing
 * header) it allows the request; the consent tick still applies (PRE-A §7).
 */
export function isRestricted(country: string | null | undefined, region: string | null | undefined, t: Territories = DEFAULT_TERRITORIES): boolean {
  const cc = country?.trim().toUpperCase();
  if (!cc) return false;
  if (t.countries.includes(cc)) return true;
  // The header carries only the region part, but accept a full "UA-43" too.
  const full = region?.trim().toUpperCase();
  const part = full?.startsWith(`${cc}-`) ? full.slice(cc.length + 1) : full;
  return !!part && (t.regions[cc] ?? []).includes(part);
}
