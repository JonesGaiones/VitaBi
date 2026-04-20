import json
import pandas as pd
from pathlib import Path
from datetime import datetime

# Caminhos
BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
OUTPUT_PATH = BASE_DIR / "data" / "de_para" / "LISTA_PARA_MAPEAR.xlsx"

def get_latest_file(prefix):
    files = sorted(RAW_DIR.glob(f"{prefix}*.jsonl"), reverse=True)
    return files[0] if files else None

def extract():
    invoice_file = get_latest_file("qb_invoice_")
    item_file = get_latest_file("qb_item_")

    if not invoice_file or not item_file:
        print("Arquivos raw não encontrados.")
        return

    print(f"Lendo itens de: {item_file.name}")
    item_map = {}
    with item_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                item_map[item["Id"]] = {
                    "Name": item.get("Name", ""),
                    "FullName": item.get("FullyQualifiedName", ""),
                    "Description": item.get("Description", "")
                }

    print(f"Lendo faturas de: {invoice_file.name}")
    # item_id -> description -> {first_date, invoice_ex, count}
    extracted = {}

    with invoice_file.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            inv = json.loads(line)
            inv_no = inv.get("DocNumber", "N/A")
            inv_date = inv.get("TxnDate", "")
            
            for l in inv.get("Line", []):
                if l.get("DetailType") != "SalesItemLineDetail":
                    continue
                
                detail = l.get("SalesItemLineDetail", {})
                item_id = (detail.get("ItemRef") or {}).get("value")
                desc = l.get("Description", "").strip()
                
                if not item_id:
                    continue
                
                key = (item_id, desc)
                if key not in extracted:
                    extracted[key] = {
                        "count": 0,
                        "first_date": inv_date,
                        "example_inv": inv_no
                    }
                
                extracted[key]["count"] += 1
                if inv_date < extracted[key]["first_date"]:
                    extracted[key]["first_date"] = inv_date
                    extracted[key]["example_inv"] = inv_no

    print(f"Processando {len(extracted)} combinações únicas de item/descrição...")
    
    rows = []
    for (item_id, desc), info in extracted.items():
        base_item = item_map.get(item_id, {})
        
        # Colunas que o usuário vai preencher (seguindo o padrão de_para)
        rows.append({
            "qb_raw_pattern": desc if desc else base_item.get("Name", ""),
            "match_type": "contains" if desc else "exact",
            "clean_name": "", # Preencher
            "category": "",   # Preencher
            "subcategory": "",
            "brand": "",
            "unit_of_measure": "",
            "pack_size": "",
            "priority": 100,
            "active": True,
            # Colunas de Contexto (ajuda o usuário a saber o que é)
            "CONTEXTO_Código_QB": base_item.get("Name", item_id),
            "CONTEXTO_Descrição_Item_QB": base_item.get("Description", ""),
            "CONTEXTO_Qtd_Vendas": info["count"],
            "CONTEXTO_Data_Primeira_Venda": info["first_date"],
            "CONTEXTO_Exemplo_Invoice": info["example_inv"]
        })

    # Ordenar por mais vendidos para facilitar
    df = pd.DataFrame(rows)
    df = df.sort_values(by="CONTEXTO_Qtd_Vendas", ascending=False)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Mapeamento", index=False)
        
        # Adicionar folha de instruções
        instrucoes = [
            ["INSTRUÇÕES"],
            ["1. As colunas que começam com 'CONTEXTO_' são apenas para sua referência. Não as altere."],
            ["2. Preencha 'clean_name' com o nome bonito que deve aparecer no dashboard."],
            ["3. Preencha 'category' (ex: Açaí, Maca, etc)."],
            ["4. Deixe 'match_type' como 'contains' se quiser que o robô procure esse texto em qualquer lugar."],
            ["5. Use 'exact' se quiser bater o código SKU exatamente."],
            ["6. Salve o arquivo e me avise para eu carregar no banco de dados."]
        ]
        pd.DataFrame(instrucoes).to_excel(writer, sheet_name="Instruções", index=False, header=False)

    print(f"Sucesso! Planilha gerada em: {OUTPUT_PATH}")

if __name__ == "__main__":
    extract()
