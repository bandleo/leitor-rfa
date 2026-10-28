"""Fórmulas: a árvore de expressão do NamedParam (m_oExpression) em texto, como o Revit escreve.

Classes da árvore (esquema do próprio arquivo): StringConstantExpression ("texto"),
NumberConstantExpression (valor em unidade interna + m_unitType), ParameterExpression
(id do parâmetro), BinaryOperatorExpression (código + esquerda + direita),
UnaryOperatorExpression, FunctionExpression (código + argumentos), ParenExpression.
Os códigos de operador, função e unidade são constantes do Revit, aprendidas do
gabarito (tabelas.json, seção "formulas"). Código sem tabela vira ErroFormula, nunca chute.
"""
from .grafo import id_elemento


class ErroFormula(Exception):
    """Nó ou código da expressão sem tradução conhecida."""


def _numero(v):
    texto = f"{v:.10g}"
    return texto if "e" not in texto else repr(v)


def renderizar(no, grafo, nomes, tabelas):
    """no: Objeto do grafo; nomes: {id do parâmetro: nome}; tabelas: tabelas['formulas']."""
    if no is None:
        raise ErroFormula("expressão vazia")
    c, k = no.campos, no.classe
    sub = lambda chave: renderizar(grafo.alvo(c[chave]), grafo, nomes, tabelas)  # noqa: E731
    if k == "StringConstantExpression":
        return f'"{c["m_value"]}"'
    if k == "NumberConstantExpression":
        if "m_unitType" in c:
            unidade, codigo = tabelas["unidades"].get(str(c["m_unitType"])), c["m_unitType"]
        else:  # 2022+: ForgeTypeId do spec no lugar do código de unidade
            codigo = c["m_specTypeId"]["m_typeId"].rsplit("-", 1)[0]
            unidade = tabelas.get("unidades_por_spec", {}).get(codigo)
        if unidade is None:
            raise ErroFormula(f"unidade {codigo} sem tabela")
        escala, sufixo = unidade
        return _numero(round(c["m_value"] * escala, 9)) + sufixo
    if k == "ParameterExpression":
        pid = id_elemento(c["m_paramId"])
        if pid not in nomes:
            raise ErroFormula(f"parâmetro {pid} sem nome")
        return nomes[pid]
    if k == "ParenExpression":
        return f"({sub('m_pSubexpression')})"
    if k == "BinaryOperatorExpression":
        op = tabelas["binarios"].get(str(c["m_binaryOperator"]))
        if op is None:
            raise ErroFormula(f"operador binário {c['m_binaryOperator']} sem tabela")
        return f"{sub('m_pLeftSubexpression')} {op} {sub('m_pRightSubexpression')}"
    if k == "UnaryOperatorExpression":
        op = tabelas["unarios"].get(str(c["m_unaryOperator"]))
        if op is None:
            raise ErroFormula(f"operador unário {c['m_unaryOperator']} sem tabela")
        return f"{op}{sub('m_pSubexpression')}"
    if k == "FunctionExpression":
        nome = tabelas["funcoes"].get(str(c["m_function"]))
        if nome is None:
            raise ErroFormula(f"função {c['m_function']} sem tabela")
        args = [renderizar(grafo.alvo(a), grafo, nomes, tabelas) for a in c["m_subexpressions"]]
        return f"{nome}({', '.join(args)})"
    raise ErroFormula(f"nó {k} sem tradução")
