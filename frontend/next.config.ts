import path from "node:path";
import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(__dirname, ".."),
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
      {
        source: "/images/:path*",
        destination: `${API_URL}/images/:path*`,
      },
    ];
  },
};

export default nextConfig;
