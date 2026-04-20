"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import { useStore } from "@/lib/store";
import { useRanking, useDrilldown, type RankingRow, type DrillRow } from "@/lib/queries";
import { fmtCurrency, fmtNumber, fmtPercent } from "@/lib/format";
import type { EChartsOption } from "echarts";

// ECharts é pesado; carrega só no client
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Dimension = "customer" | "product" | "salesperson" | "category";

// ---------------------------------------------------------------------------
// Lógica do "próximo nível"
// Quando o usuário clica numa barra, decide qual breakdown usar a seguir.
// ---------------------------------------------------------------------------
function nextBreakdown(
  currentDimension: Dimension,
  drillStackLength: number,
): "customer" | "product" | "salesperson" | "category" | "month" {
  // Se já temos um drill-down profundo, último nível vai para mês
  if (drillStackLength >= 2) return "month";

  // Caso contrário, cascata lógica:
  // customer → product → month
  // product → customer → month
  // salesperson → customer → month
  // category → product → month
  const map: Record<Dimension, any> = {
    customer: "product",
    product: "customer",
    salesperson: "customer",
    category: "product",
  };
  return map[currentDimension];
}

// ---------------------------------------------------------------------------
// Formatter dinâmico baseado na métrica
// ---------------------------------------------------------------------------
function formatMetric(value: number, metric: "revenue" | "quantity" | "margin"): string {
  if (metric === "quantity") return fmtNumber(value, true);
  return fmtCurrency(value, true);
}

// ---------------------------------------------------------------------------
// Opção do gráfico ECharts
// ---------------------------------------------------------------------------
function buildChartOption(
  rows: Array<RankingRow | DrillRow>,
  metric: "revenue" | "quantity" | "margin",
): EChartsOption {
  // Já vêm ordenados DESC do backend; invertemos pro ECharts
  // (que empilha do topo pra baixo, e queremos o maior NO TOPO)
  const data = [...rows].reverse();

  return {
    grid: { left: 12, right: 80, top: 12, bottom: 12, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(18, 18, 26, 0.95)",
      borderColor: "rgba(255, 107, 53, 0.4)",
      borderWidth: 1,
      textStyle: { color: "#e8e8eb", fontSize: 12 },
      extraCssText: "backdrop-filter: blur(8px); box-shadow: 0 12px 32px rgba(0,0,0,0.6);",
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params;
        const row = data[p.dataIndex];
        const share = "share" in row ? (row.share * 100).toFixed(1) : "";
        return `
          <div style="font-family: 'Geist Sans'; padding: 4px;">
            <div style="font-weight: 600; margin-bottom: 4px;">${row.label}</div>
            <div style="color: #ff6b35; font-family: 'JetBrains Mono'; font-size: 13px;">
              ${formatMetric(row.value, metric)}
            </div>
            ${share ? `<div style="color: #9e9ea8; font-size: 11px; margin-top: 2px;">
              ${share}% do total • ${row.orders} pedidos
            </div>` : ""}
            <div style="color: #ff6b35; font-size: 10px; margin-top: 6px;
                        padding-top: 4px; border-top: 1px solid rgba(255,255,255,0.08);">
              → Clique para detalhar
            </div>
          </div>
        `;
      },
    },
    xAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
      axisLabel: {
        color: "#6e6e7a",
        fontSize: 10,
        fontFamily: "JetBrains Mono",
        formatter: (v: number) => formatMetric(v, metric),
      },
    },
    yAxis: {
      type: "category",
      data: data.map((r) => r.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#cdcdd3",
        fontSize: 11,
        fontFamily: "Geist Sans",
        formatter: (label: string) => label.length > 24 ? label.slice(0, 22) + "…" : label,
      },
    },
    series: [
      {
        type: "bar",
        data: data.map((r, i) => ({
          value: r.value,
          itemStyle: {
            // Gradiente com intensidade proporcional ao rank (maior = mais vivo)
            color: {
              type: "linear",
              x: 0, y: 0, x2: 1, y2: 0,
              colorStops: [
                { offset: 0, color: `rgba(255, 107, 53, ${0.4 + 0.5 * (i / data.length)})` },
                { offset: 1, color: `rgba(255, 149, 112, ${0.5 + 0.4 * (i / data.length)})` },
              ],
            },
            borderRadius: [0, 4, 4, 0],
          },
          emphasis: {
            itemStyle: { color: "#ff6b35" },
          },
        })),
        barWidth: "55%",
        label: {
          show: true,
          position: "right",
          color: "#ff9570",
          fontSize: 11,
          fontFamily: "JetBrains Mono",
          formatter: (p: any) => formatMetric(p.value, metric),
        },
        animationDuration: 600,
        animationEasing: "cubicOut",
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------
export function DrillDownChart({
  initialDimension,
  title,
}: {
  initialDimension: Dimension;
  title: string;
}) {
  const { filters, metric, drillStack, pushDrill } = useStore();

  // Decide qual query rodar: ranking de topo, ou drill-down?
  const isDrilling = drillStack.length > 0;
  const currentDrill = drillStack[drillStack.length - 1];
  const nextBreak = isDrilling
    ? nextBreakdown(currentDrill.entity, drillStack.length)
    : initialDimension;

  // Query #1: ranking de topo (quando não há drill-down ativo)
  const rankingQuery = useRanking(initialDimension, filters, metric, 15);

  // Query #2: drill-down (quando está dentro de uma entidade)
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

  // Chart option
  const option = useMemo(() => rows ? buildChartOption(rows, metric) : {}, [rows, metric]);

  // Click handler — o coração do drill-down
  const onChartClick = (params: any) => {
    if (!rows || rows.length === 0) return;
    // ECharts inverte o índice quando invertemos o array
    const idx = rows.length - 1 - params.dataIndex;
    const clicked = rows[idx];
    if (!clicked.id) return;

    // Mês não é drillable (não faz sentido drill "por mês" recursivamente)
    const drillInto = (isDrilling ? nextBreak : initialDimension) as Dimension;
    if (drillInto === ("month" as any)) return;

    pushDrill({
      entity: drillInto,
      id: String(clicked.id),
      label: clicked.label,
    });
  };

  // Subtítulo dinâmico
  const subtitle = isDrilling
    ? `Quebra por ${labelFor(nextBreak)} • ordem decrescente`
    : `Top ${rows?.length || 15} por ${metric === "revenue" ? "receita" : metric === "quantity" ? "volume" : "margem"}`;

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h3 className="font-display text-lg text-ink-50 tracking-tight leading-none">
            {title}
          </h3>
          <p className="text-xs text-ink-400 mt-1">{subtitle}</p>
        </div>
        {rows && !isLoading && (
          <div className="text-[10px] uppercase tracking-[0.2em] text-pulse/70 font-mono">
            clique p/ detalhar
          </div>
        )}
      </div>

      <div className="panel-body">
        {isLoading && (
          <div className="h-[440px] flex items-center justify-center text-ink-400 text-sm">
            <div className="shimmer-bg w-full h-full rounded animate-pulse" />
          </div>
        )}
        {!isLoading && rows && rows.length > 0 && (
          <ReactECharts
            option={option}
            style={{ height: 440 }}
            onEvents={{ click: onChartClick }}
            opts={{ renderer: "canvas" }}
          />
        )}
        {!isLoading && rows && rows.length === 0 && (
          <div className="h-[440px] flex items-center justify-center text-ink-400 text-sm">
            Nenhum dado encontrado para esses filtros.
          </div>
        )}
      </div>
    </div>
  );
}

function labelFor(key: string): string {
  const map: Record<string, string> = {
    customer: "cliente",
    product: "produto",
    salesperson: "vendedor",
    category: "categoria",
    month: "mês",
  };
  return map[key] || key;
}
