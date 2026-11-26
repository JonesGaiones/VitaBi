# sos_mcp — servidor MCP do SOS Inventory (somente leitura)

Dá ao Claude (Claude Desktop, Claude Code, Cowork ou um conector do claude.ai) acesso de **leitura**
ao SOS Inventory da Vita Forte: itens, estoque, lotes, produção (PRT), estimates, sales orders,
shipments, invoices, compras, ajustes, transferências, clientes, fornecedores e tabelas de configuração.

**Não escreve nada no SOS.** O código só faz `GET` nos dados (o único `POST` é a troca/renovação do token OAuth).

## Ferramentas

| Ferramenta | Para que serve |
|---|---|
| `sos_entities` | Lista as entidades e os filtros que cada uma aceita |
| `sos_list` | Lista qualquer entidade, com filtros (texto, status, datas, location, alterados desde...), paginação e escolha de campos |
| `sos_get` | Um registro completo pelo id interno |
| `sos_search_items` | Procura itens por código/nome com estoque e custos resumidos |
| `sos_item_bom` | Lista de materiais de um item montado/kit |
| `sos_production_runs` | Produções (PRT) de um período: entradas, saídas, lotes, Tank, Labor e rendimento rápido |
| `sos_open_orders` | Sales orders em aberto com linhas, entregue/faturado e prazo |
| `sos_lots` | Lotes (ex. `OFAIVF258`) |

## Instalar

```bash
cd VitaBi
python -m pip install -r sos_mcp/requirements.txt   # Python 3.10+
```

Variáveis de ambiente necessárias (já existem no ambiente de nuvem "VitaForte"):

- `SOS_CLIENT_ID` e `SOS_CLIENT_SECRET` (app **VitaForte-Claude** no SOS, redirect `https://localhost/callback`)

## Autorizar (uma vez por máquina/hospedagem)

```bash
python -m sos_mcp auth
```

1. Abra o link mostrado, logado no SOS, e aprove.
2. O navegador vai para `https://localhost/callback?code=...` e dá erro. É normal.
3. Cole a URL inteira no terminal.

O token fica em `~/.config/sos-mcp/token.json` (permissão 600, fora do repositório). Ele dura cerca de
90 dias e o servidor renova sozinho quando expira. Teste com `python -m sos_mcp check`.

> **Limitação:** cada lugar onde o servidor roda precisa dessa autorização uma vez (ou de um
> `SOS_ACCESS_TOKEN`, veja abaixo). O SOS troca o refresh token a cada renovação, então o mesmo token
> não pode ser copiado para vários lugares ao mesmo tempo: quando um renova, o outro perde a renovação.

Nunca coloque token em arquivo do repositório, na memória do projeto ou em chat.

## Conectar a um projeto Claude

### Opção A — no seu computador (mais simples)

Claude Desktop (`Settings > Developer > Edit Config`) ou Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "sos": {
      "command": "python",
      "args": ["-m", "sos_mcp", "serve"],
      "cwd": "C:/caminho/para/VitaBi",
      "env": { "SOS_CLIENT_ID": "...", "SOS_CLIENT_SECRET": "..." }
    }
  }
}
```

Funciona em qualquer conversa/projeto **nesse computador**. Rode o `auth` antes, uma vez.

### Opção B — sessões na nuvem do Claude Code (ambiente "VitaForte")

1. Nas configurações do ambiente, adicione a variável `SOS_ACCESS_TOKEN` com um access token
   (gere com `python -m sos_mcp auth --show-access-token` no seu computador). Vale ~90 dias; depois, gere outro.
2. No repositório que o projeto usa, um `.mcp.json` na raiz com
   `"command": "python", "args": ["-m", "sos_mcp", "serve"]` (e `pip install -r sos_mcp/requirements.txt`
   no script de setup do ambiente).

Sem `SOS_REFRESH_TOKEN` o servidor não renova sozinho: quando o token vencer, ele avisa e é só gerar outro.

### Opção C — hospedado (um endereço para todos os projetos, inclusive web e celular)

Rode numa máquina/servidor que fica ligado (VPS, Render, Fly.io, Cloud Run com disco persistente):

```bash
export SOS_MCP_KEY="uma-chave-longa-e-aleatoria"
python -m sos_mcp auth            # uma vez, nessa máquina
python -m sos_mcp serve --http --host 0.0.0.0 --port 8000
```

Depois, no claude.ai: **Settings > Connectors > Add custom connector** com a URL
`https://SEU-ENDERECO/mcp?key=SUA_CHAVE` (ou o header `Authorization: Bearer SUA_CHAVE`).
Sem `SOS_MCP_KEY` o servidor se recusa a abrir fora do localhost. Use sempre HTTPS na frente.

## Dicas de uso (já vão nas instruções do servidor)

- Fluxo: Estimate (nasce no QuickBooks) → Sales Order → Shipment → Invoice.
- Produção = `process` (PRT). Matéria-prima tem código com prefixo `R`.
- Código com `W` e sem `W` é o mesmo produto.
- Saldos de estoque do SOS ainda não são totalmente confiáveis.

## Testes

```bash
python -m pytest sos_mcp/tests -q     # sem rede, API simulada
```
