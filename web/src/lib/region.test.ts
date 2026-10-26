import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { proxy } from "../proxy";
import { isRestricted, loadTerritories } from "./region";

const req = (path: string, headers: Record<string, string> = {}) => new NextRequest(new URL(path, "https://safecut.example"), { headers });

describe("region check (UI-SPEC §7, PRE-A §7)", () => {
  it.each([
    ["RU", null, true],
    ["ru", null, true],
    ["UA", "43", true],
    ["UA", "UA-14", true],
    ["UA", "30", false],
    ["KE", null, false],
    ["US", "CA", false],
    [null, null, false],
    ["", "", false],
  ] as const)("%s/%s → %s", (country, region, blocked) => {
    expect(isRestricted(country, region)).toBe(blocked);
  });

  it("rewrites /try and job pages to the unavailable page, and lets others through", () => {
    const blocked = proxy(req("/try", { "x-vercel-ip-country": "RU" }));
    expect(blocked.headers.get("x-middleware-rewrite")).toBe("https://safecut.example/unavailable");
    expect(proxy(req("/jobs/j_1", { "x-vercel-ip-country": "UA", "x-vercel-ip-country-region": "43" })).headers.get("x-middleware-rewrite")).toBe("https://safecut.example/unavailable");
    const kyiv = proxy(req("/try", { "x-vercel-ip-country": "UA", "x-vercel-ip-country-region": "30" }));
    expect(kyiv.headers.get("x-middleware-rewrite")).toBeNull();
    expect(proxy(req("/try")).headers.get("x-middleware-rewrite")).toBeNull();
  });

  it("reads an override and rejects a malformed one", () => {
    expect(isRestricted("KE", null, loadTerritories('{"countries":["ke"],"regions":{}}'))).toBe(true);
    expect(() => loadTerritories('{"countries":"RU"}')).toThrow();
  });
});
