import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import rdf_utils as r  # noqa: E402

SOCIO = {"cnpj_basico": "12345678", "id_socio": "P0000001", "nome_socio": 'Joao "Zé" Lima',
         "qualificacao": "Sócio", "data_entrada": "2018-02-10", "data_saida": "2022-07-01"}


def test_lit_escapa_aspas_e_quebra_de_linha():
    assert r.lit('a"b\nc') == '"a\\"b\\nc"'


def test_uri_remove_caracteres_inseguros():
    assert r.uri("empresa", "12 34>") == f"<{r.BASE}/empresa/12_34_>"


def test_participacao_tem_sete_triplas_com_saida_e_seis_sem():
    ent = r.ENTIDADES["socios"]
    assert len(list(ent.triplas(SOCIO))) == 7
    assert len(list(ent.triplas({**SOCIO, "data_saida": ""}))) == 6


def test_sujeito_da_participacao_e_deterministico():
    ent = r.ENTIDADES["socios"]
    assert ent.sujeito(SOCIO) == f"<{r.BASE}/participacao/12345678_P0000001_20180210>"


def test_parentesco_materializa_temparente_nos_dois_sentidos():
    row = {"id_pessoa_a": "E1", "id_pessoa_b": "P1", "tipo_parentesco": "CONJUGE", "grau": "1"}
    triplas = list(r.ENTIDADES["parentescos"].triplas(row))
    assert (r.uri("pessoa", "E1"), r.onto("temParente"), r.uri("pessoa", "P1")) in triplas
    assert (r.uri("pessoa", "P1"), r.onto("temParente"), r.uri("pessoa", "E1")) in triplas


def test_linha_com_grafo_vira_nquad():
    assert r.linha("<s>", "<p>", "<o>", "g") == "<s> <p> <o> <g> ."


def test_hash_linha_estavel_e_sensivel_a_mudanca():
    assert r.hash_linha(SOCIO) == r.hash_linha(dict(SOCIO))
    assert r.hash_linha(SOCIO) != r.hash_linha({**SOCIO, "data_saida": ""})


def test_escritor_particiona_por_numero_de_triplas(tmp_path):
    with r.EscritorParticionado(tmp_path, "t", triplas_por_parte=2) as esc:
        for i in range(5):
            esc.escrever("<s>", "<p>", f'"{i}"')
    arquivos = sorted(tmp_path.glob("t_*.nt.gz"))
    assert len(arquivos) == 3 and esc.triplas == 5
    with gzip.open(arquivos[-1], "rt", encoding="utf-8") as f:
        assert len(f.readlines()) == 1
