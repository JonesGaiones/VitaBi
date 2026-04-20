"use client";

import { Header } from "@/components/Header";
import { FilterBar } from "@/components/FilterBar";
import { KpiCards } from "@/components/KpiCards";
import { DrillBreadcrumb } from "@/components/DrillBreadcrumb";
import { DrillDownChart } from "@/components/DrillDownChart";
import { RankingGrid } from "@/components/RankingGrid";
import { TimeseriesChart } from "@/components/TimeseriesChart";
import { InsightsFeed } from "@/components/InsightsFeed";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/cn";
import { Users, Package, UserCog, Boxes } from "lucide-react";
import { useState } from "react";

type Dimension = "customer" | "product" | "salesperson" | "category";

export default function DashboardPage() {
  const { drillStack } = useStore();
  const [dimension, setDimension] = useState<Dimension>("customer");

  const dimensionTabs: { id: Dimension; label: string; icon: any }[] = [
    { id: "customer",    label: "Clientes",    icon: Users },
    { id: "product",     label: "Produtos",    icon: Package },
    { id: "salesperson", label: "Vendedores",  icon: UserCog },
    { id: "category",    label: "Categorias",  icon: Boxes },
  ];

  const chartTitle = drillStack.length === 0
    ? `${dimensionTabs.find(t => t.id === dimension)?.label} — ranking`
    : `Detalhamento: ${drillStack[drillStack.length - 1].label}`;

  return (
    <div className="min-h-screen">
      <Header />

      <main className="px-6 py-5 space-y-4 animate-fade-up">
        {/* Title + breadcrumb */}
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="font-display text-3xl text-ink-50 tracking-tight leading-none mb-2">
              Visão geral de vendas
            </h1>
            <DrillBreadcrumb />
          </div>
        </div>

        {/* Filters */}
        <FilterBar />

        {/* KPI cards */}
        <KpiCards />

        {/* Main grid: chart area (8 cols) + insights feed (4 cols) */}
        <div className="grid grid-cols-12 gap-4">
          {/* Left: dimension tabs + chart + grid + timeseries */}
          <div className="col-span-12 xl:col-span-8 space-y-4">
            {/* Dimension selector (only when NOT drilling) */}
            {drillStack.length === 0 && (
              <div className="panel px-4 py-2 flex items-center gap-1">
                <span className="text-[10px] uppercase tracking-[0.2em] text-ink-400 font-mono mr-3 pl-1">
                  quebrar por
                </span>
                {dimensionTabs.map((t) => {
                  const Icon = t.icon;
                  return (
                    <button
                      key={t.id}
                      onClick={() => setDimension(t.id)}
                      className={cn(
                        "flex items-center gap-1.5 px-3 py-1.5 text-xs rounded transition-colors",
                        dimension === t.id
                          ? "bg-pulse/15 text-pulse"
                          : "text-ink-300 hover:text-ink-100 hover:bg-ink-700/40",
                      )}
                    >
                      <Icon size={12} />
                      {t.label}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Chart + Grid side by side */}
            <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
              <DrillDownChart
                initialDimension={dimension}
                title={chartTitle}
              />
              <RankingGrid initialDimension={dimension} />
            </div>

            {/* Timeseries */}
            <TimeseriesChart />
          </div>

          {/* Right: insights feed */}
          <div className="col-span-12 xl:col-span-4">
            <div className="xl:sticky xl:top-20" style={{ height: "calc(100vh - 96px)" }}>
              <InsightsFeed />
            </div>
          </div>
        </div>

        <footer className="pt-6 pb-2 text-center text-[10px] text-ink-500 uppercase tracking-[0.3em] font-mono">
          Vita BI · Rodando no Antigravity · v1.0.0
        </footer>
      </main>
    </div>
  );
}
