# Vita BI — Arquitetura Completa

Sistema de Inteligência de Vendas para Vita Forte Inc. desenhado para rodar no framework **Antigravity** como plataforma de execução e build.

---

## 1. Visão Arquitetural (High-Level)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         CAMADA DE APRESENTAÇÃO                            │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │  Next.js 14 (App Router) + React Server Components                 │   │
│  │  • ECharts 5 (gráficos ricos com drill-down nativo)                │   │
│  │  • AG-Grid Enterprise (tabelas pivot + aggregation server-side)    │   │
│  │  • TanStack Query (cache client-side + invalidação inteligente)    │   │
│  │  • Zustand (estado global de filtros)                              │   │
│  │  • Tailwind + shadcn/ui (design system)                            │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬───────────────────────────────────┘
                                       │ HTTPS + JWT
┌──────────────────────────────────────▼───────────────────────────────────┐
│                           CAMADA DE API                                   │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │  FastAPI (Python 3.12) + Pydantic v2                               │   │
│  │  • /api/sales          → métricas core + drill-down                │   │
│  │  • /api/customers      → 360° do cliente + churn                   │   │
│  │  • /api/products       → performance + giro                        │   │
│  │  • /api/insights       → motor de recomendações                    │   │
│  │  • /api/etl            → triggers manuais de ingestão              │   │
│  │  • /api/auth           → login SSO/JWT                             │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬───────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
┌──────────────────┐         ┌──────────────────┐         ┌──────────────────┐
│ PostgreSQL 16    │         │ Redis 7          │         │ Motor de         │
│ (OLAP otimizado) │         │ (cache + queue)  │         │ Insights         │
│ • Columnar idx   │         │ • Sessions       │         │ (Python workers) │
│ • Materialized   │         │ • RQ/Celery      │         │ • scikit-learn   │
│   views          │         │ • Rate limiting  │         │ • statsmodels    │
│ • pg_partman     │         │                  │         │                  │
└──────────────────┘         └──────────────────┘         └──────────────────┘
        ▲
        │
┌───────┴──────────────────────────────────────────────────────────────────┐
│                           CAMADA DE ETL                                   │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │  Prefect 2 (orquestração) — roda em workers Antigravity            │   │
│  │                                                                     │   │
│  │  Flow 1: qb_extract_flow (cron: a cada 2h)                         │   │
│  │    → puxa deltas do QuickBooks API (OAuth2)                        │   │
│  │    → grava raw em data/raw/qb_YYYYMMDD_HHMM.jsonl                  │   │
│  │                                                                     │   │
│  │  Flow 2: de_para_apply_flow (trigger: upload de Excel)             │   │
│  │    → lê planilha em data/de_para/                                   │   │
│  │    → valida com Great Expectations                                  │   │
│  │    → faz UPSERT em dim_de_para                                     │   │
│  │                                                                     │   │
│  │  Flow 3: transform_flow (dependency: flow 1 ou 2)                  │   │
│  │    → aplica limpeza + categorização                                 │   │
│  │    → refresh materialized views                                     │   │
│  │    → invalida cache Redis                                           │   │
│  │    → dispara notificação WebSocket para clientes                   │   │
│  │                                                                     │   │
│  │  Flow 4: insights_flow (cron: diário 05:00)                        │   │
│  │    → roda algoritmos de churn, anomalias, sugestões                │   │
│  │    → popula tabela fact_insights                                   │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Por que essas escolhas

| Decisão | Razão |
|---|---|
| **FastAPI** em vez de Node | Python tem o ecossistema científico (pandas, scikit-learn, statsmodels) que o motor de insights precisa. FastAPI é comparable em performance a Node graças ao Starlette/uvloop. |
| **PostgreSQL** em vez de MongoDB | Vendas são dados relacionais e transacionais por natureza. Queries de BI precisam de JOINs agressivos e agregações — Postgres com índices columnar (via `cstore_fdw` ou partitioned BRIN) é ideal. |
| **Prefect** em vez de Airflow | Mais leve, Python-native, melhor DX. Roda bem em containers Antigravity sem o overhead do Airflow. |
| **Next.js 14** | Server Components permitem pré-renderizar dashboards pesados no servidor → time-to-interactive baixo. Streaming SSR para drill-downs instantâneos. |
| **ECharts** | Mais poderoso que Chart.js, mais leve que D3 puro, com drill-down nativo via `dataZoom` e `dispatchAction`. |
| **AG-Grid Enterprise** | Server-side row model lida com milhões de linhas sem travar o browser. Pivot mode nativo. |
| **Redis** | Cache de queries agregadas (que são caras no Postgres) + broker do Prefect + rate limiting. |

---

## 3. Como o Antigravity executa

O Antigravity é o orquestrador de execução. O projeto expõe um manifesto declarativo (`antigravity.yaml` na raiz) que descreve:

- **Services** (backend, frontend, worker, db, redis) → cada um vira um container isolado
- **Routes** → mapeamento de URLs públicas para services internos
- **Secrets** → credenciais do QB, JWT, DB são injetadas via vault
- **Cron jobs** → flows do Prefect agendados nativamente
- **Volumes** → persistência de `data/` e do Postgres

Detalhes no arquivo `antigravity.yaml`.

---

## 4. Modelo de Dados (resumo)

Schema em estrela otimizado para BI:

**Dimensões** (mudam pouco): `dim_customer`, `dim_product`, `dim_salesperson`, `dim_date`, `dim_de_para`

**Fatos** (crescem sempre): `fact_sales` (grão = linha de invoice), `fact_inventory_snapshot` (grão = produto × dia), `fact_insights` (grão = insight × dia)

**Views materializadas** para acelerar o dashboard:
- `mv_customer_360` → KPIs por cliente (refresh a cada 15min)
- `mv_product_performance` → performance por produto (refresh a cada 15min)
- `mv_churn_signals` → sinais de churn (refresh diário)

Schema completo em `backend/app/db/schema.sql`.

---

## 5. Fluxo de uma Requisição (exemplo: drill-down)

1. Gestor clica em barra "Cliente ABC" no gráfico de faturamento
2. Frontend dispara `GET /api/sales/drilldown?entity=customer&id=123&period=2026-01`
3. FastAPI checa Redis (chave: `drilldown:customer:123:2026-01`)
   - **HIT** → retorna JSON em ~15ms
   - **MISS** → query em `mv_customer_360` + `fact_sales`, ordenada por faturamento DESC, grava no Redis com TTL 15min
4. Frontend recebe, ECharts anima a transição (morph de barras)
5. AG-Grid ao lado atualiza com linhas detalhadas

Target de latência: **p95 < 200ms** no drill-down.

---

## 6. Segurança

- JWT com refresh tokens em cookie httpOnly
- Row-Level Security no Postgres: gestor vê só a carteira dele (se configurado)
- Audit log de toda query em `fact_audit_log`
- Secrets via vault (nunca em código)
- CORS restrito ao domínio do dashboard
- Rate limit: 100 req/min por usuário

---

## 7. Roadmap de Build

**Fase 1 (semanas 1-2):** Schema + ETL do QB + endpoints básicos
**Fase 2 (semanas 3-4):** Frontend com métricas core + drill-down
**Fase 3 (semanas 5-6):** Motor de insights + alertas
**Fase 4 (semana 7):** Features "fora da curva" (ver seção 10 do README)
**Fase 5 (semana 8):** Hardening, load test, deploy em produção
