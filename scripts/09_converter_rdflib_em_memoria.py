"""ANTI-PADRÃO didático: converte socios.csv para RDF acumulando tudo em memória com rdflib.

Compare o pico de memória com o script 02 (streaming) usando o script 05:
  python scripts/05_monitor_memoria.py rdflib python scripts/09_converter_rdflib_em_memoria.py
  python scripts/05_monitor_memoria.py streaming python scripts/02_csv_para_rdf_streaming.py --entidade socios
"""
import re
import sys
from pathlib import Path

from rdflib import Graph, Literal, URIRef

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import DADOS, ENTIDADES, ler_csv  # noqa: E402

LITERAL = re.compile(r'^"(.*)"(?:\^\^<(.+)>)?$')


def termo(t):
    if t.startswith("<"):
        return URIRef(t[1:-1])
    texto, tipo = LITERAL.match(t).groups()
    return Literal(texto.replace('\\"', '"').replace("\\\\", "\\"), datatype=URIRef(tipo) if tipo else None)


def main():
    ent = ENTIDADES["socios"]
    g = Graph()
    for row in ler_csv(DADOS / "raw" / ent.arquivo):
        for s, p, o in ent.triplas(row):
            g.add((termo(s), termo(p), termo(o)))  # tudo fica na RAM até o final
    destino = DADOS / "rdf" / "socios_rdflib.nt"
    g.serialize(destino, format="nt")
    print(f"{len(g)} triplas gravadas em {destino}")


if __name__ == "__main__":
    main()
