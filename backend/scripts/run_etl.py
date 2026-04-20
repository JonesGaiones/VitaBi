"""
Roda o pipeline ETL sem Prefect — para uso local.
Uso: python scripts/run_etl.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.etl.transformer import run_full_transform
from app.services.quickbooks_client import QuickBooksClient
from sqlalchemy import text


async def main():
    print("=== VITA BI — ETL Pipeline ===\n")

    # 1. Extract do QuickBooks
    print("[1/3] Extraindo dados do QuickBooks...")
    qb = QuickBooksClient()
    try:
        raw_dir = settings.RAW_DIR
        print(f"  Customers...")
        c = await qb.dump_entity_jsonl("Customer", raw_dir)
        print(f"  -> {c}")

        print(f"  Items (produtos)...")
        i = await qb.dump_entity_jsonl("Item", raw_dir)
        print(f"  -> {i}")

        print(f"  Invoices...")
        inv = await qb.dump_entity_jsonl("Invoice", raw_dir)
        print(f"  -> {inv}")
    finally:
        await qb.close()

    # 2. Transform
    print("\n[2/3] Transformando e carregando no banco...")
    async with AsyncSessionLocal() as session:
        stats = await run_full_transform(session, Path(raw_dir))
        print(f"  Stats: {stats}")

    # 3. Refresh materialized views
    print("\n[3/3] Atualizando materialized views...")
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT refresh_all_materialized_views()"))
        await session.commit()
        print("  OK")

    print("\n=== Pipeline concluido! Atualize o dashboard. ===")


if __name__ == "__main__":
    asyncio.run(main())
