/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/ws',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000'}/ws`,
      },
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000'}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
