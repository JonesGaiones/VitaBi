"use client";

import { use } from "react";
import Link from "next/link";
import { Header } from "@/components/Header";
import { CustomerGenome } from "@/components/CustomerGenome";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtCurrency, fmtNumber } from "@/lib/format";
import { ArrowLeft, Mail, Phone, MapPin, Calendar } from "lucide-react";
import { format, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";

type CustomerDetail = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  tier: string | null;
  segment: string | null;
  city: string | null;
  state: string | null;
  first_purchase_date: string | null;
  last_purchase_date: string | null;
  lifetime_revenue: number | null;
  lifetime_margin: number | null;
  revenue_ytd: number | null;
  revenue_last_year: number | null;
  avg_cycle_days: number | null;
  days_since_last_purchase: number | null;
  total_orders: number | null;
  avg_price_paid: number | null;
};

export default function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const { data, isLoading } = useQuery({
    queryKey: ["customer", id],
    queryFn: async () => {
      const r = await api.get<CustomerDetail>(`/api/customers/${id}`);
      return r.data;
    },
  });

  return (
    <div className="min-h-screen">
      <Header />

      <main className="px-6 py-5 space-y-4 animate-fade-up">
        {/* Back link */}
        <Link
          href="/customers"
          className="inline-flex items-center gap-1.5 text-sm text-ink-300 hover:text-pulse transition-colors"
        >
          <ArrowLeft size={14} /> Voltar para clientes
        </Link>

        {/* Header card */}
        {isLoading ? (
          <div className="panel h-32 shimmer-bg rounded-xl" />
        ) : data ? (
          <div className="panel panel-body">
            <div className="flex items-start justify-between flex-wrap gap-4">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h1 className="font-display text-3xl text-ink-50 tracking-tight">
                    {data.name}
                  </h1>
                  {data.tier && (
                    <span className="pill pill-info font-mono">Tier {data.tier}</span>
                  )}
                  {data.segment && (
                    <span className="pill pill-info">{data.segment}</span>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-4 mt-3 text-sm text-ink-300">
                  {data.email && (
                    <span className="flex items-center gap-1.5">
                      <Mail size={12} /> {data.email}
                    </span>
                  )}
                  {data.phone && (
                    <span className="flex items-center gap-1.5">
                      <Phone size={12} /> {data.phone}
                    </span>
                  )}
                  {(data.city || data.state) && (
                    <span className="flex items-center gap-1.5">
                      <MapPin size={12} /> {[data.city, data.state].filter(Boolean).join(", ")}
                    </span>
                  )}
                  {data.first_purchase_date && (
                    <span className="flex items-center gap-1.5">
                      <Calendar size={12} />
                      Cliente desde {format(parseISO(data.first_purchase_date), "MMM yyyy", { locale: ptBR })}
                    </span>
                  )}
                </div>
              </div>

              {/* Right-side metrics */}
              <div className="grid grid-cols-3 gap-6 text-right">
                <div>
                  <div className="metric-label">LTV</div>
                  <div className="metric-value text-xl text-pulse mt-0.5">
                    {fmtCurrency(data.lifetime_revenue, true)}
                  </div>
                </div>
                <div>
                  <div className="metric-label">YTD</div>
                  <div className="metric-value text-xl text-ink-50 mt-0.5">
                    {fmtCurrency(data.revenue_ytd, true)}
                  </div>
                </div>
                <div>
                  <div className="metric-label">Ciclo médio</div>
                  <div className="metric-value text-xl text-ink-50 mt-0.5">
                    {data.avg_cycle_days ? `${Math.round(data.avg_cycle_days)}d` : "—"}
                  </div>
                </div>
              </div>
            </div>

            {/* Alert bar for churn risk */}
            {data.avg_cycle_days && data.days_since_last_purchase &&
             data.days_since_last_purchase > data.avg_cycle_days * 1.3 && (
              <div className="mt-4 pt-4 border-t border-ink-600/40">
                <div className="pill pill-warning">
                  ⚠ {data.days_since_last_purchase} dias sem comprar (ciclo: {Math.round(data.avg_cycle_days)}d)
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="panel panel-body text-center text-ink-400">
            Cliente não encontrado.
          </div>
        )}

        {/* Customer Genome */}
        <CustomerGenome customerId={id} />
      </main>
    </div>
  );
}
