"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Filters } from "./store";

// ---------------------------------------------------------------------------
// Shared params builder
// ---------------------------------------------------------------------------
function filterParams(filters: Filters) {
  return {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    ...(filters.customerId ? { customer_id: filters.customerId } : {}),
    ...(filters.productId ? { product_id: filters.productId } : {}),
    ...(filters.salespersonId ? { salesperson_id: filters.salespersonId } : {}),
  };
}

// ---------------------------------------------------------------------------
// KPIs
// ---------------------------------------------------------------------------
export type Kpis = {
  revenue: number;
  revenue_change_pct: number | null;
  quantity: number;
  quantity_change_pct: number | null;
  margin: number;
  avg_order_value: number;
  customers: number;
  customers_change_pct: number | null;
  orders: number;
  avg_unit_price: number;
};

export function useKpis(filters: Filters) {
  return useQuery({
    queryKey: ["kpis", filters.dateFrom, filters.dateTo],
    queryFn: async () => {
      const r = await api.get<Kpis>("/api/sales/kpis", {
        params: { date_from: filters.dateFrom, date_to: filters.dateTo },
      });
      return r.data;
    },
  });
}

// ---------------------------------------------------------------------------
// Ranking
// ---------------------------------------------------------------------------
export type RankingRow = {
  id: string | null;
  label: string;
  value: number;
  orders: number;
  share: number;
};

export function useRanking(
  dimension: "customer" | "product" | "salesperson" | "category",
  filters: Filters,
  metric: "revenue" | "quantity" | "margin",
  limit = 20,
) {
  return useQuery({
    queryKey: ["ranking", dimension, metric, limit, filters],
    queryFn: async () => {
      const r = await api.get<RankingRow[]>("/api/sales/ranking", {
        params: { dimension, metric, limit, ...filterParams(filters) },
      });
      return r.data;
    },
  });
}

// ---------------------------------------------------------------------------
// Drill-down
// ---------------------------------------------------------------------------
export type DrillRow = {
  id: string;
  label: string;
  value: number;
  orders: number;
  avg_price: number;
  share: number;
};

export function useDrilldown(params: {
  entity: "customer" | "product" | "salesperson" | "category";
  entityId: string;
  breakdownBy: "customer" | "product" | "salesperson" | "category" | "month";
  metric: "revenue" | "quantity" | "margin";
  dateFrom: string;
  dateTo: string;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ["drilldown", params],
    enabled: params.enabled !== false,
    queryFn: async () => {
      const r = await api.get<DrillRow[]>("/api/sales/drilldown", {
        params: {
          entity: params.entity,
          entity_id: params.entityId,
          breakdown_by: params.breakdownBy,
          metric: params.metric,
          date_from: params.dateFrom,
          date_to: params.dateTo,
          limit: 50,
        },
      });
      return r.data;
    },
  });
}

// ---------------------------------------------------------------------------
// Timeseries (MoM / YoY)
// ---------------------------------------------------------------------------
export type TimeseriesPoint = { period: string; value: number };
export type TimeseriesResponse = {
  current: TimeseriesPoint[];
  compare: TimeseriesPoint[] | null;
};

export function useTimeseries(
  metric: "revenue" | "quantity" | "margin" | "customers",
  granularity: "day" | "week" | "month",
  compare: "none" | "mom" | "yoy",
  filters: Filters,
) {
  return useQuery({
    queryKey: ["timeseries", metric, granularity, compare, filters],
    queryFn: async () => {
      const r = await api.get<TimeseriesResponse>("/api/sales/timeseries", {
        params: { metric, granularity, compare, ...filterParams(filters) },
      });
      return r.data;
    },
  });
}

// ---------------------------------------------------------------------------
// Insights
// ---------------------------------------------------------------------------
export type Insight = {
  id: string;
  insight_type: string;
  severity: "info" | "warning" | "critical";
  status: string;
  title: string;
  description: string;
  recommended_action: string | null;
  metric_value: number | null;
  metric_baseline: number | null;
  confidence_score: number | null;
  generated_at: string;
  customer_name: string | null;
  customer_id: string | null;
  product_name: string | null;
  product_id: string | null;
  salesperson_name: string | null;
};

export function useInsightsFeed(params?: {
  insightType?: string;
  severity?: "info" | "warning" | "critical" | "all";
  limit?: number;
}) {
  return useQuery({
    queryKey: ["insights-feed", params],
    queryFn: async () => {
      const r = await api.get<Insight[]>("/api/insights/feed", {
        params: {
          status: "new",
          insight_type: params?.insightType,
          severity: params?.severity || "all",
          limit: params?.limit || 20,
        },
      });
      return r.data;
    },
  });
}

export function useInsightCounters() {
  return useQuery({
    queryKey: ["insights-counters"],
    queryFn: async () => {
      const r = await api.get<Record<string, number>>("/api/insights/counters");
      return r.data;
    },
    refetchInterval: 60_000,  // refresh a cada minuto
  });
}
