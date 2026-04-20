import { create } from "zustand";
import { subDays, format } from "date-fns";

export type DrillLevel = {
  entity: "customer" | "product" | "salesperson" | "category";
  id: string;
  label: string;
};

export type Filters = {
  dateFrom: string;
  dateTo: string;
  customerId: string | null;
  productId: string | null;
  salespersonId: string | null;
};

type Store = {
  // filtros globais
  filters: Filters;
  setFilter: <K extends keyof Filters>(key: K, value: Filters[K]) => void;
  resetFilters: () => void;

  // pilha de drill-down (breadcrumbs)
  drillStack: DrillLevel[];
  pushDrill: (level: DrillLevel) => void;
  popDrill: () => void;
  goToDrill: (index: number) => void;
  clearDrill: () => void;

  // métricas selecionadas
  metric: "revenue" | "quantity" | "margin";
  setMetric: (m: "revenue" | "quantity" | "margin") => void;

  // comparativo
  compare: "none" | "mom" | "yoy";
  setCompare: (c: "none" | "mom" | "yoy") => void;
};

const defaultFilters: Filters = {
  dateFrom: format(subDays(new Date(), 90), "yyyy-MM-dd"),
  dateTo: format(new Date(), "yyyy-MM-dd"),
  customerId: null,
  productId: null,
  salespersonId: null,
};

export const useStore = create<Store>((set) => ({
  filters: defaultFilters,
  setFilter: (key, value) =>
    set((s) => ({ filters: { ...s.filters, [key]: value } })),
  resetFilters: () => set({ filters: defaultFilters, drillStack: [] }),

  drillStack: [],
  pushDrill: (level) => set((s) => ({ drillStack: [...s.drillStack, level] })),
  popDrill: () => set((s) => ({ drillStack: s.drillStack.slice(0, -1) })),
  goToDrill: (index) => set((s) => ({ drillStack: s.drillStack.slice(0, index + 1) })),
  clearDrill: () => set({ drillStack: [] }),

  metric: "revenue",
  setMetric: (metric) => set({ metric }),

  compare: "yoy",
  setCompare: (compare) => set({ compare }),
}));
