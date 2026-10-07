import type { NextConfig } from "next";

// Malayalam (default) is served at clean URLs ("/", "/accuracy", ...) by rewriting to /ml/...;
// English lives at /en/... Both stay statically generated with ISR.
const ML_PAGES = "accuracy|models|challenger|drift|health";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/", destination: "/ml" },
        { source: `/:page(${ML_PAGES})`, destination: "/ml/:page" },
        { source: "/p/:crop/:market", destination: "/ml/p/:crop/:market" },
        { source: "/opengraph-image", destination: "/ml/opengraph-image" },
      ],
    };
  },
};

export default nextConfig;
