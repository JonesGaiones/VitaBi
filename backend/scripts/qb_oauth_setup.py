"""
Fluxo inicial de autorização OAuth2 do QuickBooks Online.

Uso:
    python -m scripts.qb_oauth_setup

O que faz:
1. Abre o browser na URL de autorização do QuickBooks
2. Inicia um servidor HTTP local na porta 8888 para capturar o callback
3. Troca o `code` pelo refresh_token via POST /tokens/bearer
4. Salva QB_REFRESH_TOKEN e QB_REALM_ID nos arquivos .env
"""
from __future__ import annotations

import base64
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
REDIRECT_PORT = 8888
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"

AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SCOPE = "com.intuit.quickbooks.accounting"

# Paths dos .env a serem atualizados
ENV_FILES = [
    Path(__file__).parent.parent.parent / ".env",          # vita_bi/.env
    Path(__file__).parent.parent / ".env",                 # backend/.env
]

# Lê credenciais do ambiente (já devem estar no .env ou passadas manualmente)
CLIENT_ID = os.environ.get("QB_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("QB_CLIENT_SECRET", "")

# ---------------------------------------------------------------------------
# Servidor de callback
# ---------------------------------------------------------------------------
_callback_result: dict | None = None
_server_ready = threading.Event()


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _callback_result
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self._respond(404, "Not found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        realm_id = params.get("realmId", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            _callback_result = {"error": error}
            self._respond(200, f"<h2>Erro: {error}</h2><p>Pode fechar esta aba.</p>")
        elif code and realm_id:
            _callback_result = {"code": code, "realm_id": realm_id}
            self._respond(200, """
                <html><body style="font-family:sans-serif;text-align:center;padding:60px">
                <h2 style="color:#2e7d32">OK Autorização concluída!</h2>
                <p>Pode fechar esta aba e voltar ao terminal.</p>
                </body></html>
            """)
        else:
            _callback_result = {"error": "parametros_faltando"}
            self._respond(400, "Parâmetros inesperados.")

        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _respond(self, code: int, body: str):
        body_bytes = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def log_message(self, *args):
        pass  # silenciar logs do servidor


def _run_server():
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    _server_ready.set()
    server.serve_forever()


# ---------------------------------------------------------------------------
# Troca de código por tokens
# ---------------------------------------------------------------------------
def exchange_code(code: str) -> dict:
    credentials = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Atualiza variável nos arquivos .env
# ---------------------------------------------------------------------------
def update_env(path: Path, key: str, value: str):
    if not path.exists():
        print(f"  !  {path} nao encontrado, pulando.")
        return
    text = path.read_text(encoding="utf-8")
    # Substitui linha existente ou acrescenta
    if f"{key}=" in text:
        lines = text.splitlines()
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                new_lines.append(f"{key}={value}")
            else:
                new_lines.append(line)
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        path.write_text(text.rstrip() + f"\n{key}={value}\n", encoding="utf-8")
    print(f"  OK  {path.name} atualizado ({key})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERRO  QB_CLIENT_ID e QB_CLIENT_SECRET precisam estar no ambiente.")
        print("   Certifique-se de rodar de dentro da pasta backend/ com o .env carregado.")
        sys.exit(1)

    state = secrets.token_urlsafe(16)
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state,
    })
    auth_url = f"{AUTH_URL}?{params}"

    print("\n" + "=" * 60)
    print("  VITA BI — Autorização QuickBooks OAuth2")
    print("=" * 60)
    print(f"\n  Client ID : {CLIENT_ID[:20]}...")
    print(f"  Redirect  : {REDIRECT_URI}")
    print(f"  Escopo    : {SCOPE}")

    # Inicia servidor de callback em background
    t = threading.Thread(target=_run_server, daemon=True)
    t.start()
    _server_ready.wait(timeout=3)

    print("\n  Abrindo browser para autorização...")
    webbrowser.open(auth_url)
    print("\n  [aguardando] Aguardando callback do QuickBooks (porta 8888)...")
    print("     Se o browser nao abrir, acesse manualmente:")
    print(f"     {auth_url}\n")

    t.join(timeout=300)

    if _callback_result is None:
        print("ERRO  Tempo esgotado (5 min). Tente novamente.")
        sys.exit(1)

    if "error" in _callback_result:
        print(f"ERRO  Erro na autorização: {_callback_result['error']}")
        sys.exit(1)

    code = _callback_result["code"]
    realm_id = _callback_result["realm_id"]

    print(f"  OK  Código recebido. Realm ID: {realm_id}")
    print("  Trocando código por tokens...")

    try:
        tokens = exchange_code(code)
    except Exception as e:
        print(f"ERRO  Falha ao obter tokens: {e}")
        sys.exit(1)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(f"ERRO  refresh_token nao retornado. Resposta: {tokens}")
        sys.exit(1)

    print(f"  OK  Tokens obtidos (refresh_token: {refresh_token[:20]}...)")

    print("\n  Salvando nos arquivos .env...")
    for env_path in ENV_FILES:
        update_env(env_path, "QB_REFRESH_TOKEN", refresh_token)
        update_env(env_path, "QB_REALM_ID", realm_id)

    print("\n" + "=" * 60)
    print("  OK  OAuth2 concluído com sucesso!")
    print(f"     QB_REALM_ID      = {realm_id}")
    print(f"     QB_REFRESH_TOKEN = {refresh_token[:30]}...")
    print("\n  Reinicie o backend para aplicar as novas variáveis.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
