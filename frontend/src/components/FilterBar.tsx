"use client";

import { useStore } from "@/lib/store";
import { cn } from "@/lib/cn";
import { Calendar, TrendingUp, GitCompareArrows } from "lucide-react";

export function FilterBar() {
  const { filters, setFilter, metric, setMetric, compare, setCompare } = useStore();

  return (
    <div className="panel px-4 py-3 flex flex-wrap items-center gap-4">
      {/* Date range */}
      <div className="flex items-center gap-2">
        <Calendar size={14} className="text-ink-300" />
        <input
          type="date"
          value={filters.dateFrom}
          onChange={(e) => setFilter("dateFrom", e.target.value)}
          className="bg-ink-700/60 border border-ink-600/50 rounded px-2 py-1
                     text-sm font-mono tracking-tight focus:outline-none
                     focus:border-pulse/60"
        />
        <span className="text-ink-400 text-xs">→</span>
        <input
          type="date"
          value={filters.dateTo}
          onChange={(e) => setFilter("dateTo", e.target.value)}
          className="bg-ink-700/60 border border-ink-600/50 rounded px-2 py-1
                     text-sm font-mono tracking-tight focus:outline-none
                     focus:border-pulse/60"
        />
      </div>

      <div className="h-6 w-px bg-ink-600/50" />

      {/* Metric */}
      <div className="flex items-center gap-1">
        <TrendingUp size={14} className="text-ink-300 mr-1" />
        {([
          ["revenue",  "Receita"],
          ["quantity", "Volume"],
          ["margin",   "Margem"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setMetric(key)}
            className={cn(
              "px-3 py-1 text-xs rounded transition-colors tracking-wide",
              metric === key
                ? "bg-pulse/15 text-pulse border border-pulse/30"
                : "text-ink-300 hover:text-ink-100 border border-transparent",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="h-6 w-px bg-ink-600/50" />

      {/* Compare */}
      <div className="flex items-center gap-1">
        <GitCompareArrows size={14} className="text-ink-300 mr-1" />
        {([
          ["none", "—"],
          ["mom",  "MoM"],
          ["yoy",  "YoY"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setCompare(key)}
            className={cn(
              "px-2.5 py-1 text-xs rounded transition-colors font-mono tracking-wide",
              compare === key
                ? "bg-ink-100/10 text-ink-100 border border-ink-100/20"
                : "text-ink-300 hover:text-ink-100 border border-transparent",
            )}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
