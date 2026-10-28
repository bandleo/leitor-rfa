import json
import pathlib

import pytest

from leitor_rfa.conferencia import comparar
from leitor_rfa.documento import ler
from leitor_rfa.formulas import ErroFormula, renderizar
from leitor_rfa.grafo import Grafo, Objeto

TAB = {"binarios": {"3": "*", "1": "+"}, "unarios": {"0": "-"}, "funcoes": {"0": "if"},
       "unidades": {"0": [304.8, " mm"], "4": [1, ""]}}


def ptr(i):
    return {"ponteiro": 1, "indice": i}


def test_produto_de_parametro_por_numero():
    g = Grafo([Objeto("BinaryOperatorExpression", 0, 0, {"m_binaryOperator": 3, "m_pLeftSubexpression": ptr(1),
                                                          "m_pRightSubexpression": ptr(2)}),
               Objeto("ParameterExpression", 0, 1, {"m_paramId": {"m_id": {"m_id": 55}}}),
               Objeto("NumberConstantExpression", 0, 2, {"m_value": 2.0, "m_unitType": 4})])
    assert renderizar(g.raiz, g, {55: "Raio"}, TAB) == "Raio * 2"


def test_comprimento_em_mm_e_texto_entre_aspas():
    g = Grafo([Objeto("NumberConstantExpression", 0, 0, {"m_value": 0.024606299212598423, "m_unitType": 0})])
    assert renderizar(g.raiz, g, {}, TAB) == "7.5 mm"
    g = Grafo([Objeto("StringConstantExpression", 0, 0, {"m_value": "Metal"})])
    assert renderizar(g.raiz, g, {}, TAB) == '"Metal"'


def test_funcao_com_argumentos():
    g = Grafo([Objeto("FunctionExpression", 0, 0, {"m_function": 0, "m_subexpressions": [ptr(1), ptr(2)]}),
               Objeto("ParameterExpression", 0, 1, {"m_paramId": {"m_id": {"m_id": 7}}}),
               Objeto("StringConstantExpression", 0, 2, {"m_value": "x"})])
    assert renderizar(g.raiz, g, {7: "A"}, TAB) == 'if(A, "x")'


def test_codigo_sem_tabela_levanta_em_vez_de_chutar():
    g = Grafo([Objeto("BinaryOperatorExpression", 0, 0, {"m_binaryOperator": 99, "m_pLeftSubexpression": ptr(1),
                                                          "m_pRightSubexpression": ptr(1)}),
               Objeto("NumberConstantExpression", 0, 1, {"m_value": 1.0, "m_unitType": 4})])
    with pytest.raises(ErroFormula, match="99"):
        renderizar(g.raiz, g, {}, TAB)


@pytest.mark.parametrize("nome", ["r2012_pa2010", "r2012", "r2013", "r2014", "r2018"])
def test_formulas_reais_batem_em_90_por_cento(fixtura, nome):
    gab = json.loads((fixtura(nome) / "familia.json").read_text(encoding="utf-8"))
    doc = ler(fixtura(nome) / "familia.rfa", nome_arquivo=pathlib.PureWindowsPath(gab["origem"]["caminho"]).name)
    r = comparar(doc, gab)["formulas"]
    assert r.total == 0 or r.iguais / r.total >= 0.9, r


TAB_2025 = dict(TAB, unidades_por_spec={"autodesk.spec.aec:length": [304.8, " mm"], "autodesk.spec.aec:number": [1, ""]})


def test_constante_2025_com_spec_em_vez_de_unidade():
    g = Grafo([Objeto("NumberConstantExpression", 0, 0, {"m_value": 0.024606299212598423,
                                                         "m_specTypeId": {"m_typeId": "autodesk.spec.aec:length-1.0.0"}})])
    assert renderizar(g.raiz, g, {}, TAB_2025) == "7.5 mm"
    g = Grafo([Objeto("NumberConstantExpression", 0, 0, {"m_value": 2.0,
                                                         "m_specTypeId": {"m_typeId": "autodesk.spec.aec:area-1.0.0"}})])
    with pytest.raises(ErroFormula):
        renderizar(g.raiz, g, {}, TAB_2025)


def test_tabela_liga_spec_a_unidade_pelo_tipo_de_dado():
    from leitor_rfa.parametros import TABELAS
    assert TABELAS["formulas"]["unidades_por_spec"]["autodesk.spec.aec:length"] == [304.8, " mm"]
    assert TABELAS["formulas"]["unidades_por_spec"]["autodesk.spec.aec:number"] == [1.0, ""]
