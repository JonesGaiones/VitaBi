"""Linha de comando: `python -m sos_mcp [serve|auth|check]`."""

from __future__ import annotations

import argparse
import sys
import urllib.parse

from . import client as C


def cmd_auth(args) -> None:
    print("1. Abra este link no navegador (logado no SOS Inventory) e aprove:\n")
    print("   " + C.authorize_url() + "\n")
    print("2. O navegador vai para https://localhost/callback?code=... e mostra erro. Isso é normal.")
    url = args.url or input("3. Cole aqui a URL inteira da barra de endereço: ").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    code = (q.get("code") or [url if "://" not in url else ""])[0]
    if not code:
        sys.exit("Não achei o parâmetro code na URL.")
    tok = C.exchange_code(code)
    path = C.save_tokens(tok)
    print(f"\nPronto. Token salvo em {path} (permissão 600). Não coloque esse arquivo em repositório.")
    if args.show_access_token:
        print("\nAccess token (para colar na variável SOS_ACCESS_TOKEN de um ambiente seguro):")
        print(tok["access_token"])


def cmd_check(_args) -> None:
    r = C.SOSClient().list("location", max_results=5)
    print(f"OK: API respondeu, {r['totalCount']} locations. Ex.: {[x.get('name') for x in r['records']]}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m sos_mcp", description="Servidor MCP somente leitura do SOS Inventory")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="roda o servidor MCP (padrão: stdio)")
    s.add_argument("--http", action="store_true", help="usa streamable-http em vez de stdio")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    a = sub.add_parser("auth", help="autoriza o acesso ao SOS (OAuth, uma vez por máquina)")
    a.add_argument("--url", help="URL de callback já copiada (pula a pergunta)")
    a.add_argument("--show-access-token", action="store_true", help="mostra o access token no fim")
    sub.add_parser("check", help="testa a conexão com a API")
    args = ap.parse_args()
    if args.cmd == "auth":
        cmd_auth(args)
    elif args.cmd == "check":
        cmd_check(args)
    else:
        from .server import run
        if getattr(args, "http", False):
            run("http", args.host, args.port)
        else:
            run("stdio")


if __name__ == "__main__":
    main()
