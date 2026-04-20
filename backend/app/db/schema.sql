-- ============================================================================
-- VITA BI — SCHEMA DO BANCO DE DADOS
-- ----------------------------------------------------------------------------
-- Star schema otimizado para OLAP.
-- Dimensões mudam pouco. Fatos crescem rapidamente.
-- Índices agressivos em colunas de filtro (data, customer_id, product_id).
-- Materialized views pré-agregam KPIs caros.
-- ============================================================================

-- Extensões necessárias (instaladas como superuser antes de rodar este schema)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS "pg_trgm";
-- CREATE EXTENSION IF NOT EXISTS "btree_gin";
-- CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ============================================================================
-- DIMENSÕES
-- ============================================================================

-- ---------- dim_date -------------------------------------------------------
-- Gerada uma vez, usada em TODOS os JOINs de tempo. Evita extract() em queries.
CREATE TABLE dim_date (
    date_key        DATE PRIMARY KEY,
    year            SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    month_name      VARCHAR(20) NOT NULL,
    week            SMALLINT NOT NULL,
    day_of_month    SMALLINT NOT NULL,
    day_of_week     SMALLINT NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    is_holiday      BOOLEAN DEFAULT FALSE,
    fiscal_year     SMALLINT NOT NULL,
    fiscal_quarter  SMALLINT NOT NULL
);
CREATE INDEX idx_dim_date_year_month ON dim_date(year, month);

-- ---------- dim_customer ---------------------------------------------------
CREATE TABLE dim_customer (
    customer_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    qb_customer_id      VARCHAR(64) UNIQUE NOT NULL,          -- ID no QuickBooks
    name                VARCHAR(255) NOT NULL,
    display_name        VARCHAR(255),
    email               VARCHAR(255),
    phone               VARCHAR(50),
    billing_address     JSONB,                                 -- flexível
    shipping_address    JSONB,
    city                VARCHAR(100),
    state               VARCHAR(50),
    country             VARCHAR(50) DEFAULT 'BR',
    segment             VARCHAR(50),                           -- varejo, atacado, food-service
    tier                VARCHAR(20),                           -- A, B, C (ABC curve)
    first_purchase_date DATE,
    last_purchase_date  DATE,
    lifetime_value      NUMERIC(14,2) DEFAULT 0,
    avg_purchase_cycle_days  INTEGER,                          -- usado no churn
    is_active           BOOLEAN DEFAULT TRUE,
    qb_sync_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_customer_qb ON dim_customer(qb_customer_id);
CREATE INDEX idx_customer_tier ON dim_customer(tier) WHERE is_active;
CREATE INDEX idx_customer_name_trgm ON dim_customer USING gin(name gin_trgm_ops);

-- ---------- dim_product ----------------------------------------------------
CREATE TABLE dim_product (
    product_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    qb_item_id          VARCHAR(64) UNIQUE NOT NULL,
    qb_raw_name         VARCHAR(500) NOT NULL,                 -- nome "sujo" do QB
    clean_name          VARCHAR(500),                          -- vem do de-para
    category            VARCHAR(100),                          -- vem do de-para
    subcategory         VARCHAR(100),
    brand               VARCHAR(100),
    unit_of_measure     VARCHAR(20),                           -- kg, un, cx
    pack_size           NUMERIC(10,3),                         -- ex: 1.0, 0.25
    base_cost           NUMERIC(12,4),                         -- custo interno
    suggested_price     NUMERIC(12,4),                         -- preço alvo
    min_margin_pct      NUMERIC(5,2),                          -- margem mínima aceitável
    is_active           BOOLEAN DEFAULT TRUE,
    needs_cleanup       BOOLEAN DEFAULT TRUE,                  -- não está no de-para ainda
    qb_sync_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_product_qb ON dim_product(qb_item_id);
CREATE INDEX idx_product_category ON dim_product(category) WHERE is_active;
CREATE INDEX idx_product_clean_trgm ON dim_product USING gin(clean_name gin_trgm_ops);
CREATE INDEX idx_product_needs_cleanup ON dim_product(needs_cleanup) WHERE needs_cleanup;

-- ---------- dim_salesperson ------------------------------------------------
CREATE TABLE dim_salesperson (
    salesperson_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    qb_employee_id      VARCHAR(64) UNIQUE,
    name                VARCHAR(255) NOT NULL,
    email               VARCHAR(255),
    region              VARCHAR(100),
    commission_pct      NUMERIC(5,2),
    quota_monthly       NUMERIC(14,2),
    hired_at            DATE,
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_salesperson_active ON dim_salesperson(is_active) WHERE is_active;

-- ---------- dim_de_para ----------------------------------------------------
-- Tabela de limpeza ingerida via Excel. Regra: o QB tem itens sujos,
-- o humano mantém a planilha de-para, o ETL aplica nela todo batch.
CREATE TABLE dim_de_para (
    de_para_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    qb_raw_pattern      VARCHAR(500) NOT NULL,                 -- regex ou string exata do QB
    match_type          VARCHAR(20) NOT NULL DEFAULT 'exact',  -- 'exact', 'contains', 'regex'
    clean_name          VARCHAR(500) NOT NULL,
    category            VARCHAR(100) NOT NULL,
    subcategory         VARCHAR(100),
    brand               VARCHAR(100),
    unit_of_measure     VARCHAR(20),
    pack_size           NUMERIC(10,3),
    priority            INTEGER DEFAULT 100,                   -- menor = aplica primeiro
    active              BOOLEAN DEFAULT TRUE,
    source_file         VARCHAR(255),                          -- nome do Excel que gerou
    created_by          VARCHAR(100),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_de_para_pattern UNIQUE (qb_raw_pattern, match_type)
);
CREATE INDEX idx_de_para_pattern ON dim_de_para(qb_raw_pattern) WHERE active;
CREATE INDEX idx_de_para_priority ON dim_de_para(priority, active) WHERE active;

-- ============================================================================
-- FATOS
-- ============================================================================

-- ---------- fact_sales -----------------------------------------------------
-- Grão: uma linha por line-item de invoice do QB.
-- Particionado por mês para ganhar performance em queries de período.
CREATE TABLE fact_sales (
    sale_id             UUID DEFAULT uuid_generate_v4(),
    qb_invoice_id       VARCHAR(64) NOT NULL,
    qb_line_id          VARCHAR(64) NOT NULL,
    date_key            DATE NOT NULL,
    customer_id         UUID NOT NULL REFERENCES dim_customer(customer_id),
    product_id          UUID NOT NULL REFERENCES dim_product(product_id),
    salesperson_id      UUID REFERENCES dim_salesperson(salesperson_id),
    quantity            NUMERIC(12,3) NOT NULL,
    unit_price          NUMERIC(12,4) NOT NULL,
    discount_pct        NUMERIC(5,2) DEFAULT 0,
    discount_amount     NUMERIC(12,2) DEFAULT 0,
    revenue             NUMERIC(14,2) NOT NULL,                -- quantity * unit_price - discount
    cost                NUMERIC(14,2),                          -- quantity * product.base_cost (snapshot)
    margin              NUMERIC(14,2),                          -- revenue - cost
    margin_pct          NUMERIC(7,4),                           -- margin / revenue
    invoice_status      VARCHAR(20),                            -- paid, pending, overdue
    payment_date        DATE,
    raw_payload         JSONB,                                   -- guarda o JSON bruto do QB
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (date_key, sale_id)
) PARTITION BY RANGE (date_key);

-- Partições para 3 anos passados + 2 futuros (cria via pg_partman em produção)
CREATE TABLE fact_sales_2024 PARTITION OF fact_sales
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE fact_sales_2025 PARTITION OF fact_sales
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE fact_sales_2026 PARTITION OF fact_sales
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE fact_sales_2027 PARTITION OF fact_sales
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

-- Índices críticos em cada partição (se aplica via template)
CREATE INDEX idx_fact_sales_customer ON fact_sales(customer_id, date_key);
CREATE INDEX idx_fact_sales_product ON fact_sales(product_id, date_key);
CREATE INDEX idx_fact_sales_salesperson ON fact_sales(salesperson_id, date_key);
CREATE INDEX idx_fact_sales_invoice ON fact_sales(qb_invoice_id);
CREATE UNIQUE INDEX idx_fact_sales_unique_line ON fact_sales(qb_invoice_id, qb_line_id, date_key);

-- ---------- fact_inventory_snapshot ----------------------------------------
-- Grão: produto × dia. Snapshot diário do estoque para cruzar com vendas.
CREATE TABLE fact_inventory_snapshot (
    snapshot_date       DATE NOT NULL,
    product_id          UUID NOT NULL REFERENCES dim_product(product_id),
    qty_on_hand         NUMERIC(12,3) NOT NULL,
    qty_committed       NUMERIC(12,3) DEFAULT 0,
    qty_available       NUMERIC(12,3) GENERATED ALWAYS AS (qty_on_hand - qty_committed) STORED,
    days_of_cover       NUMERIC(8,2),                          -- qty_available / avg_daily_sales
    turnover_rate       NUMERIC(8,4),                          -- COGS / avg_inventory (rolling 90d)
    is_slow_mover       BOOLEAN DEFAULT FALSE,                  -- giro < threshold
    is_stockout_risk    BOOLEAN DEFAULT FALSE,                  -- days_of_cover < 7
    needs_desova        BOOLEAN DEFAULT FALSE,                  -- qty alto + giro baixo
    PRIMARY KEY (snapshot_date, product_id)
);
CREATE INDEX idx_inv_risk ON fact_inventory_snapshot(snapshot_date) 
    WHERE is_stockout_risk OR needs_desova;

-- ---------- fact_insights --------------------------------------------------
-- Grão: um insight gerado pelo motor em um determinado dia.
CREATE TABLE fact_insights (
    insight_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    generated_at        TIMESTAMPTZ DEFAULT NOW(),
    insight_type        VARCHAR(50) NOT NULL,  -- churn, anomaly, opportunity, pricing, inventory
    severity            VARCHAR(20) NOT NULL,  -- info, warning, critical
    customer_id         UUID REFERENCES dim_customer(customer_id),
    product_id          UUID REFERENCES dim_product(product_id),
    salesperson_id      UUID REFERENCES dim_salesperson(salesperson_id),
    title               VARCHAR(255) NOT NULL,
    description         TEXT,
    recommended_action  TEXT,
    metric_value        NUMERIC(14,4),          -- valor numérico principal do insight
    metric_baseline     NUMERIC(14,4),          -- baseline para comparação
    confidence_score    NUMERIC(5,4),           -- 0-1, quão confiável é
    status              VARCHAR(20) DEFAULT 'new',  -- new, acknowledged, resolved, dismissed
    resolved_at         TIMESTAMPTZ,
    resolved_by         VARCHAR(100),
    context             JSONB                   -- dados adicionais para o front renderizar
);
CREATE INDEX idx_insights_type ON fact_insights(insight_type, status);
CREATE INDEX idx_insights_customer ON fact_insights(customer_id) WHERE status = 'new';
CREATE INDEX idx_insights_severity ON fact_insights(severity, generated_at DESC);

-- ---------- fact_audit_log -------------------------------------------------
CREATE TABLE fact_audit_log (
    audit_id            BIGSERIAL PRIMARY KEY,
    user_email          VARCHAR(255) NOT NULL,
    action              VARCHAR(100) NOT NULL,
    endpoint            VARCHAR(500),
    query_params        JSONB,
    response_ms         INTEGER,
    ip_address          INET,
    user_agent          TEXT,
    at                  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_user_time ON fact_audit_log(user_email, at DESC);

-- ============================================================================
-- MATERIALIZED VIEWS — pré-agregação para dashboard rápido
-- ============================================================================

-- ---------- mv_customer_360 ------------------------------------------------
-- KPIs completos por cliente. Refresh a cada 15min.
CREATE MATERIALIZED VIEW mv_customer_360 AS
SELECT
    c.customer_id,
    c.name,
    c.segment,
    c.tier,
    COUNT(DISTINCT s.qb_invoice_id) AS total_orders,
    SUM(s.revenue) AS lifetime_revenue,
    SUM(s.margin) AS lifetime_margin,
    AVG(s.unit_price) AS avg_price_paid,
    MAX(s.date_key) AS last_purchase_date,
    MIN(s.date_key) AS first_purchase_date,
    -- métricas YTD
    SUM(s.revenue) FILTER (WHERE s.date_key >= date_trunc('year', CURRENT_DATE)) AS revenue_ytd,
    SUM(s.revenue) FILTER (
        WHERE s.date_key >= date_trunc('year', CURRENT_DATE - INTERVAL '1 year')
          AND s.date_key <  date_trunc('year', CURRENT_DATE)
    ) AS revenue_last_year,
    -- ciclo de recompra
    (MAX(s.date_key) - MIN(s.date_key))::NUMERIC
        / NULLIF(COUNT(DISTINCT s.qb_invoice_id) - 1, 0) AS avg_cycle_days,
    CURRENT_DATE - MAX(s.date_key) AS days_since_last_purchase
FROM dim_customer c
LEFT JOIN fact_sales s ON s.customer_id = c.customer_id
WHERE c.is_active
GROUP BY c.customer_id, c.name, c.segment, c.tier;

CREATE UNIQUE INDEX idx_mv_customer_360_pk ON mv_customer_360(customer_id);

-- ---------- mv_product_performance -----------------------------------------
CREATE MATERIALIZED VIEW mv_product_performance AS
SELECT
    p.product_id,
    p.clean_name,
    p.category,
    SUM(s.quantity) AS units_sold,
    SUM(s.revenue) AS total_revenue,
    SUM(s.margin) AS total_margin,
    AVG(s.unit_price) AS avg_price,
    STDDEV(s.unit_price) AS price_stddev,         -- usado na anomalia
    COUNT(DISTINCT s.customer_id) AS unique_customers,
    COUNT(DISTINCT s.qb_invoice_id) AS orders,
    -- tendência (últimos 30d vs 30d anteriores)
    SUM(s.revenue) FILTER (WHERE s.date_key >= CURRENT_DATE - INTERVAL '30 days') AS revenue_30d,
    SUM(s.revenue) FILTER (
        WHERE s.date_key >= CURRENT_DATE - INTERVAL '60 days'
          AND s.date_key <  CURRENT_DATE - INTERVAL '30 days'
    ) AS revenue_30d_prev
FROM dim_product p
LEFT JOIN fact_sales s ON s.product_id = p.product_id
WHERE p.is_active
GROUP BY p.product_id, p.clean_name, p.category;

CREATE UNIQUE INDEX idx_mv_product_perf_pk ON mv_product_performance(product_id);

-- ---------- mv_monthly_sales -----------------------------------------------
-- Para MoM e YoY. Grão: mês × customer × product × salesperson
CREATE MATERIALIZED VIEW mv_monthly_sales AS
SELECT
    date_trunc('month', s.date_key)::DATE AS month,
    s.customer_id,
    s.product_id,
    s.salesperson_id,
    SUM(s.quantity) AS qty,
    SUM(s.revenue) AS revenue,
    SUM(s.margin) AS margin,
    AVG(s.unit_price) AS avg_price,
    COUNT(DISTINCT s.qb_invoice_id) AS orders
FROM fact_sales s
GROUP BY 1, 2, 3, 4;

CREATE INDEX idx_mv_monthly_customer ON mv_monthly_sales(month, customer_id);
CREATE INDEX idx_mv_monthly_product ON mv_monthly_sales(month, product_id);
CREATE INDEX idx_mv_monthly_sp ON mv_monthly_sales(month, salesperson_id);

-- ============================================================================
-- VIEWS AUXILIARES (não materializadas, mas usadas muito)
-- ============================================================================

-- Representatividade: peso de cada produto no portfólio de cada cliente
CREATE VIEW v_product_share_per_customer AS
SELECT
    s.customer_id,
    s.product_id,
    SUM(s.revenue) AS revenue,
    SUM(s.revenue) / NULLIF(SUM(SUM(s.revenue)) OVER (PARTITION BY s.customer_id), 0) AS share_in_customer
FROM fact_sales s
WHERE s.date_key >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY s.customer_id, s.product_id;

-- Representatividade: peso de cada cliente na empresa toda
CREATE VIEW v_customer_share_of_company AS
SELECT
    s.customer_id,
    SUM(s.revenue) AS revenue,
    SUM(s.revenue) / NULLIF(SUM(SUM(s.revenue)) OVER (), 0) AS share_of_company
FROM fact_sales s
WHERE s.date_key >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY s.customer_id;

-- ============================================================================
-- FUNÇÕES UTILITÁRIAS
-- ============================================================================

-- Refresh de todas as MVs em ordem
CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_customer_360;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_product_performance;
    REFRESH MATERIALIZED VIEW mv_monthly_sales;  -- sem UNIQUE index, não pode CONCURRENTLY
END;
$$ LANGUAGE plpgsql;

-- Popula dim_date de 2020 a 2030
CREATE OR REPLACE FUNCTION populate_dim_date(start_date DATE, end_date DATE)
RETURNS void AS $$
BEGIN
    INSERT INTO dim_date (
        date_key, year, quarter, month, month_name, week,
        day_of_month, day_of_week, is_weekend,
        fiscal_year, fiscal_quarter
    )
    SELECT
        d::DATE,
        EXTRACT(YEAR FROM d)::SMALLINT,
        EXTRACT(QUARTER FROM d)::SMALLINT,
        EXTRACT(MONTH FROM d)::SMALLINT,
        TO_CHAR(d, 'Month'),
        EXTRACT(WEEK FROM d)::SMALLINT,
        EXTRACT(DAY FROM d)::SMALLINT,
        EXTRACT(DOW FROM d)::SMALLINT,
        EXTRACT(DOW FROM d) IN (0, 6),
        EXTRACT(YEAR FROM d)::SMALLINT,
        EXTRACT(QUARTER FROM d)::SMALLINT
    FROM generate_series(start_date, end_date, '1 day'::INTERVAL) d
    ON CONFLICT (date_key) DO NOTHING;
END;
$$ LANGUAGE plpgsql;

-- Popular dim_date inicial
SELECT populate_dim_date('2020-01-01'::DATE, '2030-12-31'::DATE);

-- ============================================================================
-- PERMISSÕES (exemplo para role de leitura do dashboard)
-- ============================================================================
-- CREATE ROLE vitabi_reader NOLOGIN;
-- GRANT USAGE ON SCHEMA public TO vitabi_reader;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO vitabi_reader;
-- GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO vitabi_reader;
