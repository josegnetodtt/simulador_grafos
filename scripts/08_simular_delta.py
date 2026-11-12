"""Simula uma nova versão mensal de socios.csv para exercitar a carga incremental (script 04).

Do total de linhas: PCT% alteradas (data_saida preenchida), PCT/2% removidas e PCT/2% novas.
Uso: python scripts/08_simular_delta.py [--pct 5]   ->  data/raw/receita/socios_delta.csv
"""
import argparse
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import DADOS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pct", type=float, default=5.0)
    args = ap.parse_args()
    random.seed(7)
    p = args.pct / 100
    origem = DADOS / "raw" / "receita" / "socios.csv"
    destino = DADOS / "raw" / "receita" / "socios_delta.csv"

    n = 0
    with open(origem, newline="", encoding="utf-8") as fi, \
            open(destino, "w", newline="", encoding="utf-8") as fo:
        leitor = csv.DictReader(fi, delimiter=";")
        w = csv.DictWriter(fo, fieldnames=leitor.fieldnames, delimiter=";")
        w.writeheader()
        for row in leitor:
            n += 1
            r = random.random()
            if r < p:
                entrada = date.fromisoformat(row["data_entrada"])
                row["data_saida"] = (entrada + timedelta(days=random.randint(30, 1000))).isoformat()
            elif r < p * 1.5:
                continue  # removido
            w.writerow(row)
        for k in range(int(n * p / 2)):
            w.writerow({"cnpj_basico": f"{random.randrange(10000):08d}", "id_socio": f"PN{k:06d}",
                        "nome_socio": f"Socio Novo {k}", "qualificacao": "Sócio",
                        "data_entrada": "2025-07-01", "data_saida": ""})
    print(f"Delta simulado em {destino}")


if __name__ == "__main__":
    main()
