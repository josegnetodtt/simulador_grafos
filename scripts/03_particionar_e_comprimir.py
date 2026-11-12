"""Divide um arquivo RDF linha-a-linha (.nt/.nq, com ou sem .gz) em partes .gz menores para carga paralela.

Uso: python scripts/03_particionar_e_comprimir.py ARQUIVO [--saida PASTA] [--triplas-por-parte 500000]
"""
import argparse
import gzip
import re
from pathlib import Path


def abrir(caminho):
    if caminho.suffix == ".gz":
        return gzip.open(caminho, "rt", encoding="utf-8")
    return open(caminho, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("arquivo", type=Path)
    ap.add_argument("--saida", type=Path, default=None)
    ap.add_argument("--triplas-por-parte", type=int, default=500_000)
    args = ap.parse_args()

    ext = ".nq.gz" if ".nq" in args.arquivo.name else ".nt.gz"
    base = re.sub(r"\.(nt|nq)(\.gz)?$", "", args.arquivo.name)
    saida = args.saida or args.arquivo.parent / f"{base}_partes"
    saida.mkdir(parents=True, exist_ok=True)

    parte, n, out = 0, 0, None
    with abrir(args.arquivo) as entrada:
        for linha in entrada:
            if out is None or n >= args.triplas_por_parte:
                if out:
                    out.close()
                out = gzip.open(saida / f"{base}_{parte:05d}{ext}", "wt", encoding="utf-8", newline="\n")
                parte, n = parte + 1, 0
            out.write(linha)
            n += 1
    if out:
        out.close()
    print(f"{parte} partes gravadas em {saida}")


if __name__ == "__main__":
    main()
