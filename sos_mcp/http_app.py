"""Modo HTTP (streamable-http) com uma chave simples, para hospedar o servidor numa máquina/nuvem."""

from __future__ import annotations

import hmac
import inspect
import sys

import uvicorn


class KeyMiddleware:
    """Exige `Authorization: Bearer <SOS_MCP_KEY>` ou `?key=<SOS_MCP_KEY>` em toda requisição."""

    def __init__(self, app, key: str):
        self.app, self.key = app, key.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"")
            given = auth[7:] if auth.lower().startswith(b"bearer ") else b""
            if not given:
                from urllib.parse import parse_qs
                given = (parse_qs(scope.get("query_string", b"").decode()).get("key") or [""])[0].encode()
            if not hmac.compare_digest(given, self.key):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
                await send({"type": "http.response.body", "body": "chave invalida".encode()})
                return
        await self.app(scope, receive, send)


def build_app(server, key: str | None, host: str = "127.0.0.1"):
    params = inspect.signature(server.streamable_http_app).parameters
    if params:  # mcp 2.x
        kw = {"stateless_http": True}
        if "host" in params:
            kw["host"] = host
        app = server.streamable_http_app(**kw)
    else:  # mcp 1.x
        server.settings.stateless_http = True
        server.settings.host = host
        app = server.streamable_http_app()
    return KeyMiddleware(app, key) if key else app


def serve_http(server, host: str, port: int, key: str | None) -> None:
    local = host in ("127.0.0.1", "localhost", "::1")
    if not key and not local:
        sys.exit("Defina SOS_MCP_KEY antes de abrir o servidor fora do localhost (os dados da empresa ficariam expostos).")
    uvicorn.run(build_app(server, key, host), host=host, port=port, log_level="info")
