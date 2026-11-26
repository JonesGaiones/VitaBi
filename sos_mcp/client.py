"""Cliente somente leitura da API do SOS Inventory (https://api.sosinventory.com/api/v2).

Este módulo só faz GET nos dados. O único POST é para /oauth2/token (trocar o code
ou renovar o token). Não existe código de escrita ou DELETE aqui, de propósito.

De onde vem o token, em ordem:
  1. SOS_ACCESS_TOKEN (variável de ambiente). Vale ~90 dias.
  2. Arquivo de token (SOS_TOKEN_FILE, padrão ~/.config/sos-mcp/token.json, permissão 600),
     criado por `python -m sos_mcp auth`.
  3. SOS_REFRESH_TOKEN (variável de ambiente): troca por um access token ao iniciar.

Renovação automática (em erro 401) usa SOS_CLIENT_ID e SOS_CLIENT_SECRET e grava o
par novo no arquivo de token. Atenção: o SOS troca o refresh token a cada renovação,
então um SOS_REFRESH_TOKEN em variável de ambiente só serve uma vez.
"""

from __future__ import annotations

import json
import os
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("SOS_BASE_URL", "https://api.sosinventory.com")
API = BASE_URL.rstrip("/") + "/api/v2/"
TOKEN_URL = BASE_URL.rstrip("/") + "/oauth2/token"
AUTHORIZE_URL = BASE_URL.rstrip("/") + "/oauth2/authorize"
REDIRECT_URI = os.environ.get("SOS_REDIRECT_URI", "https://localhost/callback")
PAGE = 200  # máximo por página aceito pela API


class SOSError(RuntimeError):
    pass


def token_file() -> Path:
    p = os.environ.get("SOS_TOKEN_FILE")
    return Path(p).expanduser() if p else Path.home() / ".config" / "sos-mcp" / "token.json"


def save_tokens(tok: dict[str, Any]) -> Path:
    """Grava o token só no arquivo local com permissão 600 (nunca em repositório)."""
    path = token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: tok.get(k) for k in ("access_token", "refresh_token", "expires_in", "token_type")}
    if tok.get("expires_in"):
        data["expires_at"] = int(time.time()) + int(tok["expires_in"])
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def _client_creds() -> tuple[str, str]:
    cid, sec = os.environ.get("SOS_CLIENT_ID"), os.environ.get("SOS_CLIENT_SECRET")
    if not cid or not sec:
        raise SOSError("Faltam SOS_CLIENT_ID e SOS_CLIENT_SECRET nas variáveis de ambiente.")
    return cid, sec


def authorize_url() -> str:
    cid, _ = _client_creds()
    q = urllib.parse.urlencode({"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT_URI})
    return f"{AUTHORIZE_URL}?{q}"


def _token_request(form: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as f:
            tok = json.load(f)
    except urllib.error.HTTPError as e:
        raise SOSError(f"OAuth falhou ({e.code}): {e.read().decode(errors='replace')[:300]}") from None
    if "access_token" not in tok:
        raise SOSError(f"Resposta OAuth sem access_token: {str(tok)[:300]}")
    return tok


def exchange_code(code: str) -> dict[str, Any]:
    cid, sec = _client_creds()
    return _token_request({
        "grant_type": "authorization_code", "client_id": cid, "client_secret": sec,
        "code": code, "redirect_uri": REDIRECT_URI,
    })


def refresh(refresh_token: str) -> dict[str, Any]:
    cid, sec = _client_creds()
    return _token_request({
        "grant_type": "refresh_token", "client_id": cid, "client_secret": sec,
        "refresh_token": refresh_token,
    })


class SOSClient:
    """Faz GET na API com paginação, nova tentativa em 429 e renovação do token em 401."""

    def __init__(self, opener=None):
        self._open = opener or urllib.request.urlopen
        self._access: str | None = None
        self._refresh: str | None = None
        self._load()

    # ---- token ----
    def _load(self) -> None:
        self._access = os.environ.get("SOS_ACCESS_TOKEN") or None
        path = token_file()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._access = self._access or data.get("access_token")
                self._refresh = data.get("refresh_token")
            except (OSError, ValueError):
                pass
        self._refresh = self._refresh or os.environ.get("SOS_REFRESH_TOKEN") or None

    def _renew(self) -> bool:
        if not self._refresh:
            return False
        tok = refresh(self._refresh)
        self._access, self._refresh = tok["access_token"], tok.get("refresh_token") or self._refresh
        try:
            save_tokens(tok)
        except OSError:
            pass  # sem disco gravável: segue com o token em memória
        return True

    def _ensure(self) -> None:
        if not self._access and not self._renew():
            raise SOSError(
                "SOS não autorizado. Rode `python -m sos_mcp auth` nesta máquina, "
                "ou defina SOS_ACCESS_TOKEN no ambiente."
            )

    # ---- HTTP ----
    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure()
        clean = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        url = API + path.lstrip("/") + ("?" + urllib.parse.urlencode(clean) if clean else "")
        renewed = False
        for attempt in range(5):
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self._access}", "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            try:
                with self._open(req, timeout=120) as f:
                    return json.load(f)
            except urllib.error.HTTPError as e:
                if e.code == 401 and not renewed and self._renew():
                    renewed = True
                    continue
                if e.code == 429 or e.code >= 500:
                    time.sleep(3 * (attempt + 1))
                    continue
                body = e.read().decode(errors="replace")[:400]
                raise SOSError(f"SOS respondeu {e.code} em GET /{path}: {body}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt == 4:
                    raise SOSError(f"Falha de rede em GET /{path}: {e}") from None
                time.sleep(3 * (attempt + 1))
        raise SOSError(f"SOS não respondeu em GET /{path} depois de várias tentativas.")

    def list(self, entity: str, params: dict[str, Any] | None = None, start: int = 0,
             max_results: int = 50, all_pages: bool = False, cap: int = 2000) -> dict[str, Any]:
        """Lista registros. Com all_pages=True, junta páginas até `cap` registros."""
        params = dict(params or {})
        want = cap if all_pages else max(1, min(max_results, PAGE))
        out: list[dict] = []
        total = None
        pos = start
        while len(out) < want:
            r = self.get(entity, {**params, "start": pos, "maxresults": min(PAGE, want - len(out)) if not all_pages else PAGE})
            data = r.get("data") or []
            total = r.get("totalCount", total)
            out += data
            if not all_pages or len(data) < PAGE or (total is not None and pos + len(data) >= total):
                break
            pos += len(data)
        # a API às vezes repete 1 linha entre páginas: remove duplicados por id
        seen, uniq = set(), []
        for rec in out:
            k = rec.get("id") if isinstance(rec, dict) else None
            if k is None or k not in seen:
                seen.add(k)
                uniq.append(rec)
        uniq = uniq[:want]
        return {"totalCount": total, "start": start, "count": len(uniq), "records": uniq,
                "truncated": bool(all_pages and total and start + len(uniq) < total)}
