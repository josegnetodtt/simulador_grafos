"""Funções compartilhadas: URIs, literais e conversão CSV -> triplas RDF (N-Triples / N-Quads).

Cada entidade define duas funções:
  - sujeito(row): URI do nó principal da linha (usada no incremental para apagar/substituir);
  - triplas(row): tuplas (sujeito, predicado, objeto) já formatadas como termos N-Triples.
"""
import csv
import gzip
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import yaml

RAIZ = Path(__file__).resolve().parent.parent
# Escalas M/G geram GBs: aponte SIMULADOR_DADOS para fora do OneDrive (ex.: C:\simulador_dados).
DADOS = Path(os.environ.get("SIMULADOR_DADOS", RAIZ / "data"))
BASE = yaml.safe_load((RAIZ / "config" / "namespaces.yaml").read_text(encoding="utf-8"))["base"]
ONTO = f"{BASE}/onto#"
XSD = "http://www.w3.org/2001/XMLSchema#"
TIPO = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"


def seguro(valor):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", valor.strip())


def uri(tipo, chave):
    return f"<{BASE}/{tipo}/{seguro(chave)}>"


def onto(nome):
    return f"<{ONTO}{nome}>"


def lit(valor, tipo=None):
    v = valor.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{v}"^^<{XSD}{tipo}>' if tipo else f'"{v}"'


def linha(s, p, o, grafo=None):
    return f"{s} {p} {o} <{grafo}> ." if grafo else f"{s} {p} {o} ."


def ler_csv(caminho):
    with open(caminho, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f, delimiter=";")


def hash_linha(row):
    texto = "|".join(f"{k}={row[k]}" for k in sorted(row))
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


def salvar_json(caminho, dados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


class EscritorParticionado:
    """Grava triplas em vários arquivos .gz (N-Triples, ou N-Quads se houver grafo).

    Memória praticamente constante: cada tripla vai direto para o disco.
    """

    def __init__(self, pasta, prefixo, triplas_por_parte=500_000, grafo=None):
        self.pasta = Path(pasta)
        self.prefixo = prefixo
        self.limite = triplas_por_parte
        self.grafo = grafo
        self.ext = ".nq.gz" if grafo else ".nt.gz"
        self.pasta.mkdir(parents=True, exist_ok=True)
        for antigo in self.pasta.glob(f"{prefixo}_*"):
            antigo.unlink()
        self.partes = 0
        self.triplas = 0
        self._n = 0
        self._arq = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    def escrever(self, s, p, o):
        if self._arq is None or self._n >= self.limite:
            self._abrir_proxima()
        self._arq.write(linha(s, p, o, self.grafo) + "\n")
        self._n += 1
        self.triplas += 1

    def _abrir_proxima(self):
        self.fechar()
        nome = f"{self.prefixo}_{self.partes:05d}{self.ext}"
        self._arq = gzip.open(self.pasta / nome, "wt", encoding="utf-8", newline="\n")
        self.partes += 1
        self._n = 0

    def fechar(self):
        if self._arq is not None:
            self._arq.close()
            self._arq = None


# ---------------------------------------------------------------- conversores


def _t(s, classe):
    return (s, TIPO, onto(classe))


def _opt(s, row, coluna, pred, tipo=None):
    valor = (row.get(coluna) or "").strip()
    if valor:
        yield (s, onto(pred), lit(valor, tipo))


def _suj_empregado(r):
    return uri("pessoa", r["id_empregado"])


def _tri_empregado(r):
    s = _suj_empregado(r)
    yield _t(s, "Empregado")
    yield _t(s, "Pessoa")
    yield (s, onto("nome"), lit(r["nome"]))
    yield (s, onto("lotacao"), lit(r["lotacao"]))
    yield (s, onto("cargo"), lit(r["cargo"]))
    yield (s, onto("dataAdmissao"), lit(r["data_admissao"], "date"))
    yield from _opt(s, r, "data_desligamento", "dataDesligamento", "date")


PROP_PARENTESCO = {
    "CONJUGE": "temConjuge", "PAI": "temPai", "MAE": "temMae", "FILHO": "temFilho",
    "IRMAO": "temIrmao", "SOGRO": "temSogro", "CUNHADO": "temCunhado",
}


def _tri_parentesco(r):
    # Linha (a, b, tipo) significa "a tem <tipo> b".
    # temParente é materializada nos dois sentidos para as consultas funcionarem sem inferência.
    a, b = uri("pessoa", r["id_pessoa_a"]), uri("pessoa", r["id_pessoa_b"])
    yield (a, onto(PROP_PARENTESCO[r["tipo_parentesco"]]), b)
    yield (a, onto("temParente"), b)
    yield (b, onto("temParente"), a)


def _suj_empresa(r):
    return uri("empresa", r["cnpj_basico"])


def _tri_empresa(r):
    s = _suj_empresa(r)
    yield _t(s, "Empresa")
    yield (s, onto("razaoSocial"), lit(r["razao_social"]))
    yield (s, onto("naturezaJuridica"), lit(r["natureza_juridica"]))
    yield (s, onto("capitalSocial"), lit(r["capital_social"], "decimal"))
    yield (s, onto("porte"), lit(r["porte"]))
    yield from _opt(s, r, "data_atualizacao", "dataAtualizacao", "date")


def _suj_estab(r):
    return uri("estabelecimento", f"{r['cnpj_basico']}{r['cnpj_ordem']}{r['cnpj_dv']}")


def _tri_estab(r):
    s = _suj_estab(r)
    yield _t(s, "Estabelecimento")
    yield (s, onto("pertenceA"), uri("empresa", r["cnpj_basico"]))
    yield (s, onto("situacaoCadastral"), lit(r["situacao_cadastral"]))
    yield (s, onto("dataSituacao"), lit(r["data_situacao"], "date"))
    yield (s, onto("cnae"), lit(r["cnae_principal"]))
    yield (s, onto("uf"), lit(r["uf"]))
    yield (s, onto("municipio"), lit(r["municipio"]))


def _suj_socio(r):
    chave = f"{r['cnpj_basico']}_{r['id_socio']}_{r['data_entrada'].replace('-', '')}"
    return uri("participacao", chave)


def _tri_socio(r):
    # URI determinística: recarregar o mesmo dado não duplica nada (idempotência).
    s = _suj_socio(r)
    yield _t(s, "ParticipacaoSocietaria")
    yield (s, onto("socio"), uri("pessoa", r["id_socio"]))
    yield (s, onto("empresa"), uri("empresa", r["cnpj_basico"]))
    yield (s, onto("nomeSocio"), lit(r["nome_socio"]))
    yield (s, onto("qualificacao"), lit(r["qualificacao"]))
    yield (s, onto("validoDe"), lit(r["data_entrada"], "date"))
    yield from _opt(s, r, "data_saida", "validoAte", "date")


def _suj_contrato(r):
    return uri("contrato", r["id_contrato"])


def _tri_contrato(r):
    s = _suj_contrato(r)
    yield _t(s, "Contrato")
    yield (s, onto("fornecedor"), uri("empresa", r["cnpj_basico_fornecedor"]))
    yield (s, onto("valor"), lit(r["valor"], "decimal"))
    yield (s, onto("vigenciaInicio"), lit(r["data_inicio"], "date"))
    yield (s, onto("vigenciaFim"), lit(r["data_fim"], "date"))
    yield (s, onto("gestor"), uri("pessoa", r["id_gestor"]))


def _suj_modelo(r):
    return uri("modelo", f"{r['id_modelo']}_v{r['versao']}")


def _tri_modelo(r):
    s = _suj_modelo(r)
    yield _t(s, "ModeloVersao")
    yield (s, onto("campo"), uri("campo", r["id_campo"]))
    yield (s, onto("numeroVersao"), lit(r["versao"], "integer"))
    if r["id_versao_anterior"]:
        yield (s, onto("versaoAnterior"), uri("modelo", r["id_versao_anterior"]))
    yield (s, onto("autor"), lit(r["autor"]))
    yield (s, onto("dataCriacao"), lit(r["data_criacao"], "date"))
    yield (s, onto("status"), lit(r["status"]))
    yield (s, onto("hashConteudo"), lit(r["hash_conteudo"]))


def _suj_composicao(r):
    return uri("composicao", f"{r['id_mistura']}_{r['id_componente']}")


def _tri_composicao(r):
    s = _suj_composicao(r)
    yield _t(s, "ComposicaoItem")
    yield (s, onto("mistura"), uri("mistura", r["id_mistura"]))
    yield (s, onto("componente"), uri("componente", r["id_componente"]))
    yield (s, onto("percentual"), lit(r["percentual"], "decimal"))
    yield (s, onto("grauAPI"), lit(r["propriedade_api"], "decimal"))
    yield (s, onto("teorEnxofre"), lit(r["teor_enxofre"], "decimal"))


def _suj_rota(r):
    chave = f"{r['id_navio']}_{r['porto_origem']}_{r['porto_destino']}_{r['janela_inicio'].replace('-', '')}"
    return uri("rota", chave)


def _tri_rota(r):
    s = _suj_rota(r)
    yield _t(s, "Rota")
    yield (s, onto("navio"), uri("navio", r["id_navio"]))
    yield (s, onto("portoOrigem"), uri("porto", r["porto_origem"]))
    yield (s, onto("portoDestino"), uri("porto", r["porto_destino"]))
    yield (s, onto("capacidade"), lit(r["capacidade"], "integer"))
    yield (s, onto("janelaInicio"), lit(r["janela_inicio"], "date"))
    yield (s, onto("janelaFim"), lit(r["janela_fim"], "date"))


def _suj_documento(r):
    return uri("documento", r["id_doc"])


def _tri_documento(r):
    s = _suj_documento(r)
    yield _t(s, "Documento")
    yield (s, onto("titulo"), lit(r["titulo"]))
    yield (s, onto("area"), lit(r["area"]))
    yield (s, onto("dataPublicacao"), lit(r["data_publicacao"], "date"))
    yield (s, onto("fonte"), lit("simulado"))  # proveniência: de onde veio o fato
    for cnpj in filter(None, r["entidades_citadas"].split("|")):
        yield (s, onto("menciona"), uri("empresa", cnpj))


@dataclass(frozen=True)
class Entidade:
    arquivo: str  # relativo a data/raw
    sujeito: Callable[[dict], str]
    triplas: Callable[[dict], Iterator[tuple]]
    incremental: bool = True  # False = triplas não pertencem só ao sujeito (ex.: arestas entre pessoas)


ENTIDADES = {
    "empregados": Entidade("rh/empregados.csv", _suj_empregado, _tri_empregado),
    "parentescos": Entidade("rh/parentescos.csv", None, _tri_parentesco, incremental=False),
    "contratos": Entidade("contratos/contratos.csv", _suj_contrato, _tri_contrato),
    "empresas": Entidade("receita/empresas.csv", _suj_empresa, _tri_empresa),
    "estabelecimentos": Entidade("receita/estabelecimentos.csv", _suj_estab, _tri_estab),
    "socios": Entidade("receita/socios.csv", _suj_socio, _tri_socio),
    "modelos": Entidade("resops/modelos_reservatorio.csv", _suj_modelo, _tri_modelo),
    "composicoes": Entidade("ciranda/misturas.csv", _suj_composicao, _tri_composicao),
    "rotas": Entidade("ciranda/rotas.csv", _suj_rota, _tri_rota),
    "documentos": Entidade("conhecimento_ia/documentos.csv", _suj_documento, _tri_documento),
}


def converter_csv(entidade, caminho, escritor):
    """Lê o CSV linha a linha e grava as triplas. Retorna o número de linhas lidas."""
    n = 0
    for row in ler_csv(caminho):
        for s, p, o in entidade.triplas(row):
            escritor.escrever(s, p, o)
        n += 1
    return n
