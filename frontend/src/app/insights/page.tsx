"use client";

import { useState } from "react";
import { Header } from "@/components/Header";
import { useInsightsFeed, useInsightCounters, type Insight } from "@/lib/queries";
import { api } from "@/lib/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { cn } from "@/lib/cn";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";
import {
  AlertTriangle, TrendingDown, Target, Clock, DollarSign,
  Sparkles, Check, X, ChevronRight, Zap,
} from "lucide-react";
import Link from "next/link";

const TYPE_META: Record<string, { icon: any; label: string; color: string }> = {
  churn:         { icon: TrendingDown, label: "Churn",       color: "text-rose-500" },
  pricing:       { icon: DollarSign,   label: "Preço",       color: "text-amber-500" },
  margin:        { icon: AlertTriangle,label: "Margem",      color: "text-rose-500" },
  opportunity:   { icon: Target,       label: "Oportunidade",color: "text-emerald-500" },
  replenishment: { icon: Clock,        label: "Recompra",    color: "text-pulse" },
};

export default function InsightsPage() {
  const [severityFilter, setSeverityFilter] = useState<"info" | "warning" | "critical" | "all">("all");
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const { data: counters } = useInsightCounters();
  const { data: insights, isLoading } = useInsightsFeed({
    severity: severityFilter,
    insightType: typeFilter,
    limit: 100,
  });

  const queryClient = useQueryClient();

  const updateStatus = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) => {
      await api.patch(`/api/insights/${id}/status`, { status, resolved_by: "dashboard" });
    },
    onSuccess: (_, v) => {
      queryClient.invalidateQueries({ queryKey: ["insights-feed"] });
      queryClient.invalidateQueries({ queryKey: ["insights-counters"] });
      toast.success(v.status === "resolved" ? "Insight resolvido" : "Insight descartado");
    },
  });

  const types = [
    { id: undefined,          label: "Todos" },
    { id: "churn",            label: "Churn",       count: counters?.churn },
    { id: "opportunity",      label: "Oportunidade",count: counters?.opportunity },
    { id: "replenishment",    label: "Recompra",    count: counters?.replenishment },
    { id: "margin",           label: "Margem",      count: counters?.margin },
    { id: "pricing",          label: "Preço",       count: counters?.pricing },
  ];

  return (
    <div className="min-h-screen">
      <Header />
      <main className="px-6 py-5 space-y-4 animate-fade-up">
        <div className="flex items-center gap-3">
          <Sparkles className="text-pulse" size={24} />
          <div>
            <h1 className="font-display text-3xl text-ink-50 tracking-tight leading-none">
              Inteligência
            </h1>
            <p className="text-sm text-ink-400 mt-2">
              Feed do motor de recomendações — ordenado por severidade × confiança
            </p>
          </div>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <SummaryCard label="Críticos" value={counters?.critical || 0} severity="critical" />
          <SummaryCard label="Atenção"  value={counters?.warning || 0}  severity="warning" />
          <SummaryCard label="Informativos" value={counters?.info || 0} severity="info" />
          <SummaryCard label="Oportunidades"
                       value={counters?.opportunity || 0} severity="success" />
        </div>

        {/* Filters */}
        <div className="panel px-4 py-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1">
            <span className="text-[10px] uppercase tracking-[0.15em] text-ink-400 mr-2">severidade</span>
            {(["all", "critical", "warning", "info"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSeverityFilter(s)}
                className={cn(
                  "px-3 py-1 text-xs rounded transition-colors",
                  severityFilter === s
                    ? "bg-pulse/15 text-pulse border border-pulse/30"
                    : "text-ink-300 hover:text-ink-100 border border-transparent",
                )}
              >
                {s === "all" ? "todas" : s === "critical" ? "crítico" : s === "warning" ? "atenção" : "info"}
              </button>
            ))}
          </div>

          <div className="h-6 w-px bg-ink-600/50" />

          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-[10px] uppercase tracking-[0.15em] text-ink-400 mr-2">tipo</span>
            {types.map((t) => (
              <button
                key={String(t.id)}
                onClick={() => setTypeFilter(t.id)}
                className={cn(
                  "px-3 py-1 text-xs rounded transition-colors flex items-center gap-1.5",
                  typeFilter === t.id
                    ? "bg-pulse/15 text-pulse border border-pulse/30"
                    : "text-ink-300 hover:text-ink-100 border border-transparent",
                )}
              >
                {t.label}
                {t.count !== undefined && t.count > 0 && (
                  <span className={cn(
                    "text-[10px] font-mono px-1 rounded",
                    typeFilter === t.id ? "bg-pulse/20" : "bg-ink-700/60",
                  )}>
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Insights list */}
        <div className="panel">
          {isLoading && (
            <div className="p-8 space-y-3">
              {[0, 1, 2, 3].map((i) => <div key={i} className="h-24 bg-ink-700/20 shimmer-bg rounded" />)}
            </div>
          )}
          {!isLoading && insights?.length === 0 && (
            <div className="p-16 text-center text-ink-400">
              <Zap className="mx-auto mb-2 text-emerald-500" size={32} />
              <div className="text-sm">Nenhum insight pendente nesse filtro.</div>
              <div className="text-xs text-ink-500 mt-1">Tudo sob controle.</div>
            </div>
          )}
          {!isLoading && insights?.map((i) => (
            <InsightFullCard
              key={i.id}
              insight={i}
              onResolve={() => updateStatus.mutate({ id: i.id, status: "resolved" })}
              onDismiss={() => updateStatus.mutate({ id: i.id, status: "dismissed" })}
            />
          ))}
        </div>
      </main>
    </div>
  );
}

function SummaryCard({ label, value, severity }: { label: string; value: number; severity: "critical" | "warning" | "info" | "success" }) {
  const styles = {
    critical: "border-rose-500/30 text-rose-500",
    warning:  "border-amber-500/30 text-amber-500",
    info:     "border-ink-500/30 text-ink-100",
    success:  "border-emerald-500/30 text-emerald-500",
  }[severity];
  return (
    <div className={cn("panel panel-body border", styles)}>
      <div className="metric-label">{label}</div>
      <div className={cn("metric-value text-3xl mt-1", styles.split(" ")[1])}>{value}</div>
    </div>
  );
}

function InsightFullCard({
  insight, onResolve, onDismiss,
}: { insight: Insight; onResolve: () => void; onDismiss: () => void }) {
  const meta = TYPE_META[insight.insight_type] || TYPE_META.opportunity;
  const Icon = meta.icon;
  const ago = formatDistanceToNow(parseISO(insight.generated_at), { locale: ptBR, addSuffix: true });

  return (
    <div className="px-4 py-4 border-b border-ink-600/30 hover:bg-ink-700/10 transition-colors">
      <div className="flex gap-4">
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0",
                           insight.severity === "critical" ? "bg-rose-500/15" :
                           insight.severity === "warning" ? "bg-amber-500/15" : "bg-ink-700")}>
          <Icon size={14} className={meta.color} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-[10px] uppercase tracking-[0.15em] text-ink-400 font-mono">
              {meta.label}
            </span>
            <span className={cn("pill",
              insight.severity === "critical" ? "pill-critical" :
              insight.severity === "warning" ? "pill-warning" : "pill-info")}>
              {insight.severity === "critical" ? "Crítico" : insight.severity === "warning" ? "Atenção" : "Info"}
            </span>
            {insight.customer_name && insight.customer_id && (
              <Link href={`/customers/${insight.customer_id}`}
                    className="text-xs text-ink-300 hover:text-pulse transition-colors flex items-center gap-0.5">
                {insight.customer_name} <ChevronRight size={10} />
              </Link>
            )}
            {insight.product_name && (
              <span className="text-xs text-ink-400">• {insight.product_name}</span>
            )}
            <span className="ml-auto text-[10px] text-ink-500 font-mono">{ago}</span>
          </div>

          <div className="text-base text-ink-50 font-medium leading-snug mb-1.5">
            {insight.title}
          </div>

          <div className="text-sm text-ink-300 leading-relaxed mb-3">
            {insight.description}
          </div>

          {insight.recommended_action && (
            <div className="text-sm text-pulse leading-relaxed bg-pulse/5 border-l-2 border-pulse/40 px-3 py-2 rounded-r mb-3">
              <span className="text-[10px] uppercase tracking-widest text-pulse/70 block mb-1 font-mono">
                Ação recomendada
              </span>
              {insight.recommended_action}
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              onClick={onResolve}
              className="flex items-center gap-1.5 px-3 py-1 text-xs rounded
                         bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/25 transition-colors"
            >
              <Check size={12} /> Resolver
            </button>
            <button
              onClick={onDismiss}
              className="flex items-center gap-1.5 px-3 py-1 text-xs rounded
                         text-ink-400 hover:text-ink-100 hover:bg-ink-700/40 transition-colors"
            >
              <X size={12} /> Descartar
            </button>
            {insight.confidence_score !== null && (
              <div className="ml-auto flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-ink-500">confiança</span>
                <div className="w-16 h-1 bg-ink-700 rounded overflow-hidden">
                  <div className={cn("h-full", meta.color, "bg-current")}
                       style={{ width: `${(insight.confidence_score || 0) * 100}%` }} />
                </div>
                <span className="font-mono text-[10px] text-ink-400">
                  {((insight.confidence_score || 0) * 100).toFixed(0)}%
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
