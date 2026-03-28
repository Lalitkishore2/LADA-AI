import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import { Settings, MessageSquare, Layers } from "lucide-react";
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
      <body className="bg-zinc-950 text-zinc-100 min-h-screen flex">
        {/* Sidebar */}
        <aside className="hidden md:flex w-16 flex-col items-center py-4 gap-4 border-r border-zinc-800/50 bg-zinc-950">
          {/* Logo */}
          <Link
            href="/"
            className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-sm mb-4"
          >
            L
          </Link>

          {/* Nav icons */}
          <Link
            href="/"
            className="w-10 h-10 rounded-xl flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50 transition-all group"
            title="Chat"
          >
            <MessageSquare className="w-5 h-5" />
          </Link>
          <Link
            href="/models"
            className="w-10 h-10 rounded-xl flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50 transition-all"
            title="Models"
          >
            <Layers className="w-5 h-5" />
          </Link>
          
          <div className="flex-1" />
          
          <Link
            href="/settings"
            className="w-10 h-10 rounded-xl flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50 transition-all"
            title="Settings"
          >
            <Settings className="w-5 h-5" />
          </Link>
        </aside>

        {/* Mobile header */}
        <div className="md:hidden fixed top-0 left-0 right-0 h-14 border-b border-zinc-800/50 bg-zinc-950/95 backdrop-blur flex items-center justify-between px-4 z-50">
          <Link
            href="/"
            className="flex items-center gap-2 text-lg font-bold"
          >
            <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-sm">L</span>
            <span className="text-zinc-100">LADA</span>
          </Link>
          <div className="flex items-center gap-2">
            <Link href="/" className="p-2 text-zinc-400 hover:text-zinc-100">
              <MessageSquare className="w-5 h-5" />
            </Link>
            <Link href="/models" className="p-2 text-zinc-400 hover:text-zinc-100">
              <Layers className="w-5 h-5" />
            </Link>
            <Link href="/settings" className="p-2 text-zinc-400 hover:text-zinc-100">
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
