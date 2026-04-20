"""
/api/insights — feed de inteligência gerada pelo motor.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal
from pydantic import BaseModel

from app.db.session import get_db

router = APIRouter()


@router.get("/feed")
async def insights_feed(
    status: Literal["new", "acknowledged", "resolved", "dismissed", "all"] = "new",
    insight_type: str | None = None,
    severity: Literal["info", "warning", "critical", "all"] = "all",
    customer_id: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Feed principal de insights, ordenado por severidade + confiança."""
    where = []
    params: dict = {"limit": limit}
    if status != "all":
        where.append("i.status = :status"); params["status"] = status
    if severity != "all":
        where.append("i.severity = :severity"); params["severity"] = severity
    if insight_type:
        where.append("i.insight_type = :itype"); params["itype"] = insight_type
    if customer_id:
        where.append("i.customer_id = :cid"); params["cid"] = customer_id

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = text(f"""
        SELECT
            i.insight_id::text AS id,
            i.insight_type, i.severity, i.status,
            i.title, i.description, i.recommended_action,
            i.metric_value, i.metric_baseline, i.confidence_score,
            i.generated_at, i.context,
            c.name AS customer_name, c.customer_id::text AS customer_id,
            p.clean_name AS product_name, p.product_id::text AS product_id,
            sp.name AS salesperson_name
        FROM fact_insights i
        LEFT JOIN dim_customer c USING (customer_id)
        LEFT JOIN dim_product p USING (product_id)
        LEFT JOIN dim_salesperson sp USING (salesperson_id)
        {where_sql}
        ORDER BY
            CASE i.severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
            i.confidence_score DESC,
            i.generated_at DESC
        LIMIT :limit
    """)
    result = await db.execute(sql, params)
    rows = []
    for r in result.mappings():
        d = dict(r)
        for k in ("metric_value", "metric_baseline", "confidence_score"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        if d.get("generated_at"):
            d["generated_at"] = d["generated_at"].isoformat()
        rows.append(d)
    return rows


@router.get("/counters")
async def insight_counters(db: AsyncSession = Depends(get_db)):
    """Contadores para badges do header."""
    sql = text("""
        SELECT
            COUNT(*) FILTER (WHERE status='new' AND severity='critical') AS critical,
            COUNT(*) FILTER (WHERE status='new' AND severity='warning') AS warning,
            COUNT(*) FILTER (WHERE status='new' AND severity='info') AS info,
            COUNT(*) FILTER (WHERE status='new' AND insight_type='churn') AS churn,
            COUNT(*) FILTER (WHERE status='new' AND insight_type='pricing') AS pricing,
            COUNT(*) FILTER (WHERE status='new' AND insight_type='margin') AS margin,
            COUNT(*) FILTER (WHERE status='new' AND insight_type='opportunity') AS opportunity,
            COUNT(*) FILTER (WHERE status='new' AND insight_type='replenishment') AS replenishment
        FROM fact_insights
    """)
    row = (await db.execute(sql)).mappings().one()
    return {k: int(v or 0) for k, v in row.items()}


class InsightStatusUpdate(BaseModel):
    status: Literal["acknowledged", "resolved", "dismissed"]
    resolved_by: str | None = None


@router.patch("/{insight_id}/status")
async def update_insight_status(
    insight_id: str,
    body: InsightStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    sql = text("""
        UPDATE fact_insights
        SET status = :status,
            resolved_at = CASE WHEN :status IN ('resolved','dismissed') THEN NOW() ELSE resolved_at END,
            resolved_by = COALESCE(:resolved_by, resolved_by)
        WHERE insight_id = :id
        RETURNING insight_id
    """)
    result = await db.execute(sql, {
        "status": body.status,
        "resolved_by": body.resolved_by,
        "id": insight_id,
    })
    if not result.fetchone():
        raise HTTPException(404, "Insight not found")
    await db.commit()
    return {"ok": True}
