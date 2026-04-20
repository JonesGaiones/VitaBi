"use client";

import { useInsightsFeed, useInsightCounters, type Insight } from "@/lib/queries";
import { fmtCurrency, fmtNumber } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  AlertTriangle, TrendingDown, Target, Clock, DollarSign,
  CircleDot, Sparkles,
} from "lucide-react";
import { useState } from "react";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";

const TYPE_META: Record<string, { icon: any; label: string; color: string }> = {
  churn:         { icon: TrendingDown, label: "Churn",       color: "text-rose-500" },
  pricing:       { icon: DollarSign,   label: "Preço",       color: "text-amber-500" },
  margin:        { icon: AlertTriangle,label: "Margem",      color: "text-rose-500" },
  opportunity:   { icon: Target,       label: "Oportunidade",color: "text-emerald-500" },
  replenishment: { icon: Clock,        label: "Recompra",    color: "text-pulse" },
};

const SEVERITY_PILL: Record<string, string> = {
  critical: "pill-critical",
  warning: "pill-warning",
  info: "pill-info",
};

export function InsightsFeed() {
  const [activeTab, setActiveTab] = useState<"all" | string>("all");

  const { data: counters } = useInsightCounters();
  const { data: insights, isLoading } = useInsightsFeed({
    insightType: activeTab === "all" ? undefined : activeTab,
    limit: 30,
  });

  const tabs = [
    { id: "all",           label: "Todos",       count: (counters?.critical || 0) + (counters?.warning || 0) + (counters?.info || 0) },
    { id: "churn",         label: "Churn",       count: counters?.churn || 0 },
    { id: "opportunity",   label: "Oportunidades", count: counters?.opportunity || 0 },
    { id: "replenishment", label: "Recompra",    count: counters?.replenishment || 0 },
    { id: "margin",        label: "Margem",      count: counters?.margin || 0 },
    { id: "pricing",       label: "Preço",       count: counters?.pricing || 0 },
  ];

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-pulse" />
          <h3 className="font-display text-lg text-ink-50 tracking-tight leading-none">
            Inteligência
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-[0.2em] text-ink-400 font-mono">
          atualizado agora
        </span>
      </div>

      {/* Tabs */}
      <div className="px-3 pt-3 flex gap-1 flex-wrap border-b border-ink-600/40 pb-3">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={cn(
              "px-2.5 py-1 rounded text-xs transition-colors flex items-center gap-1.5",
              activeTab === t.id
                ? "bg-pulse/15 text-pulse border border-pulse/30"
                : "text-ink-300 hover:text-ink-100 border border-transparent hover:bg-ink-700/40",
            )}
          >
            {t.label}
            {t.count > 0 && (
              <span className={cn(
                "text-[10px] font-mono px-1 rounded",
                activeTab === t.id ? "bg-pulse/20" : "bg-ink-700/60",
              )}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="p-4 space-y-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-24 rounded bg-ink-700/30 shimmer-bg" />
            ))}
          </div>
        )}
        {!isLoading && insights && insights.length === 0 && (
          <div className="p-8 text-center text-ink-400 text-sm">
            Nenhum insight pendente.
            <br />
            <span className="text-ink-500 text-xs">Tudo sob controle.</span>
          </div>
        )}
        {!isLoading && insights && insights.map((i) => <InsightCard key={i.id} insight={i} />)}
      </div>
    </div>
  );
}

function InsightCard({ insight }: { insight: Insight }) {
  const meta = TYPE_META[insight.insight_type] || TYPE_META.opportunity;
  const Icon = meta.icon;

  const ago = insight.generated_at
    ? formatDistanceToNow(parseISO(insight.generated_at), { locale: ptBR, addSuffix: true })
    : "";

  return (
    <div className="px-4 py-3 border-b border-ink-600/30 hover:bg-ink-700/20 transition-colors cursor-pointer">
      {/* Top bar */}
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={12} className={meta.color} />
        <span className="text-[10px] uppercase tracking-[0.15em] text-ink-400 font-mono">
          {meta.label}
        </span>
        <span className={cn("pill", SEVERITY_PILL[insight.severity])}>
          <CircleDot size={8} />
          {insight.severity === "critical" ? "Crítico" : insight.severity === "warning" ? "Atenção" : "Info"}
        </span>
        <span className="ml-auto text-[10px] text-ink-500 font-mono">{ago}</span>
      </div>

      {/* Title */}
      <div className="text-sm text-ink-50 font-medium leading-snug mb-1">
        {insight.title}
      </div>

      {/* Description */}
      <div className="text-xs text-ink-300 leading-relaxed mb-2 line-clamp-2">
        {insight.description}
      </div>

      {/* Action */}
      {insight.recommended_action && (
        <div className="text-xs text-pulse leading-relaxed bg-pulse/5 border-l-2 border-pulse/40 px-2.5 py-1.5 rounded-r">
          {insight.recommended_action}
        </div>
      )}

      {/* Confidence meter */}
      {insight.confidence_score !== null && (
        <div className="flex items-center gap-2 mt-2">
          <span className="text-[10px] text-ink-500 uppercase tracking-wider">confiança</span>
          <div className="flex-1 h-0.5 bg-ink-700 rounded overflow-hidden">
            <div
              className={cn("h-full", meta.color, "bg-current")}
              style={{ width: `${(insight.confidence_score || 0) * 100}%` }}
            />
          </div>
          <span className="text-[10px] font-mono text-ink-400">
            {((insight.confidence_score || 0) * 100).toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  );
}
