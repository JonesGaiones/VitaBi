"""
Orquestrador do motor de insights.
Chamado diariamente pelo flow `insights_flow`.
"""
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.insights.churn_detector import detect_churn_signals
from app.insights.anomaly_detector import (
    detect_price_anomalies,
    detect_margin_violations,
)
from app.insights.recommender import (
    generate_cross_sell_insights,
    generate_replenishment_insights,
)

log = structlog.get_logger()


async def run_all_detectors(session: AsyncSession) -> dict:
    """
    Ordem:
    1. Arquiva insights antigos (status=new há mais de 14 dias → dismissed)
    2. Churn (clientes)
    3. Anomalias (preço / margem)
    4. Cross-sell (oportunidades)
    5. Replenishment (reabastecimento)
    """
    # 1. Archive stale
    await session.execute(text("""
        UPDATE fact_insights
        SET status = 'dismissed', resolved_at = NOW(), resolved_by = 'system-archival'
        WHERE status = 'new'
          AND generated_at < NOW() - INTERVAL '14 days'
    """))
    await session.commit()

    results = {
        "churn": await detect_churn_signals(session),
        "price_anomalies": await detect_price_anomalies(session),
        "margin_violations": await detect_margin_violations(session),
        "cross_sell": await generate_cross_sell_insights(session),
        "replenishment": await generate_replenishment_insights(session),
    }

    # 6. Notify critical insights via Slack
    await notify_critical_insights(session)

    log.info("insights_engine_full_run_done", **{k: str(v) for k, v in results.items()})
    return results


async def notify_critical_insights(session: AsyncSession):
    """
    Busca insights críticos gerados recentemente e envia para o Slack.
    """
    from app.services.notifications import send_slack_notification

    # Busca apenas os críticos que ainda são 'new' e foram gerados nos últimos 10 minutos
    # (margem de segurança para o tempo de execução do engine)
    query = text("""
        SELECT title, description, severity
        FROM fact_insights
        WHERE severity = 'critical'
          AND status = 'new'
          AND generated_at > NOW() - INTERVAL '10 minutes'
        ORDER BY generated_at ASC
    """)
    result = await session.execute(query)
    rows = result.mappings().all()

    if not rows:
        return

    log.info("notifying_slack", count=len(rows))
    for row in rows:
        await send_slack_notification(
            title=row["title"],
            description=row["description"],
            severity=row["severity"]
        )
