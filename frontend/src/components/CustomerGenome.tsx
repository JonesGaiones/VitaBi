"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtCurrency, fmtNumber, fmtPercent } from "@/lib/format";
import type { EChartsOption } from "echarts";
import { cn } from "@/lib/cn";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Genome = {
  seasonality: Array<{ month: number; revenue: number; orders: number }>;
  anchor_products: Array<{
    id: string; name: string; category: string;
    revenue: number; quantity: number; orders: number; avg_price: number;
  }>;
  elasticity: {
    discount_elasticity: number;
    avg_discount_pct: number;
    price_volatility: number;
  };
  implicit_nps: number;
};

// ---------------------------------------------------------------------------
// Visualização radial da sazonalidade (12 meses em 360°)
// ---------------------------------------------------------------------------
function buildRadialOption(genome: Genome): EChartsOption {
  const months = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
  const byMonth = new Array(12).fill(0);
  genome.seasonality.forEach((s) => { byMonth[s.month - 1] = s.revenue; });
  const max = Math.max(...byMonth) || 1;

  return {
    polar: { radius: ["25%", "85%"] },
    angleAxis: {
      type: "category",
      data: months,
      axisLabel: {
        color: "#9e9ea8",
        fontSize: 11,
        fontFamily: "JetBrains Mono",
      },
      axisLine: { show: false },
      axisTick: { show: false },
      startAngle: 90,
    },
    radiusAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.06)" } },
    },
    tooltip: {
      backgroundColor: "rgba(18,18,26,0.95)",
      borderColor: "rgba(255,107,53,0.4)",
      textStyle: { color: "#e8e8eb", fontSize: 12 },
      formatter: (p: any) => `
        <div style="font-family: 'Geist Sans'; padding: 4px;">
          <div style="color: #9e9ea8; font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em;">
            ${p.name}
          </div>
          <div style="color: #ff6b35; font-family: 'JetBrains Mono'; font-size: 14px; margin-top: 2px;">
            ${fmtCurrency(p.value, true)}
          </div>
        </div>
      `,
    },
    series: [
      {
        type: "bar",
        coordinateSystem: "polar",
        data: byMonth.map((v) => ({
          value: v,
          itemStyle: {
            color: {
              type: "radial",
              x: 0.5, y: 0.5, r: 0.5,
              colorStops: [
                { offset: 0, color: `rgba(255, 107, 53, ${0.3 + 0.7 * (v / max)})` },
                { offset: 1, color: `rgba(255, 149, 112, ${0.2 + 0.5 * (v / max)})` },
              ],
            },
            borderRadius: [2, 2, 0, 0],
          },
        })),
        animationDuration: 800,
        animationEasing: "elasticOut",
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Helpers para interpretar a elasticidade
// ---------------------------------------------------------------------------
function interpretElasticity(e: number): { label: string; color: string; description: string } {
  if (e > 0.3)  return { label: "Reage a desconto",  color: "text-emerald-500", description: "Quando há desconto, compra mais. Ferramenta útil pra mover volume." };
  if (e > 0.1)  return { label: "Leve sensibilidade", color: "text-amber-500",  description: "Responde de forma moderada a promoções." };
  if (e > -0.1) return { label: "Indiferente",        color: "text-ink-300",    description: "Desconto não afeta comportamento. Comprador por necessidade." };
  return          { label: "Inelástico",               color: "text-rose-500",   description: "Compra sempre igual independente de preço. Cliente premium." };
}

function interpretVolatility(v: number): { label: string; color: string } {
  if (v < 0.08) return { label: "Preço muito estável",  color: "text-emerald-500" };
  if (v < 0.15) return { label: "Preço estável",        color: "text-ink-200" };
  if (v < 0.25) return { label: "Preço variável",       color: "text-amber-500" };
  return         { label: "Preço muito volátil",         color: "text-rose-500" };
}

function interpretNPS(n: number): { label: string; color: string } {
  if (n >= 80) return { label: "Cliente premium",      color: "text-emerald-500" };
  if (n >= 60) return { label: "Cliente saudável",     color: "text-emerald-600" };
  if (n >= 40) return { label: "Cliente em atenção",   color: "text-amber-500" };
  if (n >= 20) return { label: "Cliente em risco",     color: "text-rose-500" };
  return         { label: "Cliente crítico",             color: "text-rose-600" };
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------
export function CustomerGenome({ customerId }: { customerId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["genome", customerId],
    queryFn: async () => {
      const r = await api.get<Genome>(`/api/customers/${customerId}/genome`);
      return r.data;
    },
  });

  const option = useMemo(() => data ? buildRadialOption(data) : {}, [data]);

  if (isLoading) {
    return (
      <div className="panel h-96 flex items-center justify-center text-ink-400">
        <div className="shimmer-bg w-full h-full rounded-xl" />
      </div>
    );
  }
  if (!data) return null;

  const elast = interpretElasticity(data.elasticity.discount_elasticity);
  const vol   = interpretVolatility(data.elasticity.price_volatility);
  const nps   = interpretNPS(data.implicit_nps);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Radial Seasonality (2 cols) */}
      <div className="panel lg:col-span-2">
        <div className="panel-header">
          <div>
            <h3 className="font-display text-lg text-ink-50 tracking-tight leading-none">
              Assinatura sazonal
            </h3>
            <p className="text-xs text-ink-400 mt-1">
              Faturamento por mês — últimos 24 meses
            </p>
          </div>
          <span className="text-[10px] uppercase tracking-[0.2em] text-pulse/70 font-mono">
            genoma
          </span>
        </div>
        <div className="panel-body">
          <ReactECharts option={option} style={{ height: 400 }} opts={{ renderer: "canvas" }} />
        </div>
      </div>

      {/* NPS + Behavioral traits (1 col) */}
      <div className="panel flex flex-col">
        <div className="panel-header">
          <div>
            <h3 className="font-display text-lg text-ink-50 tracking-tight leading-none">
              Personalidade
            </h3>
            <p className="text-xs text-ink-400 mt-1">Comportamento de compra</p>
          </div>
        </div>
        <div className="panel-body flex-1 space-y-5">
          {/* NPS implícito */}
          <div>
            <div className="metric-label mb-2">NPS implícito</div>
            <div className="relative h-2 bg-ink-700 rounded-full overflow-hidden mb-2">
              <div
                className={cn("absolute left-0 top-0 h-full transition-all",
                  data.implicit_nps >= 60 ? "bg-emerald-500" :
                  data.implicit_nps >= 40 ? "bg-amber-500" : "bg-rose-500")}
                style={{ width: `${data.implicit_nps}%` }}
              />
            </div>
            <div className="flex items-baseline justify-between">
              <span className={cn("font-mono text-2xl", nps.color)}>{data.implicit_nps}</span>
              <span className={cn("text-xs", nps.color)}>{nps.label}</span>
            </div>
            <p className="text-[10px] text-ink-500 mt-1">
              Derivado de frequência de compra × atraso vs. ciclo esperado
            </p>
          </div>

          <div className="h-px bg-ink-600/40" />

          {/* Elasticidade */}
          <div>
            <div className="metric-label mb-2">Elasticidade a desconto</div>
            <div className="flex items-baseline justify-between mb-1">
              <span className="font-mono text-lg text-ink-100">
                {data.elasticity.discount_elasticity.toFixed(3)}
              </span>
              <span className={cn("text-xs font-medium", elast.color)}>{elast.label}</span>
            </div>
            <p className="text-[11px] text-ink-400 leading-snug">{elast.description}</p>
            {data.elasticity.avg_discount_pct > 0 && (
              <p className="text-[10px] text-ink-500 mt-1">
                Desconto médio aplicado: {fmtPercent(data.elasticity.avg_discount_pct)}
              </p>
            )}
          </div>

          <div className="h-px bg-ink-600/40" />

          {/* Volatilidade de preço */}
          <div>
            <div className="metric-label mb-2">Volatilidade de preço</div>
            <div className="flex items-baseline justify-between mb-1">
              <span className="font-mono text-lg text-ink-100">
                {fmtPercent(data.elasticity.price_volatility * 100)}
              </span>
              <span className={cn("text-xs font-medium", vol.color)}>{vol.label}</span>
            </div>
            <p className="text-[11px] text-ink-400 leading-snug">
              Dispersão do preço pago relativa à média
            </p>
          </div>
        </div>
      </div>

      {/* Anchor Products (full width) */}
      <div className="panel lg:col-span-3">
        <div className="panel-header">
          <div>
            <h3 className="font-display text-lg text-ink-50 tracking-tight leading-none">
              Produtos âncora
            </h3>
            <p className="text-xs text-ink-400 mt-1">
              Top 5 por faturamento — últimos 12 meses
            </p>
          </div>
        </div>
        <div className="panel-body">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
            {data.anchor_products.map((p, i) => (
              <div
                key={p.id}
                className={cn(
                  "rounded-lg border p-3 relative overflow-hidden transition-colors",
                  i === 0 ? "border-pulse/30 bg-pulse/5" : "border-ink-600/40 bg-ink-700/20",
                )}
              >
                {i === 0 && (
                  <div className="absolute top-0 right-0 text-[9px] uppercase tracking-widest text-pulse/70 font-mono px-2 py-0.5">
                    #1
                  </div>
                )}
                <div className="text-[10px] uppercase tracking-[0.15em] text-ink-400 mb-1">
                  {p.category}
                </div>
                <div className="text-sm text-ink-100 font-medium leading-tight mb-2 line-clamp-2 h-10">
                  {p.name}
                </div>
                <div className="font-mono text-base text-pulse">
                  {fmtCurrency(p.revenue, true)}
                </div>
                <div className="text-[10px] text-ink-400 mt-1 font-mono">
                  {fmtNumber(p.quantity)} un • {fmtCurrency(p.avg_price)} méd.
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
