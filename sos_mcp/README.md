# sos_mcp — servidor MCP do SOS Inventory

Dá ao Claude (Claude Desktop, Claude Code, Cowork ou um conector do claude.ai) acesso ao SOS Inventory
da Vita Forte: itens, estoque, lotes, produção (PRT), estimates, sales orders, shipments, invoices,
compras, ajustes, transferências, clientes, fornecedores e tabelas de configuração.

Leitura é livre. **Escrita sempre em duas etapas, com backup** (veja "Escrita" abaixo).
Para um servidor só de leitura, defina `SOS_MCP_READONLY=1`.

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
| `sos_update_record` | **Escrita.** Altera um registro (item, invoice, SO, estimate, PRT, lote, cliente...) |
| `sos_create_record` | **Escrita.** Cria um item, ajuste de estoque, transferência, cliente ou fornecedor |
| `sos_delete_item` | **Escrita.** Exclusão lógica de um item ("(deleted)" no nome, histórico mantido) |

## Escrita: como funciona a proteção

1. A primeira chamada **não grava nada**: devolve a prévia (cada campo, antes e depois) e um `confirm_token`.
2. O Claude mostra a prévia e só chama de novo, com o `confirm_token`, se você aprovar.
3. Antes de gravar, o registro inteiro vai para um **backup JSON**, e a mudança vai para um **log**.

Regras:
- O `confirm_token` só vale para os mesmos argumentos da prévia. Ele também deixa de valer se alguém
  mudar o registro no meio do caminho (syncToken do SOS) ou se o servidor reiniciar.
- Um registro por chamada. Não existe ação em massa.
- Linhas (`lines`, `inputs`, `outputs`) mudam uma a uma, pelo id da linha.
- `id` e `syncToken` não podem ser alterados.
- O único DELETE é a exclusão lógica de item. O SOS recusa se houver saldo em alguma location.
- O PUT manda o objeto inteiro, como o SOS exige: GET, altera e devolve.
- Invoices, POs e itens vão para o QuickBooks no próximo sync do SOS.

Onde ficam os backups e o log:
- No projeto Claude "SOS - VitaForte": `/mnt/project-files/sos/backup-2026-10-04/mcp/` e `/mnt/project-files/sos/sos-mcp-escritas.jsonl`.
- Fora dele: `~/.local/share/sos-mcp/backups/`.
- Para mudar: `SOS_BACKUP_DIR` e `SOS_WRITE_LOG`.

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
2. O script de setup do ambiente (já configurado no VitaForte) registra o servidor em toda sessão nova:

   ```bash
   if [ -d VitaBi/sos_mcp ]; then
     claude mcp add -s user sos -e PYTHONPATH="$(pwd)/VitaBi" -- python3 -m sos_mcp serve || true
   fi
   ```

   A sessão precisa ter o repositório VitaBi. O pacote `mcp` já vem instalado na imagem da nuvem.

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
