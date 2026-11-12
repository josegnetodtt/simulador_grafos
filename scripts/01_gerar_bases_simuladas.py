"""Gera bases simuladas (100% fictícias) em data/raw/ e o gabarito dos casos plantados.

Uso: python scripts/01_gerar_bases_simuladas.py [S|M|G]
"""
import csv
import random
import sys
from contextlib import ExitStack
from pathlib import Path

import yaml
from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rdf_utils import DADOS, RAIZ, salvar_json  # noqa: E402

LOTACOES = ["ABAST/REFINO", "E&P/RESERVATORIOS", "LOGISTICA", "JURIDICO", "TIC", "FINANCEIRO"]
CARGOS = ["Analista", "Engenheiro", "Gerente", "Técnico", "Consultor"]
TIPOS_PARENTESCO = {"CONJUGE": 1, "PAI": 1, "MAE": 1, "FILHO": 1, "IRMAO": 2, "SOGRO": 2, "CUNHADO": 2}
SITUACOES = ["ATIVA", "ATIVA", "ATIVA", "BAIXADA", "SUSPENSA"]
PORTES = ["ME", "EPP", "DEMAIS"]
PORTOS = ["SANTOS", "ANGRA", "SUAPE", "ITAQUI", "RIO_GRANDE", "SAO_SEBASTIAO"]
STATUS_MODELO = ["RASCUNHO", "APROVADO", "OBSOLETO"]

CAB = {
    "empregados": ["id_empregado", "cpf", "nome", "lotacao", "cargo", "data_admissao", "data_desligamento"],
    "parentescos": ["id_pessoa_a", "id_pessoa_b", "tipo_parentesco", "grau"],
    "contratos": ["id_contrato", "cnpj_basico_fornecedor", "valor", "data_inicio", "data_fim", "id_gestor"],
    "empresas": ["cnpj_basico", "razao_social", "natureza_juridica", "capital_social", "porte", "data_atualizacao"],
    "estabelecimentos": ["cnpj_basico", "cnpj_ordem", "cnpj_dv", "situacao_cadastral", "data_situacao",
                         "cnae_principal", "uf", "municipio"],
    "socios": ["cnpj_basico", "id_socio", "nome_socio", "qualificacao", "data_entrada", "data_saida"],
    "modelos": ["id_modelo", "id_campo", "versao", "id_versao_anterior", "autor", "data_criacao", "status",
                "hash_conteudo"],
    "misturas": ["id_mistura", "id_componente", "percentual", "propriedade_api", "teor_enxofre"],
    "rotas": ["id_navio", "porto_origem", "porto_destino", "capacidade", "janela_inicio", "janela_fim"],
    "documentos": ["id_doc", "titulo", "area", "entidades_citadas", "data_publicacao"],
}

ARQUIVOS = {
    "empregados": "rh/empregados.csv", "parentescos": "rh/parentescos.csv",
    "contratos": "contratos/contratos.csv", "empresas": "receita/empresas.csv",
    "estabelecimentos": "receita/estabelecimentos.csv", "socios": "receita/socios.csv",
    "modelos": "resops/modelos_reservatorio.csv", "misturas": "ciranda/misturas.csv",
    "rotas": "ciranda/rotas.csv", "documentos": "conhecimento_ia/documentos.csv",
}

# Resultado esperado de cada caso plantado (IDs com prefixo X/9 nunca colidem com os aleatórios).
GABARITO = [
    {"caso": "A", "esperado": "ALERTA", "contrato": "CX-0001",
     "descricao": "Empregado EX000001 é cônjuge do sócio PX000001 de fornecedor com contrato vigente."},
    {"caso": "B", "esperado": "SEM ALERTA", "contrato": "CX-0002",
     "descricao": "Sócio PX000002 (cônjuge de EX000002) saiu em 2020, antes do contrato de 2023."},
    {"caso": "C", "esperado": "CX-0003 SEM ALERTA; CX-0004 ALERTA", "contrato": "CX-0003/CX-0004",
     "descricao": "Empresa 99999993 troca de sócios; irmão PX000004 de EX000003 era sócio de 2014 a 2019."},
    {"caso": "D", "esperado": "DESEMPENHO", "contrato": "-",
     "descricao": "Empresa 99999990 é um supernó (hub) com milhares de estabelecimentos."},
    {"caso": "E", "esperado": "ALERTA só com caminho de até 3 graus", "contrato": "CX-0005",
     "descricao": "EX000004 -> PX000010 -> PX000011 -> PX000012 (sócio de 99999994)."},
    {"caso": "F", "esperado": "QUALIDADE", "contrato": "-",
     "descricao": "CNPJ inválido (1234567), razão social duplicada (00000004) e sócio com saída < entrada (99999995)."},
]


def abrir(stack, raiz, nome):
    caminho = raiz / ARQUIVOS[nome]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    arq = stack.enter_context(open(caminho, "w", newline="", encoding="utf-8"))
    w = csv.writer(arq, delimiter=";")
    w.writerow(CAB[nome])
    return w


def main():
    escala = sys.argv[1].upper() if len(sys.argv) > 1 else "S"
    cfg = yaml.safe_load((RAIZ / "config" / "escalas.yaml").read_text(encoding="utf-8"))[escala]
    fake = Faker("pt_BR")
    Faker.seed(42)
    random.seed(42)
    raw = DADOS / "raw"

    def estab(cnpj, ordem, dv):
        return [cnpj, f"{ordem:04d}", dv, random.choice(SITUACOES), fake.date_between("-10y", "-1y").isoformat(),
                f"{random.randint(1000000, 9999999)}", fake.estado_sigla(), fake.city()]

    def empresa(cnpj, razao=None):
        return [cnpj, razao or fake.company(), "2062", round(random.uniform(1e3, 1e7), 2),
                random.choice(PORTES), "2025-06-30"]

    with ExitStack() as st:
        w = {nome: abrir(st, raw, nome) for nome in CAB}

        # ---- casos plantados (sempre primeiro) ----
        for i, nome in enumerate(["Maria Plantada", "Joao Plantado", "Ana Plantada", "Pedro Plantado"], start=1):
            w["empregados"].writerow([f"EX{i:06d}", fake.cpf(), nome, "TIC", "Analista", "2012-03-01", ""])
        w["parentescos"].writerows([
            ["EX000001", "PX000001", "CONJUGE", 1],
            ["EX000002", "PX000002", "CONJUGE", 1],
            ["EX000003", "PX000004", "IRMAO", 2],
            ["EX000004", "PX000010", "PAI", 1],
            ["PX000010", "PX000011", "PAI", 1],
            ["PX000011", "PX000012", "PAI", 1],
        ])
        for cnpj in ["99999991", "99999992", "99999993", "99999994", "99999995"]:
            w["empresas"].writerow(empresa(cnpj, f"Fornecedora Plantada {cnpj} Ltda"))
            w["estabelecimentos"].writerow(estab(cnpj, 1, "00"))
        w["socios"].writerows([
            ["99999991", "PX000001", "Socio Alfa", "Sócio-Administrador", "2015-01-10", ""],
            ["99999992", "PX000002", "Socio Beta", "Sócio-Administrador", "2010-05-01", "2020-12-31"],
            ["99999993", "PX000003", "Socio Gama", "Sócio", "2010-01-01", "2014-01-31"],
            ["99999993", "PX000004", "Socio Delta", "Sócio-Administrador", "2014-02-01", "2019-06-30"],
            ["99999993", "PX000005", "Socio Epsilon", "Sócio", "2019-07-01", ""],
            ["99999994", "PX000012", "Socio Zeta", "Sócio", "2016-01-01", ""],
            ["99999995", "PX000020", "Socio Eta", "Sócio", "2022-05-01", "2021-01-01"],  # saída < entrada
        ])
        w["contratos"].writerows([
            ["CX-0001", "99999991", "1500000.00", "2023-01-01", "2025-12-31", "EX000001"],
            ["CX-0002", "99999992", "800000.00", "2023-01-01", "2025-12-31", "EX000002"],
            ["CX-0003", "99999993", "300000.00", "2012-01-01", "2013-12-31", "EX000003"],
            ["CX-0004", "99999993", "450000.00", "2016-01-01", "2017-12-31", "EX000003"],
            ["CX-0005", "99999994", "950000.00", "2023-06-01", "2026-05-31", "EX000004"],
        ])
        # supernó artificial: ordem/dv variam para gerar milhares de estabelecimentos distintos
        w["empresas"].writerow(empresa("99999990", "Mega Holding Plantada S.A."))
        for k in range(cfg["hub_estabelecimentos"]):
            w["estabelecimentos"].writerow(estab("99999990", k % 9999 + 1, f"{(k // 9999) % 100:02d}"))

        # ---- RH ----
        for i in range(1, cfg["empregados"] + 1):
            adm = fake.date_between("-30y", "-1y")
            desl = fake.date_between(adm, "today").isoformat() if random.random() < 0.15 else ""
            id_emp = f"E{i:07d}"
            w["empregados"].writerow([id_emp, fake.cpf(), fake.name(), random.choice(LOTACOES),
                                      random.choice(CARGOS), adm.isoformat(), desl])
            for _ in range(random.randint(0, 3)):
                tipo = random.choice(list(TIPOS_PARENTESCO))
                w["parentescos"].writerow([id_emp, f"P{random.randint(1, cfg['pessoas']):07d}", tipo,
                                           TIPOS_PARENTESCO[tipo]])

        # ---- Receita Federal (streaming: nada fica acumulado na memória) ----
        for i in range(cfg["empresas"]):
            cnpj = f"{i:08d}"
            w["empresas"].writerow(empresa(cnpj))
            for ordem in range(1, (2 if random.random() < 0.2 else 1) + 1):
                w["estabelecimentos"].writerow(estab(cnpj, ordem, f"{random.randint(0, 99):02d}"))
            for _ in range(random.randint(1, 4)):
                entrada = fake.date_between("-15y", "-1y")
                saida = fake.date_between(entrada, "today").isoformat() if random.random() < 0.3 else ""
                w["socios"].writerow([cnpj, f"P{random.randint(1, cfg['pessoas']):07d}", fake.name(),
                                      random.choice(["Sócio", "Sócio-Administrador"]),
                                      entrada.isoformat(), saida])
        # qualidade: razão social duplicada e CNPJ inválido (7 dígitos)
        w["empresas"].writerow(empresa("00000004", "Razao Social Divergente S.A."))
        w["empresas"].writerow(empresa("1234567", "Empresa CNPJ Invalido Ltda"))

        # ---- Contratos ----
        for c in range(cfg["contratos"]):
            ini = fake.date_between("-8y", "-1y")
            fim = fake.date_between(ini, "+3y")
            w["contratos"].writerow([f"C{c:07d}", f"{random.randrange(cfg['empresas']):08d}",
                                     round(random.uniform(5e4, 5e6), 2), ini.isoformat(), fim.isoformat(),
                                     f"E{random.randint(1, cfg['empregados']):07d}"])

        # ---- ResOps: versões encadeadas de modelos de reservatório ----
        for m in range(cfg["modelos"]):
            id_modelo, campo = f"M{m:05d}", f"CAMPO{random.randint(1, 50):03d}"
            for v in range(1, random.randint(1, 6) + 1):
                w["modelos"].writerow([id_modelo, campo, v, f"{id_modelo}_v{v - 1}" if v > 1 else "",
                                       fake.user_name(), fake.date_between("-3y", "today").isoformat(),
                                       random.choice(STATUS_MODELO), fake.sha1()])

        # ---- Ciranda: composição de misturas e rotas de navios ----
        for m in range(cfg["misturas"]):
            n = random.randint(2, 5)
            pesos = [random.random() for _ in range(n)]
            pct = [round(100 * p / sum(pesos), 2) for p in pesos]
            pct[-1] = round(100 - sum(pct[:-1]), 2)
            for k, p in enumerate(pct):
                w["misturas"].writerow([f"MIX{m:05d}", f"COMP{random.randint(1, 80):03d}_{k}", p,
                                        round(random.uniform(15, 45), 1), round(random.uniform(0.1, 3.0), 2)])
        for n in range(cfg["navios"]):
            for _ in range(random.randint(1, 3)):
                origem, destino = random.sample(PORTOS, 2)
                ini = fake.date_between("today", "+1y")
                w["rotas"].writerow([f"N{n:04d}", origem, destino, random.choice([80000, 120000, 270000]),
                                     ini.isoformat(), fake.date_between(ini, "+1y").isoformat()])

        # ---- Conhecimento para IA ----
        for d in range(cfg["documentos"]):
            citadas = "|".join(f"{random.randrange(cfg['empresas']):08d}" for _ in range(random.randint(1, 3)))
            w["documentos"].writerow([f"DOC{d:06d}", fake.sentence(nb_words=6), random.choice(LOTACOES), citadas,
                                      fake.date_between("-3y", "today").isoformat()])

    salvar_json(raw / "casos_plantados.json", GABARITO)
    print(f"Escala {escala} gerada em {raw}")


if __name__ == "__main__":
    main()
