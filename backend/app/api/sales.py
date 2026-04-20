"""
/api/sales — endpoints de agregações e drill-down.

Todos endpoints seguem o padrão:
- Aceitam filtros dinâmicos (period, customer_id, product_id, salesperson_id)
- Retornam resultados SEMPRE ordenados por métrica DESC (maior para menor)
- Usam cache Redis com chave determinística baseada nos filtros
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Literal

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db

router = APIRouter()

# ----------- Redis client (shared) -----------------------------------------
_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def cache_key(prefix: str, **params) -> str:
    """Gera chave Redis determinística."""
    raw = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"{prefix}:{h}"


# ===========================================================================
# KPIs TOP-LEVEL
# ===========================================================================
@router.get("/kpis")
async def kpis(
    date_from: date = Query(..., description="YYYY-MM-DD"),
    date_to: date = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """KPIs do header do dashboard: faturamento, volume, ticket médio, # clientes."""
    key = cache_key("kpis", date_from=date_from, date_to=date_to)
    if cached := await r.get(key):
        return json.loads(cached)

    sql = text("""
        WITH current AS (
            SELECT
                COALESCE(SUM(revenue), 0) AS revenue,
                COALESCE(SUM(quantity), 0) AS qty,
                COALESCE(SUM(margin), 0) AS margin,
                COUNT(DISTINCT customer_id) AS customers,
                COUNT(DISTINCT qb_invoice_id) AS orders,
                COALESCE(AVG(unit_price), 0) AS avg_price
            FROM fact_sales
            WHERE date_key BETWEEN :d_from AND :d_to
        ),
        previous AS (
            -- mesmo comprimento de janela, imediatamente anterior
            SELECT
                COALESCE(SUM(revenue), 0) AS revenue,
                COALESCE(SUM(quantity), 0) AS qty,
                COUNT(DISTINCT customer_id) AS customers
            FROM fact_sales
            WHERE date_key BETWEEN (CAST(:d_from AS date) - (CAST(:d_to AS date) - CAST(:d_from AS date) + 1))
                               AND (CAST(:d_from AS date) - 1)
        )
        SELECT c.*, p.revenue AS prev_revenue, p.qty AS prev_qty, p.customers AS prev_customers
        FROM current c, previous p
    """)
    row = (await db.execute(sql, {"d_from": date_from, "d_to": date_to})).mappings().one()

    def pct_change(current, previous):
        if not previous:
            return None
        return round((float(current) - float(previous)) / float(previous) * 100, 2)

    response = {
        "revenue": float(row["revenue"]),
        "revenue_change_pct": pct_change(row["revenue"], row["prev_revenue"]),
        "quantity": float(row["qty"]),
        "quantity_change_pct": pct_change(row["qty"], row["prev_qty"]),
        "margin": float(row["margin"]),
        "avg_order_value": float(row["revenue"]) / float(row["orders"]) if row["orders"] else 0,
        "customers": row["customers"],
        "customers_change_pct": pct_change(row["customers"], row["prev_customers"]),
        "orders": row["orders"],
        "avg_unit_price": float(row["avg_price"]),
    }
    await r.setex(key, settings.CACHE_TTL_SECONDS, json.dumps(response))
    return response


# ===========================================================================
# RANKINGS (faturamento por X, sempre DESC)
# ===========================================================================
@router.get("/ranking")
async def ranking(
    dimension: Literal["customer", "product", "salesperson", "category"],
    metric: Literal["revenue", "quantity", "margin"] = "revenue",
    date_from: date = Query(...),
    date_to: date = Query(...),
    customer_id: str | None = None,
    product_id: str | None = None,
    salesperson_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """
    Ranking ordenado DESC do maior para menor.
    Usado como base dos gráficos de barras e como detalhe do drill-down.
    """
    key = cache_key(
        "ranking",
        dimension=dimension, metric=metric,
        date_from=date_from, date_to=date_to,
        customer_id=customer_id, product_id=product_id,
        salesperson_id=salesperson_id, limit=limit,
    )
    if cached := await r.get(key):
        return json.loads(cached)

    dim_sql = {
        "customer":    ("dim_customer c ON c.customer_id = s.customer_id", "c.customer_id", "c.name"),
        "product":     ("dim_product p ON p.product_id = s.product_id",    "p.product_id",  "p.clean_name"),
        "salesperson": ("dim_salesperson sp ON sp.salesperson_id = s.salesperson_id", "sp.salesperson_id", "sp.name"),
        "category":    ("dim_product p ON p.product_id = s.product_id",    "p.category",    "p.category"),
    }[dimension]
    join, id_col, label_col = dim_sql

    where_clauses = ["s.date_key BETWEEN :d_from AND :d_to"]
    params = {"d_from": date_from, "d_to": date_to, "limit": limit}
    if customer_id:
        where_clauses.append("s.customer_id = :customer_id")
        params["customer_id"] = customer_id
    if product_id:
        where_clauses.append("s.product_id = :product_id")
        params["product_id"] = product_id
    if salesperson_id:
        where_clauses.append("s.salesperson_id = :salesperson_id")
        params["salesperson_id"] = salesperson_id

    metric_expr = {
        "revenue": "SUM(s.revenue)",
        "quantity": "SUM(s.quantity)",
        "margin": "SUM(s.margin)",
    }[metric]

    sql = f"""
        SELECT
            {id_col} AS id,
            {label_col} AS label,
            {metric_expr} AS value,
            COUNT(DISTINCT s.qb_invoice_id) AS orders,
            {metric_expr} / NULLIF(SUM(SUM(s.revenue)) OVER (), 0) AS share
        FROM fact_sales s
        JOIN {join}
        WHERE {' AND '.join(where_clauses)}
        GROUP BY {id_col}, {label_col}
        ORDER BY value DESC NULLS LAST
        LIMIT :limit
    """
    result = await db.execute(text(sql), params)
    rows = [
        {
            "id": str(r["id"]) if r["id"] is not None else None,
            "label": r["label"],
            "value": float(r["value"] or 0),
            "orders": r["orders"],
            "share": float(r["share"] or 0),
        }
        for r in result.mappings()
    ]
    await r.setex(key, settings.CACHE_TTL_SECONDS, json.dumps(rows, default=str))
    return rows


# ===========================================================================
# DRILL-DOWN (o coração da UX)
# ===========================================================================
@router.get("/drilldown")
async def drilldown(
    entity: Literal["customer", "product", "salesperson", "category"],
    entity_id: str,
    breakdown_by: Literal["customer", "product", "salesperson", "category", "month"],
    metric: Literal["revenue", "quantity", "margin"] = "revenue",
    date_from: date = Query(...),
    date_to: date = Query(...),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    """
    Dado um entity (ex: customer X), retorna o breakdown dele por outra dimensão.
    Sempre ordenado DESC.

    Exemplo: clicou no cliente X → quer ver os produtos.
    entity=customer, entity_id=X, breakdown_by=product
    """
    # evita auto-breakdown (customer x customer não faz sentido)
    if entity == breakdown_by and breakdown_by != "month":
        raise HTTPException(400, f"entity e breakdown_by não podem ser ambos '{entity}'")

    key = cache_key(
        "drilldown",
        entity=entity, entity_id=entity_id, breakdown_by=breakdown_by,
        metric=metric, date_from=date_from, date_to=date_to, limit=limit,
    )
    if cached := await r.get(key):
        return json.loads(cached)

    entity_filter = {
        "customer": "s.customer_id = :entity_id",
        "product": "s.product_id = :entity_id",
        "salesperson": "s.salesperson_id = :entity_id",
        "category": "p2.category = :entity_id",
    }[entity]

    # Para filtro por categoria precisa do JOIN em dim_product com alias diferente
    extra_join = "JOIN dim_product p2 ON p2.product_id = s.product_id" if entity == "category" else ""

    breakdown_config = {
        "customer":    ("dim_customer c ON c.customer_id = s.customer_id", "c.customer_id::text", "c.name"),
        "product":     ("dim_product p ON p.product_id = s.product_id",    "p.product_id::text",  "p.clean_name"),
        "salesperson": ("dim_salesperson sp ON sp.salesperson_id = s.salesperson_id", "sp.salesperson_id::text", "sp.name"),
        "category":    ("dim_product p ON p.product_id = s.product_id",    "p.category",          "p.category"),
        "month":       ("", "to_char(date_trunc('month', s.date_key), 'YYYY-MM')", "to_char(date_trunc('month', s.date_key), 'YYYY-MM')"),
    }[breakdown_by]
    join, id_col, label_col = breakdown_config

    metric_expr = {
        "revenue": "SUM(s.revenue)",
        "quantity": "SUM(s.quantity)",
        "margin": "SUM(s.margin)",
    }[metric]

    sql = f"""
        SELECT
            {id_col} AS id,
            {label_col} AS label,
            {metric_expr} AS value,
            COUNT(DISTINCT s.qb_invoice_id) AS orders,
            AVG(s.unit_price) AS avg_price,
            {metric_expr} / NULLIF(SUM(SUM(s.revenue)) OVER (), 0) AS share
        FROM fact_sales s
        {"JOIN " + join if join else ""}
        {extra_join}
        WHERE s.date_key BETWEEN :d_from AND :d_to
          AND {entity_filter}
        GROUP BY 1, 2
        ORDER BY value DESC NULLS LAST
        LIMIT :limit
    """
    result = await db.execute(text(sql), {
        "d_from": date_from,
        "d_to": date_to,
        "entity_id": entity_id,
        "limit": limit,
    })
    rows = [
        {
            "id": r["id"],
            "label": r["label"],
            "value": float(r["value"] or 0),
            "orders": r["orders"],
            "avg_price": float(r["avg_price"] or 0),
            "share": float(r["share"] or 0),
        }
        for r in result.mappings()
    ]
    await r.setex(key, settings.CACHE_TTL_SECONDS, json.dumps(rows, default=str))
    return rows


# ===========================================================================
# SÉRIE TEMPORAL para MoM / YoY
# ===========================================================================
@router.get("/timeseries")
async def timeseries(
    metric: Literal["revenue", "quantity", "margin", "customers"] = "revenue",
    granularity: Literal["day", "week", "month"] = "month",
    compare: Literal["none", "mom", "yoy"] = "yoy",
    date_from: date = Query(...),
    date_to: date = Query(...),
    customer_id: str | None = None,
    product_id: str | None = None,
    salesperson_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    key = cache_key(
        "timeseries", metric=metric, granularity=granularity, compare=compare,
        date_from=date_from, date_to=date_to,
        customer_id=customer_id, product_id=product_id, salesperson_id=salesperson_id,
    )
    if cached := await r.get(key):
        return json.loads(cached)

    trunc = {"day": "day", "week": "week", "month": "month"}[granularity]
    metric_expr = {
        "revenue": "SUM(revenue)",
        "quantity": "SUM(quantity)",
        "margin": "SUM(margin)",
        "customers": "COUNT(DISTINCT customer_id)",
    }[metric]

    filters = ["date_key BETWEEN :d_from AND :d_to"]
    params: dict = {"d_from": date_from, "d_to": date_to}
    if customer_id:
        filters.append("customer_id = :customer_id"); params["customer_id"] = customer_id
    if product_id:
        filters.append("product_id = :product_id"); params["product_id"] = product_id
    if salesperson_id:
        filters.append("salesperson_id = :salesperson_id"); params["salesperson_id"] = salesperson_id

    sql_current = f"""
        SELECT date_trunc('{trunc}', date_key)::date AS period,
               {metric_expr} AS value
        FROM fact_sales
        WHERE {' AND '.join(filters)}
        GROUP BY 1
        ORDER BY 1
    """
    current = [
        {"period": r["period"].isoformat(), "value": float(r["value"] or 0)}
        for r in (await db.execute(text(sql_current), params)).mappings()
    ]

    response: dict = {"current": current, "compare": None}

    if compare != "none":
        delta = timedelta(days=365) if compare == "yoy" else timedelta(days=30)
        params_cmp = {
            **params,
            "d_from": date_from - delta,
            "d_to": date_to - delta,
        }
        compare_data = [
            {"period": r["period"].isoformat(), "value": float(r["value"] or 0)}
            for r in (await db.execute(text(sql_current), params_cmp)).mappings()
        ]
        response["compare"] = compare_data

    await r.setex(key, settings.CACHE_TTL_SECONDS, json.dumps(response, default=str))
    return response


# ===========================================================================
# REPRESENTATIVIDADE (market share interno)
# ===========================================================================
@router.get("/share")
async def share(
    target: Literal["product_in_customer", "customer_in_company"],
    customer_id: str | None = None,
    date_from: date = Query(...),
    date_to: date = Query(...),
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """
    - product_in_customer: qual % do faturamento do cliente X vem de cada produto
    - customer_in_company: qual % do faturamento total vem de cada cliente
    """
    if target == "product_in_customer":
        if not customer_id:
            raise HTTPException(400, "customer_id obrigatório para product_in_customer")
        sql = text("""
            SELECT
                p.product_id::text AS id,
                p.clean_name AS label,
                SUM(s.revenue) AS value,
                SUM(s.revenue) / NULLIF(SUM(SUM(s.revenue)) OVER (), 0) AS share
            FROM fact_sales s
            JOIN dim_product p USING (product_id)
            WHERE s.customer_id = :customer_id
              AND s.date_key BETWEEN :d_from AND :d_to
            GROUP BY p.product_id, p.clean_name
            ORDER BY value DESC
            LIMIT :limit
        """)
        result = await db.execute(sql, {
            "customer_id": customer_id,
            "d_from": date_from, "d_to": date_to, "limit": limit,
        })
    else:
        sql = text("""
            SELECT
                c.customer_id::text AS id,
                c.name AS label,
                SUM(s.revenue) AS value,
                SUM(s.revenue) / NULLIF(SUM(SUM(s.revenue)) OVER (), 0) AS share
            FROM fact_sales s
            JOIN dim_customer c USING (customer_id)
            WHERE s.date_key BETWEEN :d_from AND :d_to
            GROUP BY c.customer_id, c.name
            ORDER BY value DESC
            LIMIT :limit
        """)
        result = await db.execute(sql, {
            "d_from": date_from, "d_to": date_to, "limit": limit,
        })

    return [
        {
            "id": r["id"],
            "label": r["label"],
            "value": float(r["value"] or 0),
            "share": float(r["share"] or 0),
        }
        for r in result.mappings()
    ]
