import path from 'node:path';
import type { NextConfig } from 'next';

const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Permissions-Policy', value: 'camera=(self), geolocation=(), microphone=()' },
  // CSP + HSTS are finalised in M4/M6 with the security reviewer (NFR-6).
];

const nextConfig: NextConfig = {
  // The Docker image sets NEXT_OUTPUT=standalone; local `next start` uses the regular output.
  output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
  outputFileTracingRoot: path.join(__dirname, '../..'),
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: [
    '@insmartfix/contracts',
    '@insmartfix/core',
    '@insmartfix/tokens',
    '@insmartfix/ui-web',
  ],
  // Lint runs as its own CI step (root eslint.config.mjs); don't repeat it inside `next build`.
  eslint: { ignoreDuringBuilds: true },
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

export default nextConfig;
