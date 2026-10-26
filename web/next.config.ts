import type { NextConfig } from "next";

function sigmoraOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_SIGMORA_URL?.trim() || "https://sigmora.org";
  return new URL(raw).origin;
}

const dev = process.env.NODE_ENV !== "production";

// Static pages can't carry per-request nonces, so inline scripts are allowed (the Next.js
// guidance for statically rendered apps); everything else is locked to known origins.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  // Signed media and keyframe URLs come from the API's storage host, so any https origin.
  "img-src 'self' data: blob: https:",
  "media-src 'self' blob: https:",
  // The API and its presigned upload host; both are https.
  "connect-src 'self' https:",
  "frame-src 'self' https:",
  `frame-ancestors 'self' ${sigmoraOrigin()}`,
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
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
