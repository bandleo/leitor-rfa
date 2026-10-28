import json
import pathlib
import re

import pytest

from leitor_rfa.conferencia import comparar
from leitor_rfa.documento import ler

COM_GABARITO = ("r2012_pa2010", "r2012", "r2012_sem_previa", "r2013", "r2014", "r2018")


def _doc_e_gab(fixtura, nome):
    gab = json.loads((fixtura(nome) / "familia.json").read_text(encoding="utf-8"))
    doc = ler(fixtura(nome) / "familia.rfa", nome_arquivo=pathlib.PureWindowsPath(gab["origem"]["caminho"]).name)
    return doc, gab


@pytest.mark.parametrize("nome", COM_GABARITO)
def test_campos_dos_parametros_batem_em_95_por_cento(fixtura, nome):
    doc, gab = _doc_e_gab(fixtura, nome)
    r = comparar(doc, gab)["parametros"]
    assert r.iguais / r.total >= 0.95, r


def test_compartilhado_traz_guid_e_proprio_nao(fixtura):
    doc, gab = _doc_e_gab(fixtura, "r2012")
    p = {x["nome"]: x for x in doc["parametros"]}
    do_gabarito = [x["nome"] for x in gab["parametros"] if x["compartilhado"] and x["nome"] in p]
    assert do_gabarito and all(p[n]["compartilhado"] is True for n in do_gabarito)
    assert all(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", p[n]["guid"])
               for n in do_gabarito)
    proprios = [x for x in doc["parametros"] if not x["compartilhado"]]
    assert proprios and all(x["guid"] is None for x in proprios)


def test_acrescentados_pelo_revit_ficam_marcados_como_inferidos(fixtura):
    doc, _ = _doc_e_gab(fixtura, "r2012")
    cob = doc["cobertura"]
    assert "Exportar tipo para IFC como" in cob["parametros_inferidos"]
    assert "inferido" in cob["secoes"]["parametros"]["nota"]
    nomes = [x["nome"] for x in doc["parametros"]]
    assert len(nomes) == len(set(nomes))


def test_categoria_id_e_tipos_da_tabela_de_tipos(fixtura):
    doc, gab = _doc_e_gab(fixtura, "r2018")
    assert doc["familia"]["categoria_id"] == gab["familia"]["categoria_id"]
    assert set(doc["tipos"]) == set(gab["tipos"])
    assert doc["cobertura"]["secoes"]["tipos"]["estado"] == "decifrado"
