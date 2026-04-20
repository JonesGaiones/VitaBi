"""
Cliente para a API do QuickBooks Online.

Responsabilidades:
- Refresh automático do OAuth2 token
- Paginação de queries (QB limita a 1000 rows/página)
- Retry com backoff exponencial em 429/5xx
- Serialização para formato raw (JSONL) em data/raw/
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger()


@dataclass
class QBToken:
    access_token: str
    refresh_token: str
    expires_at: datetime


class QuickBooksClient:
    """
    Cliente assíncrono da API Online do QuickBooks.
    Usa o endpoint /v3/company/{realmId}/query com QBQL.
    """

    MINOR_VERSION = 69  # versão da API
    PAGE_SIZE = 1000

    def __init__(self) -> None:
        self.base_url = settings.QB_BASE_URL
        self.realm_id = settings.QB_REALM_ID
        self._token: QBToken | None = None
        self._client = httpx.AsyncClient(timeout=60.0)

    # ----------------------------------------------------------------
    # OAuth2
    # ----------------------------------------------------------------
    async def _refresh_token(self) -> QBToken:
        """Troca o refresh_token por um novo access_token."""
        url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
        auth = (settings.QB_CLIENT_ID, settings.QB_CLIENT_SECRET)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": settings.QB_REFRESH_TOKEN,
        }
        resp = await self._client.post(url, auth=auth, data=data)
        resp.raise_for_status()
        payload = resp.json()

        token = QBToken(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_at=datetime.now(timezone.utc).replace(microsecond=0)
                       .fromtimestamp(
                           datetime.now(timezone.utc).timestamp() + payload["expires_in"] - 60,
                           tz=timezone.utc,
                       ),
        )
        self._token = token
        log.info("qb_token_refreshed", expires_at=token.expires_at.isoformat())
        return token

    async def _get_token(self) -> QBToken:
        if self._token is None or self._token.expires_at < datetime.now(timezone.utc):
            return await self._refresh_token()
        return self._token

    # ----------------------------------------------------------------
    # Query engine
    # ----------------------------------------------------------------
    async def _raw_query(self, qbql: str, start_position: int = 1) -> dict[str, Any]:
        """
        Executa uma query QBQL (QuickBooks Query Language).
        Aplica retry em 429/5xx.
        """
        token = await self._get_token()
        url = f"{self.base_url}/v3/company/{self.realm_id}/query"
        params = {"query": qbql, "minorversion": self.MINOR_VERSION}
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
        }

        for attempt in range(5):
            resp = await self._client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401:
                # token expirou antes da hora — força refresh
                await self._refresh_token()
                token = self._token
                headers["Authorization"] = f"Bearer {token.access_token}"
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                backoff = 2 ** attempt
                log.warning(
                    "qb_retry",
                    status=resp.status_code,
                    attempt=attempt,
                    backoff_s=backoff,
                )
                await asyncio.sleep(backoff)
                continue
            resp.raise_for_status()

        raise RuntimeError(f"QB query failed after 5 retries: {qbql[:100]}")

    async def query_all(self, entity: str, where: str | None = None) -> AsyncIterator[dict]:
        """
        Pagina sobre todos os registros de uma entidade (Customer, Item, Invoice, etc.)
        e rende objeto por objeto.
        """
        start = 1
        while True:
            qbql = f"SELECT * FROM {entity}"
            if where:
                qbql += f" WHERE {where}"
            qbql += f" STARTPOSITION {start} MAXRESULTS {self.PAGE_SIZE}"

            payload = await self._raw_query(qbql)
            records = payload.get("QueryResponse", {}).get(entity, [])
            if not records:
                break

            for rec in records:
                yield rec

            if len(records) < self.PAGE_SIZE:
                break
            start += self.PAGE_SIZE

    # ----------------------------------------------------------------
    # Dump raw para arquivo (para replay e auditoria)
    # ----------------------------------------------------------------
    async def dump_entity_jsonl(
        self,
        entity: str,
        output_dir: str | Path,
        where: str | None = None,
    ) -> Path:
        """
        Salva todos os registros de `entity` num arquivo JSONL.
        Retorna o path do arquivo.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = output_dir / f"qb_{entity.lower()}_{timestamp}.jsonl"

        count = 0
        with out_file.open("w", encoding="utf-8") as f:
            async for rec in self.query_all(entity, where=where):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1

        log.info("qb_dump_complete", entity=entity, rows=count, file=str(out_file))
        return out_file

    async def close(self) -> None:
        await self._client.aclose()
