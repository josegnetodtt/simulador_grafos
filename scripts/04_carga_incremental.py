"""Carga incremental simulada: compara o CSV com o estado do lote anterior e gera só o delta.

Saídas em data/rdf/delta/<lote>/:
  - <entidade>/*.nq.gz        : N-Quads dos registros novos/alterados, no named graph do lote;
  - <entidade>_remocoes.ru    : SPARQL Update que apaga registros alterados/removidos (aplicar ANTES da carga).

Uso: python scripts/04_carga_incremental.py --entidade socios --lote 2026-06 [--arquivo CSV]
"""
import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import BASE, DADOS, ENTIDADES, EscritorParticionado, hash_linha, ler_csv, salvar_json  # noqa: E402


def apagar(s):
    return f"DELETE {{ GRAPH ?g {{ {s} ?p ?o }} }} WHERE {{ GRAPH ?g {{ {s} ?p ?o }} }} ;\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entidade", required=True, choices=list(ENTIDADES))
    ap.add_argument("--lote", required=True, help="identificador único e crescente, ex.: 2026-06")
    ap.add_argument("--arquivo", type=Path, default=None)
    ap.add_argument("--triplas-por-parte", type=int, default=500_000)
    args = ap.parse_args()

    ent = ENTIDADES[args.entidade]
    if not ent.incremental:
        sys.exit(f"'{args.entidade}' não suporta incremental por sujeito; recarregue o conjunto inteiro.")
    origem = args.arquivo or DADOS / "raw" / ent.arquivo

    db_dir = DADOS / "manifests"
    db_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_dir / "estado.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS estado (entidade TEXT, sujeito TEXT, hash TEXT, lote TEXT, "
               "PRIMARY KEY (entidade, sujeito))")

    grafo = f"{BASE}/graph/{args.entidade}/{args.lote}"
    pasta = DADOS / "rdf" / "delta" / args.lote
    cont = Counter()

    with EscritorParticionado(pasta / args.entidade, args.entidade, args.triplas_por_parte, grafo) as esc, \
            open(pasta / f"{args.entidade}_remocoes.ru", "w", encoding="utf-8") as rem:
        for i, row in enumerate(ler_csv(origem), start=1):
            s, h = ent.sujeito(row), hash_linha(row)
            atual = db.execute("SELECT hash, lote FROM estado WHERE entidade=? AND sujeito=?",
                               (args.entidade, s)).fetchone()
            if atual and atual[1] == args.lote:
                cont["repetido_no_lote"] += 1  # mesmo sujeito duas vezes no arquivo: mantém as duas versões
            elif atual and atual[0] == h:
                db.execute("UPDATE estado SET lote=? WHERE entidade=? AND sujeito=?", (args.lote, args.entidade, s))
                cont["inalterado"] += 1
                continue
            elif atual:
                rem.write(apagar(s))
                cont["alterado"] += 1
            else:
                cont["novo"] += 1
            for t in ent.triplas(row):
                esc.escrever(*t)
            if not atual or atual[1] != args.lote:
                db.execute("INSERT OR REPLACE INTO estado VALUES (?,?,?,?)", (args.entidade, s, h, args.lote))
            if i % 100_000 == 0:
                db.commit()

        # quem não apareceu neste lote deixou de existir na origem
        for (s,) in db.execute("SELECT sujeito FROM estado WHERE entidade=? AND lote<>?", (args.entidade, args.lote)):
            rem.write(apagar(s))
            cont["removido"] += 1
        db.execute("DELETE FROM estado WHERE entidade=? AND lote<>?", (args.entidade, args.lote))
        db.commit()

    salvar_json(db_dir / f"{args.lote}_{args.entidade}_delta.json",
                {"entidade": args.entidade, "lote": args.lote, "grafo": grafo, "contagens": dict(cont),
                 "partes": esc.partes, "triplas": esc.triplas})
    print(f"[{args.entidade}/{args.lote}] {dict(cont)} | {esc.triplas} triplas em {esc.partes} partes")
    print(f"Aplicar na ordem: 1) {args.entidade}_remocoes.ru  2) carga dos .nq.gz")


if __name__ == "__main__":
    main()
