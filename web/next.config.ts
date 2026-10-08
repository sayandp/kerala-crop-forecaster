import type { NextConfig } from "next";

// Malayalam (default) is served at clean URLs ("/", "/crop/banana", ...) by rewriting to /ml/...;
// English lives at /en/... Everything stays statically generated with ISR.
const ML_PAGES = "crops|alerts|how|offline|accuracy|models|challenger|drift|health";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/", destination: "/ml" },
        { source: `/:page(${ML_PAGES})`, destination: "/ml/:page" },
        { source: "/:page(accuracy|models|challenger|drift|health)/opengraph-image", destination: "/ml/:page/opengraph-image" },
        { source: "/crop/:path*", destination: "/ml/crop/:path*" },
        { source: "/opengraph-image", destination: "/ml/opengraph-image" },
      ],
    };
  },
  async redirects() {
    // Phase 4 per-market pages moved to /crop/<crop>/<market>.
    return [
      { source: "/p/:crop/:market", destination: "/crop/:crop/:market", permanent: true },
      { source: "/en/p/:crop/:market", destination: "/en/crop/:crop/:market", permanent: true },
    ];
  },
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

export default nextConfig;
