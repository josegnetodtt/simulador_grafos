"""Gera os gráficos (PNG) em benchmarks/relatorios/ a partir dos resultados em benchmarks/resultados/.

Gráficos (cada um responde a uma pergunta simples):
  01  Quantas triplas e quanta memória cada modelo temporal usa?
  02  Qual modelo responde mais rápido a cada pergunta?
  03  O que acontece com o modelo B quando aumenta o número de fotos mensais?
  04  O quanto uma consulta mal escrita custa a mais?
  05  Quanta memória precisaríamos em 1 e 2 bilhões de triplas? (projeção linear, a calibrar)
  06  Streaming x tudo-em-memória: como a RAM se comporta na conversão para RDF?
  07  Desenho do grafo dos casos plantados (para entender as relações)

Uso: python scripts/11_gerar_graficos.py [--escala S]
"""
import argparse
import csv
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import DADOS, RAIZ, ler_csv  # noqa: E402

RES = RAIZ / "benchmarks" / "resultados"
OUT = RAIZ / "benchmarks" / "relatorios"
COR = {"A": "#4C78A8", "A2": "#54A24B", "B": "#F58518"}
NOME = {"A": "A: vínculo com OPTIONAL", "A2": "A2: vínculo com data-fim 9999-12-31", "B": "B: foto mensal (named graph)"}


def ler(caminho):
    if not caminho.exists():
        print(f"  (pulado: {caminho.name} não existe)")
        return None
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def salvar(fig, nome):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / nome, dpi=130)
    plt.close(fig)
    print(f"  gerado: {nome}")


def g01_triplas_memoria(escala):
    d = ler(RES / f"modelos_{escala}.csv")
    if not d:
        return
    fig, eixos = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, campo, titulo in [(eixos[0], "triplas_modelo", "Triplas do modelo (milhões)"),
                              (eixos[1], "mem_modelo_mb", "Memória do modelo (MB)")]:
        escala_y = 1e6 if campo == "triplas_modelo" else 1
        valores = [float(r[campo]) / escala_y for r in d]
        barras = ax.bar([r["modelo"] for r in d], valores, color=[COR[r["modelo"]] for r in d])
        ax.bar_label(barras, fmt="%.2f" if escala_y > 1 else "%.0f")
        ax.set_title(titulo)
    fig.suptitle(f"Custo de armazenar o histórico de sócios (escala {escala}) — menos é melhor\n"
                 + "   |   ".join(NOME[k] for k in NOME), fontsize=9)
    salvar(fig, f"01_triplas_e_memoria_por_modelo_{escala}.png")


def g02_consultas(escala):
    d = ler(RES / f"consultas_modelos_{escala}.csv")
    if not d:
        return
    consultas = list(dict.fromkeys(r["consulta"] for r in d))
    modelos = list(dict.fromkeys(r["modelo"] for r in d))
    fig, ax = plt.subplots(figsize=(12, 5))
    larg = 0.8 / len(modelos)
    for i, m in enumerate(modelos):
        tempos = [max(float(r["segundos"]) * 1000, 0.01) for c in consultas for r in d
                  if r["modelo"] == m and r["consulta"] == c]
        ax.bar([x + i * larg for x in range(len(consultas))], tempos, larg, label=NOME[m], color=COR[m])
    ax.set_xticks([x + larg * (len(modelos) - 1) / 2 for x in range(len(consultas))])
    ax.set_xticklabels([c.split("_", 1)[0] + "\n" + textwrap.fill(c.split("_", 1)[1].replace("_", " "), 22)
                        for c in consultas], fontsize=8)
    ax.set_yscale("log")
    ax.set_ylabel("tempo em ms (escala logarítmica)")
    ax.set_title(f"Tempo de resposta por modelo (escala {escala}) — menos é melhor")
    ax.legend(fontsize=8)
    salvar(fig, f"02_tempo_consultas_por_modelo_{escala}.png")


def g03_varredura(escala):
    d = ler(RES / f"varredura_snapshots_{escala}.csv")
    m = ler(RES / f"modelos_{escala}.csv")
    if not d:
        return
    b = [(int(r["snapshots"]), float(r["triplas_modelo"]) / 1e6) for r in d if r["modelo"] == "B"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(*zip(*b), marker="o", color=COR["B"], label=NOME["B"])
    for r in (m or []):
        if r["modelo"] in ("A", "A2"):
            ax.axhline(float(r["triplas_modelo"]) / 1e6, color=COR[r["modelo"]], linestyle="--", label=NOME[r["modelo"]])
    ax.set_xlabel("número de fotos mensais guardadas")
    ax.set_ylabel("triplas (milhões)")
    ax.set_title(f"O modelo B cresce com o tempo; o A não (escala {escala})")
    ax.legend(fontsize=8)
    salvar(fig, f"03_custo_do_modelo_B_por_fotos_{escala}.png")


def g04_tuning(escala):
    d = ler(RES / f"tuning_{escala}.csv")
    if not d:
        return
    nomes = {"01": "OPTIONAL só depois\ndo padrão obrigatório", "02": "Caminho de parentesco\nlimitado a 3 graus",
             "03": "SELECT só com o\nnecessário + LIMIT"}
    pares = {}
    for r in d:
        num = r["consulta"][:2]
        tipo = "ruim" if "ruim" in r["consulta"] else "bom"
        pares.setdefault(num, {})[tipo] = max(float(r["segundos"]) * 1000, 0.01)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for i, (num, v) in enumerate(sorted(pares.items())):
        ax.bar(i - 0.2, v.get("ruim", 0.01), 0.4, color="#E45756", label="consulta ruim" if i == 0 else None)
        ax.bar(i + 0.2, v.get("bom", 0.01), 0.4, color="#54A24B", label="consulta boa" if i == 0 else None)
    ax.set_xticks(range(len(pares)))
    ax.set_xticklabels([nomes.get(n, n) for n in sorted(pares)], fontsize=9)
    ax.set_yscale("log")
    ax.set_ylabel("tempo em ms (escala logarítmica)")
    ax.set_title(f"Mesma pergunta, escrita de duas formas (escala {escala}, modelo A)")
    ax.legend()
    salvar(fig, f"04_tuning_ruim_vs_bom_{escala}.png")


def g05_projecao():
    pontos = []
    for arq in sorted(RES.glob("modelos_*.csv")):
        for r in ler(arq) or []:
            pontos.append((r["modelo"], float(r["triplas_modelo"]) / 1e6, float(r["mem_modelo_mb"]) / 1e3))
    if len(pontos) < 2:
        return
    # reta pela origem: GB por milhão de triplas (mínimos quadrados)
    k = sum(x * y for _, x, y in pontos) / sum(x * x for _, x, _ in pontos)
    fig, ax = plt.subplots(figsize=(9, 5))
    for m in COR:
        p = [(x, y) for mm, x, y in pontos if mm == m]
        if p:
            ax.scatter(*zip(*p), s=60, color=COR[m], label=f"medido — {NOME[m]}", zorder=3)
    xs = [0, 2000]
    ax.plot(xs, [k * x for x in xs], color="gray", linestyle="--", label=f"projeção linear (~{k * 1000:.0f} MB por milhão de triplas)")
    for alvo in (1000, 2000):
        ax.annotate(f"{alvo / 1000:.0f} bi triplas ≈ {k * alvo:.0f} GB", (alvo, k * alvo), textcoords="offset points",
                    xytext=(-110, 8), fontsize=9)
    ax.set_xlabel("triplas do modelo (milhões)")
    ax.set_ylabel("memória (GB)")
    ax.set_title("Projeção de memória — valor de referência do simulador (pyoxigraph), NÃO do AnzoGraph")
    ax.legend(fontsize=8, loc="upper left")
    salvar(fig, "05_projecao_de_memoria.png")


def g06_conversao():
    curvas = sorted(RES.glob("memoria_*.csv"))
    if not curvas:
        print("  (pulado: nenhum memoria_*.csv; rode o script 05)")
        return
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for arq in curvas:
        d = ler(arq)
        ax.plot([float(r["segundos"]) for r in d], [float(r["rss_mb"]) for r in d], label=arq.stem.replace("memoria_", ""))
    ax.set_xlabel("segundos")
    ax.set_ylabel("memória (MB)")
    ax.set_title("Memória durante a conversão para RDF: linha reta = streaming; subida contínua = tudo na RAM")
    ax.title.set_fontsize(10)
    ax.legend()
    salvar(fig, "06_memoria_na_conversao.png")


def g07_grafo():
    raw = DADOS / "raw"
    if not (raw / "rh" / "parentescos.csv").exists():
        print("  (pulado: rode o script 01)")
        return
    g = nx.DiGraph()
    tipo_no = {}

    def no(id_, tipo, rotulo=None):
        g.add_node(id_)
        tipo_no[id_] = tipo
        g.nodes[id_]["rotulo"] = rotulo or id_

    emp = {r["cnpj_basico"] for r in ler_csv(raw / "receita" / "empresas.csv") if r["cnpj_basico"] in
           {"99999991", "99999992", "99999993", "99999994"}}
    for r in ler_csv(raw / "rh" / "empregados.csv"):
        if r["id_empregado"].startswith("EX"):
            no(r["id_empregado"], "Empregado", r["id_empregado"])
    for r in ler_csv(raw / "rh" / "parentescos.csv"):
        if r["id_pessoa_a"][:2] in ("EX", "PX") and r["id_pessoa_b"][:2] == "PX":
            for p in (r["id_pessoa_a"], r["id_pessoa_b"]):
                if p not in g:
                    no(p, "Pessoa")
            g.add_edge(r["id_pessoa_a"], r["id_pessoa_b"], rotulo=r["tipo_parentesco"].lower())
    for r in ler_csv(raw / "receita" / "socios.csv"):
        if r["cnpj_basico"] in emp:
            no(r["cnpj_basico"], "Empresa")
            if r["id_socio"] not in g:
                no(r["id_socio"], "Pessoa")
            fim = r["data_saida"][:4] or "hoje"
            g.add_edge(r["id_socio"], r["cnpj_basico"], rotulo=f"sócio\n{r['data_entrada'][:4]}→{fim}")
    alerta = {"CX-0001", "CX-0004", "CX-0005"}
    for r in ler_csv(raw / "contratos" / "contratos.csv"):
        if r["id_contrato"].startswith("CX-") and r["cnpj_basico_fornecedor"] in emp:
            no(r["id_contrato"], "Contrato", f"{r['id_contrato']}\n{r['data_inicio'][:4]}–{r['data_fim'][:4]}")
            g.add_edge(r["id_contrato"], r["cnpj_basico_fornecedor"], rotulo="fornecedor")
            g.add_edge(r["id_gestor"], r["id_contrato"], rotulo="gestor")

    cores = {"Empregado": "#4C78A8", "Pessoa": "#F58518", "Empresa": "#54A24B", "Contrato": "#B0B0B0"}
    pos = {}
    for i, comp in enumerate(nx.weakly_connected_components(g)):
        sub = nx.kamada_kawai_layout(g.subgraph(comp))
        for n, (x, y) in sub.items():
            pos[n] = (x + (i % 2) * 3.0, y - (i // 2) * 2.6)
    fig, ax = plt.subplots(figsize=(16, 10))
    nx.draw_networkx_edges(g, pos, ax=ax, arrows=True, arrowsize=14, edge_color="#777777", node_size=2200,
                           connectionstyle="arc3,rad=0.08")
    nx.draw_networkx_nodes(g, pos, ax=ax, node_size=2200, node_color=[cores[tipo_no[n]] for n in g],
                           edgecolors=["red" if n in alerta else "white" for n in g],
                           linewidths=[4 if n in alerta else 1 for n in g])
    nx.draw_networkx_labels(g, pos, {n: g.nodes[n]["rotulo"] for n in g}, font_size=7, ax=ax)
    nx.draw_networkx_edge_labels(g, pos, nx.get_edge_attributes(g, "rotulo"), font_size=7, ax=ax,
                                 connectionstyle="arc3,rad=0.08")
    ax.legend(handles=[plt.Line2D([], [], marker="o", linestyle="", color=c, label=t, markersize=12)
                       for t, c in cores.items()] +
              [plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="white", markeredgecolor="red",
                          markeredgewidth=3, label="contrato que DEVE gerar alerta", markersize=12)], loc="upper left")
    ax.set_title("Casos plantados: empregado → parente → sócio de empresa → contrato (A, B, C e E)")
    ax.axis("off")
    salvar(fig, "07_grafo_casos_plantados.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--escala", default="S")
    args = ap.parse_args()
    for f in (lambda: g01_triplas_memoria(args.escala), lambda: g02_consultas(args.escala),
              lambda: g03_varredura(args.escala), lambda: g04_tuning(args.escala), g05_projecao, g06_conversao, g07_grafo):
        f()


if __name__ == "__main__":
    main()
