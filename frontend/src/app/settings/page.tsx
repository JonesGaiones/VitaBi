"use client";

import { useRef, useState } from "react";
import { Header } from "@/components/Header";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FileSpreadsheet, RefreshCw, Database, Clock, AlertCircle } from "lucide-react";
import { cn } from "@/lib/cn";
import { formatDistanceToNow, parseISO } from "date-fns";
import { ptBR } from "date-fns/locale";

type EtlStatus = {
  last_customer_sync: string | null;
  last_product_sync: string | null;
  last_sales_ingested: string | null;
  products_needing_cleanup: number;
  open_insights: number;
};

export default function SettingsPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const queryClient = useQueryClient();

  const { data: status, refetch } = useQuery({
    queryKey: ["etl-status"],
    queryFn: async () => {
      const r = await api.get<EtlStatus>("/api/etl/status");
      return r.data;
    },
    refetchInterval: 30_000,
  });

  const triggerFlow = useMutation({
    mutationFn: async (flow: string) => {
      await api.post(`/api/etl/trigger/${flow}`);
    },
    onSuccess: (_, flow) => {
      toast.success(`Flow '${flow}' enfileirado. Aguarde a próxima atualização.`);
    },
    onError: (e: any) => {
      toast.error(e.response?.data?.detail || "Erro ao disparar flow");
    },
  });

  const uploadDePara = async (file: File) => {
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const r = await api.post("/api/etl/de-para/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(
        `Planilha processada: ${r.data.inserted} novas regras, ${r.data.updated} atualizadas`,
      );
      queryClient.invalidateQueries({ queryKey: ["etl-status"] });
      queryClient.invalidateQueries({ queryKey: ["products-cleanup"] });
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao processar planilha");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const fmtTimestamp = (s: string | null) => {
    if (!s) return "nunca";
    try {
      return formatDistanceToNow(parseISO(s), { locale: ptBR, addSuffix: true });
    } catch { return s; }
  };

  return (
    <div className="min-h-screen">
      <Header />
      <main className="px-6 py-5 space-y-4 animate-fade-up max-w-5xl">
        <div>
          <h1 className="font-display text-3xl text-ink-50 tracking-tight leading-none">
            Configurações
          </h1>
          <p className="text-sm text-ink-400 mt-2">
            Upload de planilhas, status do ETL e triggers manuais
          </p>
        </div>

        {/* De-Para upload */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <h3 className="font-display text-lg text-ink-50 tracking-tight">
                Planilha De-Para
              </h3>
              <p className="text-xs text-ink-400 mt-1">
                Faça upload da planilha Excel para categorizar os produtos sujos do QuickBooks
              </p>
            </div>
          </div>
          <div className="panel-body">
            <label className={cn(
              "border-2 border-dashed border-ink-600/60 rounded-lg p-8 text-center cursor-pointer",
              "hover:border-pulse/50 hover:bg-pulse/5 transition-colors block",
              uploading && "opacity-50 pointer-events-none",
            )}>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadDePara(f);
                }}
              />
              <div className="flex flex-col items-center gap-2">
                {uploading ? (
                  <>
                    <RefreshCw className="text-pulse animate-spin" size={24} />
                    <div className="text-sm text-ink-200">Processando planilha…</div>
                  </>
                ) : (
                  <>
                    <Upload className="text-pulse" size={24} />
                    <div className="text-sm text-ink-200">
                      <span className="text-pulse font-medium">Clique para selecionar</span> uma planilha (.xlsx)
                    </div>
                    <div className="text-xs text-ink-500">
                      Colunas obrigatórias: qb_raw_pattern, match_type, clean_name, category
                    </div>
                  </>
                )}
              </div>
            </label>

            <div className="mt-4 flex items-start gap-2 text-xs text-ink-400">
              <FileSpreadsheet size={14} className="text-pulse shrink-0 mt-0.5" />
              <div>
                Após o upload, o sistema marca todos os produtos para re-processamento
                e roda o transform_flow automaticamente. Você vai ver o resultado na
                aba <span className="text-pulse">Produtos → Precisam limpeza</span> em poucos segundos.
              </div>
            </div>
          </div>
        </div>

        {/* ETL status */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <h3 className="font-display text-lg text-ink-50 tracking-tight">
                Status do ETL
              </h3>
              <p className="text-xs text-ink-400 mt-1">
                Última sincronização de cada entidade do QuickBooks
              </p>
            </div>
            <button
              onClick={() => refetch()}
              className="text-xs text-ink-300 hover:text-pulse flex items-center gap-1"
            >
              <RefreshCw size={12} /> atualizar
            </button>
          </div>
          <div className="panel-body grid grid-cols-1 md:grid-cols-3 gap-4">
            <StatusItem
              icon={Database} label="Clientes" timestamp={status?.last_customer_sync}
              fmt={fmtTimestamp}
            />
            <StatusItem
              icon={Database} label="Produtos" timestamp={status?.last_product_sync}
              fmt={fmtTimestamp}
            />
            <StatusItem
              icon={Database} label="Vendas"   timestamp={status?.last_sales_ingested}
              fmt={fmtTimestamp}
            />
          </div>

          {(status?.products_needing_cleanup || 0) > 0 && (
            <div className="px-5 pb-4">
              <div className="flex items-center gap-2 text-xs">
                <AlertCircle size={12} className="text-amber-500" />
                <span className="text-ink-300">
                  <span className="text-amber-500 font-medium">{status?.products_needing_cleanup}</span>{" "}
                  produtos aguardando categorização no de-para
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Manual triggers */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <h3 className="font-display text-lg text-ink-50 tracking-tight">
                Triggers manuais
              </h3>
              <p className="text-xs text-ink-400 mt-1">
                Dispare flows do Prefect fora do cron agendado
              </p>
            </div>
          </div>
          <div className="panel-body grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { id: "qb_extract",  label: "Extrair do QuickBooks",
                desc: "Puxa incremental dos últimos dados" },
              { id: "transform",   label: "Transformar e recarregar",
                desc: "Reaplica de-para e refresh das MVs" },
              { id: "insights",    label: "Rodar motor de insights",
                desc: "Churn + anomalias + recomendações" },
              { id: "full",        label: "Pipeline completo",
                desc: "Extract + transform + insights em sequência" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => triggerFlow.mutate(f.id)}
                disabled={triggerFlow.isPending}
                className="border border-ink-600/50 rounded-lg p-4 text-left
                           hover:border-pulse/40 hover:bg-pulse/5 transition-colors
                           disabled:opacity-50 disabled:pointer-events-none"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Clock size={12} className="text-pulse" />
                  <span className="text-sm text-ink-100 font-medium">{f.label}</span>
                </div>
                <div className="text-xs text-ink-400">{f.desc}</div>
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

function StatusItem({ icon: Icon, label, timestamp, fmt }: {
  icon: any; label: string; timestamp: string | null | undefined; fmt: (s: string | null) => string;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-8 h-8 rounded-lg bg-ink-700/60 border border-ink-600/50 flex items-center justify-center shrink-0">
        <Icon size={14} className="text-ink-300" />
      </div>
      <div className="min-w-0">
        <div className="metric-label">{label}</div>
        <div className="font-mono text-sm text-ink-100 mt-0.5">
          {fmt(timestamp || null)}
        </div>
      </div>
    </div>
  );
}
