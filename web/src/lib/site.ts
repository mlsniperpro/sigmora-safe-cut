/** Public links and IDs, from env with safe defaults (documented in web/README.md). */
export const SITE = {
  siteUrl: process.env.NEXT_PUBLIC_SITE_URL?.trim() || "https://safecut.sigmora.org",
  repoUrl: process.env.NEXT_PUBLIC_REPO_URL?.trim() || "https://github.com/mlsniperpro/sigmora-safe-cut",
  sigmoraUrl: process.env.NEXT_PUBLIC_SIGMORA_URL?.trim() || "https://sigmora.org",
  heroId: process.env.NEXT_PUBLIC_SAFECUT_HERO_ID?.trim() || "hero1",
  /** WP8 sets this from the hero clip actually filmed (UI-SPEC §1.3 copy notes). */
  heroHasChild: process.env.NEXT_PUBLIC_HERO_HAS_CHILD !== "false",
  geoPolicyUrl: "https://dev.meta.ai/legal/geographic-use-policy",
  evalUrl: process.env.NEXT_PUBLIC_EVAL_URL?.trim() || "https://github.com/mlsniperpro/sigmora-safe-cut/blob/main/docs/EVAL.md",
} as const;

/** True when the page was opened from Sigmora (`?from=sigmora`, UI-SPEC §0, §5). */
export function fromSigmora(params: URLSearchParams | null): boolean {
  return params?.get("from") === "sigmora";
}

/** Query parameters kept across redirects (UI-SPEC §10.4); `view` is dropped. */
export function keptQuery(params: URLSearchParams | null): string {
  const out = new URLSearchParams();
  for (const key of ["from", "demo"]) {
    const v = params?.get(key);
    if (v) out.set(key, v);
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}
