"""Valida a qualidade do RDF gerado (streaming; memória constante).

Checagens: padrão de URIs, campos obrigatórios da participação societária, datas válidas,
validoAte >= validoDe e contagem de triplas x manifesto.
Os casos plantados (CNPJ inválido, sócio com saída < entrada) DEVEM aparecer como problemas.

Uso: python scripts/07_validar_qualidade.py [--pasta data/rdf] [--max-exemplos 10]
"""
import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import BASE, DADOS, ONTO, TIPO, XSD  # noqa: E402

LINHA = re.compile(r"^(<[^>]*>) (<[^>]*>) (.+?) (?:<[^>]*> )?\.$")
URI_OK = re.compile(rf"^<{re.escape(BASE)}/(pessoa|empresa|estabelecimento|participacao|contrato|modelo|"
                    r"composicao|rota|documento)/[A-Za-z0-9_.-]+>$")
EMPRESA_8 = re.compile(rf"^<{re.escape(BASE)}/empresa/\d{{8}}>$")
DATA = re.compile(rf'^"(\d{{4}}-\d{{2}}-\d{{2}})"\^\^<{re.escape(XSD)}date>$')
OBRIGATORIOS = ["socio", "empresa", "validoDe"]


def data_valida(texto):
    try:
        date.fromisoformat(texto)
        return True
    except ValueError:
        return False


def validar_grupo(sujeito, preds, arquivo, registrar):
    if not URI_OK.match(sujeito) or (sujeito.startswith(f"<{BASE}/empresa/") and not EMPRESA_8.match(sujeito)):
        registrar("URI fora do padrão", arquivo, sujeito)
    for pred, objs in preds.items():
        for o in objs:
            if f"^^<{XSD}date>" in o:
                m = DATA.match(o)
                if not m or not data_valida(m.group(1)):
                    registrar("data inválida", arquivo, f"{sujeito} {pred} {o}")
    if f"<{ONTO}ParticipacaoSocietaria>" in preds.get(TIPO, []):
        for campo in OBRIGATORIOS:
            if f"<{ONTO}{campo}>" not in preds:
                registrar(f"participação sem {campo}", arquivo, sujeito)
        de, ate = preds.get(f"<{ONTO}validoDe>"), preds.get(f"<{ONTO}validoAte>")
        if de and ate:
            d1, d2 = DATA.match(de[0]), DATA.match(ate[0])
            if d1 and d2 and d2.group(1) < d1.group(1):
                registrar("validoAte < validoDe", arquivo, sujeito)


def validar_arquivo(caminho, registrar):
    """Triplas do mesmo sujeito são gravadas juntas, então basta agrupar linhas consecutivas."""
    sujeito, preds, total = None, defaultdict(list), 0
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        for linha in f:
            m = LINHA.match(linha.rstrip("\n"))
            if not m:
                registrar("linha N-Triples inválida", caminho.name, linha[:80])
                continue
            s, p, o = m.groups()
            total += 1
            if s != sujeito:
                if sujeito:
                    validar_grupo(sujeito, preds, caminho.name, registrar)
                sujeito, preds = s, defaultdict(list)
            preds[p].append(o)
    if sujeito:
        validar_grupo(sujeito, preds, caminho.name, registrar)
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pasta", type=Path, default=DADOS / "rdf")
    ap.add_argument("--max-exemplos", type=int, default=10)
    args = ap.parse_args()

    problemas, exemplos = Counter(), defaultdict(list)

    def registrar(tipo, arquivo, detalhe):
        problemas[tipo] += 1
        if len(exemplos[tipo]) < args.max_exemplos:
            exemplos[tipo].append(f"{arquivo}: {detalhe}")

    por_pasta = Counter()
    for arq in sorted([*args.pasta.rglob("*.nt.gz"), *args.pasta.rglob("*.nq.gz")]):
        por_pasta[arq.parent] += validar_arquivo(arq, registrar)

    for pasta, total in por_pasta.items():
        manifesto = DADOS / "manifests" / f"{pasta.name}_full.json"
        if manifesto.exists():
            esperado = json.loads(manifesto.read_text(encoding="utf-8"))["triplas"]
            if esperado != total:
                registrar("contagem diverge do manifesto", pasta.name, f"manifesto={esperado} arquivos={total}")

    print(f"Triplas validadas: {sum(por_pasta.values())}")
    for tipo, n in problemas.most_common():
        print(f"\n[{n}] {tipo}")
        for e in exemplos[tipo]:
            print(f"   - {e}")
    if not problemas:
        print("Nenhum problema encontrado.")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
