"""
Ingestão da planilha Excel de 'De-Para'.

Formato esperado da planilha (colunas obrigatórias marcadas com *):
    qb_raw_pattern*  | match_type* | clean_name* | category* | subcategory |
    brand            | unit_of_measure | pack_size | priority | active

- match_type ∈ {exact, contains, regex}
- priority: menor valor = aplica primeiro. Default 100.
- active: TRUE/FALSE. Default TRUE.

O processo:
1. Lê a planilha com pandas
2. Valida colunas e tipos
3. UPSERT em dim_de_para (chave: qb_raw_pattern + match_type)
4. Marca dim_product.needs_cleanup = TRUE para produtos afetados pela mudança
5. Dispara re-aplicação assíncrona no flow `de_para_apply_flow`
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

REQUIRED_COLS = {"qb_raw_pattern", "match_type", "clean_name", "category"}
VALID_MATCH_TYPES = {"exact", "contains", "regex"}


class DeParaValidationError(Exception):
    pass


def validate_dataframe(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """
    Valida e normaliza o DataFrame da planilha.
    Retorna o DataFrame limpo, pronto para persistir.
    Levanta DeParaValidationError em caso de problema.
    """
    # 1. Colunas obrigatórias
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise DeParaValidationError(
            f"Planilha '{source_file}' sem colunas obrigatórias: {missing}"
        )

    # 2. Drop linhas totalmente vazias
    df = df.dropna(how="all").copy()

    # 3. Trim strings
    for col in ["qb_raw_pattern", "clean_name", "category", "subcategory", "brand"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None})

    # 4. match_type em lowercase e validação
    df["match_type"] = df["match_type"].astype(str).str.lower().str.strip()
    bad_mt = df[~df["match_type"].isin(VALID_MATCH_TYPES)]
    if not bad_mt.empty:
        raise DeParaValidationError(
            f"match_type inválido nas linhas {bad_mt.index.tolist()}. "
            f"Válidos: {VALID_MATCH_TYPES}"
        )

    # 5. Se match_type == 'regex', tentar compilar
    for idx, pat in df.loc[df["match_type"] == "regex", "qb_raw_pattern"].items():
        try:
            re.compile(pat)
        except re.error as e:
            raise DeParaValidationError(
                f"Regex inválido na linha {idx}: '{pat}' — {e}"
            )

    # 6. Defaults
    df["priority"] = df.get("priority", 100).fillna(100).astype(int)
    df["active"] = df.get("active", True).fillna(True).astype(bool)
    df["source_file"] = source_file

    # 7. Conflitos dentro da própria planilha
    dup = df.duplicated(subset=["qb_raw_pattern", "match_type"], keep=False)
    if dup.any():
        raise DeParaValidationError(
            f"Planilha tem linhas duplicadas (qb_raw_pattern + match_type): "
            f"{df.loc[dup].index.tolist()}"
        )

    log.info("de_para_validation_ok", rows=len(df), file=source_file)
    return df


async def upsert_de_para(
    session: AsyncSession,
    df: pd.DataFrame,
    created_by: str = "etl",
) -> dict[str, int]:
    """
    UPSERT do DataFrame em dim_de_para.
    Retorna contadores de inseridos e atualizados.
    """
    # Usa INSERT ... ON CONFLICT DO UPDATE
    sql = text("""
        INSERT INTO dim_de_para (
            qb_raw_pattern, match_type, clean_name, category, subcategory,
            brand, unit_of_measure, pack_size, priority, active,
            source_file, created_by, updated_at
        )
        VALUES (
            :qb_raw_pattern, :match_type, :clean_name, :category, :subcategory,
            :brand, :unit_of_measure, :pack_size, :priority, :active,
            :source_file, :created_by, NOW()
        )
        ON CONFLICT (qb_raw_pattern, match_type) DO UPDATE SET
            clean_name     = EXCLUDED.clean_name,
            category       = EXCLUDED.category,
            subcategory    = EXCLUDED.subcategory,
            brand          = EXCLUDED.brand,
            unit_of_measure = EXCLUDED.unit_of_measure,
            pack_size      = EXCLUDED.pack_size,
            priority       = EXCLUDED.priority,
            active         = EXCLUDED.active,
            source_file    = EXCLUDED.source_file,
            updated_at     = NOW()
        RETURNING (xmax = 0) AS inserted
    """)

    inserted = updated = 0
    for row in df.itertuples(index=False):
        params = {
            "qb_raw_pattern": row.qb_raw_pattern,
            "match_type": row.match_type,
            "clean_name": row.clean_name,
            "category": row.category,
            "subcategory": getattr(row, "subcategory", None),
            "brand": getattr(row, "brand", None),
            "unit_of_measure": getattr(row, "unit_of_measure", None),
            "pack_size": getattr(row, "pack_size", None),
            "priority": row.priority,
            "active": row.active,
            "source_file": row.source_file,
            "created_by": created_by,
        }
        result = await session.execute(sql, params)
        row_was_inserted = result.scalar()
        if row_was_inserted:
            inserted += 1
        else:
            updated += 1

    await session.commit()
    log.info("de_para_upsert_done", inserted=inserted, updated=updated)
    return {"inserted": inserted, "updated": updated}


async def load_de_para_from_excel(
    session: AsyncSession,
    file_path: str | Path,
    sheet_name: str | int = 0,
    created_by: str = "etl",
) -> dict[str, Any]:
    """
    Carrega uma planilha Excel de de-para para o banco.
    Ponto de entrada principal deste módulo.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    log.info("de_para_excel_loading", file=str(file_path))
    df_raw = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")

    df_clean = validate_dataframe(df_raw, source_file=file_path.name)
    counts = await upsert_de_para(session, df_clean, created_by=created_by)

    # Marca produtos como "needs_cleanup" para que o transform_flow os re-processe
    await session.execute(text(
        "UPDATE dim_product SET needs_cleanup = TRUE "
        "WHERE is_active = TRUE"
    ))
    await session.commit()

    return {
        "file": str(file_path),
        "rows_in_excel": len(df_raw),
        "rows_processed": len(df_clean),
        **counts,
    }
