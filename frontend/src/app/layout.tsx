import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "LADA - Language Agnostic Digital Assistant",
  description: "AI-powered desktop assistant with multi-provider support",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.className}>
      <body className="bg-gray-950 text-gray-100 min-h-screen flex flex-col">
        {/* Navigation bar */}
        <nav className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-14">
              {/* Brand */}
              <Link
                href="/"
                className="flex items-center gap-2 text-lg font-bold tracking-tight"
              >
                <span className="text-indigo-400">LADA</span>
              </Link>

              {/* Nav links */}
              <div className="flex items-center gap-6">
                <Link
                  href="/"
                  className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  Chat
                </Link>
                <Link
                  href="/models"
                  className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  Models
                </Link>
                <Link
                  href="/settings"
                  className="text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  Settings
                </Link>
              </div>
            </div>
          </div>
        </nav>

        {/* Page content */}
        <main className="flex-1 flex flex-col">{children}</main>
      </body>
    </html>
  );
}
