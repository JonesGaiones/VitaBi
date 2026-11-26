"""Escrita no SOS com segurança: prévia obrigatória, confirmação, backup e log.

Cada alteração é feita em duas chamadas da mesma ferramenta:
  1. Sem `confirm_token`: devolve a PRÉVIA (o que muda, campo a campo) e um `confirm_token`.
  2. Com o `confirm_token` da prévia e os MESMOS argumentos: grava um backup JSON do registro,
     faz a alteração e registra no log.
O token muda se os argumentos mudarem ou se o registro for alterado por outra pessoa entre
a prévia e a confirmação (syncToken), então nada é gravado "às cegas".

Desligue toda a escrita com SOS_MCP_READONLY=1.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

from .client import SOSClient, SOSError

# Entidades em que se pode atualizar (PUT) um registro inteiro, um por vez.
UPDATABLE = ("item", "invoice", "salesorder", "estimate", "shipment", "purchaseorder", "process",
             "lot", "customer", "vendor", "adjustment", "transfer", "workorder", "itemreceipt")
# Entidades em que se pode criar (POST) um registro, um por vez.
CREATABLE = ("item", "adjustment", "transfer", "customer", "vendor")
LINE_KEYS = ("lines", "inputs", "outputs")
# Campos que nunca são alterados à mão.
PROTECTED = ("id", "syncToken")

_SALT = secrets.token_bytes(16)  # muda a cada vez que o servidor sobe


def readonly() -> bool:
    return os.environ.get("SOS_MCP_READONLY", "").lower() in ("1", "true", "yes", "sim")


def backup_dir() -> Path:
    p = os.environ.get("SOS_BACKUP_DIR")
    if p:
        return Path(p).expanduser()
    shared = Path("/mnt/project-files/sos/backup-2026-10-04")
    if shared.is_dir():
        return shared / "mcp"
    return Path.home() / ".local" / "share" / "sos-mcp" / "backups"


def log_file() -> Path:
    p = os.environ.get("SOS_WRITE_LOG")
    if p:
        return Path(p).expanduser()
    shared = Path("/mnt/project-files/sos")
    return shared / "sos-mcp-escritas.jsonl" if shared.is_dir() else backup_dir() / "escritas.jsonl"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _token(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str).encode()
    return hmac.new(_SALT, raw, hashlib.sha256).hexdigest()[:16]


def _backup(entity: str, rid: Any, record: Any, action: str) -> str:
    d = backup_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{entity}-{rid}-antes-{action}-{_now()}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
    return str(path)


def _log(entry: dict) -> None:
    path = log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps({"ts": _now(), **entry}, ensure_ascii=False, default=str) + "\n")


def _diff(old: Any, new: Any, prefix: str = "") -> list[dict]:
    out: list[dict] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            out += _diff(old.get(k), new.get(k), f"{prefix}.{k}" if prefix else k)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for i, (a, b) in enumerate(zip(old, new)):
            out += _diff(a, b, f"{prefix}[{i}]")
    elif old != new:
        out.append({"campo": prefix, "antes": old, "depois": new})
    return out


def _guard():
    if readonly():
        raise SOSError("Escrita desligada neste servidor (SOS_MCP_READONLY=1).")


def _apply(record: dict, changes: dict | None, line_changes: list[dict] | None) -> dict:
    new = copy.deepcopy(record)
    for k, v in (changes or {}).items():
        if k in PROTECTED:
            raise SOSError(f"O campo {k} não pode ser alterado.")
        if k in LINE_KEYS:
            raise SOSError(f"Para mudar {k}, use line_changes (uma linha por vez, pelo id da linha).")
        if isinstance(v, dict) and isinstance(new.get(k), dict) and k != "customFields":
            new[k] = {**new[k], **v}  # ex.: {"category": {"id": 137}} mantém o resto
        else:
            new[k] = v
    for lc in line_changes or []:
        key, lid, fields = lc.get("list", "lines"), lc.get("line_id"), lc.get("fields") or {}
        if key not in LINE_KEYS:
            raise SOSError(f"list deve ser um de {LINE_KEYS}.")
        lines = new.get(key) or []
        match = [l for l in lines if l.get("id") == lid]
        if len(match) != 1:
            raise SOSError(f"Linha id={lid} não encontrada em {key}.")
        for fk, fv in fields.items():
            if fk == "id":
                raise SOSError("O id da linha não pode ser alterado.")
            match[0][fk] = {**match[0][fk], **fv} if isinstance(fv, dict) and isinstance(match[0].get(fk), dict) else fv
    return new


def update(c: SOSClient, entity: str, rid: int, changes: dict | None, line_changes: list[dict] | None,
           confirm_token: str | None, reason: str | None) -> dict:
    _guard()
    if entity not in UPDATABLE:
        raise SOSError(f"Atualização não permitida em {entity}. Permitidas: {', '.join(UPDATABLE)}.")
    if not changes and not line_changes:
        raise SOSError("Nada para mudar: informe changes e/ou line_changes.")
    current = c.get(f"{entity}/{int(rid)}").get("data")
    if not current:
        raise SOSError(f"{entity} {rid} não encontrado.")
    new = _apply(current, changes, line_changes)
    diff = _diff(current, new)
    tok = _token("update", entity, rid, changes, line_changes, current.get("syncToken"))
    head = {"entidade": entity, "id": rid, "numero": current.get("number") or current.get("name"),
            "mudancas": diff}
    if not confirm_token:
        return {**head, "status": "PRÉVIA, nada foi gravado",
                "confirm_token": tok,
                "proximo_passo": "Mostre a prévia ao usuário. Se ele aprovar, chame de novo com os mesmos argumentos e este confirm_token."}
    if not hmac.compare_digest(confirm_token, tok):
        raise SOSError("confirm_token não confere (argumentos diferentes da prévia, registro mudou ou "
                       "o servidor reiniciou). Faça a prévia de novo.")
    if not diff:
        return {**head, "status": "Nada mudou, nada foi gravado."}
    bkp = _backup(entity, rid, current, "update")
    try:
        r = c.send("PUT", f"{entity}/{int(rid)}", new)
    except SOSError as e:
        _log({"acao": "update", "entidade": entity, "id": rid, "ok": False, "erro": str(e), "backup": bkp, "motivo": reason})
        raise
    _log({"acao": "update", "entidade": entity, "id": rid, "ok": True, "mudancas": diff, "backup": bkp, "motivo": reason})
    return {**head, "status": "GRAVADO", "backup": bkp, "resposta": (r or {}).get("status") or "ok"}


def create(c: SOSClient, entity: str, data: dict, confirm_token: str | None, reason: str | None) -> dict:
    _guard()
    if entity not in CREATABLE:
        raise SOSError(f"Criação não permitida em {entity}. Permitidas: {', '.join(CREATABLE)}.")
    if not data:
        raise SOSError("Informe os dados do registro em data.")
    data = dict(data)
    if entity == "item" and "salesPrice" in data and "useMarkup" not in data:
        data["useMarkup"] = False  # senão o SOS ignora o salesPrice
    tok = _token("create", entity, data)
    if not confirm_token:
        return {"entidade": entity, "status": "PRÉVIA, nada foi gravado", "sera_criado": data,
                "confirm_token": tok,
                "proximo_passo": "Mostre a prévia ao usuário. Se ele aprovar, chame de novo com os mesmos argumentos e este confirm_token."}
    if not hmac.compare_digest(confirm_token, tok):
        raise SOSError("confirm_token não confere com a prévia. Faça a prévia de novo.")
    try:
        r = c.send("POST", entity, data)
    except SOSError as e:
        _log({"acao": "create", "entidade": entity, "ok": False, "erro": str(e), "dados": data, "motivo": reason})
        raise
    rec = (r or {}).get("data") or {}
    _log({"acao": "create", "entidade": entity, "ok": True, "id": rec.get("id"), "dados": data, "motivo": reason})
    return {"entidade": entity, "status": "CRIADO", "id": rec.get("id"),
            "numero": rec.get("number") or rec.get("name")}


def delete_item(c: SOSClient, item_id: int, confirm_token: str | None, reason: str | None) -> dict:
    """Exclusão lógica de item: o SOS põe "(deleted)" no nome e mantém o histórico."""
    _guard()
    current = c.get(f"item/{int(item_id)}").get("data")
    if not current:
        raise SOSError(f"Item {item_id} não encontrado.")
    tok = _token("delete", "item", item_id, current.get("syncToken"))
    head = {"entidade": "item", "id": item_id, "nome": current.get("name"),
            "descricao": current.get("description"), "saldo": current.get("onhand")}
    if not confirm_token:
        return {**head, "status": "PRÉVIA, nada foi gravado", "confirm_token": tok,
                "aviso": "Exclusão lógica: o item some do uso, o nome ganha '(deleted)' e o histórico fica. "
                         "O SOS recusa se houver saldo diferente de zero em alguma location.",
                "proximo_passo": "Só confirme se o usuário pediu explicitamente para excluir este item."}
    if not hmac.compare_digest(confirm_token, tok):
        raise SOSError("confirm_token não confere com a prévia. Faça a prévia de novo.")
    bkp = _backup("item", item_id, current, "delete")
    try:
        r = c.send("DELETE", f"item/{int(item_id)}")
    except SOSError as e:
        _log({"acao": "delete", "entidade": "item", "id": item_id, "ok": False, "erro": str(e), "backup": bkp, "motivo": reason})
        raise
    _log({"acao": "delete", "entidade": "item", "id": item_id, "ok": True, "backup": bkp, "motivo": reason})
    return {**head, "status": "EXCLUÍDO (lógico)", "backup": bkp, "resposta": (r or {}).get("status") or "ok"}
