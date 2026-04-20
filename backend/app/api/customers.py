"""
/api/customers — visão 360° de clientes.
"""
from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("")
async def list_customers(
    search: str | None = None,
    tier: str | None = None,
    segment: str | None = None,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Lista paginada de clientes com KPIs resumidos (usa mv_customer_360)."""
    where = []
    params: dict = {"limit": limit, "offset": offset}
    if active_only:
        where.append("c.is_active = TRUE")
    if search:
        where.append("c.name ILIKE :search")
        params["search"] = f"%{search}%"
    if tier:
        where.append("c.tier = :tier"); params["tier"] = tier
    if segment:
        where.append("c.segment = :segment"); params["segment"] = segment

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    sql = text(f"""
        SELECT
            c.customer_id::text AS id,
            c.name, c.tier, c.segment,
            mv.lifetime_revenue, mv.revenue_ytd,
            mv.last_purchase_date, mv.days_since_last_purchase,
            mv.avg_cycle_days, mv.total_orders
        FROM dim_customer c
        LEFT JOIN mv_customer_360 mv USING (customer_id)
        {where_sql}
        ORDER BY mv.lifetime_revenue DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(sql, params)
    return [dict(r) for r in result.mappings()]


@router.get("/{customer_id}")
async def customer_detail(customer_id: str, db: AsyncSession = Depends(get_db)):
    """Ficha completa do cliente — base para Customer Genome no frontend."""
    sql = text("""
        SELECT
            c.customer_id::text AS id,
            c.name, c.email, c.phone, c.tier, c.segment,
            c.city, c.state, c.country,
            c.first_purchase_date, c.last_purchase_date,
            mv.lifetime_revenue, mv.lifetime_margin,
            mv.revenue_ytd, mv.revenue_last_year,
            mv.avg_cycle_days, mv.days_since_last_purchase,
            mv.total_orders, mv.avg_price_paid
        FROM dim_customer c
        LEFT JOIN mv_customer_360 mv USING (customer_id)
        WHERE c.customer_id = :id
    """)
    row = (await db.execute(sql, {"id": customer_id})).mappings().first()
    if not row:
        raise HTTPException(404, "Customer not found")
    return dict(row)


@router.get("/{customer_id}/genome")
async def customer_genome(customer_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retorna os dados para o 'Customer Genome' — a visualização radial:
    - sazonalidade por mês (último 24m)
    - produtos âncora (top 5 por frequência e revenue)
    - elasticidade a desconto (correlação entre discount_pct e quantity)
    - sensibilidade a preço (stddev do unit_price normalizado)
    - NPS implícito (derivado de churn e frequência)
    """
    # 1. Sazonalidade
    seasonality_sql = text("""
        SELECT EXTRACT(MONTH FROM date_key)::INT AS month,
               SUM(revenue) AS revenue,
               COUNT(DISTINCT qb_invoice_id) AS orders
        FROM fact_sales
        WHERE customer_id = :id
          AND date_key >= CURRENT_DATE - INTERVAL '24 months'
        GROUP BY 1
        ORDER BY 1
    """)
    seasonality = [dict(r) for r in
                   (await db.execute(seasonality_sql, {"id": customer_id})).mappings()]
    for s in seasonality:
        s["revenue"] = float(s["revenue"] or 0)

    # 2. Produtos âncora (top 5 por revenue nos últimos 12m)
    anchors_sql = text("""
        SELECT
            p.product_id::text AS id,
            p.clean_name AS name,
            p.category,
            SUM(s.revenue) AS revenue,
            SUM(s.quantity) AS quantity,
            COUNT(DISTINCT s.qb_invoice_id) AS orders,
            AVG(s.unit_price) AS avg_price
        FROM fact_sales s
        JOIN dim_product p USING (product_id)
        WHERE s.customer_id = :id
          AND s.date_key >= CURRENT_DATE - INTERVAL '12 months'
        GROUP BY p.product_id, p.clean_name, p.category
        ORDER BY revenue DESC
        LIMIT 5
    """)
    anchors = [{**dict(r), "revenue": float(r["revenue"] or 0),
                "quantity": float(r["quantity"] or 0),
                "avg_price": float(r["avg_price"] or 0)}
               for r in (await db.execute(anchors_sql, {"id": customer_id})).mappings()]

    # 3. Elasticidade a desconto (correlação simplificada)
    elasticity_sql = text("""
        SELECT CORR(discount_pct::FLOAT, quantity::FLOAT) AS elasticity,
               AVG(discount_pct) AS avg_discount,
               STDDEV(unit_price) / NULLIF(AVG(unit_price), 0) AS price_volatility
        FROM fact_sales
        WHERE customer_id = :id
          AND date_key >= CURRENT_DATE - INTERVAL '12 months'
    """)
    elasticity = (await db.execute(elasticity_sql, {"id": customer_id})).mappings().first()

    # 4. Implicit NPS (score 0-100):
    # base 50 + bonus por frequência + penalidade por atraso
    nps_sql = text("""
        SELECT
            LEAST(100, GREATEST(0,
                50
                + LEAST(30, total_orders * 1.5)
                - LEAST(40, COALESCE(days_since_last_purchase, 0) / NULLIF(avg_cycle_days, 0) * 20)
            ))::INT AS nps_score
        FROM mv_customer_360
        WHERE customer_id = :id
    """)
    nps = (await db.execute(nps_sql, {"id": customer_id})).scalar() or 50

    return {
        "seasonality": seasonality,
        "anchor_products": anchors,
        "elasticity": {
            "discount_elasticity": float(elasticity["elasticity"] or 0) if elasticity else 0,
            "avg_discount_pct": float(elasticity["avg_discount"] or 0) if elasticity else 0,
            "price_volatility": float(elasticity["price_volatility"] or 0) if elasticity else 0,
        },
        "implicit_nps": int(nps),
    }
