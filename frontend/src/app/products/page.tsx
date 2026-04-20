"use client";

import { useState } from "react";
import { Header } from "@/components/Header";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtCurrency, fmtNumber, fmtPercent, fmtDelta } from "@/lib/format";
import { AlertTriangle, Package, TrendingUp, TrendingDown, Archive, Zap } from "lucide-react";
import { cn } from "@/lib/cn";

type ProductRow = {
  id: string;
  qb_raw_name: string;
  clean_name: string;
  category: string | null;
  needs_cleanup: boolean;
  units_sold: number | null;
  total_revenue: number | null;
  total_margin: number | null;
  avg_price: number | null;
  unique_customers: number | null;
  revenue_30d: number | null;
  revenue_30d_prev: number | null;
  growth_30d: number | null;
};

type CleanupRow = {
  id: string;
  qb_raw_name: string;
  sales_count: number;
  revenue_lost_to_uncategorized: number;
};

type InventoryRow = {
  id: string;
  clean_name: string;
  category: string;
  qty_on_hand: number;
  qty_available: number;
  days_of_cover: number | null;
  turnover_rate: number | null;
  is_slow_mover: boolean;
  is_stockout_risk: boolean;
  needs_desova: boolean;
  snapshot_date: string;
};

export default function ProductsPage() {
  const [tab, setTab] = useState<"performance" | "cleanup" | "inventory">("performance");

  const productsQuery = useQuery({
    queryKey: ["products", tab],
    queryFn: async () => {
      const r = await api.get<ProductRow[]>("/api/products", { params: { limit: 100 } });
      return r.data;
    },
    enabled: tab === "performance",
  });

  const cleanupQuery = useQuery({
    queryKey: ["products-cleanup"],
    queryFn: async () => {
      const r = await api.get<CleanupRow[]>("/api/products/needs-cleanup");
      return r.data;
    },
    enabled: tab === "cleanup",
  });

  const inventoryQuery = useQuery({
    queryKey: ["products-inventory"],
    queryFn: async () => {
      const r = await api.get<InventoryRow[]>("/api/products/inventory-alerts");
      return r.data;
    },
    enabled: tab === "inventory",
  });

  // Counts for badges
  const cleanupCountQuery = useQuery({
    queryKey: ["products-cleanup-count"],
    queryFn: async () => {
      const r = await api.get<CleanupRow[]>("/api/products/needs-cleanup");
      return r.data.length;
    },
  });

  const inventoryCountQuery = useQuery({
    queryKey: ["products-inventory-count"],
    queryFn: async () => {
      const r = await api.get<InventoryRow[]>("/api/products/inventory-alerts");
      return r.data.length;
    },
  });

  return (
    <div className="min-h-screen">
      <Header />
      <main className="px-6 py-5 space-y-4 animate-fade-up">
        <div>
          <h1 className="font-display text-3xl text-ink-50 tracking-tight leading-none">
            Produtos
          </h1>
          <p className="text-sm text-ink-400 mt-2">
            Performance, categorização e estoque
          </p>
        </div>

        {/* Tabs */}
        <div className="panel px-3 py-2 flex items-center gap-1">
          {[
            { id: "performance", label: "Performance",     icon: TrendingUp,    count: null },
            { id: "cleanup",     label: "Precisam limpeza", icon: AlertTriangle, count: cleanupCountQuery.data },
            { id: "inventory",   label: "Alertas estoque",  icon: Archive,       count: inventoryCountQuery.data },
          ].map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id as any)}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-colors",
                  tab === t.id
                    ? "bg-pulse/15 text-pulse"
                    : "text-ink-300 hover:text-ink-100 hover:bg-ink-700/40",
                )}
              >
                <Icon size={14} />
                {t.label}
                {t.count !== null && t.count !== undefined && t.count > 0 && (
                  <span className={cn(
                    "text-[10px] font-mono px-1.5 py-0.5 rounded",
                    tab === t.id ? "bg-pulse/20" : "bg-rose-500/15 text-rose-500",
                  )}>
                    {t.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Performance tab */}
        {tab === "performance" && (
          <div className="panel">
            {productsQuery.isLoading && (
              <div className="p-8 space-y-2">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="h-14 bg-ink-700/20 shimmer-bg rounded" />
                ))}
              </div>
            )}
            {!productsQuery.isLoading && productsQuery.data?.map((p) => {
              const delta = fmtDelta(p.growth_30d !== null ? p.growth_30d * 100 : undefined);
              return (
                <div
                  key={p.id}
                  className="grid grid-cols-12 items-center gap-3 px-4 py-3 border-b border-ink-600/30 hover:bg-ink-700/20 transition-colors"
                >
                  <div className="col-span-5">
                    <div className="flex items-center gap-2">
                      {p.needs_cleanup && <AlertTriangle size={12} className="text-amber-500 shrink-0" />}
                      <div className="text-sm text-ink-100 font-medium">{p.clean_name}</div>
                    </div>
                    {p.category && (
                      <div className="text-[10px] text-ink-400 uppercase tracking-wider mt-0.5">
                        {p.category}
                      </div>
                    )}
                  </div>
                  <div className="col-span-2 text-right">
                    <div className="metric-label">Receita</div>
                    <div className="font-mono text-sm text-pulse">{fmtCurrency(p.total_revenue, true)}</div>
                  </div>
                  <div className="col-span-2 text-right">
                    <div className="metric-label">Volume</div>
                    <div className="font-mono text-sm text-ink-100">{fmtNumber(p.units_sold)}</div>
                  </div>
                  <div className="col-span-2 text-right">
                    <div className="metric-label">30d</div>
                    <div className="font-mono text-sm text-ink-100">{fmtCurrency(p.revenue_30d, true)}</div>
                  </div>
                  <div className="col-span-1 text-right">
                    {p.growth_30d !== null && (
                      <span className={cn(
                        "font-mono text-xs",
                        delta.sign === "up" && "text-emerald-500",
                        delta.sign === "down" && "text-rose-500",
                        delta.sign === "flat" && "text-ink-400",
                      )}>
                        {delta.label}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Cleanup tab */}
        {tab === "cleanup" && (
          <div className="panel">
            <div className="panel-header">
              <div>
                <h3 className="font-display text-lg text-ink-50 tracking-tight">
                  Produtos sem correspondência no de-para
                </h3>
                <p className="text-xs text-ink-400 mt-1">
                  Adicione essas linhas na sua planilha de-para para categorizar automaticamente
                </p>
              </div>
            </div>
            {cleanupQuery.isLoading && (
              <div className="p-8 space-y-2">
                {[0, 1, 2].map((i) => <div key={i} className="h-14 bg-ink-700/20 shimmer-bg rounded" />)}
              </div>
            )}
            {!cleanupQuery.isLoading && cleanupQuery.data?.length === 0 && (
              <div className="p-12 text-center text-ink-400 text-sm">
                <Zap className="mx-auto mb-2 text-emerald-500" size={32} />
                Todos os produtos estão categorizados.
              </div>
            )}
            {!cleanupQuery.isLoading && cleanupQuery.data?.map((p) => (
              <div
                key={p.id}
                className="grid grid-cols-12 items-center gap-3 px-4 py-3 border-b border-ink-600/30"
              >
                <div className="col-span-7">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={12} className="text-amber-500 shrink-0" />
                    <div className="text-sm text-ink-100 font-mono">{p.qb_raw_name}</div>
                  </div>
                </div>
                <div className="col-span-2 text-right">
                  <div className="metric-label">Vendas</div>
                  <div className="font-mono text-sm text-ink-100">{fmtNumber(p.sales_count)}</div>
                </div>
                <div className="col-span-3 text-right">
                  <div className="metric-label">Receita não categorizada</div>
                  <div className="font-mono text-sm text-rose-500">{fmtCurrency(p.revenue_lost_to_uncategorized, true)}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Inventory tab */}
        {tab === "inventory" && (
          <div className="panel">
            <div className="panel-header">
              <div>
                <h3 className="font-display text-lg text-ink-50 tracking-tight">
                  Alertas de estoque
                </h3>
                <p className="text-xs text-ink-400 mt-1">
                  Risco de stockout ou produtos que precisam desovar
                </p>
              </div>
            </div>
            {inventoryQuery.isLoading && (
              <div className="p-8 space-y-2">
                {[0, 1, 2].map((i) => <div key={i} className="h-14 bg-ink-700/20 shimmer-bg rounded" />)}
              </div>
            )}
            {!inventoryQuery.isLoading && inventoryQuery.data?.length === 0 && (
              <div className="p-12 text-center text-ink-400 text-sm">
                <Package className="mx-auto mb-2 text-emerald-500" size={32} />
                Estoque saudável.
              </div>
            )}
            {!inventoryQuery.isLoading && inventoryQuery.data?.map((p) => (
              <div
                key={p.id}
                className="grid grid-cols-12 items-center gap-3 px-4 py-3 border-b border-ink-600/30"
              >
                <div className="col-span-5">
                  <div className="flex items-center gap-2">
                    {p.is_stockout_risk && <span className="pill pill-critical">Stockout</span>}
                    {p.needs_desova && <span className="pill pill-warning">Desova</span>}
                  </div>
                  <div className="text-sm text-ink-100 font-medium mt-1">{p.clean_name}</div>
                  <div className="text-[10px] text-ink-400 uppercase tracking-wider">{p.category}</div>
                </div>
                <div className="col-span-2 text-right">
                  <div className="metric-label">Qty disponível</div>
                  <div className="font-mono text-sm text-ink-100">{fmtNumber(p.qty_available)}</div>
                </div>
                <div className="col-span-3 text-right">
                  <div className="metric-label">Dias de cobertura</div>
                  <div className={cn(
                    "font-mono text-sm",
                    p.is_stockout_risk ? "text-rose-500" :
                    p.needs_desova ? "text-amber-500" : "text-ink-100",
                  )}>
                    {p.days_of_cover !== null ? `${Math.round(p.days_of_cover)}d` : "—"}
                  </div>
                </div>
                <div className="col-span-2 text-right">
                  <div className="metric-label">Giro</div>
                  <div className="font-mono text-sm text-ink-100">
                    {p.turnover_rate !== null ? p.turnover_rate.toFixed(2) : "—"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
