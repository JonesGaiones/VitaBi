"""
Gera o template da planilha de-para e um exemplo preenchido com produtos típicos
de Vita Forte (açaí, maca, superfoods).

Uso: python -m scripts.generate_de_para_template
"""
from pathlib import Path
import pandas as pd

OUTPUT = Path(__file__).parent.parent / "data" / "de_para" / "TEMPLATE_de_para.xlsx"


COLUMNS_DOC = """
INSTRUÇÕES DE USO — Planilha De-Para Vita Forte

Colunas obrigatórias:
    qb_raw_pattern   → trecho ou padrão do nome sujo no QuickBooks
    match_type       → "exact" (match literal), "contains" (contém substring),
                       ou "regex" (expressão regular)
    clean_name       → nome limpo/padronizado que aparecerá no dashboard
    category         → categoria principal (Açaí, Maca, Cacau, etc.)

Colunas opcionais:
    subcategory      → subcategoria (Polpa, Em pó, Cápsula, ...)
    brand            → marca
    unit_of_measure  → kg, g, un, cx
    pack_size        → 0.25, 1.0, 5.0 ...
    priority         → número inteiro (menor = aplica primeiro). Default 100.
                       Use números menores (10, 20) para regras mais específicas.
    active           → TRUE/FALSE. Default TRUE.

Ordem de matching:
    1º  Tenta match exato (match_type = "exact")
    2º  Se não achou, tenta contains ordenado por priority ASC
    3º  Se não achou, tenta regex ordenado por priority ASC
    4º  Se nada bateu, produto fica "UNCATEGORIZED" e aparece no alerta
        /products/needs-cleanup para o time revisar.

IMPORTANTE:
- Evite regex caro (.*.*.*); use "contains" sempre que possível.
- Se houver conflito entre regras, a de menor priority vence.
- Após salvar, faça upload em "Config → Upload de-para" no dashboard,
  OU coloque o arquivo em /app/data/de_para/ que o watcher pega.
"""


TEMPLATE_ROWS = [
    # Exemplo 1: match exato de SKU completo
    {
        "qb_raw_pattern": "ACAI POLPA 1KG CONGELADA",
        "match_type": "exact",
        "clean_name": "Açaí Polpa Congelada 1kg",
        "category": "Açaí",
        "subcategory": "Polpa",
        "brand": "Vita Forte",
        "unit_of_measure": "kg",
        "pack_size": 1.0,
        "priority": 10,
        "active": True,
    },
    # Exemplo 2: "contains" — pega qualquer linha que tenha "ACAI 250"
    {
        "qb_raw_pattern": "ACAI 250",
        "match_type": "contains",
        "clean_name": "Açaí Polpa Congelada 250g",
        "category": "Açaí",
        "subcategory": "Polpa",
        "brand": "Vita Forte",
        "unit_of_measure": "g",
        "pack_size": 0.25,
        "priority": 50,
        "active": True,
    },
    # Exemplo 3: regex sofisticado — captura variações de maca
    {
        "qb_raw_pattern": r"MACA\s*(PERUANA|EM\s*PO|POWDER)",
        "match_type": "regex",
        "clean_name": "Maca Peruana em Pó",
        "category": "Maca",
        "subcategory": "Em pó",
        "brand": "Vita Forte",
        "unit_of_measure": "g",
        "pack_size": 0.2,
        "priority": 30,
        "active": True,
    },
    # Exemplo 4: regra "guarda-chuva" de baixa prioridade
    {
        "qb_raw_pattern": "CACAU",
        "match_type": "contains",
        "clean_name": "Cacau (genérico)",
        "category": "Cacau",
        "subcategory": None,
        "brand": None,
        "unit_of_measure": None,
        "pack_size": None,
        "priority": 900,  # aplica só se nada mais bateu
        "active": True,
    },
    # Exemplo 5: regra desativada (histórica)
    {
        "qb_raw_pattern": "ACAI ANTIGO",
        "match_type": "contains",
        "clean_name": "[desativado]",
        "category": "Açaí",
        "subcategory": None,
        "brand": None,
        "unit_of_measure": None,
        "pack_size": None,
        "priority": 1000,
        "active": False,
    },
]


def generate() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(TEMPLATE_ROWS)

    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
        # Aba principal
        df.to_excel(writer, sheet_name="de_para", index=False)
        # Aba de instruções
        pd.DataFrame({"Instruções": COLUMNS_DOC.strip().split("\n")}).to_excel(
            writer, sheet_name="LEIAME", index=False,
        )

    print(f"Template gerado em {OUTPUT}")


if __name__ == "__main__":
    generate()
