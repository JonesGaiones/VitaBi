"use client";

import { useState } from "react";
import Link from "next/link";
import { Header } from "@/components/Header";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtCurrency } from "@/lib/format";
import { Search, ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";

type CustomerRow = {
  id: string;
  name: string;
  tier: string | null;
  segment: string | null;
  lifetime_revenue: number | null;
  revenue_ytd: number | null;
  last_purchase_date: string | null;
  days_since_last_purchase: number | null;
  avg_cycle_days: number | null;
  total_orders: number | null;
};

export default function CustomersPage() {
  const [search, setSearch] = useState("");
  const [tier, setTier] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["customers-list", search, tier],
    queryFn: async () => {
      const r = await api.get<CustomerRow[]>("/api/customers", {
        params: {
          search: search || undefined,
          tier: tier || undefined,
          limit: 200,
        },
      });
      return r.data;
    },
  });

  return (
    <div className="min-h-screen">
      <Header />
      <main className="px-6 py-5 space-y-4 animate-fade-up">
        <div>
          <h1 className="font-display text-3xl text-ink-50 tracking-tight leading-none">
            Clientes
          </h1>
          <p className="text-sm text-ink-400 mt-2">
            Clique em um cliente para ver o <span className="text-pulse">Customer Genome</span>
          </p>
        </div>

        {/* Search + filters */}
        <div className="panel px-4 py-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 flex-1 min-w-[240px]">
            <Search size={14} className="text-ink-300" />
            <input
              type="text"
              placeholder="Buscar por nome…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-transparent w-full text-sm focus:outline-none placeholder:text-ink-500"
            />
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[10px] uppercase tracking-[0.15em] text-ink-400 mr-2">tier</span>
            {[null, "A", "B", "C"].map((t) => (
              <button
                key={String(t)}
                onClick={() => setTier(t)}
                className={cn(
                  "px-2.5 py-1 text-xs rounded transition-colors font-mono",
                  tier === t
                    ? "bg-pulse/15 text-pulse border border-pulse/30"
                    : "text-ink-300 hover:text-ink-100 border border-transparent",
                )}
              >
                {t || "todos"}
              </button>
            ))}
          </div>
        </div>

        {/* List */}
        <div className="panel">
          {isLoading && (
            <div className="p-8 space-y-2">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="h-12 bg-ink-700/20 shimmer-bg rounded" />
              ))}
            </div>
          )}

          {!isLoading && data && data.length === 0 && (
            <div className="p-12 text-center text-ink-400 text-sm">
              Nenhum cliente encontrado.
            </div>
          )}

          {!isLoading && data && data.map((c) => {
            const isAtRisk = c.avg_cycle_days && c.days_since_last_purchase &&
                             c.days_since_last_purchase > c.avg_cycle_days * 1.3;
            return (
              <Link
                key={c.id}
                href={`/customers/${c.id}`}
                className="grid grid-cols-12 items-center gap-3 px-4 py-3 border-b border-ink-600/30
                           hover:bg-ink-700/30 transition-colors cursor-pointer group"
              >
                <div className="col-span-5 flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-ink-700 border border-ink-600/60
                                  flex items-center justify-center text-xs text-ink-300 font-medium">
                    {c.name?.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <div className="text-sm text-ink-100 font-medium">{c.name}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                      {c.tier && <span className="text-[10px] font-mono text-ink-400">Tier {c.tier}</span>}
                      {c.segment && <span className="text-[10px] text-ink-400">• {c.segment}</span>}
                      {isAtRisk && <span className="pill pill-warning text-[9px] py-0">em risco</span>}
                    </div>
                  </div>
                </div>

                <div className="col-span-2 text-right">
                  <div className="metric-label">LTV</div>
                  <div className="font-mono text-sm text-pulse">{fmtCurrency(c.lifetime_revenue, true)}</div>
                </div>

                <div className="col-span-2 text-right">
                  <div className="metric-label">YTD</div>
                  <div className="font-mono text-sm text-ink-100">{fmtCurrency(c.revenue_ytd, true)}</div>
                </div>

                <div className="col-span-2 text-right">
                  <div className="metric-label">Última</div>
                  <div className="font-mono text-sm text-ink-300">
                    {c.days_since_last_purchase !== null ? `${c.days_since_last_purchase}d atrás` : "—"}
                  </div>
                </div>

                <div className="col-span-1 flex justify-end">
                  <ChevronRight size={16} className="text-ink-500 group-hover:text-pulse transition-colors" />
                </div>
              </Link>
            );
          })}
        </div>
      </main>
    </div>
  );
}
