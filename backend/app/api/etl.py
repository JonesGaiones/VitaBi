"""
/api/etl — triggers manuais e upload de planilhas.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.etl.de_para_loader import load_de_para_from_excel, DeParaValidationError

router = APIRouter()


@router.post("/de-para/upload")
async def upload_de_para(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload de planilha Excel de-para.
    Salva o arquivo em data/de_para/ e dispara o processamento.
    Retorna estatísticas.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Apenas arquivos .xlsx ou .xls são aceitos")

    # Salva com timestamp para audit trail
    dest_dir = Path(settings.DE_PARA_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_path = dest_dir / f"{timestamp}_{file.filename}"

    with dest_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        result = await load_de_para_from_excel(db, dest_path, created_by="ui-upload")
        return {"ok": True, **result}
    except DeParaValidationError as e:
        # Remove arquivo inválido
        dest_path.unlink(missing_ok=True)
        raise HTTPException(400, str(e))


@router.get("/status")
async def etl_status(db: AsyncSession = Depends(get_db)):
    """Status da última sincronização de cada entidade."""
    sql = text("""
        SELECT
            (SELECT MAX(qb_sync_at) FROM dim_customer) AS last_customer_sync,
            (SELECT MAX(qb_sync_at) FROM dim_product) AS last_product_sync,
            (SELECT MAX(created_at) FROM fact_sales) AS last_sales_ingested,
            (SELECT COUNT(*) FROM dim_product WHERE needs_cleanup) AS products_needing_cleanup,
            (SELECT COUNT(*) FROM fact_insights WHERE status='new') AS open_insights
    """)
    row = (await db.execute(sql)).mappings().one()
    result = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = int(v) if v is not None else 0
    return result


@router.post("/trigger/{flow_name}")
async def trigger_flow(flow_name: str):
    """
    Dispara um flow manualmente. Roda diretamente sem precisar do Prefect.
    """
    from pathlib import Path
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal

    valid_flows = ["qb_extract", "qb_extract_full", "transform", "insights", "churn", "full"]
    if flow_name not in valid_flows:
        raise HTTPException(400, f"Flow inválido. Disponíveis: {valid_flows}")

    try:
        if flow_name in ("transform", "full"):
            from app.etl.transformer import run_full_transform
            async with AsyncSessionLocal() as session:
                result = await run_full_transform(session, Path(settings.RAW_DIR))
            return {"ok": True, "flow": flow_name, "result": result}

        elif flow_name == "insights":
            from app.insights.engine import run_all_detectors
            async with AsyncSessionLocal() as session:
                result = await run_all_detectors(session)
            return {"ok": True, "flow": flow_name, "result": result}

        elif flow_name in ("qb_extract", "qb_extract_full"):
            from app.services.quickbooks_client import QuickBooksClient
            qb = QuickBooksClient()
            try:
                await qb.dump_entity_jsonl("Customer", settings.RAW_DIR)
                await qb.dump_entity_jsonl("Item", settings.RAW_DIR)
                await qb.dump_entity_jsonl("Invoice", settings.RAW_DIR)
            finally:
                await qb.close()
            return {"ok": True, "flow": flow_name, "status": "done"}

        else:
            return {"ok": True, "flow": flow_name, "status": "dispatched"}

    except Exception as e:
        import traceback
        raise HTTPException(500, detail=f"Erro no flow '{flow_name}': {str(e)}\n{traceback.format_exc()}")
@router.post("/bootstrap-mapping")
async def bootstrap_mapping(db: AsyncSession = Depends(get_db)):
    """
    Importa o mapeamento JSON de rascunho para o banco profissional.
    """
    import json
    json_path = r"C:\Users\joaog\.gemini\antigravity\scratch\product_mapping.json"
    
    with open(json_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    sql = text("""
        INSERT INTO dim_de_para (
            qb_raw_pattern, match_type, clean_name, category, 
            priority, active, source_file, created_by, updated_at
        )
        VALUES (
            :pattern, 'contains', :clean_name, :category, 
            100, TRUE, 'product_mapping.json', 'bootstrap_api', NOW()
        )
        ON CONFLICT (qb_raw_pattern, match_type) DO UPDATE SET
            clean_name = EXCLUDED.clean_name,
            category = EXCLUDED.category,
            updated_at = NOW()
    """)

    count = 0
    for pattern, values in mapping.items():
        if not pattern or not values or "Considerar somente Valor" in values[0]:
            continue
        await db.execute(sql, {"pattern": pattern, "clean_name": values[0], "category": values[1]})
        count += 1
    
    await db.commit()
    return {"ok": True, "imported": count}
