"""
/api/products — performance por produto e categoria.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("")
async def list_products(
    search: str | None = None,
    category: str | None = None,
    needs_cleanup: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    where = ["p.is_active = TRUE"]
    params: dict = {"limit": limit, "offset": offset}
    if search:
        where.append("(p.clean_name ILIKE :search OR p.qb_raw_name ILIKE :search)")
        params["search"] = f"%{search}%"
    if category:
        where.append("p.category = :category"); params["category"] = category
    if needs_cleanup is not None:
        where.append("p.needs_cleanup = :nc"); params["nc"] = needs_cleanup

    sql = text(f"""
        SELECT
            p.product_id::text AS id,
            p.qb_raw_name, p.clean_name, p.category, p.subcategory,
            p.brand, p.needs_cleanup,
            mv.units_sold, mv.total_revenue, mv.total_margin,
            mv.avg_price, mv.unique_customers,
            mv.revenue_30d, mv.revenue_30d_prev,
            CASE WHEN mv.revenue_30d_prev > 0
                 THEN (mv.revenue_30d - mv.revenue_30d_prev) / mv.revenue_30d_prev
                 ELSE NULL END AS growth_30d
        FROM dim_product p
        LEFT JOIN mv_product_performance mv USING (product_id)
        WHERE {' AND '.join(where)}
        ORDER BY mv.total_revenue DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(sql, params)
    rows = []
    for r in result.mappings():
        d = dict(r)
        for k in ("units_sold", "total_revenue", "total_margin", "avg_price",
                  "revenue_30d", "revenue_30d_prev", "growth_30d"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        rows.append(d)
    return rows


@router.get("/needs-cleanup")
async def products_needing_cleanup(db: AsyncSession = Depends(get_db)):
    """
    Lista todos os produtos que estão sem correspondência no de-para.
    Front usa isso como um "to-do" do time de operações.
    """
    sql = text("""
        SELECT
            p.product_id::text AS id,
            p.qb_raw_name,
            p.qb_item_id,
            COUNT(s.sale_id) AS sales_count,
            COALESCE(SUM(s.revenue), 0) AS revenue_lost_to_uncategorized
        FROM dim_product p
        LEFT JOIN fact_sales s ON s.product_id = p.product_id
            AND s.date_key >= CURRENT_DATE - INTERVAL '6 months'
        WHERE p.needs_cleanup = TRUE AND p.is_active = TRUE
        GROUP BY p.product_id, p.qb_raw_name, p.qb_item_id
        ORDER BY revenue_lost_to_uncategorized DESC
    """)
    result = await db.execute(sql)
    return [{**dict(r), "revenue_lost_to_uncategorized": float(r["revenue_lost_to_uncategorized"])}
            for r in result.mappings()]


@router.get("/inventory-alerts")
async def inventory_alerts(db: AsyncSession = Depends(get_db)):
    """Produtos em risco de stockout ou que precisam desovar."""
    sql = text("""
        SELECT
            p.product_id::text AS id,
            p.clean_name, p.category,
            inv.qty_on_hand, inv.qty_available,
            inv.days_of_cover, inv.turnover_rate,
            inv.is_slow_mover, inv.is_stockout_risk, inv.needs_desova,
            inv.snapshot_date
        FROM dim_product p
        JOIN LATERAL (
            SELECT * FROM fact_inventory_snapshot
            WHERE product_id = p.product_id
            ORDER BY snapshot_date DESC LIMIT 1
        ) inv ON TRUE
        WHERE inv.is_stockout_risk OR inv.needs_desova
        ORDER BY
            CASE WHEN inv.is_stockout_risk THEN 1 ELSE 2 END,
            inv.days_of_cover ASC NULLS LAST
    """)
    result = await db.execute(sql)
    rows = []
    for r in result.mappings():
        d = dict(r)
        for k in ("qty_on_hand", "qty_available", "days_of_cover", "turnover_rate"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        rows.append(d)
    return rows
