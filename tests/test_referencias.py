import collections
import json
import pathlib

import pytest

from leitor_rfa.documento import ler

COM_GABARITO = ("r2012_pa2010", "r2012", "r2012_sem_previa", "r2013", "r2014", "r2018")
COM_ANINHADAS = ("r2012_aninhada", "r2018_aninhadas")  # 1 compartilhada; 2 famílias com 20 + 1 instâncias


def _doc_e_gab(fixtura, nome):
    gab = json.loads((fixtura(nome) / "familia.json").read_text(encoding="utf-8"))
    doc = ler(fixtura(nome) / "familia.rfa", nome_arquivo=pathlib.PureWindowsPath(gab["origem"]["caminho"]).name)
    return doc, gab


@pytest.mark.parametrize("nome", COM_GABARITO)
def test_planos_com_nome_e_referencia_do_gabarito(fixtura, nome):
    doc, gab = _doc_e_gab(fixtura, nome)
    lidos = collections.Counter((p["nome"], p["referencia"]) for p in doc["planos_referencia"])
    esperados = collections.Counter((p["nome"], p["referencia"]) for p in gab["planos_referencia"])
    assert lidos == esperados
    assert doc["cobertura"]["secoes"]["planos_referencia"]["estado"] == "parcial"  # extremos ainda não


@pytest.mark.parametrize("nome", COM_GABARITO + COM_ANINHADAS)
def test_aninhadas_iguais_ao_gabarito(fixtura, nome):
    doc, gab = _doc_e_gab(fixtura, nome)
    assert doc["aninhadas"] == gab["aninhadas"]  # família, tipo, categoria, compartilhada, quantidade; mesma ordem
    assert doc["cobertura"]["secoes"]["aninhadas"]["estado"] == "decifrado"


@pytest.mark.parametrize("nome", COM_GABARITO)
def test_cotas_com_rotulo_valor_e_referencias_do_gabarito(fixtura, nome):
    doc, gab = _doc_e_gab(fixtura, nome)
    assert len(doc["cotas"]) == len(gab["cotas"])
    for lida, esperada in zip(doc["cotas"], gab["cotas"]):  # mesma ordem: id do elemento
        assert lida["rotulo"] == esperada["rotulo"]
        assert lida["referencias"] == esperada["referencias"]
        if esperada["valor_mm"] is None:
            assert lida["valor_mm"] is None
        else:
            assert lida["valor_mm"] == pytest.approx(esperada["valor_mm"], rel=1e-6, abs=1e-6)
    assert doc["cobertura"]["secoes"]["cotas"]["estado"] == "decifrado"
