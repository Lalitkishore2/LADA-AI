import type { Metadata } from "next";
import { JetBrains_Mono, Manrope, Space_Grotesk } from "next/font/google";
import Link from "next/link";
import { Settings, MessageSquare, Layers, TerminalSquare } from "lucide-react";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-main",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

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
    <html
      lang="en"
      className={`${manrope.variable} ${spaceGrotesk.variable} ${jetBrainsMono.variable}`}
    >
      <body className="min-h-screen flex bg-[var(--bg)] text-[var(--text)]">
        {/* Sidebar */}
        <aside className="hidden md:flex w-[72px] flex-col items-center py-4 gap-3 border-r border-[var(--border)]/70 bg-[linear-gradient(180deg,rgba(18,25,35,.96)_0%,rgba(15,21,30,.96)_100%)] shadow-[8px_0_24px_rgba(0,0,0,.28)]">
          {/* Logo */}
          <Link
            href="/"
            className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[linear-gradient(140deg,var(--accent)_0%,var(--accent-dark)_100%)] text-white font-bold text-sm shadow-[0_8px_18px_rgba(16,163,127,.3)]"
          >
            L
          </Link>

          {/* Nav icons */}
          <Link
            href="/"
            className="flex h-10 w-10 items-center justify-center rounded-xl text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition-colors"
            title="Chat"
          >
            <MessageSquare className="w-5 h-5" />
          </Link>
          <Link
            href="/models"
            className="flex h-10 w-10 items-center justify-center rounded-xl text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition-colors"
            title="Models"
          >
            <Layers className="w-5 h-5" />
          </Link>
          <Link
            href="/remote"
            className="flex h-10 w-10 items-center justify-center rounded-xl text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition-colors"
            title="Remote"
          >
            <TerminalSquare className="w-5 h-5" />
          </Link>

          <div className="flex-1" />

          <Link
            href="/settings"
            className="flex h-10 w-10 items-center justify-center rounded-xl text-[var(--text-dim)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition-colors"
            title="Settings"
          >
            <Settings className="w-5 h-5" />
          </Link>
        </aside>

        {/* Mobile header */}
        <div className="md:hidden fixed top-0 left-0 right-0 h-14 border-b border-[var(--border)] bg-[linear-gradient(180deg,rgba(18,25,35,.9)_0%,rgba(16,22,31,.84)_100%)] backdrop-blur flex items-center justify-between px-4 z-50">
          <Link
            href="/"
            className="flex items-center gap-2 text-lg"
          >
            <span className="w-8 h-8 rounded-lg bg-[linear-gradient(140deg,var(--accent)_0%,var(--accent-dark)_100%)] flex items-center justify-center text-white text-sm shadow-[0_6px_16px_rgba(16,163,127,.25)]">L</span>
            <span className="text-[var(--text)] font-semibold tracking-[0.01em]">LADA</span>
          </Link>
          <div className="flex items-center gap-2">
            <Link href="/" className="p-2 text-[var(--text-dim)] hover:text-[var(--text)]">
              <MessageSquare className="w-5 h-5" />
            </Link>
            <Link href="/models" className="p-2 text-[var(--text-dim)] hover:text-[var(--text)]">
              <Layers className="w-5 h-5" />
            </Link>
            <Link href="/remote" className="p-2 text-[var(--text-dim)] hover:text-[var(--text)]">
              <TerminalSquare className="w-5 h-5" />
            </Link>
            <Link href="/settings" className="p-2 text-[var(--text-dim)] hover:text-[var(--text)]">
              <Settings className="w-5 h-5" />
            </Link>
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 flex flex-col md:pt-0 pt-14">{children}</main>
      </body>
    </html>
  );
}
