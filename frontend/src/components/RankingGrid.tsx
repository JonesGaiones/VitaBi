"use client";

import { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";
import { useStore } from "@/lib/store";
import { useRanking, useDrilldown } from "@/lib/queries";
import { fmtCurrency, fmtNumber, fmtPercent } from "@/lib/format";
import type { ColDef } from "ag-grid-community";

type Dimension = "customer" | "product" | "salesperson" | "category";

function nextBreakdown(currentDim: Dimension, stackLen: number) {
  if (stackLen >= 2) return "month";
  const map: Record<Dimension, any> = {
    customer: "product",
    product: "customer",
    salesperson: "customer",
    category: "product",
  };
  return map[currentDim];
}

export function RankingGrid({ initialDimension }: { initialDimension: Dimension }) {
  const { filters, metric, drillStack, pushDrill } = useStore();

  const isDrilling = drillStack.length > 0;
  const currentDrill = drillStack[drillStack.length - 1];
  const nextBreak = isDrilling
    ? nextBreakdown(currentDrill.entity, drillStack.length)
    : initialDimension;

  const rankingQuery = useRanking(initialDimension, filters, metric, 50);
  const drillQuery = useDrilldown({
    entity: currentDrill?.entity || "customer",
    entityId: currentDrill?.id || "",
    breakdownBy: nextBreak as any,
    metric,
    dateFrom: filters.dateFrom,
    dateTo: filters.dateTo,
    enabled: isDrilling,
  });

  const rows = isDrilling ? drillQuery.data : rankingQuery.data;
  const isLoading = isDrilling ? drillQuery.isLoading : rankingQuery.isLoading;

  const metricLabel = metric === "revenue" ? "Receita"
                     : metric === "quantity" ? "Volume" : "Margem";

  const columnDefs: ColDef[] = useMemo(() => {
    const cols: ColDef[] = [
      {
        headerName: "#",
        valueGetter: (p) => (p.node?.rowIndex ?? 0) + 1,
        width: 52, pinned: "left", sortable: false, filter: false,
        cellClass: "text-ink-400 font-mono text-xs",
      },
      {
        field: "label",
        headerName: labelFor(nextBreak),
        flex: 2, minWidth: 180,
        cellClass: "font-medium",
      },
      {
        field: "value",
        headerName: metricLabel,
        width: 130,
        type: "numericColumn",
        valueFormatter: (p) => metric === "quantity" ? fmtNumber(p.value) : fmtCurrency(p.value),
        cellClass: "text-pulse font-mono text-right",
        sort: "desc",
      },
      {
        field: "share",
        headerName: "% do total",
        width: 110,
        type: "numericColumn",
        valueFormatter: (p) => fmtPercent(p.value),
        cellRenderer: (p: any) => {
          const pct = (p.value || 0) * 100;
          return (
            <div className="flex items-center gap-2 justify-end">
              <span className="font-mono text-xs text-ink-200">{fmtPercent(p.value)}</span>
              <div className="w-12 h-1 bg-ink-700 rounded overflow-hidden">
                <div
                  className="h-full bg-pulse"
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
            </div>
          );
        },
      },
      {
        field: "orders",
        headerName: "Pedidos",
        width: 90,
        type: "numericColumn",
        valueFormatter: (p) => fmtNumber(p.value),
        cellClass: "font-mono text-ink-300 text-right",
      },
    ];
    if (isDrilling && "avg_price" in (rows?.[0] || {})) {
      cols.push({
        field: "avg_price",
        headerName: "Preço médio",
        width: 120,
        type: "numericColumn",
        valueFormatter: (p) => fmtCurrency(p.value),
        cellClass: "font-mono text-ink-300 text-right",
      });
    }
    return cols;
  }, [metric, metricLabel, isDrilling, nextBreak, rows]);

  const onRowClicked = (e: any) => {
    const row = e.data;
    if (!row.id) return;
    const drillInto = (isDrilling ? nextBreak : initialDimension) as Dimension;
    if (drillInto === ("month" as any)) return;
    pushDrill({ entity: drillInto, id: String(row.id), label: row.label });
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h3 className="font-display text-lg text-ink-50 tracking-tight leading-none">
            Detalhe numérico
          </h3>
          <p className="text-xs text-ink-400 mt-1">
            Ordenado do maior para o menor • clique em uma linha para detalhar
          </p>
        </div>
        {rows && (
          <span className="text-xs font-mono text-ink-400">
            {rows.length} {rows.length === 1 ? "registro" : "registros"}
          </span>
        )}
      </div>

      <div className="panel-body">
        <div className="ag-theme-alpine-dark" style={{ height: 440 }}>
          <AgGridReact
            rowData={rows || []}
            columnDefs={columnDefs}
            defaultColDef={{
              resizable: true, sortable: true, filter: true, filterParams: { buttons: ["reset"] },
            }}
            animateRows
            rowHeight={36}
            headerHeight={36}
            suppressCellFocus
            onRowClicked={onRowClicked}
            loadingOverlayComponent={() => (
              <div className="text-ink-400 text-sm">Carregando…</div>
            )}
            overlayNoRowsTemplate='<span class="text-ink-400">Sem dados</span>'
          />
        </div>
      </div>
    </div>
  );
}

function labelFor(key: string): string {
  const map: Record<string, string> = {
    customer: "Cliente",
    product: "Produto",
    salesperson: "Vendedor",
    category: "Categoria",
    month: "Mês",
  };
  return map[key] || key;
}
