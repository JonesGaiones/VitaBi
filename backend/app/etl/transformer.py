"""
Transformação dos dados brutos do QuickBooks para o star schema.

Fluxo:
1. Lê arquivos raw JSONL (dump do QB)
2. Para cada entidade (Customer, Item, Invoice), mapeia para as tabelas dim/fact
3. Para itens, aplica a lógica de de-para:
    a. Busca match exato primeiro
    b. Depois 'contains' (por priority ASC)
    c. Por último 'regex' (por priority ASC)
    d. Se nada bate, mantém raw e flaga needs_cleanup = TRUE
4. Faz UPSERT em dim_* e INSERT em fact_sales
5. Retorna stats para observabilidade
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


# ============================================================================
# DE-PARA RESOLVER
# ============================================================================

@dataclass
class DeParaRule:
    qb_raw_pattern: str
    match_type: str
    clean_name: str
    category: str
    subcategory: str | None
    brand: str | None
    unit_of_measure: str | None
    pack_size: float | None
    priority: int
    _compiled_regex: re.Pattern | None = None

    def matches(self, raw_name: str) -> bool:
        if self.match_type == "exact":
            return raw_name.strip().lower() == self.qb_raw_pattern.strip().lower()
        if self.match_type == "contains":
            return self.qb_raw_pattern.lower() in raw_name.lower()
        if self.match_type == "regex":
            if self._compiled_regex is None:
                self._compiled_regex = re.compile(self.qb_raw_pattern, re.IGNORECASE)
            return bool(self._compiled_regex.search(raw_name))
        return False


class DeParaResolver:
    """
    Carrega todas as regras ativas em memória (são poucas — ~centenas)
    e resolve raw_name → clean attributes.
    Ordem de prioridade:
        1. match_type = exact (sempre vence)
        2. match_type = contains, por priority ASC
        3. match_type = regex, por priority ASC
    """

    def __init__(self) -> None:
        self._rules_exact: dict[str, DeParaRule] = {}
        self._rules_contains: list[DeParaRule] = []
        self._rules_regex: list[DeParaRule] = []

    async def load(self, session: AsyncSession) -> None:
        result = await session.execute(text("""
            SELECT qb_raw_pattern, match_type, clean_name, category, subcategory,
                   brand, unit_of_measure, pack_size, priority
            FROM dim_de_para
            WHERE active = TRUE
            ORDER BY priority ASC
        """))
        for row in result.mappings():
            rule = DeParaRule(
                qb_raw_pattern=row["qb_raw_pattern"],
                match_type=row["match_type"],
                clean_name=row["clean_name"],
                category=row["category"],
                subcategory=row["subcategory"],
                brand=row["brand"],
                unit_of_measure=row["unit_of_measure"],
                pack_size=float(row["pack_size"]) if row["pack_size"] else None,
                priority=row["priority"],
            )
            if rule.match_type == "exact":
                self._rules_exact[rule.qb_raw_pattern.strip().lower()] = rule
            elif rule.match_type == "contains":
                self._rules_contains.append(rule)
            else:
                self._rules_regex.append(rule)

        log.info(
            "de_para_loaded",
            exact=len(self._rules_exact),
            contains=len(self._rules_contains),
            regex=len(self._rules_regex),
        )

    def resolve(self, raw_name: str) -> DeParaRule | None:
        if not raw_name:
            return None
        # 1. exact
        hit = self._rules_exact.get(raw_name.strip().lower())
        if hit:
            return hit
        # 2. contains
        for rule in self._rules_contains:
            if rule.matches(raw_name):
                return rule
        # 3. regex
        for rule in self._rules_regex:
            if rule.matches(raw_name):
                return rule
        return None


# ============================================================================
# TRANSFORMERS POR ENTIDADE
# ============================================================================

async def transform_customers(session: AsyncSession, jsonl_path: Path) -> int:
    """Customer do QB → dim_customer (UPSERT por qb_customer_id)."""
    sql = text("""
        INSERT INTO dim_customer (
            qb_customer_id, name, display_name, email, phone,
            billing_address, shipping_address, city, state, country,
            is_active, qb_sync_at, updated_at
        )
        VALUES (
            :qb_customer_id, :name, :display_name, :email, :phone,
            :billing_address, :shipping_address, :city, :state, :country,
            :is_active, NOW(), NOW()
        )
        ON CONFLICT (qb_customer_id) DO UPDATE SET
            name             = EXCLUDED.name,
            display_name     = EXCLUDED.display_name,
            email            = EXCLUDED.email,
            phone            = EXCLUDED.phone,
            billing_address  = EXCLUDED.billing_address,
            shipping_address = EXCLUDED.shipping_address,
            city             = EXCLUDED.city,
            state            = EXCLUDED.state,
            country          = EXCLUDED.country,
            is_active        = EXCLUDED.is_active,
            qb_sync_at       = NOW(),
            updated_at       = NOW()
    """)

    count = 0
    for rec in _iter_jsonl(jsonl_path):
        billing = rec.get("BillAddr") or {}
        shipping = rec.get("ShipAddr") or {}
        await session.execute(sql, {
            "qb_customer_id": rec["Id"],
            "name": rec.get("CompanyName") or rec.get("DisplayName") or "",
            "display_name": rec.get("DisplayName"),
            "email": (rec.get("PrimaryEmailAddr") or {}).get("Address"),
            "phone": (rec.get("PrimaryPhone") or {}).get("FreeFormNumber"),
            "billing_address": json.dumps(billing) if billing else None,
            "shipping_address": json.dumps(shipping) if shipping else None,
            "city": billing.get("City"),
            "state": billing.get("CountrySubDivisionCode"),
            "country": billing.get("Country", "BR"),
            "is_active": rec.get("Active", True),
        })
        count += 1

    await session.commit()
    log.info("transform_customers_done", rows=count)
    return count


async def transform_products(
    session: AsyncSession,
    jsonl_path: Path,
    resolver: DeParaResolver,
) -> dict[str, int]:
    """
    Item do QB → dim_product, aplicando de-para.
    Se não há match no de-para, marca needs_cleanup = TRUE.
    """
    sql = text("""
        INSERT INTO dim_product (
            qb_item_id, qb_raw_name, clean_name, category, subcategory,
            brand, unit_of_measure, pack_size, is_active, needs_cleanup,
            qb_sync_at, updated_at
        )
        VALUES (
            :qb_item_id, :qb_raw_name, :clean_name, :category, :subcategory,
            :brand, :unit_of_measure, :pack_size, :is_active, :needs_cleanup,
            NOW(), NOW()
        )
        ON CONFLICT (qb_item_id) DO UPDATE SET
            qb_raw_name      = EXCLUDED.qb_raw_name,
            clean_name       = EXCLUDED.clean_name,
            category         = EXCLUDED.category,
            subcategory      = EXCLUDED.subcategory,
            brand            = EXCLUDED.brand,
            unit_of_measure  = EXCLUDED.unit_of_measure,
            pack_size        = EXCLUDED.pack_size,
            is_active        = EXCLUDED.is_active,
            needs_cleanup    = EXCLUDED.needs_cleanup,
            qb_sync_at       = NOW(),
            updated_at       = NOW()
    """)

    matched = unmatched = 0
    for rec in _iter_jsonl(jsonl_path):
        raw_name = rec.get("Name") or rec.get("FullyQualifiedName") or ""
        fqn = rec.get("FullyQualifiedName") or ""
        description = rec.get("Description") or ""

        # Tenta várias variações para bater no De-Para:
        # 1. Description do item (geralmente o nome legível, ex: "Freeze Dried Acai Organic Powder")
        # 2. Nome completo (pode ser código como "9601-0B0-VFI")
        # 3. FullyQualifiedName sem prefixo de categoria (ex: "Finished Goods:9601-..." → "9601-...")
        # 4. FQN completo
        fqn_short = fqn.split(":")[-1].strip() if ":" in fqn else fqn

        rule = (
            resolver.resolve(description)   # Prioriza descrição legível
            or resolver.resolve(raw_name)
            or resolver.resolve(fqn_short)
            or resolver.resolve(fqn)
        )

        if rule:
            clean_name = rule.clean_name
            category = rule.category
            subcategory = rule.subcategory
            brand = rule.brand
            uom = rule.unit_of_measure
            pack = rule.pack_size
            needs_cleanup = False
            matched += 1
        else:
            # Fallback: usar Description (nome legível do produto) ao invés
            # do código bruto (Name). Ex: "Freeze Dried Acai Powder" vs "9601-0B0-VFI"
            clean_name = description if description else raw_name
            category = "UNCATEGORIZED"
            subcategory = None
            brand = None
            uom = None
            pack = None
            needs_cleanup = True
            unmatched += 1

        await session.execute(sql, {
            "qb_item_id": rec["Id"],
            "qb_raw_name": raw_name,
            "clean_name": clean_name,
            "category": category,
            "subcategory": subcategory,
            "brand": brand,
            "unit_of_measure": uom,
            "pack_size": pack,
            "is_active": rec.get("Active", True),
            "needs_cleanup": needs_cleanup,
        })

    await session.commit()
    log.info("transform_products_done", matched=matched, unmatched=unmatched)
    return {"matched": matched, "unmatched": unmatched}


async def transform_invoices(
    session: AsyncSession,
    invoices_path: Path,
    resolver: Optional[DeParaResolver] = None,
) -> int:
    """
    Invoice do QB → fact_sales (1 linha por line-item).
    Usa UPSERT na chave (qb_invoice_id, qb_line_id, date_key).
    """
    sql = text("""
        INSERT INTO fact_sales (
            qb_invoice_id, qb_line_id, date_key,
            customer_id, product_id, salesperson_id,
            quantity, unit_price, discount_pct, discount_amount,
            revenue, cost, margin, margin_pct,
            invoice_status, payment_date, raw_payload
        )
        SELECT
            :qb_invoice_id, :qb_line_id, :date_key,
            c.customer_id, p.product_id, NULL,
            :quantity, :unit_price, :discount_pct, :discount_amount,
            :revenue,
            :quantity * COALESCE(p.base_cost, 0),
            :revenue - (:quantity * COALESCE(p.base_cost, 0)),
            CASE WHEN :revenue > 0
                 THEN (:revenue - (:quantity * COALESCE(p.base_cost, 0))) / :revenue
                 ELSE 0 END,
            :invoice_status, :payment_date, :raw_payload
        FROM dim_customer c, dim_product p
        WHERE c.qb_customer_id = :qb_customer_id
          AND (
              (:clean_name IS NOT NULL AND p.clean_name = :clean_name)
              OR
              (:clean_name IS NULL AND p.qb_item_id = :qb_item_id)
          )
        ORDER BY (p.clean_name = :clean_name) DESC
        LIMIT 1
        ON CONFLICT (qb_invoice_id, qb_line_id, date_key) DO UPDATE SET
            quantity        = EXCLUDED.quantity,
            unit_price      = EXCLUDED.unit_price,
            discount_pct    = EXCLUDED.discount_pct,
            discount_amount = EXCLUDED.discount_amount,
            revenue         = EXCLUDED.revenue,
            cost            = EXCLUDED.cost,
            margin          = EXCLUDED.margin,
            margin_pct      = EXCLUDED.margin_pct,
            invoice_status  = EXCLUDED.invoice_status,
            payment_date    = EXCLUDED.payment_date,
            raw_payload     = EXCLUDED.raw_payload
    """)

    count = 0
    for invoice in _iter_jsonl(invoices_path):
        invoice_id = invoice["Id"]
        date_key_raw = invoice.get("TxnDate")
        date_key = datetime.date.fromisoformat(date_key_raw) if date_key_raw else None
        customer_ref = (invoice.get("CustomerRef") or {}).get("value")
        status = "paid" if invoice.get("Balance", 0) == 0 else "pending"
        payment_date_raw = invoice.get("MetaData", {}).get("LastUpdatedTime", "")[:10] \
            if status == "paid" else None
        payment_date = datetime.date.fromisoformat(payment_date_raw) if payment_date_raw else None

        for line in invoice.get("Line", []):
            if line.get("DetailType") != "SalesItemLineDetail":
                continue
            detail = line.get("SalesItemLineDetail", {})
            description = line.get("Description", "")
            item_ref = (detail.get("ItemRef") or {}).get("value")
            
            # 1. Tentar resolver pela descrição primeiro (especialmente se o item for genérico como 'SALES')
            # ou se não temos o item_ref (raro no QB, mas possível em ajustes)
            rule = resolver.resolve(description) if resolver else None
            
            # 2. Se temos uma regra, buscamos o product_id desse Clean Name
            # (assume-se que transform_products já criou ou criará esse registro limpo)
            qty = float(detail.get("Qty", 0))
            unit_price = float(detail.get("UnitPrice", 0))
            amount = float(line.get("Amount", 0))
            discount_pct = float(detail.get("DiscountRate", 0))
            discount_amount = (qty * unit_price) - amount if qty * unit_price > amount else 0

            await session.execute(sql, {
                "qb_invoice_id": invoice_id,
                "qb_line_id": line.get("Id", "0"),
                "date_key": date_key,
                "qb_customer_id": customer_ref,
                "qb_item_id": item_ref,
                "clean_name": rule.clean_name if rule else None,
                "quantity": qty,
                "unit_price": unit_price,
                "discount_pct": discount_pct,
                "discount_amount": discount_amount,
                "revenue": amount,
                "invoice_status": status,
                "payment_date": payment_date,
                "raw_payload": json.dumps(line),
            })
            count += 1

    await session.commit()
    log.info("transform_invoices_done", lines=count)
    return count


# ============================================================================
# UTIL
# ============================================================================

def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


# ============================================================================
# ORQUESTRAÇÃO
# ============================================================================

async def run_full_transform(
    session: AsyncSession,
    raw_dir: Path,
) -> dict:
    """
    Orquestra a transformação completa a partir do diretório de raws mais recente.
    Chamado pelo Prefect flow `transform_flow`.
    """
    resolver = DeParaResolver()
    await resolver.load(session)

    stats: dict = {}

    customers_file = _latest(raw_dir, "qb_customer_")
    if customers_file:
        stats["customers"] = await transform_customers(session, customers_file)

    items_file = _latest(raw_dir, "qb_item_")
    if items_file:
        stats["products"] = await transform_products(session, items_file, resolver)

    invoices_file = _latest(raw_dir, "qb_invoice_")
    if invoices_file:
        stats["sales"] = await transform_invoices(session, invoices_file, resolver)
        # Aplica De-Para usando as descrições das faturas para corrigir dim_product
        stats["product_name_fixes"] = await fix_product_names_from_invoices(
            session, invoices_file, resolver
        )

    # Refresh das MVs
    await session.execute(text("SELECT refresh_all_materialized_views()"))
    await session.commit()

    log.info("transform_full_done", **stats)
    return stats


async def fix_product_names_from_invoices(
    session: AsyncSession,
    invoices_path: Path,
    resolver: DeParaResolver,
) -> dict:
    """
    Lê as faturas e constrói um mapa {item_id → melhor_descrição}.
    Usa o De-Para para resolver a descrição em um clean_name e
    atualiza dim_product diretamente.

    Isso resolve o caso where o QB Item usa código (ex: 9601-0B0-VFI)
    mas as faturas têm a descrição legível (ex: Freeze Dried Acai Organic Powder).
    """
    # 1. Construir mapa item_id → descrição mais frequente / mais longa
    item_descriptions: dict[str, str] = {}
    item_desc_count: dict[str, dict[str, int]] = {}

    for invoice in _iter_jsonl(invoices_path):
        for line in invoice.get("Line", []):
            if line.get("DetailType") != "SalesItemLineDetail":
                continue
            detail = line.get("SalesItemLineDetail", {})
            item_id = (detail.get("ItemRef") or {}).get("value")
            description = line.get("Description", "").strip()

            if not item_id or not description or len(description) < 5:
                continue

            # Conta frequência de cada descrição por item_id
            if item_id not in item_desc_count:
                item_desc_count[item_id] = {}
            item_desc_count[item_id][description] = (
                item_desc_count[item_id].get(description, 0) + 1
            )

    # Escolhe a descrição mais frequente para cada item_id
    for item_id, desc_counts in item_desc_count.items():
        best = max(desc_counts, key=lambda d: (desc_counts[d], len(d)))
        item_descriptions[item_id] = best

    # 2. Para cada item_id com descrição, resolver com De-Para e atualizar dim_product
    fixed = skipped = 0
    update_sql = text("""
        UPDATE dim_product
        SET clean_name      = :clean_name,
            category        = :category,
            subcategory     = COALESCE(:subcategory, subcategory),
            brand           = COALESCE(:brand, brand),
            unit_of_measure = COALESCE(:uom, unit_of_measure),
            pack_size       = COALESCE(:pack_size, pack_size),
            needs_cleanup   = FALSE,
            updated_at      = NOW()
        WHERE qb_item_id = :item_id
          AND needs_cleanup = TRUE
    """)

    for item_id, description in item_descriptions.items():
        rule = resolver.resolve(description)
        if rule:
            await session.execute(update_sql, {
                "item_id": item_id,
                "clean_name": rule.clean_name,
                "category": rule.category,
                "subcategory": rule.subcategory,
                "brand": rule.brand,
                "uom": rule.unit_of_measure,
                "pack_size": rule.pack_size,
            })
            fixed += 1
        else:
            skipped += 1

    await session.commit()
    log.info("fix_product_names_done", fixed=fixed, skipped=skipped)
    return {"fixed": fixed, "skipped": skipped}


def _latest(dir_path: Path, prefix: str) -> Path | None:
    files = sorted(dir_path.glob(f"{prefix}*.jsonl"), reverse=True)
    return files[0] if files else None
