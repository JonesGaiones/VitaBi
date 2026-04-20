"""
Motor de Recomendação: "O que vender e para quem".

Duas heurísticas combinadas:

1. CROSS-SELL baseado em afinidade:
   "Clientes do segmento X que compram produto A, costumam também comprar B.
    Este cliente Y compra A mas não B → oportunidade."
   Similar a market basket analysis, mas agrupado por segmento.

2. REPLENISHMENT baseado em ciclo:
   "Cliente Z tem ciclo médio de 30 dias para produto A. Já faz 25 dias →
    abordar agora para não perder a janela."

3. INVENTORY PUSH:
   Cruza com fact_inventory_snapshot. Produtos com needs_desova = TRUE
   ganham boost no score de sugestão.
"""
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# 1) CROSS-SELL por afinidade de segmento
# ---------------------------------------------------------------------------
CROSS_SELL_QUERY = """
WITH segment_baskets AS (
    -- para cada segmento, calcula frequência de cada produto
    SELECT
        c.segment,
        s.product_id,
        COUNT(DISTINCT s.customer_id) AS customers_buying,
        COUNT(DISTINCT c.customer_id) FILTER (WHERE TRUE) 
            OVER (PARTITION BY c.segment) AS total_customers_in_segment
    FROM fact_sales s
    JOIN dim_customer c USING (customer_id)
    WHERE s.date_key >= CURRENT_DATE - INTERVAL '12 months'
      AND c.segment IS NOT NULL
    GROUP BY c.segment, s.product_id, c.customer_id
),
segment_penetration AS (
    SELECT
        segment,
        product_id,
        MAX(customers_buying) AS customers_buying,
        MAX(total_customers_in_segment) AS total_customers_in_segment,
        MAX(customers_buying)::NUMERIC / NULLIF(MAX(total_customers_in_segment), 0) AS penetration
    FROM segment_baskets
    GROUP BY segment, product_id
    HAVING MAX(customers_buying) >= 3
       AND MAX(customers_buying)::NUMERIC / NULLIF(MAX(total_customers_in_segment), 0) > 0.3
),
customer_gaps AS (
    -- para cada cliente, lista produtos que o segmento compra mas ele não
    SELECT
        c.customer_id,
        c.name AS customer_name,
        c.segment,
        sp.product_id,
        p.clean_name AS product_name,
        sp.penetration,
        -- estima tamanho da oportunidade: ticket médio daquele produto no segmento
        (SELECT AVG(revenue) FROM fact_sales fs 
         JOIN dim_customer dc USING (customer_id)
         WHERE fs.product_id = sp.product_id AND dc.segment = c.segment
           AND fs.date_key >= CURRENT_DATE - INTERVAL '6 months'
        ) AS estimated_ticket
    FROM dim_customer c
    JOIN segment_penetration sp ON sp.segment = c.segment
    JOIN dim_product p ON p.product_id = sp.product_id
    WHERE c.is_active
      AND NOT EXISTS (
          SELECT 1 FROM fact_sales s
          WHERE s.customer_id = c.customer_id
            AND s.product_id = sp.product_id
            AND s.date_key >= CURRENT_DATE - INTERVAL '12 months'
      )
)
SELECT * FROM customer_gaps
WHERE estimated_ticket IS NOT NULL
ORDER BY penetration * estimated_ticket DESC
LIMIT 500;
"""


# ---------------------------------------------------------------------------
# 2) REPLENISHMENT — cliente próximo da janela de recompra
# ---------------------------------------------------------------------------
REPLENISHMENT_QUERY = """
WITH customer_product_cycles AS (
    SELECT
        s.customer_id,
        s.product_id,
        COUNT(*) AS purchases,
        MAX(s.date_key) AS last_date,
        AVG(cycle_days) AS avg_cycle,
        STDDEV(cycle_days) AS std_cycle
    FROM (
        SELECT
            customer_id, product_id, date_key,
            EXTRACT(DAY FROM date_key - LAG(date_key) OVER (
                PARTITION BY customer_id, product_id ORDER BY date_key
            )) AS cycle_days
        FROM fact_sales
        WHERE date_key >= CURRENT_DATE - INTERVAL '18 months'
    ) s
    GROUP BY s.customer_id, s.product_id
    HAVING COUNT(*) >= 3
       AND AVG(cycle_days) IS NOT NULL
)
SELECT
    cpc.customer_id,
    c.name AS customer_name,
    cpc.product_id,
    p.clean_name AS product_name,
    cpc.avg_cycle::INT AS avg_cycle,
    (CURRENT_DATE - cpc.last_date)::INT AS days_since_last,
    (cpc.avg_cycle - (CURRENT_DATE - cpc.last_date))::INT AS days_until_due,
    -- inventory boost
    COALESCE(inv.needs_desova, FALSE) AS inventory_push,
    inv.days_of_cover
FROM customer_product_cycles cpc
JOIN dim_customer c USING (customer_id)
JOIN dim_product p USING (product_id)
LEFT JOIN LATERAL (
    SELECT needs_desova, days_of_cover
    FROM fact_inventory_snapshot
    WHERE product_id = cpc.product_id
    ORDER BY snapshot_date DESC
    LIMIT 1
) inv ON TRUE
WHERE (CURRENT_DATE - cpc.last_date) BETWEEN (cpc.avg_cycle * 0.85)::INT AND (cpc.avg_cycle * 1.15)::INT
ORDER BY 
    -- prioriza quem está dentro da janela E produto precisa desovar
    (CASE WHEN inv.needs_desova THEN 1 ELSE 2 END),
    ABS(cpc.avg_cycle - (CURRENT_DATE - cpc.last_date));
"""


async def generate_cross_sell_insights(session: AsyncSession) -> int:
    result = await session.execute(text(CROSS_SELL_QUERY))
    rows = result.mappings().all()
    count = 0
    for row in rows[:100]:  # limita a top 100 para não poluir
        await session.execute(text("""
            INSERT INTO fact_insights (
                insight_type, severity,
                customer_id, product_id,
                title, description, recommended_action,
                metric_value, metric_baseline, confidence_score, context
            ) VALUES (
                'opportunity', 'info',
                :customer_id, :product_id,
                :title, :description, :action,
                :metric_value, :baseline, :confidence, :context
            )
        """), {
            "customer_id": row["customer_id"],
            "product_id": row["product_id"],
            "title": f"Oportunidade: oferecer {row['product_name']} para {row['customer_name']}",
            "description": (
                f"{float(row['penetration']) * 100:.0f}% dos clientes do segmento "
                f"'{row['segment']}' compram {row['product_name']}, mas {row['customer_name']} "
                f"ainda não compra. Ticket médio esperado: R$ {float(row['estimated_ticket']):.2f}."
            ),
            "action": f"Abordar com foco em {row['product_name']}. Possível upside anual: R$ {float(row['estimated_ticket']) * 6:.0f}",
            "metric_value": float(row["estimated_ticket"] or 0),
            "baseline": float(row["penetration"]),
            "confidence": min(0.9, float(row["penetration"])),
            "context": f'{{"segment": "{row["segment"]}", "penetration": {float(row["penetration"]):.3f}}}',
        })
        count += 1

    await session.commit()
    log.info("cross_sell_insights_done", count=count)
    return count


async def generate_replenishment_insights(session: AsyncSession) -> int:
    result = await session.execute(text(REPLENISHMENT_QUERY))
    rows = result.mappings().all()
    count = 0
    for row in rows:
        # boost se precisa desovar estoque
        if row["inventory_push"]:
            severity = "critical"
            action_prefix = "PRIORIDADE (estoque precisa girar): "
        else:
            severity = "warning"
            action_prefix = ""

        await session.execute(text("""
            INSERT INTO fact_insights (
                insight_type, severity,
                customer_id, product_id,
                title, description, recommended_action,
                metric_value, metric_baseline, confidence_score, context
            ) VALUES (
                'replenishment', :severity,
                :customer_id, :product_id,
                :title, :description, :action,
                :metric_value, :baseline, 0.80, :context
            )
        """), {
            "severity": severity,
            "customer_id": row["customer_id"],
            "product_id": row["product_id"],
            "title": f"Janela de recompra: {row['customer_name']} / {row['product_name']}",
            "description": (
                f"{row['customer_name']} compra {row['product_name']} a cada "
                f"{row['avg_cycle']} dias. Já se passaram {row['days_since_last']} dias. "
                f"Janela ideal agora."
            ),
            "action": f"{action_prefix}Contatar cliente para confirmar pedido. "
                     f"Estoque atual cobre {float(row['days_of_cover'] or 0):.0f} dias.",
            "metric_value": float(row["days_since_last"]),
            "baseline": float(row["avg_cycle"]),
            "context": f'{{"inventory_push": {str(row["inventory_push"]).lower()}, "days_of_cover": {float(row["days_of_cover"] or 0):.1f}}}',
        })
        count += 1

    await session.commit()
    log.info("replenishment_insights_done", count=count)
    return count
