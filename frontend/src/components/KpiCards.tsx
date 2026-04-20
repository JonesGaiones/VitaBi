"use client";

import { useKpis } from "@/lib/queries";
import { useStore } from "@/lib/store";
import { fmtCurrency, fmtNumber, fmtDelta } from "@/lib/format";
import { cn } from "@/lib/cn";
import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";

type CardProps = {
  label: string;
  value: string;
  delta?: number | null;
  subtitle?: string;
  accent?: boolean;
  loading?: boolean;
};

function Card({ label, value, delta, subtitle, accent, loading }: CardProps) {
  const d = fmtDelta(delta ?? undefined);

  return (
    <div className={cn(
      "panel panel-body relative",
      accent && "border-pulse/30 shadow-glow-pulse",
    )}>
      {loading && <div className="absolute inset-0 shimmer-bg rounded-xl" />}

      <div className="metric-label mb-2">{label}</div>
      <div className="flex items-baseline gap-3">
        <div className={cn(
          "metric-value text-3xl",
          accent ? "text-pulse" : "text-ink-50",
        )}>
          {loading ? "—" : value}
        </div>
        {delta !== undefined && delta !== null && !loading && (
          <div className={cn(
            "flex items-center gap-0.5 text-xs font-mono",
            d.sign === "up" && "text-emerald-500",
            d.sign === "down" && "text-rose-500",
            d.sign === "flat" && "text-ink-400",
          )}>
            {d.sign === "up" && <ArrowUpRight size={12} />}
            {d.sign === "down" && <ArrowDownRight size={12} />}
            {d.sign === "flat" && <Minus size={12} />}
            {d.label}
          </div>
        )}
      </div>
      {subtitle && (
        <div className="text-xs text-ink-400 mt-1">{subtitle}</div>
      )}
    </div>
  );
}

export function KpiCards() {
  const { filters } = useStore();
  const { data, isLoading } = useKpis(filters);

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Card
        label="Faturamento"
        value={fmtCurrency(data?.revenue, true)}
        delta={data?.revenue_change_pct}
        subtitle="vs. período anterior"
        accent
        loading={isLoading}
      />
      <Card
        label="Margem bruta"
        value={fmtCurrency(data?.margin, true)}
        subtitle={data ? `${((data.margin / data.revenue) * 100).toFixed(1)}% do faturamento` : undefined}
        loading={isLoading}
      />
      <Card
        label="Pedidos"
        value={fmtNumber(data?.orders)}
        subtitle={data ? `Ticket médio: ${fmtCurrency(data.avg_order_value)}` : undefined}
        loading={isLoading}
      />
      <Card
        label="Clientes ativos"
        value={fmtNumber(data?.customers)}
        delta={data?.customers_change_pct}
        subtitle="únicos no período"
        loading={isLoading}
      />
    </div>
  );
}
