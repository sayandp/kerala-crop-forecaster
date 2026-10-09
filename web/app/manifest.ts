import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "കേരള വിപണി വില · Kerala market prices",
    short_name: "വിപണി വില",
    description: "Daily Kerala mandi prices and the range expected in 7 days. Malayalam first.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#e8f0e1",
    theme_color: "#1d6a43",
    lang: "ml",
    categories: ["business", "news", "utilities"],
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
