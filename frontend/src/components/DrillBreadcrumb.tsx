"use client";

import { useStore } from "@/lib/store";
import { cn } from "@/lib/cn";
import { ChevronRight, Home, X } from "lucide-react";

export function DrillBreadcrumb() {
  const { drillStack, goToDrill, clearDrill } = useStore();

  if (drillStack.length === 0) {
    return (
      <div className="trail">
        <div className="trail-item trail-item--active flex items-center gap-1.5">
          <Home size={12} />
          Visão geral
        </div>
      </div>
    );
  }

  return (
    <div className="trail flex-wrap">
      <button
        className="trail-item flex items-center gap-1.5"
        onClick={clearDrill}
      >
        <Home size={12} />
        Visão geral
      </button>

      {drillStack.map((level, i) => (
        <div key={`${level.entity}-${level.id}`} className="flex items-center">
          <ChevronRight size={12} className="text-ink-500 mx-0.5" />
          <button
            onClick={() => goToDrill(i)}
            className={cn(
              "trail-item",
              i === drillStack.length - 1 && "trail-item--active",
            )}
          >
            <span className="text-ink-400 text-[10px] uppercase tracking-wider mr-1.5">
              {labelForEntity(level.entity)}
            </span>
            {level.label}
          </button>
        </div>
      ))}

      {drillStack.length > 0 && (
        <button
          onClick={clearDrill}
          className="ml-2 text-ink-400 hover:text-ink-100 flex items-center gap-1
                     text-xs transition-colors"
          title="Limpar drill-down"
        >
          <X size={12} /> limpar
        </button>
      )}
    </div>
  );
}

function labelForEntity(entity: string): string {
  switch (entity) {
    case "customer": return "Cliente";
    case "product": return "Produto";
    case "salesperson": return "Vendedor";
    case "category": return "Categoria";
    default: return entity;
  }
}
