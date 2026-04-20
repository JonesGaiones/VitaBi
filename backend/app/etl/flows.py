"""
Prefect flows executados pelos cron jobs do Antigravity.

Cada flow é idempotente e observável via UI do Prefect.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from prefect import flow, task
from prefect.logging import get_run_logger
from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.etl.transformer import run_full_transform
from app.etl.de_para_loader import load_de_para_from_excel
from app.services.quickbooks_client import QuickBooksClient


# ============================================================================
# TASKS
# ============================================================================

@task(retries=3, retry_delay_seconds=60)
async def qb_dump_customers() -> Path:
    qb = QuickBooksClient()
    try:
        return await qb.dump_entity_jsonl("Customer", settings.RAW_DIR)
    finally:
        await qb.close()


@task(retries=3, retry_delay_seconds=60)
async def qb_dump_items() -> Path:
    qb = QuickBooksClient()
    try:
        return await qb.dump_entity_jsonl("Item", settings.RAW_DIR)
    finally:
        await qb.close()


@task(retries=3, retry_delay_seconds=60)
async def qb_dump_invoices(incremental_since: str | None = None) -> Path:
    qb = QuickBooksClient()
    try:
        where = f"MetaData.LastUpdatedTime > '{incremental_since}'" if incremental_since else None
        return await qb.dump_entity_jsonl("Invoice", settings.RAW_DIR, where=where)
    finally:
        await qb.close()


@task
async def apply_transforms() -> dict:
    async with AsyncSessionLocal() as session:
        return await run_full_transform(session, Path(settings.RAW_DIR))


@task
async def refresh_mvs() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT refresh_all_materialized_views()"))
        await session.commit()


@task
async def invalidate_redis_cache() -> None:
    """Flush chaves de cache de dashboard após transform."""
    import redis.asyncio as redis
    client = redis.from_url(settings.REDIS_URL)
    async for key in client.scan_iter(match="dashboard:*"):
        await client.delete(key)
    async for key in client.scan_iter(match="drilldown:*"):
        await client.delete(key)
    await client.aclose()


@task
async def run_insights_engine() -> dict:
    """Chama o motor de insights (delega para app.insights)."""
    from app.insights.engine import run_all_detectors
    async with AsyncSessionLocal() as session:
        return await run_all_detectors(session)


# ============================================================================
# FLOWS
# ============================================================================

@flow(name="qb_extract_flow")
async def qb_extract_flow(incremental: bool = True) -> dict:
    """Dump completo do QB para JSONL em data/raw/."""
    logger = get_run_logger()

    # Pega timestamp do último sync (se incremental)
    incremental_since = None
    if incremental:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(
                "SELECT MAX(qb_sync_at) FROM dim_customer"
            ))
            last = result.scalar()
            if last:
                incremental_since = last.isoformat()
                logger.info(f"Incremental sync since {incremental_since}")

    customers = await qb_dump_customers()
    items = await qb_dump_items()
    invoices = await qb_dump_invoices(incremental_since=incremental_since)

    return {
        "customers_file": str(customers),
        "items_file": str(items),
        "invoices_file": str(invoices),
    }


@flow(name="de_para_apply_flow")
async def de_para_apply_flow(excel_path: str) -> dict:
    """
    Processa um Excel de de-para recém-uploaded.
    Pode ser disparado manualmente pela API ou pelo file-watcher.
    """
    async with AsyncSessionLocal() as session:
        result = await load_de_para_from_excel(session, excel_path)
    # re-roda transform para aplicar as novas regras
    transform_result = await apply_transforms()
    await invalidate_redis_cache()
    return {"de_para": result, "transform": transform_result}


@flow(name="transform_flow")
async def transform_flow() -> dict:
    """Transform completo + refresh MV + invalidate cache."""
    stats = await apply_transforms()
    await invalidate_redis_cache()
    return stats


@flow(name="mv_refresh_flow")
async def mv_refresh_flow() -> None:
    await refresh_mvs()


@flow(name="insights_flow")
async def insights_flow() -> dict:
    """Roda o motor de insights diariamente."""
    return await run_insights_engine()


@flow(name="churn_flow")
async def churn_flow() -> dict:
    """Scan específico de churn (mais rápido, roda separado)."""
    from app.insights.churn_detector import detect_churn_signals
    async with AsyncSessionLocal() as session:
        return await detect_churn_signals(session)


@flow(name="full_pipeline")
async def full_pipeline() -> dict:
    """Pipeline ponta-a-ponta: extract → transform → insights."""
    extract = await qb_extract_flow(incremental=True)
    transform = await transform_flow()
    insights = await insights_flow()
    return {"extract": extract, "transform": transform, "insights": insights}
