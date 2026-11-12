"""Compara o DESEMPENHO de modelos temporais para o vínculo sócio-empresa.

  Modelo A  (nó de vínculo): cada vínculo vira um nó com validoDe/validoAte. Guarda o histórico exato.
            Vínculo ainda ativo = SEM validoAte (a consulta precisa de OPTIONAL).
  Modelo A2 (nó de vínculo + data-fim sentinela): igual ao A, mas vínculo ativo recebe validoAte = 9999-12-31,
            então a consulta não precisa de OPTIONAL.
  Modelo B  (foto mensal): um named graph por mês; o vínculo é COPIADO em cada foto em que está ativo.

Cada modelo roda em um processo separado (para medir a memória sem interferência) num triple store
local em memória (pyoxigraph). Atenção: NÃO é o AnzoGraph. Compare os modelos entre si (proporções),
não use os valores absolutos como dimensionamento do ambiente real.

Uso: python scripts/10_benchmark_modelos.py [--escala S] [--modelo todos|A|A2|B] [--snapshots 12] [--repeticoes 3]
     python scripts/10_benchmark_modelos.py --escala S --varredura 3,6,12,24,60   (custo do B x nº de fotos)
Saídas em benchmarks/resultados/: modelos_<escala>.csv, consultas_modelos_<escala>.csv, tuning_<escala>.csv,
  varredura_snapshots_<escala>.csv
"""
import argparse
import csv
import gc
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import psutil
from pyoxigraph import RdfFormat, Store

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import BASE, DADOS, ENTIDADES, ONTO, RAIZ, XSD, ler_csv, linha, onto, uri  # noqa: E402

RESULTADOS = RAIZ / "benchmarks" / "resultados"
ENTIDADES_BASE = ["empregados", "parentescos", "contratos", "empresas"]  # iguais nos dois modelos
EMPRESA_TESTE = "99999993"  # caso plantado C: troca de sócios ao longo do tempo
PREFIXOS = f"PREFIX ex: <{ONTO}>\nPREFIX xsd: <{XSD}>\n"

VIGENTE_A = ('?p a ex:ParticipacaoSocietaria ; ex:socio ?socio ; ex:empresa ?empresa ; ex:validoDe ?de . '
             'OPTIONAL { ?p ex:validoAte ?ate } '
             'FILTER (?de <= "@D@"^^xsd:date && (!BOUND(?ate) || ?ate >= "@D@"^^xsd:date))')
CONTRATO = ('?c ex:fornecedor ?empresa ; ex:vigenciaInicio ?ci ; ex:vigenciaFim ?cf . '
            'FILTER (?ci <= "@D@"^^xsd:date && ?cf >= "@D@"^^xsd:date)')
VIGENTE_A2 = ('?p a ex:ParticipacaoSocietaria ; ex:socio ?socio ; ex:empresa ?empresa ; ex:validoDe ?de ; '
              'ex:validoAte ?ate . FILTER (?de <= "@D@"^^xsd:date && ?ate >= "@D@"^^xsd:date)')
SENTINELA = "9999-12-31"
SNAP = f"<{BASE}/graph/snapshot/@D@>"

# As mesmas 5 perguntas de negócio, escritas para cada modelo.
CONSULTAS = {
    "A": {
        "Q1_socios_da_empresa_na_data":
            "SELECT ?socio WHERE { ?p ex:empresa <@EMP@> ; ex:socio ?socio ; ex:validoDe ?de . "
            'OPTIONAL { ?p ex:validoAte ?ate } FILTER (?de <= "@D@"^^xsd:date && '
            '(!BOUND(?ate) || ?ate >= "@D@"^^xsd:date)) }',
        "Q2_total_de_vinculos_ativos_na_data":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT DISTINCT ?socio ?empresa WHERE { " + VIGENTE_A + " } }",
        "Q3_conflito_de_interesse_na_data":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT DISTINCT ?emp ?socio ?empresa WHERE { "
            "?emp a ex:Empregado ; ex:temParente ?socio . " + VIGENTE_A + " " + CONTRATO + " } }",
        "Q4_historico_completo_da_empresa":
            "SELECT ?socio ?de ?ate WHERE { ?p ex:empresa <@EMP@> ; ex:socio ?socio ; ex:validoDe ?de . "
            "OPTIONAL { ?p ex:validoAte ?ate } }",
        "Q5_empresas_com_mais_de_um_socio_no_historico":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT ?empresa (COUNT(DISTINCT ?socio) AS ?k) WHERE { "
            "?p ex:empresa ?empresa ; ex:socio ?socio } GROUP BY ?empresa HAVING (COUNT(DISTINCT ?socio) > 1) }",
    },
    "A2": {
        "Q1_socios_da_empresa_na_data":
            "SELECT ?socio WHERE { ?p ex:empresa <@EMP@> ; ex:socio ?socio ; ex:validoDe ?de ; ex:validoAte ?ate . "
            'FILTER (?de <= "@D@"^^xsd:date && ?ate >= "@D@"^^xsd:date) }',
        "Q2_total_de_vinculos_ativos_na_data":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT DISTINCT ?socio ?empresa WHERE { " + VIGENTE_A2 + " } }",
        "Q3_conflito_de_interesse_na_data":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT DISTINCT ?emp ?socio ?empresa WHERE { "
            "?emp a ex:Empregado ; ex:temParente ?socio . " + VIGENTE_A2 + " " + CONTRATO + " } }",
        "Q4_historico_completo_da_empresa":
            "SELECT ?socio ?de ?ate WHERE { ?p ex:empresa <@EMP@> ; ex:socio ?socio ; ex:validoDe ?de ; "
            "ex:validoAte ?ate }",
        "Q5_empresas_com_mais_de_um_socio_no_historico":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT ?empresa (COUNT(DISTINCT ?socio) AS ?k) WHERE { "
            "?p ex:empresa ?empresa ; ex:socio ?socio } GROUP BY ?empresa HAVING (COUNT(DISTINCT ?socio) > 1) }",
    },
    "B": {
        "Q1_socios_da_empresa_na_data":
            "SELECT ?socio WHERE { GRAPH " + SNAP + " { ?socio ex:socioDe <@EMP@> } }",
        "Q2_total_de_vinculos_ativos_na_data":
            "SELECT (COUNT(*) AS ?n) WHERE { GRAPH " + SNAP + " { ?socio ex:socioDe ?empresa } }",
        "Q3_conflito_de_interesse_na_data":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT DISTINCT ?emp ?socio ?empresa WHERE { "
            "?emp a ex:Empregado ; ex:temParente ?socio . GRAPH " + SNAP + " { ?socio ex:socioDe ?empresa } "
            + CONTRATO + " } }",
        "Q4_historico_completo_da_empresa":
            "SELECT DISTINCT ?socio WHERE { GRAPH ?g { ?socio ex:socioDe <@EMP@> } }",
        "Q5_empresas_com_mais_de_um_socio_no_historico":
            "SELECT (COUNT(*) AS ?n) WHERE { SELECT ?empresa (COUNT(DISTINCT ?socio) AS ?k) WHERE { "
            "GRAPH ?g { ?socio ex:socioDe ?empresa } } GROUP BY ?empresa HAVING (COUNT(DISTINCT ?socio) > 1) }",
    },
}
COMPARAVEIS = ["Q1_socios_da_empresa_na_data", "Q2_total_de_vinculos_ativos_na_data",
               "Q3_conflito_de_interesse_na_data"]  # devem dar o mesmo número nos dois modelos


def datas_snapshot(n):
    hoje, ano, mes, datas = date.today(), date.today().year, date.today().month, []
    for _ in range(n):
        datas.append(date(ano, mes, 1).isoformat())
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return sorted(datas)


def linhas_entidade(nome):
    ent = ENTIDADES[nome]
    for row in ler_csv(DADOS / "raw" / ent.arquivo):
        for s, p, o in ent.triplas(row):
            yield linha(s, p, o)


def linhas_modelo_a2():
    ent = ENTIDADES["socios"]
    for row in ler_csv(DADOS / "raw" / ent.arquivo):
        for s, p, o in ent.triplas({**row, "data_saida": row["data_saida"] or SENTINELA}):
            yield linha(s, p, o)


def linhas_modelo_b(datas):
    grafos = {d: f"{BASE}/graph/snapshot/{d}" for d in datas}
    socio_de = onto("socioDe")
    for row in ler_csv(DADOS / "raw" / ENTIDADES["socios"].arquivo):
        pessoa, empresa = uri("pessoa", row["id_socio"]), uri("empresa", row["cnpj_basico"])
        entrada, saida = row["data_entrada"], row["data_saida"]
        for d in datas:
            if entrada <= d and (not saida or saida >= d):
                yield linha(pessoa, socio_de, empresa, grafos[d])


def carregar(store, linhas, formato, lote=200_000):
    buf = []
    for texto in linhas:
        buf.append(texto)
        if len(buf) >= lote:
            store.bulk_load(input=("\n".join(buf) + "\n").encode("utf-8"), format=formato)
            buf = []
    if buf:
        store.bulk_load(input=("\n".join(buf) + "\n").encode("utf-8"), format=formato)


def executar(store, consulta, repeticoes, limite=0):
    """Retorna (menor tempo em s, valor, estourou). Conta linhas sem guardá-las na memória.

    Com limite > 0 a consulta roda numa thread; se passar do limite, o tempo devolvido é só o limite
    (o real é maior) e a thread fica para trás — por isso o chamador deve rodar essa consulta por último.
    """
    def uma_vez():
        resultado = store.query(PREFIXOS + consulta)
        variaveis = [v.value for v in resultado.variables]
        n, primeira = 0, None
        for sol in resultado:
            if n == 0:
                primeira = sol
            n += 1
        return int(primeira["n"].value) if variaveis == ["n"] and primeira is not None else n

    tempos, valor = [], None
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        if limite:
            caixa = []
            th = threading.Thread(target=lambda: caixa.append(uma_vez()), daemon=True)
            th.start()
            th.join(limite)
            if th.is_alive():
                return float(limite), -1, True
            valor = caixa[0]
        else:
            valor = uma_vez()
        tempos.append(time.perf_counter() - t0)
    return min(tempos), valor, False


def rodar_modelo(args):
    proc = psutil.Process()
    rss = lambda: proc.memory_info().rss / 1e6  # noqa: E731
    pico = lambda: (getattr(proc.memory_info(), "peak_wset", None) or proc.memory_info().rss) / 1e6  # noqa: E731
    datas = datas_snapshot(args.snapshots)
    data_teste = datas[len(datas) // 2]
    store = Store()

    t0 = time.time()
    for nome in ENTIDADES_BASE:
        carregar(store, linhas_entidade(nome), RdfFormat.N_TRIPLES)
    gc.collect()
    triplas_base, mem_base, seg_base = len(store), rss(), time.time() - t0
    print(f"[{args.modelo}] base carregada: {triplas_base} triplas", file=sys.stderr)

    t0 = time.time()
    if args.modelo == "A":
        carregar(store, linhas_entidade("socios"), RdfFormat.N_TRIPLES)
    elif args.modelo == "A2":
        carregar(store, linhas_modelo_a2(), RdfFormat.N_TRIPLES)
    else:
        carregar(store, linhas_modelo_b(datas), RdfFormat.N_QUADS)
    gc.collect()
    seg_modelo, mem_final = time.time() - t0, rss()
    triplas_modelo = len(store) - triplas_base
    print(f"[{args.modelo}] modelo carregado: {triplas_modelo} triplas em {seg_modelo:.1f}s", file=sys.stderr)

    consultas, estourou = [], False
    # a consulta mais pesada (Q3) vai por último: se estourar o limite, não atrapalha as demais
    for nome, texto in sorted(CONSULTAS[args.modelo].items(), key=lambda kv: kv[0].startswith("Q3")):
        q = texto.replace("@D@", data_teste).replace("@EMP@", f"{BASE}/empresa/{EMPRESA_TESTE}")
        seg, valor, passou = executar(store, q, args.repeticoes, args.limite_seg)
        estourou = estourou or passou
        consultas.append({"consulta": nome, "segundos": round(seg, 6), "valor": valor, "estourou": passou})
        if passou:
            print(f"[{args.modelo}] {nome} passou de {args.limite_seg}s e foi interrompida", file=sys.stderr)
            break

    if args.modelo == "A" and not args.sem_tuning:
        RESULTADOS.mkdir(parents=True, exist_ok=True)
        with open(RESULTADOS / f"tuning_{args.escala}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["consulta", "segundos", "linhas"])
            for rq in sorted((RAIZ / "sparql" / "tuning").glob("*.rq")):
                print(f"[A] tuning: {rq.name}", file=sys.stderr)
                seg, valor, _ = executar(store, rq.read_text(encoding="utf-8"), 1)
                w.writerow([rq.name, round(seg, 6), valor])

    print("RESULTADO:" + json.dumps({
        "modelo": args.modelo, "escala": args.escala, "snapshots": args.snapshots if args.modelo == "B" else 0,
        "triplas_base": triplas_base, "triplas_modelo": triplas_modelo,
        "segundos_base": round(seg_base, 2), "segundos_modelo": round(seg_modelo, 2),
        "mem_base_mb": round(mem_base), "mem_modelo_mb": round(mem_final - mem_base), "pico_mb": round(pico()),
        "consultas": consultas, "data_teste": data_teste}), flush=True)
    if estourou:
        os._exit(0)  # a thread da consulta interrompida ainda está rodando; encerra sem esperar


def rodar_filho(modelo, args, snapshots, sem_tuning):
    cmd = [sys.executable, __file__, "--modelo", modelo, "--escala", args.escala,
           "--snapshots", str(snapshots), "--repeticoes", str(args.repeticoes),
           "--limite-seg", str(args.limite_seg)]
    if sem_tuning:
        cmd.append("--sem-tuning")
    saida = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    if saida.returncode:
        sys.exit(f"Modelo {modelo} falhou (código {saida.returncode})")
    return json.loads([x for x in saida.stdout.splitlines() if x.startswith("RESULTADO:")][-1][10:])


def varredura(args):
    """Custo do modelo B conforme cresce o número de fotos mensais (A é a referência fixa)."""
    linhas = [rodar_filho("A", args, args.snapshots, True)]
    for n in [int(x) for x in args.varredura.split(",")]:
        linhas.append(rodar_filho("B", args, n, True))
    RESULTADOS.mkdir(parents=True, exist_ok=True)
    with open(RESULTADOS / f"varredura_snapshots_{args.escala}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["modelo", "snapshots", "triplas_modelo", "mem_modelo_mb", "segundos_modelo"])
        for r in linhas:
            w.writerow([r["modelo"], r["snapshots"], r["triplas_modelo"], r["mem_modelo_mb"], r["segundos_modelo"]])
            print(f"{r['modelo']} fotos={r['snapshots']:>3}: {r['triplas_modelo']:>12,} triplas | {r['mem_modelo_mb']} MB")


def orquestrar(args):
    modelos = ["A", "A2", "B"] if args.modelo == "todos" else [args.modelo]
    resultados = [rodar_filho(m, args, args.snapshots, args.sem_tuning) for m in modelos]

    RESULTADOS.mkdir(parents=True, exist_ok=True)
    campos = ["modelo", "escala", "snapshots", "triplas_base", "triplas_modelo", "segundos_modelo",
              "mem_modelo_mb", "pico_mb"]
    with open(RESULTADOS / f"modelos_{args.escala}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(resultados)
    with open(RESULTADOS / f"consultas_modelos_{args.escala}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["modelo", "consulta", "segundos", "valor", "estourou_limite"])
        for r in resultados:
            w.writerows([r["modelo"], c["consulta"], c["segundos"], c["valor"], int(c["estourou"])]
                        for c in r["consultas"])

    print(f"\n=== Escala {args.escala} | fotos mensais no modelo B: {args.snapshots} ===")
    for r in resultados:
        print(f"Modelo {r['modelo']}: {r['triplas_modelo']:>12,} triplas | carga {r['segundos_modelo']:>7.1f}s | "
              f"memória do modelo {r['mem_modelo_mb']:>6} MB | pico do processo {r['pico_mb']} MB")
    if len(resultados) > 1:
        a = resultados[0]
        va = {c["consulta"]: c for c in a["consultas"]}
        for r in resultados[1:]:
            print(f"{r['modelo']}/A: {r['triplas_modelo'] / a['triplas_modelo']:.2f}x triplas | "
                  f"{r['mem_modelo_mb'] / max(a['mem_modelo_mb'], 1):.2f}x memória")
        print("\nTempo por consulta em ms (" + " / ".join(r["modelo"] for r in resultados) + ")")
        for nome in va:
            por_modelo = [{c["consulta"]: c for c in r["consultas"]}[nome] for r in resultados]
            tempos = " / ".join((">" if c["estourou"] else "") + f"{c['segundos'] * 1000:.1f}" for c in por_modelo)
            extra = ""
            if nome in COMPARAVEIS:
                valores = {c["valor"] for c in por_modelo if not c["estourou"]}
                igual = len(valores) == 1
                extra = "  resultado igual nos modelos" if igual else f"  DIVERGE {[c['valor'] for c in por_modelo]}"
                if any(c["estourou"] for c in por_modelo):
                    extra = "  (passou do limite de tempo: o valor mostrado é só o limite)"
            print(f"  {nome}: {tempos}{extra}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--escala", default="S")
    ap.add_argument("--modelo", default="todos", choices=["todos", "A", "A2", "B"])
    ap.add_argument("--snapshots", type=int, default=12)
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--sem-tuning", action="store_true")
    ap.add_argument("--limite-seg", type=int, default=0, help="interrompe consultas que passem deste tempo (0 = sem limite)")
    ap.add_argument("--varredura", default=None, help="lista de nº de fotos para o modelo B, ex.: 3,6,12,24,60")
    args = ap.parse_args()
    if args.varredura:
        varredura(args)
    elif args.modelo == "todos":
        orquestrar(args)
    else:
        rodar_modelo(args)


if __name__ == "__main__":
    main()
