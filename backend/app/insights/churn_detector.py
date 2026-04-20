"""
Detector de Churn.

Lógica:
- Para cada cliente com >= 3 compras nos últimos 18 meses, calcula:
    - mean_cycle: média dos intervalos entre compras
    - std_cycle: desvio padrão dos intervalos
    - days_since_last: dias desde a última compra
- Se days_since_last > mean_cycle + k*std_cycle (default k=1.5), dispara alerta.
- Severidade escala com quão atrasado está:
    - k=1.5  → warning
    - k=2.5  → critical
    - k=4.0  → ghosted (provavelmente perdemos o cliente)
"""
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

log = structlog.get_logger()


CHURN_QUERY = """
WITH purchase_cycles AS (
    SELECT
        customer_id,
        date_key,
        LAG(date_key) OVER (PARTITION BY customer_id ORDER BY date_key) AS prev_date
    FROM (
        SELECT DISTINCT customer_id, date_key
        FROM fact_sales
        WHERE date_key >= CURRENT_DATE - INTERVAL '18 months'
    ) sub
),
customer_stats AS (
    SELECT
        customer_id,
        COUNT(*) FILTER (WHERE prev_date IS NOT NULL) AS n_cycles,
        AVG(EXTRACT(DAY FROM (date_key - prev_date))) FILTER (WHERE prev_date IS NOT NULL) AS mean_cycle,
        STDDEV(EXTRACT(DAY FROM (date_key - prev_date))) FILTER (WHERE prev_date IS NOT NULL) AS std_cycle,
        MAX(date_key) AS last_purchase
    FROM purchase_cycles
    GROUP BY customer_id
    HAVING COUNT(*) FILTER (WHERE prev_date IS NOT NULL) >= 3
)
SELECT
    cs.customer_id,
    c.name AS customer_name,
    cs.mean_cycle::NUMERIC(8,2) AS mean_cycle,
    COALESCE(cs.std_cycle, cs.mean_cycle * 0.3)::NUMERIC(8,2) AS std_cycle,
    (CURRENT_DATE - cs.last_purchase)::INT AS days_since_last,
    cs.last_purchase,
    mv.lifetime_revenue,
    mv.revenue_ytd,
    -- "z-score" de quão atrasado está
    ((CURRENT_DATE - cs.last_purchase) - cs.mean_cycle) 
        / NULLIF(COALESCE(cs.std_cycle, cs.mean_cycle * 0.3), 0) AS z_score
FROM customer_stats cs
JOIN dim_customer c USING (customer_id)
LEFT JOIN mv_customer_360 mv USING (customer_id)
WHERE (CURRENT_DATE - cs.last_purchase) > cs.mean_cycle + :k_sigma * COALESCE(cs.std_cycle, cs.mean_cycle * 0.3)
ORDER BY mv.lifetime_revenue DESC NULLS LAST;
"""


INSERT_INSIGHT_SQL = text("""
    INSERT INTO fact_insights (
        insight_type, severity, customer_id,
        title, description, recommended_action,
        metric_value, metric_baseline, confidence_score, context
    )
    VALUES (
        'churn', :severity, :customer_id,
        :title, :description, :recommended_action,
        :metric_value, :metric_baseline, :confidence, :context
    )
""")


def classify_severity(z_score: float) -> str:
    if z_score >= 4.0:
        return "critical"
    if z_score >= 2.5:
        return "critical"
    if z_score >= 1.5:
        return "warning"
    return "info"


async def detect_churn_signals(session: AsyncSession) -> dict:
    """
    Executa a detecção, insere insights novos em fact_insights.
    Antes de inserir, marca insights antigos de churn como 'stale'
    para evitar duplicatas.
    """
    # 1. marca os antigos como resolvidos automaticamente se o cliente comprou
    await session.execute(text("""
        UPDATE fact_insights fi
        SET status = 'resolved', resolved_at = NOW(), resolved_by = 'system'
        WHERE fi.insight_type = 'churn'
          AND fi.status = 'new'
          AND EXISTS (
              SELECT 1 FROM fact_sales fs
              WHERE fs.customer_id = fi.customer_id
                AND fs.date_key > fi.generated_at::DATE
          )
    """))

    # 2. roda a query de churn
    result = await session.execute(
        text(CHURN_QUERY),
        {"k_sigma": settings.CHURN_SIGMA_THRESHOLD},
    )
    rows = result.mappings().all()

    new_insights = 0
    for row in rows:
        z = float(row["z_score"] or 0)
        severity = classify_severity(z)
        days_late = float(row["days_since_last"]) - float(row["mean_cycle"])

        title = f"Cliente '{row['customer_name']}' em risco de churn"
        description = (
            f"Esse cliente costuma comprar a cada {row['mean_cycle']:.0f} dias "
            f"(±{row['std_cycle']:.0f}). Já se passaram {row['days_since_last']} dias "
            f"desde a última compra — {days_late:.0f} dias além do normal "
            f"(z-score: {z:.2f})."
        )
        if severity == "critical":
            action = (
                f"LIGAR HOJE. LTV de R$ {float(row['lifetime_revenue'] or 0):,.0f}. "
                f"Considere oferecer desconto ou visita presencial."
            )
        elif severity == "warning":
            action = (
                f"Enviar email ou WhatsApp proativo. "
                f"Verificar se houve problema na última entrega."
            )
        else:
            action = "Monitorar nos próximos 7 dias."

        # confiança: mais ciclos históricos = maior confiança
        confidence = min(0.99, 0.5 + 0.05 * min(z, 10))

        await session.execute(INSERT_INSIGHT_SQL, {
            "severity": severity,
            "customer_id": row["customer_id"],
            "title": title,
            "description": description,
            "recommended_action": action,
            "metric_value": float(row["days_since_last"]),
            "metric_baseline": float(row["mean_cycle"]),
            "confidence": confidence,
            "context": '{"z_score": %.3f, "lifetime_revenue": %s, "revenue_ytd": %s}' % (
                z,
                float(row["lifetime_revenue"] or 0),
                float(row["revenue_ytd"] or 0),
            ),
        })
        new_insights += 1

    await session.commit()
    log.info("churn_detection_done", new_insights=new_insights, total_candidates=len(rows))
    return {"new_insights": new_insights, "candidates": len(rows)}
