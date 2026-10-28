import json
import pathlib
import re

import pytest

from conftest import ARQUIVOS_DIR, requer_arquivo

from leitor_rfa.contenedor import abrir
from leitor_rfa.documento import ler
from leitor_rfa.partatom import ErroPartAtom, ler_partatom

SEM_PARTATOM = ARQUIVOS_DIR / "r2010_sem_partatom.rfa"
COM_GABARITO = ("r2012_pa2010", "r2012", "r2012_sem_previa", "r2013", "r2014", "r2018")


def _pa(pasta):
    with abrir(pasta / "familia.rfa") as c:
        return ler_partatom(c.ler("PartAtom"))


@pytest.mark.parametrize("nome", COM_GABARITO)
def test_tipos_iguais_ao_gabarito(fixtura, nome):
    pa = _pa(fixtura(nome))
    gab = json.loads((fixtura(nome) / "familia.json").read_text(encoding="utf-8"))
    assert set(pa.tipos) == set(gab["tipos"])


@pytest.mark.parametrize("nome", COM_GABARITO)
def test_nome_da_familia_e_o_nome_do_arquivo(fixtura, nome):
    gab = json.loads((fixtura(nome) / "familia.json").read_text(encoding="utf-8"))
    original = pathlib.PureWindowsPath(gab["origem"]["caminho"]).name
    assert ler(fixtura(nome) / "familia.rfa", nome_arquivo=original)["familia"]["nome"] == gab["familia"]["nome"]
    assert ler(fixtura(nome) / "familia.rfa")["familia"]["nome"] == "familia"


def test_tipos_vem_da_tabela_de_tipos_e_nao_do_partatom(fixtura):
    # o PartAtom lista um tipo com o nome da família até quando ela não tem tipo; a FamilyTypeTable decide
    gab = json.loads((fixtura("r2018") / "familia.json").read_text(encoding="utf-8"))
    original = pathlib.PureWindowsPath(gab["origem"]["caminho"]).name
    doc = ler(fixtura("r2018") / "familia.rfa", nome_arquivo=original)
    assert set(doc["tipos"]) == set(gab["tipos"])
    assert doc["cobertura"]["secoes"]["tipos"]["estado"] == "decifrado"


def test_titulo_do_partatom_fica_no_bloco_partatom(fixtura):
    doc = ler(fixtura("r2012") / "familia.rfa")
    titulo = _pa(fixtura("r2012")).titulo
    assert titulo and doc["partatom"]["titulo"] == titulo and doc["familia"]["nome"] == "familia"


def test_categoria_versao_e_omniclass(fixtura):
    pa = _pa(fixtura("r2018"))
    assert pa.categoria == "Peças hidrossanitárias"
    assert pa.versao_produto == "2018"
    assert pa.omniclass == "23.65.70.11.11"
    assert _pa(fixtura("r2012")).omniclass is None


def test_parametro_compartilhado_traz_guid_e_unidade(fixtura):
    pa = _pa(fixtura("r2012"))
    compartilhados = [p for ps in pa.tipos.values() for p in ps if p.tipo == "shared"]
    assert compartilhados and all(re.fullmatch(r"[0-9a-f-]{36}", p.guid) for p in compartilhados)
    assert any(p.unidade == "mm" and p.tipo_parametro == "Length" for p in compartilhados)


def test_nome_do_parametro_usa_display_name():
    xml = ('<entry xmlns="http://www.w3.org/2005/Atom" xmlns:A="urn:schemas-autodesk-com:partatom">'
           '<title>F</title><A:family type="user"><A:part><title>T1</title>'
           '<Cor_do_Corpo displayName="Cor do Corpo" type="custom" typeOfParameter="Text">azul</Cor_do_Corpo>'
           '</A:part></A:family></entry>').encode("utf-8")
    nomes = {p.nome for ps in ler_partatom(xml).tipos.values() for p in ps}
    assert nomes == {"Cor do Corpo"}


def test_xml_invalido_levanta():
    with pytest.raises(ErroPartAtom):
        ler_partatom(b"<entry><title>x</entr")


def test_documento_guarda_o_partatom_a_parte(fixtura):
    doc = ler(fixtura("r2012_pa2010") / "familia.rfa")
    gab = json.loads((fixtura("r2012_pa2010") / "familia.json").read_text(encoding="utf-8"))
    assert set(doc["tipos"]) == set(gab["tipos"]) and all(v for v in doc["tipos"].values())
    assert doc["familia"]["categoria"] is None
    assert doc["partatom"]["categoria"] == "Plumbing Fixtures"
    assert doc["cobertura"]["secoes"]["familia"]["estado"] == "parcial"
    assert doc["cobertura"]["versao_partatom"] == "2010"


@requer_arquivo("r2010_sem_partatom.rfa")
def test_documento_sem_partatom_fica_nao_decifrado_com_nota():
    doc = ler(SEM_PARTATOM)
    assert doc["cobertura"]["versao_formato"] == 2010
    assert doc["familia"]["nome"] == "r2010_sem_partatom"
    assert doc["tipos"] == {} and doc["partatom"] is None
    secoes = doc["cobertura"]["secoes"]
    assert secoes["familia"]["estado"] == "parcial" and "sem PartAtom" in secoes["familia"]["nota"]
    assert secoes["tipos"]["estado"] == "nao_decifrado" and "sem PartAtom" in secoes["tipos"]["nota"]
