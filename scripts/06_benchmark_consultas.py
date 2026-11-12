"""Roda cada consulta .rq de uma pasta contra um endpoint SPARQL e registra o tempo (mínimo e médio).

Uso: python scripts/06_benchmark_consultas.py [--endpoint URL] [--pasta sparql/tuning] [--repeticoes 3]
Endpoint padrão: Apache Jena Fuseki local (http://localhost:3030/ds/query).
"""
import argparse
import csv
import statistics
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--endpoint", default="http://localhost:3030/ds/query")
    ap.add_argument("--pasta", type=Path, default=RAIZ / "sparql" / "tuning")
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    saida = RAIZ / "benchmarks" / "resultados"
    saida.mkdir(parents=True, exist_ok=True)
    with open(saida / "consultas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["consulta", "segundos_min", "segundos_medio", "linhas", "status"])
        for rq in sorted(args.pasta.glob("*.rq")):
            tempos, linhas, status = [], "", "OK"
            for _ in range(args.repeticoes):
                t0 = time.time()
                try:
                    r = requests.post(args.endpoint, data={"query": rq.read_text(encoding="utf-8")},
                                      headers={"Accept": "application/sparql-results+json"}, timeout=args.timeout)
                    r.raise_for_status()
                    linhas = len(r.json()["results"]["bindings"])
                except Exception as e:  # noqa: BLE001 - registrar qualquer falha e seguir
                    status = f"ERRO: {type(e).__name__}"
                    break
                tempos.append(time.time() - t0)
            w.writerow([rq.name, round(min(tempos), 3) if tempos else "", round(statistics.mean(tempos), 3)
                        if tempos else "", linhas, status])
            print(f"{rq.name}: {status} {round(min(tempos), 2) if tempos else '-'}s")


if __name__ == "__main__":
    main()
