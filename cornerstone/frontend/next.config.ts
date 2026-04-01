import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.BUILD_STANDALONE === "true" ? "standalone" : undefined,
  experimental: {
    proxyTimeout: 300_000,
  },
  async rewrites() {
    const backend = process.env.API_URL;
    if (!backend) return { fallback: [] };
    return {
      fallback: [
        { source: "/api/:path*", destination: `${backend}/:path*` },
      ],
    };
  },
};

export default nextConfig;
