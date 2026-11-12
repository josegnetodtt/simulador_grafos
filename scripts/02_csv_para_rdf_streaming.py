"""Converte os CSVs de data/raw em RDF (N-Triples .gz) sem carregar tudo na memória.

Uso: python scripts/02_csv_para_rdf_streaming.py [--entidade socios] [--triplas-por-parte 500000] [--grafo URI]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import DADOS, ENTIDADES, EscritorParticionado, converter_csv, salvar_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entidade", default="todas", choices=["todas", *ENTIDADES])
    ap.add_argument("--triplas-por-parte", type=int, default=500_000)
    ap.add_argument("--grafo", default=None, help="URI do named graph; se informada, gera N-Quads")
    args = ap.parse_args()

    nomes = list(ENTIDADES) if args.entidade == "todas" else [args.entidade]
    for nome in nomes:
        entidade = ENTIDADES[nome]
        origem = DADOS / "raw" / entidade.arquivo
        if not origem.exists():
            print(f"[{nome}] ignorado: {origem} não existe (rode o script 01)")
            continue
        t0 = time.time()
        with EscritorParticionado(DADOS / "rdf" / nome, nome, args.triplas_por_parte, args.grafo) as esc:
            linhas = converter_csv(entidade, origem, esc)
        salvar_json(DADOS / "manifests" / f"{nome}_full.json",
                    {"entidade": nome, "origem": str(origem), "linhas": linhas, "partes": esc.partes,
                     "triplas": esc.triplas, "grafo": args.grafo})
        print(f"[{nome}] {linhas} linhas -> {esc.triplas} triplas em {esc.partes} partes ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
