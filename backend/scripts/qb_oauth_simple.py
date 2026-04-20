"""
OAuth2 QuickBooks - fluxo manual simples.
O usuario autoriza no browser e cola a URL de retorno no terminal.

Uso:
    python scripts/qb_oauth_simple.py
"""
import base64
import sys
import urllib.parse
import urllib.request
import json
import webbrowser

CLIENT_ID     = "ABq1xXpS4Z543dfCgspnxsdZ5JNJfoqUHLIAsysX3IKb5DCrk7"
CLIENT_SECRET = "gpC3JYYmireREHZL146HdblBCv1rKzgP1rFq2Cmq"
REDIRECT_URI  = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
SCOPE         = "com.intuit.quickbooks.accounting"

def build_auth_url():
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": "vitabi123",
    })
    return f"https://appcenter.intuit.com/connect/oauth2?{params}"

def exchange_code(code, realm_id):
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request(
        "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        data=body,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def save_env(key, value):
    for path in [
        r"c:\VitaBi\vita_bi\vita_bi\.env",
        r"c:\VitaBi\vita_bi\vita_bi\backend\.env",
    ]:
        try:
            text = open(path, encoding="utf-8").read()
            lines = []
            replaced = False
            for line in text.splitlines():
                if line.startswith(f"{key}="):
                    lines.append(f"{key}={value}")
                    replaced = True
                else:
                    lines.append(line)
            if not replaced:
                lines.append(f"{key}={value}")
            open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
            print(f"  Salvo em {path}")
        except Exception as e:
            print(f"  Erro ao salvar {path}: {e}")

url = build_auth_url()
print("\n=== VITA BI - QuickBooks OAuth2 ===\n")
print("Abrindo browser para autorizacao...")
webbrowser.open(url)
print("\nSe o browser nao abrir, acesse este link:")
print(url)
print("\nDepois de autorizar, o browser vai mostrar uma pagina do Intuit Playground.")
print("Copie a URL COMPLETA do browser (deve conter '?code=...')")
print()

redirect_url = input("Cole a URL aqui: ").strip()

parsed = urllib.parse.urlparse(redirect_url)
params = urllib.parse.parse_qs(parsed.query)

code     = params.get("code", [None])[0]
realm_id = params.get("realmId", [None])[0] or "650092360"

if not code:
    print("Nao encontrei o 'code' na URL. Tente novamente.")
    sys.exit(1)

print(f"\nCodigo recebido. Realm ID: {realm_id}")
print("Trocando codigo por tokens...")

try:
    tokens = exchange_code(code, realm_id)
except Exception as e:
    print(f"Erro ao obter tokens: {e}")
    sys.exit(1)

refresh_token = tokens.get("refresh_token")
if not refresh_token:
    print(f"refresh_token nao retornado. Resposta: {tokens}")
    sys.exit(1)

print(f"\nRefresh token: {refresh_token}")
print("\nSalvando nos .env...")
save_env("QB_REFRESH_TOKEN", refresh_token)
save_env("QB_REALM_ID", realm_id)

print("\n=== Pronto! ===")
print(f"  QB_REALM_ID      = {realm_id}")
print(f"  QB_REFRESH_TOKEN = {refresh_token[:30]}...")
print("\nReinicie o backend para aplicar.")
