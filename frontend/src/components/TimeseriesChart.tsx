"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import { useStore } from "@/lib/store";
import { useTimeseries } from "@/lib/queries";
import { fmtCurrency, fmtNumber } from "@/lib/format";
import type { EChartsOption } from "echarts";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function TimeseriesChart() {
  const { filters, metric, compare } = useStore();
  const { data, isLoading } = useTimeseries(metric, "month", compare, filters);

  const option = useMemo<EChartsOption>(() => {
    if (!data) return {};
    const periods = data.current.map((p) => p.period.slice(0, 7));
    const values = data.current.map((p) => p.value);
    const cmpValues = data.compare?.map((p) => p.value) || [];

    const fmt = (v: number) =>
      metric === "quantity" ? fmtNumber(v, true) : fmtCurrency(v, true);

    const series: EChartsOption["series"] = [
      {
        name: "Atual",
        type: "line",
        data: values,
        smooth: 0.3,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { color: "#ff6b35", width: 2 },
        itemStyle: { color: "#ff6b35", borderColor: "#12121a", borderWidth: 2 },
        areaStyle: {
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(255, 107, 53, 0.35)" },
              { offset: 1, color: "rgba(255, 107, 53, 0.00)" },
            ],
          },
        },
        z: 3,
      },
    ];

    if (compare !== "none" && cmpValues.length > 0) {
      (series as any[]).push({
        name: compare === "yoy" ? "Ano anterior" : "Mês anterior",
        type: "line",
        data: cmpValues,
        smooth: 0.3,
        symbol: "circle",
        symbolSize: 4,
        lineStyle: { color: "#6e6e7a", width: 1.5, type: "dashed" },
        itemStyle: { color: "#6e6e7a" },
        z: 2,
      });
    }

    return {
      grid: { left: 50, right: 12, top: 30, bottom: 30 },
      legend: {
        right: 0, top: 0,
        textStyle: { color: "#9e9ea8", fontSize: 11, fontFamily: "Geist Sans" },
        icon: "roundRect", itemWidth: 12, itemHeight: 3,
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(18, 18, 26, 0.95)",
        borderColor: "rgba(255, 107, 53, 0.4)",
        borderWidth: 1,
        textStyle: { color: "#e8e8eb", fontSize: 12 },
        extraCssText: "backdrop-filter: blur(8px);",
        formatter: (params: any) => {
          const arr = Array.isArray(params) ? params : [params];
          return arr
            .map((p) => `
              <div style="display: flex; justify-content: space-between; gap: 16px; margin: 2px 0;">
                <span style="color: #9e9ea8;">${p.marker} ${p.seriesName}</span>
                <span style="color: #e8e8eb; font-family: 'JetBrains Mono'; font-weight: 600;">
                  ${fmt(p.value)}
                </span>
              </div>
            `)
            .join("");
        },
      },
      xAxis: {
        type: "category",
        data: periods,
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.1)" } },
        axisLabel: {
          color: "#6e6e7a", fontSize: 10, fontFamily: "JetBrains Mono",
        },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
        axisLabel: {
          color: "#6e6e7a", fontSize: 10, fontFamily: "JetBrains Mono",
          formatter: (v: number) => fmt(v),
        },
      },
      series,
    };
  }, [data, metric, compare]);

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <h3 className="font-display text-lg text-ink-50 tracking-tight leading-none">
            Evolução temporal
          </h3>
          <p className="text-xs text-ink-400 mt-1">
            Agregação mensal
            {compare === "yoy" && " • comparativo YoY"}
            {compare === "mom" && " • comparativo MoM"}
          </p>
        </div>
      </div>
      <div className="panel-body">
        {isLoading ? (
          <div className="h-[280px] flex items-center justify-center text-ink-400 text-sm">
            <div className="shimmer-bg w-full h-full rounded" />
          </div>
        ) : (
          <ReactECharts option={option} style={{ height: 280 }} opts={{ renderer: "canvas" }} />
        )}
      </div>
    </div>
  );
}
