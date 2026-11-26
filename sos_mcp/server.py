"""Ferramentas MCP (somente leitura) para o SOS Inventory."""

from __future__ import annotations

import os
from typing import Any, Literal

import anyio

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
from mcp.types import ToolAnnotations

from .client import SOSClient, SOSError

# Filtros aceitos pela API em cada entidade (da documentação do developer.sosinventory.com).
# Comuns a quase todas: query, archived, createdsince, updatedsince.
DATE = ("from", "to")
FILTERS: dict[str, tuple[str, ...]] = {
    "item": ("query", "archived", "sku", "type", "ids", "location", "category", "tags"),
    "lot": ("query", "status", "archived", "location"),
    "serial": ("query", "location", "itemId", "status"),
    "location": ("query",),
    "process": ("query", "archived", "location", *DATE, "summary"),
    "workorder": ("query", "status", "archived", *DATE, "summary"),
    "build": ("query", "archived", "location", *DATE, "summary"),
    "adjustment": ("query", "archived", "status", "location", *DATE, "summary"),
    "transfer": ("query", "archived", "status", "fromLocation", "toLocation", *DATE),
    "estimate": ("query", "status", "archived", "channel", *DATE, "summary"),
    "salesorder": ("query", "status", "archived", "location", "channel", "orderStage", *DATE, "summary"),
    "shipment": ("query", "archived", "location", "customerId", *DATE, "summary"),
    "invoice": ("query", "status", "archived", *DATE, "summary"),
    "salesreceipt": ("query", "status", "archived", "location", "channel", "orderStage", *DATE, "summary"),
    "pickticket": ("query", "status", "archived", "location", "channel", *DATE, "summary"),
    "return": ("query", "archived", "location", *DATE, "summary"),
    "rma": ("query", "status", "archived", *DATE, "summary"),
    "purchaseorder": ("query", "status", "archived", *DATE),
    "itemreceipt": ("query", "archived", "location"),
    "returntovendor": ("query", "status", "archived", "location", *DATE),
    "customer": ("query", "name", "email", "archived", "summary"),
    "vendor": ("query", "archived", "summary"),
    "job": ("query", "status", "archived"),
    # tabelas de configuração (poucos registros)
    "class": (), "department": (), "channel": (), "salesrep": (), "terms": (), "uom": (),
    "workcenter": (), "worker": (), "customfield": (), "orderstage": (), "priority": (),
    "pricetier": (), "shipmethod": (), "paymentmethod": (), "taxcode": (), "account": (),
}
Entity = Literal[tuple(FILTERS)]  # type: ignore[valid-type]
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

INSTRUCTIONS = """Acesso SOMENTE LEITURA ao SOS Inventory da Vita Forte (estoque, produção, pedidos).
Fluxo de pedidos: Estimate (nasce no QuickBooks) -> Sales Order -> Shipment -> Invoice.
Produção = entidade `process` (números PRT...): entradas (matéria-prima, código com prefixo R) e saídas (pó, com lote).
Códigos com prefixo W e sem W são o mesmo produto: nunca some os dois como produtos diferentes.
Mostre produtos pela descrição do cadastro do SOS, com o código ao lado.
Datas no formato AAAA-MM-DD. Comece com poucas linhas (max_results pequeno) e use `fields` para respostas enxutas."""

mcp = _Server("sos-inventory", instructions=INSTRUCTIONS)
_client: SOSClient | None = None


def client() -> SOSClient:
    global _client
    if _client is None:
        _client = SOSClient()
    return _client


def _dt(d: str | None, end: bool = False) -> str | None:
    if not d:
        return None
    if "T" in d:
        return d
    return f"{d}T23:59:59" if end else f"{d}T00:00:00"


def _compact(x: Any) -> Any:
    """Remove campos vazios (None, "", [], {}) para a resposta caber no contexto."""
    if isinstance(x, dict):
        out = {k: _compact(v) for k, v in x.items()}
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    if isinstance(x, list):
        return [_compact(v) for v in x]
    return x


def _pick(rec: dict, fields: list[str] | None) -> dict:
    if not fields:
        return rec
    return {f: rec.get(f) for f in fields if f in rec} | ({"id": rec["id"]} if "id" in rec else {})


async def _run(fn, *a, **kw):
    try:
        return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))
    except SOSError as e:
        return {"erro": str(e)}


def _cf(rec: dict, name: str) -> Any:
    for c in rec.get("customFields") or []:
        if c.get("name") == name:
            return c.get("value")
    return None


# ------------------------------------------------------------------ ferramentas

@mcp.tool(annotations=RO)
async def sos_entities() -> dict:
    """Lista as entidades que dá para consultar e os filtros que cada uma aceita.

    Filtros de data `from`/`to` são a data da transação; `updated_since`/`created_since`
    servem para pegar o que mudou. Use em `sos_list` como argumentos ou em `extra_filters`.
    """
    return {"entidades": {k: list(v) + ["createdsince", "updatedsince"] for k, v in FILTERS.items()},
            "somente_leitura": True}


@mcp.tool(annotations=RO)
async def sos_list(
    entity: Entity,
    query: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    location: str | None = None,
    updated_since: str | None = None,
    created_since: str | None = None,
    archived: Literal["yes", "no"] | None = None,
    extra_filters: dict[str, str] | None = None,
    start: int = 0,
    max_results: int = 25,
    all_pages: bool = False,
    fields: list[str] | None = None,
    compact: bool = True,
) -> dict:
    """Lista registros de qualquer entidade do SOS (item, salesorder, invoice, process, lot...).

    - query: texto livre (número do documento, nome do cliente/fornecedor, nome do item etc.).
    - status: ex. "open", "closed" (invoice/estimate/salesorder/purchaseorder/lot...).
    - date_from/date_to: data da transação, AAAA-MM-DD.
    - location: nome da location (ex. "VitaForte", "Diya", "Navitas").
    - extra_filters: outros filtros da API, ex. {"sku": "...", "orderStage": "...", "customerId": "853",
      "category": "...", "type": "...", "ids": "1,2,3", "fromLocation": "...", "toLocation": "..."}.
    - start/max_results: paginação (até 200 por chamada). all_pages=True junta até 2000 registros.
    - fields: lista de campos de topo para devolver (ex. ["number","date","customer","total","status"]).
    - compact: remove campos vazios.
    Veja os filtros válidos por entidade com `sos_entities`.
    """
    params: dict[str, Any] = {
        "query": query, "status": status, "from": _dt(date_from), "to": _dt(date_to, end=True),
        "location": location, "updatedsince": _dt(updated_since), "createdsince": _dt(created_since),
        "archived": archived,
    }
    params.update(extra_filters or {})
    for k in ("start", "maxresults"):
        params.pop(k, None)
    r = await _run(client().list, entity, params, start=max(0, start),
                   max_results=max_results, all_pages=all_pages)
    if "erro" in r:
        return r
    recs = [_pick(x, fields) for x in r["records"]]
    r["records"] = _compact(recs) if compact else recs
    return r


@mcp.tool(annotations=RO)
async def sos_get(entity: Entity, id: int, compact: bool = True) -> dict:
    """Busca um registro completo pelo id interno do SOS (não o número do documento).

    Para achar o id a partir do número (ex. invoice "4095", PRT "PRT1166"), use `sos_list` com query.
    """
    r = await _run(client().get, f"{entity}/{int(id)}")
    if "erro" in r:
        return r
    data = r.get("data", r)
    return _compact(data) if compact else data


@mcp.tool(annotations=RO)
async def sos_search_items(
    text: str | None = None,
    location: str | None = None,
    item_type: str | None = None,
    category: str | None = None,
    include_archived: bool = False,
    max_results: int = 50,
) -> dict:
    """Procura itens no cadastro (por código, nome ou descrição) com estoque e custos resumidos.

    Com `location`, as quantidades refletem só aquela location. Saldos de estoque do SOS
    ainda não são totalmente confiáveis segundo a empresa: use como indicação.
    """
    params = {"query": text, "location": location, "type": item_type, "category": category,
              "archived": None if include_archived else "no"}
    r = await _run(client().list, "item", params, max_results=max_results)
    if "erro" in r:
        return r
    keep = ("id", "name", "description", "sku", "type", "category", "class", "onhand", "available",
            "onSO", "onPO", "onWO", "committed", "baseUnit", "purchaseCost", "salesPrice", "averageCost",
            "lotTracked", "serialTracked", "archived", "vendor")
    r["records"] = _compact([{k: x.get(k) for k in keep if k in x} for x in r["records"]])
    return r


@mcp.tool(annotations=RO)
async def sos_item_bom(item_id: int) -> dict:
    """Lista de materiais (BOM) de um item montado ou kit (endpoint beta do SOS)."""
    r = await _run(client().get, f"item/{int(item_id)}/bom")
    return _compact(r.get("data", r)) if isinstance(r, dict) else r


def _line(l: dict) -> dict:
    it = l.get("item") or {}
    lot = l.get("lot") or {}
    return _compact({
        "item": it.get("name"), "descricao": l.get("description"), "qtd": l.get("quantity"),
        "unidade": (l.get("uom") or {}).get("name"), "lote": lot.get("name"),
        "custo": l.get("cost") or l.get("amount"), "perda": l.get("waste") or None,
    })


@mcp.tool(annotations=RO)
async def sos_production_runs(
    date_from: str,
    date_to: str | None = None,
    location: str | None = None,
    item_contains: str | None = None,
    max_runs: int = 200,
) -> dict:
    """Produções (processos PRT) num período, resumidas: entradas, saídas, lotes, Tank e Labor.

    - item_contains: filtra os PRTs que têm esse texto no código de algum item (ex. "9601" açaí,
      "R9601" suco de açaí). Códigos W e sem W são o mesmo produto.
    - rendimento_kg = soma das saídas (sem perda) / soma das entradas com código R, quando houver.
      É só uma conta rápida: conversões, embalagem e testes também aparecem como processos.
    """
    params = {"from": _dt(date_from), "to": _dt(date_to, end=True), "location": location}
    r = await _run(client().list, "process", params, all_pages=True, cap=max(1, min(max_runs, 2000)))
    if "erro" in r:
        return r
    runs = []
    needle = (item_contains or "").lower()
    for p in sorted(r["records"], key=lambda p: p.get("date") or ""):
        ins, outs = p.get("inputs") or [], p.get("outputs") or []
        names = [((l.get("item") or {}).get("name") or "") for l in ins + outs]
        if needle and not any(needle in n.lower() for n in names):
            continue
        raw = sum(l.get("quantity") or 0 for l in ins if ((l.get("item") or {}).get("name") or "").startswith("R"))
        out = sum(l.get("quantity") or 0 for l in outs if not l.get("waste"))
        runs.append(_compact({
            "id": p.get("id"), "numero": p.get("number"), "data": (p.get("date") or "")[:10],
            "location": (p.get("location") or {}).get("name"), "tank": _cf(p, "Tank"),
            "labor": _cf(p, "Labor"), "brix": _cf(p, "Brix"), "comentario": p.get("comment"),
            "entradas": [_line(l) for l in ins], "saidas": [_line(l) for l in outs],
            "rendimento_kg": round(out / raw, 4) if raw and out > 1 else None,
        }))
    return {"periodo": [date_from, date_to], "processos_lidos": r["count"],
            "truncado": r["truncated"], "runs": runs}


@mcp.tool(annotations=RO)
async def sos_open_orders(
    customer: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    max_results: int = 50,
) -> dict:
    """Pedidos de venda (Sales Orders) em aberto, com linhas, quantidades pedidas/entregues e prazos."""
    params = {"status": "open", "query": customer, "from": _dt(date_from), "to": _dt(date_to, end=True)}
    r = await _run(client().list, "salesorder", params, max_results=max_results)
    if "erro" in r:
        return r
    out = []
    for so in r["records"]:
        lines = []
        for l in so.get("lines") or []:
            it = l.get("item") or {}
            lines.append(_compact({
                "item": it.get("name"), "descricao": l.get("description"), "qtd": l.get("quantity"),
                "entregue": l.get("shipped"), "faturado": l.get("invoiced"),
                "preco": l.get("unitprice") or l.get("unitPrice"), "valor": l.get("amount"),
                "prazo": (l.get("duedate") or l.get("dueDate") or "")[:10] or None,
            }))
        out.append(_compact({
            "id": so.get("id"), "numero": so.get("number"), "data": (so.get("date") or "")[:10],
            "cliente": (so.get("customer") or {}).get("name"), "customerPO": so.get("customerPO"),
            "etapa": (so.get("orderStage") or {}).get("name"), "total": so.get("total"),
            "vendedor": (so.get("salesRep") or {}).get("name"), "linhas": lines,
        }))
    return {"totalCount": r["totalCount"], "count": len(out), "pedidos": out}


@mcp.tool(annotations=RO)
async def sos_lots(
    text: str | None = None,
    location: str | None = None,
    status: str | None = None,
    max_results: int = 50,
) -> dict:
    """Lotes (ex. lotes de suco OFAIVF258 ou de pó), com item, quantidade e validade."""
    r = await _run(client().list, "lot", {"query": text, "location": location, "status": status},
                   max_results=max_results)
    if "erro" in r:
        return r
    r["records"] = _compact(r["records"])
    return r


# ------------------------------------------------------------------ execução

def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    if transport == "stdio":
        mcp.run("stdio")
        return
    from .http_app import serve_http
    serve_http(mcp, host=host, port=port, key=os.environ.get("SOS_MCP_KEY"))
