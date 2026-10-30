import type { NextConfig } from "next";

function sigmoraOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_SIGMORA_URL?.trim() || "https://sigmora.org";
  return new URL(raw).origin;
}

const dev = process.env.NODE_ENV !== "production";

/** A build pointed at a plain-http API on loopback (a local run or the e2e check) may talk to that origin only. */
function loopbackApi(): string | null {
  const raw = process.env.NEXT_PUBLIC_SAFECUT_API?.trim();
  if (!raw) return null;
  const url = new URL(raw);
  return url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost") ? url.origin : null;
}

// `pnpm dev` may reach any local port; a production build only the loopback API it was built for.
const localApi = dev ? " http://localhost:* http://127.0.0.1:*" : loopbackApi() ? ` ${loopbackApi()}` : "";

// Static pages can't carry per-request nonces, so inline scripts are allowed (the Next.js
// guidance for statically rendered apps); everything else is locked to known origins.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  // Signed media and keyframe URLs come from the API's storage host, so any https origin.
  `img-src 'self' data: blob: https:${localApi}`,
  `media-src 'self' blob: https:${localApi}`,
  // The API and its presigned upload host; both are https.
  `connect-src 'self' https:${localApi}`,
  `frame-src 'self' https:${localApi}`,
  `frame-ancestors 'self' ${sigmoraOrigin()}`,
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // Cache Components is off on purpose: with it, Next keeps visited pages mounted but hidden
  // (<Activity>), so a flow page (/try, a job, a result) came back stale, kept polling into
  // old jobs or kept playing audio. These pages are client-driven and gain nothing from it.
  poweredByHeader: false,
  reactStrictMode: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        ],
      },
      {
        source: "/jobs/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex" }],
      },
    ];
  },
};

export default nextConfig;
