"use client";

import Link from "next/link";
import { Activity, Users, Package, Lightbulb, Settings } from "lucide-react";
import { useInsightCounters } from "@/lib/queries";
import { cn } from "@/lib/cn";
import { usePathname } from "next/navigation";

export function Header() {
  const pathname = usePathname();
  const { data: counters } = useInsightCounters();
  const criticalCount = (counters?.critical || 0) + (counters?.warning || 0);

  const nav = [
    { href: "/",          label: "Visão geral",  icon: Activity,   match: (p: string) => p === "/" },
    { href: "/customers", label: "Clientes",     icon: Users,      match: (p: string) => p.startsWith("/customers") },
    { href: "/products",  label: "Produtos",     icon: Package,    match: (p: string) => p.startsWith("/products") },
    { href: "/insights",  label: "Inteligência", icon: Lightbulb,  match: (p: string) => p.startsWith("/insights"), badge: criticalCount },
    { href: "/settings",  label: "Config",       icon: Settings,   match: (p: string) => p.startsWith("/settings") },
  ];

  return (
    <header className="border-b border-ink-600/40 bg-ink-800/40 backdrop-blur-md sticky top-0 z-50">
      <div className="px-6 py-3 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-pulse to-pulse-deep
                          flex items-center justify-center shadow-glow-pulse
                          group-hover:scale-105 transition-transform">
            <span className="font-display text-ink-900 text-lg font-semibold leading-none">V</span>
          </div>
          <div>
            <div className="font-display text-lg text-ink-50 leading-none tracking-tight">
              Vita <span className="text-pulse">BI</span>
            </div>
            <div className="text-[10px] text-ink-400 uppercase tracking-[0.2em] font-mono mt-0.5">
              Vita Forte Inc.
            </div>
          </div>
        </Link>

        {/* Nav */}
        <nav className="flex items-center gap-1">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = item.match(pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-colors",
                  active
                    ? "text-pulse bg-pulse/10"
                    : "text-ink-300 hover:text-ink-100 hover:bg-ink-700/40",
                )}
              >
                <Icon size={14} />
                {item.label}
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full
                                   bg-rose-500 text-ink-50 text-[9px] font-mono
                                   flex items-center justify-center">
                    {item.badge > 9 ? "9+" : item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* User */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-xs text-ink-200 leading-tight">João</div>
            <div className="text-[10px] text-ink-400 leading-tight">admin</div>
          </div>
          <div className="w-8 h-8 rounded-full bg-ink-600/60 border border-ink-500/50
                          flex items-center justify-center text-ink-100 text-sm font-medium">
            J
          </div>
        </div>
      </div>
    </header>
  );
}
