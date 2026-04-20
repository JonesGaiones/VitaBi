"""
Detector de anomalias de preço e margem.

Duas lógicas principais:

1. Preço fora do padrão:
   Para cada produto, calcula preço médio + stddev nos últimos 90 dias.
   Se uma venda sai por preço > 2σ abaixo do normal → alerta.
   Evita vendedor estar queimando preço.

2. Margem abaixo do mínimo:
   Compara margem realizada vs dim_product.min_margin_pct.
   Se margem_realizada < min_margin_pct → alerta crítico.
"""
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

log = structlog.get_logger()


PRICE_ANOMALY_QUERY = """
WITH product_stats AS (
    SELECT
        product_id,
        AVG(unit_price) AS avg_price,
        STDDEV(unit_price) AS std_price
    FROM fact_sales
    WHERE date_key >= CURRENT_DATE - INTERVAL '90 days'
    GROUP BY product_id
    HAVING COUNT(*) >= 10  -- precisa de massa crítica
),
anomalies AS (
    SELECT
        s.sale_id,
        s.date_key,
        s.customer_id,
        s.product_id,
        s.salesperson_id,
        s.unit_price,
        s.quantity,
        s.revenue,
        ps.avg_price,
        ps.std_price,
        (ps.avg_price - s.unit_price) / NULLIF(ps.std_price, 0) AS z_score_down
    FROM fact_sales s
    JOIN product_stats ps USING (product_id)
    WHERE s.date_key >= CURRENT_DATE - INTERVAL '7 days'
      AND s.unit_price < ps.avg_price - :k_sigma * ps.std_price
)
SELECT
    a.*,
    c.name AS customer_name,
    p.clean_name AS product_name,
    sp.name AS salesperson_name
FROM anomalies a
JOIN dim_customer c ON c.customer_id = a.customer_id
JOIN dim_product p ON p.product_id = a.product_id
LEFT JOIN dim_salesperson sp ON sp.salesperson_id = a.salesperson_id
ORDER BY a.z_score_down DESC;
"""


MARGIN_VIOLATION_QUERY = """
SELECT
    s.sale_id,
    s.date_key,
    s.customer_id,
    s.product_id,
    s.salesperson_id,
    s.unit_price,
    s.revenue,
    s.margin,
    s.margin_pct,
    p.min_margin_pct,
    p.clean_name AS product_name,
    c.name AS customer_name,
    sp.name AS salesperson_name
FROM fact_sales s
JOIN dim_product p ON p.product_id = s.product_id
JOIN dim_customer c ON c.customer_id = s.customer_id
LEFT JOIN dim_salesperson sp ON sp.salesperson_id = s.salesperson_id
WHERE s.date_key >= CURRENT_DATE - INTERVAL '7 days'
  AND p.min_margin_pct IS NOT NULL
  AND s.margin_pct < p.min_margin_pct / 100.0
ORDER BY (p.min_margin_pct / 100.0 - s.margin_pct) DESC;
"""


async def detect_price_anomalies(session: AsyncSession) -> int:
    result = await session.execute(
        text(PRICE_ANOMALY_QUERY),
        {"k_sigma": settings.PRICE_ANOMALY_SIGMA},
    )
    rows = result.mappings().all()

    for row in rows:
        discount = float(row["avg_price"]) - float(row["unit_price"])
        discount_pct = discount / float(row["avg_price"]) * 100
        title = f"Preço baixo: {row['product_name']} para {row['customer_name']}"
        description = (
            f"Venda de {row['quantity']}x a R$ {float(row['unit_price']):.2f}/un, "
            f"mas a média dos últimos 90 dias foi R$ {float(row['avg_price']):.2f} "
            f"(±R$ {float(row['std_price']):.2f}). Desconto implícito de {discount_pct:.1f}%."
        )
        action = (
            f"Investigar razão do desconto. Se for sistemático, "
            f"revisar tabela de preços com {row['salesperson_name'] or 'vendedor'}."
        )
        await session.execute(text("""
            INSERT INTO fact_insights (
                insight_type, severity,
                customer_id, product_id, salesperson_id,
                title, description, recommended_action,
                metric_value, metric_baseline, confidence_score, context
            ) VALUES (
                'pricing', 'warning',
                :customer_id, :product_id, :salesperson_id,
                :title, :description, :action,
                :metric_value, :baseline, :confidence, :context
            )
        """), {
            "customer_id": row["customer_id"],
            "product_id": row["product_id"],
            "salesperson_id": row["salesperson_id"],
            "title": title,
            "description": description,
            "action": action,
            "metric_value": float(row["unit_price"]),
            "baseline": float(row["avg_price"]),
            "confidence": min(0.99, 0.6 + 0.05 * float(row["z_score_down"])),
            "context": f'{{"z_score": {float(row["z_score_down"]):.3f}, "discount_pct": {discount_pct:.2f}}}',
        })

    await session.commit()
    log.info("price_anomalies_done", found=len(rows))
    return len(rows)


async def detect_margin_violations(session: AsyncSession) -> int:
    result = await session.execute(text(MARGIN_VIOLATION_QUERY))
    rows = result.mappings().all()

    for row in rows:
        realized = float(row["margin_pct"] or 0) * 100
        required = float(row["min_margin_pct"])
        gap = required - realized
        title = f"Margem abaixo do mínimo: {row['product_name']}"
        description = (
            f"Margem realizada {realized:.1f}% < mínima {required:.1f}% "
            f"(gap: {gap:.1f} p.p.). Cliente: {row['customer_name']}."
        )
        action = (
            f"Revisar pricing com {row['salesperson_name'] or 'vendedor'} "
            f"ou ajustar min_margin_pct do produto se o mercado mudou."
        )
        await session.execute(text("""
            INSERT INTO fact_insights (
                insight_type, severity,
                customer_id, product_id, salesperson_id,
                title, description, recommended_action,
                metric_value, metric_baseline, confidence_score
            ) VALUES (
                'margin', 'critical',
                :customer_id, :product_id, :salesperson_id,
                :title, :description, :action,
                :metric_value, :baseline, 0.95
            )
        """), {
            "customer_id": row["customer_id"],
            "product_id": row["product_id"],
            "salesperson_id": row["salesperson_id"],
            "title": title,
            "description": description,
            "action": action,
            "metric_value": realized,
            "baseline": required,
        })

    await session.commit()
    log.info("margin_violations_done", found=len(rows))
    return len(rows)
