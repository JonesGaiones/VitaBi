# Vita BI — Sistema de Inteligência de Vendas

Dashboard BI para **Vita Forte Inc.**, projetado para rodar no framework **Antigravity**.

Pipeline completo: **QuickBooks → ETL → Postgres → API → Dashboard** com motor de insights.

---

## ⚡ Quickstart (3 comandos)

```bash
cd vita_bi
cp .env.example .env                 # (opcional) configure QB_* no arquivo
docker compose up --build
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs

**Login de teste:** `joao@vitaforte.com` / `changeme`

---

## Páginas do dashboard

| Rota | O que faz |
|---|---|
| `/` | Dashboard principal: KPIs + drill-down interativo (chart ↔ grid sincronizados) + feed de insights |
| `/customers` | Lista com busca e filtro por tier |
| `/customers/[id]` | **Customer Genome** — sazonalidade radial, elasticidade, NPS implícito, produtos âncora |
| `/products` | Três tabs: Performance • Precisam Limpeza • Alertas de estoque |
| `/insights` | Centro de comando — resolver/descartar insights com um clique |
| `/settings` | Upload da planilha de-para, status do ETL, triggers manuais |

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js 14 App Router • ECharts 5 • AG-Grid Enterprise • TanStack Query • Zustand • Tailwind • Fraunces + JetBrains Mono |
| Backend | FastAPI • SQLAlchemy 2 async • Pydantic v2 |
| Banco | PostgreSQL 16 (star schema + particionamento + materialized views) |
| Cache | Redis 7 |
| ETL | Prefect 2 • pandas • openpyxl |
| Insights | Postgres analytical SQL • scikit-learn • statsmodels |
| Runtime | **Antigravity** (via `antigravity.yaml`) ou **Docker Compose** |

---

## Fluxo de dados

```
QuickBooks API
    ↓ OAuth2 + retry + paginação
qb_extract_flow (cron 2h)
    ↓ data/raw/*.jsonl
transform_flow
    ↓ aplica de_para (exact → contains → regex)
Postgres (fact_sales, dim_*)
    ↓ refresh materialized views (a cada 15min)
mv_customer_360, mv_product_performance, mv_monthly_sales
    ↓
insights_flow (cron 05:00)
    ↓ churn, anomalias, cross-sell, replenishment
fact_insights
    ↓
API REST (cache Redis 15min por query)
    ↓
Dashboard Next.js
```

---

## Endpoints principais

| Endpoint | Retorna |
|---|---|
| `GET /api/sales/kpis` | Receita, margem, pedidos, clientes + variação |
| `GET /api/sales/ranking?dimension=customer` | Top N ordenado DESC |
| `GET /api/sales/drilldown?entity=X&entity_id=Y&breakdown_by=Z` | **Coração do drill-down** |
| `GET /api/sales/timeseries?compare=yoy` | Série temporal com MoM/YoY |
| `GET /api/customers/{id}/genome` | **Customer Genome** |
| `GET /api/products/needs-cleanup` | Produtos sem match no de-para |
| `GET /api/products/inventory-alerts` | Stockout + desova |
| `GET /api/insights/feed` | Feed ordenado por severidade × confiança |
| `PATCH /api/insights/{id}/status` | Resolver/descartar |
| `POST /api/etl/de-para/upload` | Upload Excel |
| `POST /api/etl/trigger/{flow}` | Trigger manual |

---

## Primeira carga

```bash
# Gerar template Excel
docker compose exec worker python -m scripts.generate_de_para_template

# Editar data/de_para/TEMPLATE_de_para.xlsx com produtos reais

# Disparar pipeline
docker compose exec worker python -m app.etl.run_flow full_pipeline
```

Ou use a UI: **Settings → Triggers manuais** e **Settings → Upload de-para**.

---

## Funcionalidades "fora da curva"

### 1. Customer Genome ✅ implementado
Visualização radial do DNA de compra de cada cliente. Sazonalidade em 360°, elasticidade a desconto (correlação real com volume), volatilidade de preço (stddev normalizado), NPS implícito (frequência × atraso), produtos âncora.

### 2. Pipeline de Oportunidade com boost de estoque ✅ lógica pronta
Insights de replenishment ganham severity `critical` automática quando o produto sugerido tem `needs_desova = TRUE`. Cross-sell calcula ticket estimado por segmento. Churn ranqueia por LTV. Tudo na `/insights`. Falta só webhook Slack (1h de trabalho).

### 3. What-If Simulator em WASM — próximo sprint
Sliders de preço/desconto/churn que recalculam projeção de 90 dias em memória usando ciclos históricos reais de cada cliente.

### Bônus que apareceram naturalmente
- Alertas automáticos de margem abaixo do mínimo por produto
- Auto-archival de insights que o cliente resolveu sozinho (ex: comprou de novo)
- Representatividade dupla (produto-no-cliente, cliente-na-empresa)
- Trilha navegável de breadcrumbs no drill-down — volta pra qualquer nível com um clique

---

## Decisões técnicas

**Star schema particionado** — Postgres com partições por ano, BRIN em `date_key`, materialized views pré-agregadas. Performance de DW sem custo de Snowflake.

**Drill-down server-side** — API devolve agregados já ordenados DESC. Browser só renderiza.

**Zustand > Redux** — 80 linhas resolvem filtros + pilha de drill. Redux seriam 400.

**ECharts + AG-Grid sincronizados** — Emoção (gradientes, animação) + precisão (sort, filter, pivot). Ambos ouvem o mesmo Zustand store.

**Fraunces + JetBrains Mono** — Foge da estética SaaS genérica com Inter. Números em tabular-nums.

**Cache Redis com chave determinística** — MD5 de `(endpoint, params)`. Invalidação seletiva ao fim de cada transform_flow. P95 de drill-down < 200ms.

---

## Estrutura

```
vita_bi/
├── antigravity.yaml
├── docker-compose.yml
├── .env.example
├── docs/ARCHITECTURE.md
├── backend/
│   ├── Dockerfile, requirements.txt
│   ├── scripts/generate_de_para_template.py
│   └── app/
│       ├── main.py, core/, db/schema.sql
│       ├── services/quickbooks_client.py
│       ├── etl/ (de_para_loader, transformer, flows, run_flow)
│       ├── insights/ (churn, anomaly, recommender, engine)
│       └── api/ (sales, customers, products, insights, etl, auth)
├── frontend/
│   ├── Dockerfile, package.json, tailwind.config.js
│   └── src/
│       ├── app/ (layout, page, customers, products, insights, settings)
│       ├── components/ (Header, FilterBar, KpiCards, DrillBreadcrumb,
│       │                DrillDownChart, RankingGrid, TimeseriesChart,
│       │                InsightsFeed, CustomerGenome, providers)
│       ├── lib/ (api, queries, store, format, cn)
│       └── styles/globals.css
└── data/ (raw, de_para, processed)
```

---

## Deploy no Antigravity

```bash
antigravity deploy       # lê antigravity.yaml, sobe todos os services
```

O manifesto declara:
- 5 services (backend×2, worker, db, redis, frontend)
- 4 cron jobs (qb_extract 2h, insights 05:00, mv_refresh 15min, churn 07:00)
- 2 rotas TLS-automatic (dashboard + api)
- 3 volumes persistentes (pgdata, redisdata, rawdata)
- Observabilidade: Prometheus metrics + tracing

---

## Roadmap

| Sprint | Entrega |
|---|---|
| 1 | What-If Simulator em WASM |
| 2 | Webhook Slack para alertas críticos |
| 3 | Row-Level Security (gestor vê só carteira) |
| 4 | Mobile + PWA |
| 5 | Exportação PDF server-side |
| 6 | WhatsApp Business para churn |
