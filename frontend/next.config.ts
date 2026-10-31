import type { NextConfig } from "next";

// The browser only ever talks to the Next.js origin; API calls are proxied to the FastAPI backend.
// This keeps the session cookie same-origin (no third-party cookie / CORS complications).
const backend = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // The app never uses next/image; disabling the optimiser removes the /_next/image endpoint (and its sharp attack surface).
  images: { unoptimized: true },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
