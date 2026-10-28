"""Parâmetros da família e valores por tipo, lidos do objeto Family raiz.

FamilyParams.m_params (NamedParam) dá a lista, com instância, reporting e valor.
Para id positivo, o ParamElem dá o nome (ParamDef.m_caption), o grupo e o tipo
de dado; ParamElemExternal é compartilhado e traz o GUID. Id negativo é parâmetro
embutido do Revit. Grupo, tipo de dado e nome dos embutidos são constantes do
Revit que o arquivo guarda como código: as tabelas (tabelas.json) foram
aprendidas do gabarito, sem nenhuma chave ambígua. Os parâmetros que o Revit 2025
acrescenta ao abrir (IFC e os da categoria) não estão no arquivo: vêm da tabela
'acrescentados' e saem marcados como inferidos. FamilyTypeTable dá os tipos e os
valores; o tipo de nome em branco é o padrão e não é um tipo da família.
"""
import json
import pathlib
import uuid

from .formulas import ErroFormula, renderizar
from .grafo import decodificar, id_elemento

TABELAS = json.loads(pathlib.Path(__file__).with_name("tabelas.json").read_text(encoding="utf-8"))
PES_PARA_MM = 304.8
_TEXTO = ("string", "url")
_INTEIRO = ("int64", "bool", "yesNo")


def _id(valor):
    return id_elemento(valor)


def _bruto(np, tipo_dado):
    spec = tipo_dado or ""
    if any(t in spec for t in _TEXTO):
        return np["m_str"]
    if any(t in spec for t in _INTEIRO):
        return np["m_int"]
    if "material" in spec:
        return None  # é um ElementId; o nome do material vem com a leitura dos materiais
    return np["m_value"]


def _valor(np, p):
    bruto = _bruto(np, p["tipo_dado"])
    mm = bruto * PES_PARA_MM if p["tipo_dado"] and "length" in p["tipo_dado"] and isinstance(bruto, float) else None
    return {"bruto": bruto, "texto": None, "mm": mm}


def _versao_conhecida(type_id, tabelas):
    """O arquivo guarda o ForgeTypeId com a versão de quando foi salvo; o extrator (Revit 2025) devolve a atual."""
    base = type_id.rsplit("-", 1)[0]
    return next((v for v in tabelas["tipo_dado"].values() if v.rsplit("-", 1)[0] == base), type_id)


def _grupo_e_tipo(pd, tabelas, sem_rotulo):
    """Até 2021: m_groupElemId e m_unitType (números, pelas tabelas). 2022+: ForgeTypeId em texto
    (m_groupTypeId, m_specTypeId); o tipo de dado é o próprio TypeId, o rótulo do grupo não tem tabela."""
    c = pd.campos
    if "m_groupElemId" in c:
        grupo = tabelas["grupo"].get(str(id_elemento(c["m_groupElemId"])))
    else:
        grupo = None
        sem_rotulo.add(c["m_groupTypeId"]["m_typeId"])
    tipo = tabelas["tipo_dado"].get(f"{pd.classe}|{c.get('m_unitType')}")
    if tipo is None and "m_specTypeId" in c:
        tipo = _versao_conhecida(c["m_specTypeId"]["m_typeId"], tabelas)
    return grupo, tipo


def ler_parametros(corpos, raiz, esquema, nome_familia=None, tabelas=TABELAS):
    fam = decodificar(corpos[raiz], esquema)
    rc = fam.raiz.campos
    params, por_id, desconhecidos, sem_rotulo = [], {}, [], set()
    for np in fam.alvo(rc["m_familyParams"]).campos["m_params"]:
        pid = _id(np["m_paramId"])
        comum = {"instancia": np["m_instance"], "formula": None, "reporting": np["m_reporting"]}
        if pid > 0 and pid in corpos:
            g = decodificar(corpos[pid], esquema)
            pd = g.alvo(g.raiz.campos["m_pParamDef"])
            externo = g.raiz.classe == "ParamElemExternal"
            guid = None
            if externo:
                guid = str(uuid.UUID(bytes_le=bytes(g.raiz.campos["m_externalParamKey"]["m_guidValue"]["m_guid"])))
            grupo, tipo_dado = _grupo_e_tipo(pd, tabelas, sem_rotulo)
            p = {"nome": pd.campos["m_caption"], "grupo": grupo, "compartilhado": externo, "guid": guid,
                 "tipo_dado": tipo_dado, **comum}
        elif pid < 0 and str(pid) in tabelas["embutidos"]:
            emb = tabelas["embutidos"][str(pid)]
            p = {"nome": emb["nome"], "grupo": emb.get("grupo"), "compartilhado": False, "guid": None,
                 "tipo_dado": emb.get("tipo_dado"), **comum}
        else:
            desconhecidos.append(pid)
            continue
        params.append(p)
        por_id[pid] = p
    nomes = {pid: p["nome"] for pid, p in por_id.items()}
    expressoes, falhas = [], 0
    for np in fam.alvo(rc["m_familyParams"]).campos["m_params"]:
        p, no = por_id.get(_id(np["m_paramId"])), fam.alvo(np["m_oExpression"])
        if p is None or no is None:
            continue
        expressoes.append((p["nome"], no))
        if tabelas.get("formulas"):
            try:
                p["formula"] = renderizar(no, fam, nomes, tabelas["formulas"])
            except (ErroFormula, KeyError):  # nó com campo inesperado: a fórmula fica sem tradução, o resto segue
                falhas += 1
    categoria = _id(rc["m_categoryId"])
    presentes = {p["nome"] for p in params}
    inferidos = [dict(p, formula=None) for p in tabelas["acrescentados"].get(str(categoria), [])
                 if p["nome"] not in presentes]
    tipos = {}
    pares = fam.alvo(rc["m_pFamilyTypes"]).campos["m_pairs"]
    for par in pares:
        nome_tipo = par["name"]
        if not nome_tipo.strip():  # regra do Revit (e do extrator): o tipo sem nome só existe se for o único
            if len(pares) != 1 or not nome_familia:
                continue
            nome_tipo = nome_familia
        valores = {}
        for np in par["params"]["m_params"]:
            p = por_id.get(_id(np["m_paramId"]))
            if p:
                valores[p["nome"]] = _valor(np, p)
        tipos[nome_tipo] = valores
    return {"parametros": params + inferidos, "inferidos": [p["nome"] for p in inferidos],
            "desconhecidos": desconhecidos, "tipos": tipos, "categoria_id": categoria,
            "formulas": {"lidas": len(expressoes) - falhas, "sem_traducao": falhas},
            "grafo": fam, "nomes": nomes, "expressoes": expressoes, "grupos_sem_rotulo": sorted(sem_rotulo)}
