"""Aprende do gabarito as tabelas de constantes do Revit que o arquivo não traz por extenso.

- grupo: m_groupElemId -> rótulo (PT, como o Revit 2025 mostra)
- tipo_dado: "ClasseDoParamDef|m_unitType" -> spec
- embutidos: id negativo de NamedParam -> {nome, grupo, tipo_dado}, casando o valor
  de cada tipo com o gabarito
- acrescentados: categoria_id -> parâmetros que o Revit 2025 acrescenta ao abrir
  (IFC + os da categoria): os que aparecem em todas as famílias da categoria e
  não vêm nem de ParamElem nem de embutido do arquivo

uso: python -I -X utf8 scripts/aprender_tabelas.py <gabarito> leitor_rfa/tabelas.json

<gabarito>: pasta com <nome>/familia.rfa + familia.json, o JSON v1 exportado de dentro do Revit.
"""
import collections
import json
import math
import pathlib
import sys

from leitor_rfa.compressao import inflar_stream, preparar
from leitor_rfa.contenedor import abrir
from leitor_rfa.elementos import montar_elementos
from leitor_rfa.elemtable import ler_elemtable
from leitor_rfa.esquema import ler_esquema
from leitor_rfa.grafo import decodificar, id_elemento
from leitor_rfa.registros import objetos
from leitor_rfa.segmentos import percorrer_particao

CAMPOS = ("grupo", "tipo_dado", "instancia", "compartilhado", "guid", "reporting")


def _igual(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return a == b


def ler_elementos_familia(rfa):
    """(esquema, elementos, corpos do canal 102) de um .rfa."""
    with abrir(rfa) as c:
        e = ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))
        grupos = [g for n in c.streams() if n.startswith("Partitions/")
                  for g in percorrer_particao(preparar(n, c.ler(n)), e).grupos]
        et = ler_elemtable(inflar_stream("Global/ElemTable", c.ler("Global/ElemTable")), e)
        el = montar_elementos(grupos, et, e, inflar_stream("Global/Latest", c.ler("Global/Latest")))
    corpos = {o.id: o.corpo for g in grupos if g.canal == 102 and g.chave_conteudo is None
              for o in objetos(g.dados, et.largura_id)}
    return e, el, corpos


def ler_familia(rfa):
    with abrir(rfa) as c:
        e = ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))
        grupos = [g for n in c.streams() if n.startswith("Partitions/")
                  for g in percorrer_particao(preparar(n, c.ler(n)), e).grupos]
        et = ler_elemtable(inflar_stream("Global/ElemTable", c.ler("Global/ElemTable")), e)
        el = montar_elementos(grupos, et, e, inflar_stream("Global/Latest", c.ler("Global/Latest")))
    corpos = {o.id: o.corpo for g in grupos if g.canal == 102 and g.chave_conteudo is None
              for o in objetos(g.dados, et.largura_id)}
    fam = decodificar(corpos[el.raiz], e)
    return e, corpos, fam, el.raiz


def main(gabarito, saida):
    grupo, tipo_dado = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    votos = collections.defaultdict(collections.Counter)
    sobras_por_categoria, familias_por_categoria = collections.defaultdict(collections.Counter), collections.Counter()
    exemplos = {}
    for d in sorted(p for p in pathlib.Path(gabarito).iterdir() if p.is_dir()):
        gab = json.loads((d / "familia.json").read_text(encoding="utf-8"))
        gp = {p["nome"]: p for p in gab["parametros"]}
        e, corpos, fam, _ = ler_familia(d / "familia.rfa")
        explicados = set()
        for np in fam.alvo(fam.raiz.campos["m_familyParams"]).campos["m_params"]:
            pid = id_elemento(np["m_paramId"])
            if pid <= 0:
                continue
            g = decodificar(corpos[pid], e)
            pd = g.alvo(g.raiz.campos["m_pParamDef"])
            nome = pd.campos["m_caption"]
            if nome in gp:
                explicados.add(nome)
                grupo[str(id_elemento(pd.campos["m_groupElemId"]))][gp[nome]["grupo"]] += 1
                tipo_dado[f"{pd.classe}|{pd.campos.get('m_unitType')}"][gp[nome]["tipo_dado"]] += 1
        # embutidos: casar o valor de cada tipo nomeado com o gabarito
        tabela = fam.alvo(fam.raiz.campos["m_pFamilyTypes"]).campos["m_pairs"]
        for par in tabela:
            valores_gab = gab["tipos"].get(par["name"])
            if not valores_gab:
                continue
            for np in par["params"]["m_params"]:
                pid = id_elemento(np["m_paramId"])
                if pid >= 0:
                    continue
                for nome, v in valores_gab.items():
                    if nome in explicados:
                        continue
                    b = v.get("bruto")
                    if (isinstance(b, str) and b and b == np["m_str"]) or \
                            (isinstance(b, (int, float)) and not isinstance(b, bool) and b != 0
                             and (_igual(b, np["m_value"]) or b == np["m_int"])):
                        votos[str(pid)][nome] += 1
        cat = str(gab["familia"]["categoria_id"])
        familias_por_categoria[cat] += 1
        for nome in gp:
            if nome not in explicados:
                sobras_por_categoria[cat][nome] += 1
                exemplos.setdefault((cat, nome), gp[nome])
    embutidos, conflitos = {}, []
    usados = set()
    for pid, cont in votos.items():
        (nome, n), *resto = cont.most_common()
        if resto and resto[0][1] == n:
            conflitos.append({"embutido": pid, "candidatos": cont.most_common(3)})
            continue
        embutidos[pid] = {"nome": nome}
        usados.add(nome)
    acrescentados = {}
    for cat, cont in sobras_por_categoria.items():
        total = familias_por_categoria[cat]
        lista = []
        for nome, n in cont.items():
            if n == total:  # inclui embutidos: o Revit só grava o que tem valor, mas lista sempre
                p = exemplos[(cat, nome)]
                lista.append({"nome": nome, **{k: p[k] for k in CAMPOS}})
        acrescentados[cat] = sorted(lista, key=lambda p: p["nome"])
    for pid, info in embutidos.items():  # grupo/tipo dos embutidos: do próprio gabarito
        for cat in sobras_por_categoria:
            p = exemplos.get((cat, info["nome"]))
            if p:
                info.update({k: p[k] for k in CAMPOS if k not in ("compartilhado", "guid")})
                break
    for nome_tab, tab in (("grupo", grupo), ("tipo_dado", tipo_dado)):
        for chave, cont in tab.items():
            if len(cont) > 1:
                conflitos.append({nome_tab: chave, "valores": cont.most_common()})
    resultado = {
        "fonte": "aprendido de 106 famílias exportadas de dentro do Revit 2025",
        "grupo": {k: v.most_common(1)[0][0] for k, v in grupo.items()},
        "tipo_dado": {k: v.most_common(1)[0][0] for k, v in tipo_dado.items()},
        "embutidos": embutidos,
        "acrescentados": acrescentados,
        "conflitos": conflitos,
    }
    resultado["referencia_plano"], conflitos_p = aprender_planos(gabarito)
    conflitos += conflitos_p
    resultado["categoria"], conflitos_c = aprender_categorias(gabarito)
    conflitos += conflitos_c
    resultado["vinculo_forma"], conflitos_v = aprender_vinculos(gabarito)
    conflitos += conflitos_v
    resultado["formulas"], conflitos_f = aprender_formulas(gabarito, resultado)
    conflitos += conflitos_f
    # 2022+: a constante da fórmula traz o spec (ForgeTypeId) em vez do código de unidade; o tipo de dado
    # aprendido liga os dois (ParamDefValue|<código> -> spec)
    resultado["formulas"]["unidades_por_spec"] = {
        resultado["tipo_dado"][f"ParamDefValue|{u}"].rsplit("-", 1)[0]: unidade
        for u, unidade in resultado["formulas"]["unidades"].items() if f"ParamDefValue|{u}" in resultado["tipo_dado"]}
    print("fórmulas:", {k: len(v) for k, v in resultado["formulas"].items()}, resultado["formulas"])
    print("categorias:", resultado["categoria"])
    print("vínculos de forma:", resultado["vinculo_forma"])
    pathlib.Path(saida).write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"grupo: {len(resultado['grupo'])} · tipo_dado: {len(resultado['tipo_dado'])} · "
          f"embutidos: {len(embutidos)} · acrescentados: "
          + ", ".join(f"categoria {c}: {len(v)} ({familias_por_categoria[c]} famílias)" for c, v in acrescentados.items())
          + f" · conflitos: {len(conflitos)}")
    for c in conflitos[:8]:
        print("  conflito:", c)
    return 1 if conflitos else 0


def aprender_planos(gabarito):
    """RefPlane.m_refName (código) -> rótulo da referência, casando os planos pelo nome (m_text)."""
    cont = collections.defaultdict(collections.Counter)
    for d in sorted(p for p in pathlib.Path(gabarito).iterdir() if p.is_dir()):
        gab = json.loads((d / "familia.json").read_text(encoding="utf-8"))
        por_nome = collections.defaultdict(set)
        for p in gab["planos_referencia"]:
            por_nome[p["nome"]].add(p["referencia"])
        e, corpos, _, _ = ler_familia(d / "familia.rfa")
        etq = e.etiqueta("RefPlane")
        nomes_arquivo = set()
        for corpo in corpos.values():
            if int.from_bytes(corpo[:2], "little") != etq:
                continue
            c = decodificar(corpo, e).raiz.campos
            nomes_arquivo.add(c["m_text"])
            refs = por_nome.get(c["m_text"])
            if refs and len(refs) == 1:
                cont[str(c["m_refName"])][next(iter(refs))] += 1
        if "" in nomes_arquivo:  # plano sem nome: o Revit mostra um nome padrão
            for nome in por_nome:
                if nome not in nomes_arquivo:
                    cont["nome_vazio"][nome] += 1
    tabela = {k: v.most_common(1)[0][0] for k, v in cont.items()}
    return tabela, [{"referencia_plano": k, "valores": v.most_common(3)} for k, v in cont.items() if len(v) > 1]


def aprender_categorias(gabarito):
    """m_categoryId -> nome da categoria (pt-BR): da família raiz e das aninhadas, casadas pelo nome da família."""
    cont = collections.defaultdict(collections.Counter)
    for d in sorted(p for p in pathlib.Path(gabarito).iterdir() if p.is_dir()):
        gab = json.loads((d / "familia.json").read_text(encoding="utf-8"))
        cont[str(gab["familia"]["categoria_id"])][gab["familia"]["categoria"]] += 1
        if not gab["aninhadas"]:
            continue
        categoria_de = {a["familia"]: a["categoria"] for a in gab["aninhadas"]}
        e, corpos, _, _ = ler_familia(d / "familia.rfa")
        etq = e.etiqueta("Family")
        for corpo in corpos.values():
            if int.from_bytes(corpo[:2], "little") != etq:
                continue
            c = decodificar(corpo, e).raiz.campos
            if c["m_name"] in categoria_de:
                cont[str(id_elemento(c["m_categoryId"]))][categoria_de[c["m_name"]]] += 1
    tabela = {k: v.most_common(1)[0][0] for k, v in cont.items()}
    return tabela, [{"categoria": k, "valores": v.most_common(3)} for k, v in cont.items() if len(v) > 1]


def aprender_vinculos(gabarito):
    """m_elemPropId de um vínculo da forma (formas.vinculos) -> campo do gabarito (parametro_material/_visivel), casando o
    nome do parâmetro associado; formas na ordem do id, só nas famílias com a mesma contagem."""
    from leitor_rfa.formas import TIPOS, vinculos
    from leitor_rfa.parametros import ler_parametros
    cont = collections.defaultdict(collections.Counter)
    for d in sorted(p for p in pathlib.Path(gabarito).iterdir() if p.is_dir()):
        gab = json.loads((d / "familia.json").read_text(encoding="utf-8"))
        e, el, corpos = ler_elementos_familia(d / "familia.rfa")
        if el.raiz is None:
            continue
        ids = [i for i in el.documento() if el.classe[i] in TIPOS]
        if len(ids) != len(gab["formas"]):
            continue
        nomes = ler_parametros(corpos, el.raiz, e)["nomes"]
        for i, forma in zip(ids, gab["formas"]):
            for parametro, propriedade in vinculos(decodificar(corpos[i], e)):
                nome = nomes.get(parametro)
                for campo in ("parametro_material", "parametro_visivel"):
                    if nome is not None and nome == forma[campo]:
                        cont[str(propriedade)][campo] += 1
    tabela = {k: v.most_common(1)[0][0] for k, v in cont.items()}
    return tabela, [{"vinculo_forma": k, "valores": v.most_common(3)} for k, v in cont.items() if len(v) > 1]


BINARIOS = ("+", "-", "*", "/", "^", "=", "<", ">", "<=", ">=", "<>")
UNARIOS = ("-", "+")
FUNCOES = ("if", "and", "or", "not", "sqrt", "abs", "round", "roundup", "rounddown", "sin", "cos", "tan",
           "asin", "acos", "atan", "exp", "ln", "log", "pi", "size_lookup", "min", "max")


def _codigos(no, grafo, achados):
    if no is None:
        return
    c = no.campos
    for chave, campo in (("binarios", "m_binaryOperator"), ("unarios", "m_unaryOperator"), ("funcoes", "m_function")):
        if campo in c:
            achados.add((chave, str(c[campo])))
    for v in c.values():
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, dict) and "indice" in x:
                _codigos(grafo.alvo(x), grafo, achados)


def aprender_formulas(gabarito, tabelas_base):
    """Unidades pelas constantes numéricas; operadores e funções testando os candidatos do Revit."""
    import re as _re
    from leitor_rfa.formulas import ErroFormula, renderizar
    from leitor_rfa.parametros import ler_parametros
    casos, unidades = [], collections.defaultdict(collections.Counter)
    for d in sorted(p for p in pathlib.Path(gabarito).iterdir() if p.is_dir()):
        gab = json.loads((d / "familia.json").read_text(encoding="utf-8"))
        gform = {p["nome"]: p["formula"] for p in gab["parametros"] if p["formula"]}
        e, corpos, _, raiz = ler_familia(d / "familia.rfa")
        r = ler_parametros(corpos, raiz, e, gab["familia"]["nome"], dict(tabelas_base, formulas=None))
        for nome, no in r["expressoes"]:
            alvo = gform.get(nome)
            if not alvo:
                continue
            achados = set()
            _codigos(no, r["grafo"], achados)
            casos.append((no, r["grafo"], r["nomes"], alvo, achados))
            m = _re.fullmatch(r"(-?[0-9.]+)\s*(\S.*)?", alvo)
            if no.classe == "NumberConstantExpression" and m and no.campos["m_value"]:
                escala = round(float(m.group(1)) / no.campos["m_value"], 4)
                unidades[str(no.campos["m_unitType"])][(escala, f" {m.group(2)}" if m.group(2) else "")] += 1
    tab = {"binarios": {}, "unarios": {}, "funcoes": {}, "unidades": {k: list(v.most_common(1)[0][0]) for k, v in unidades.items()}}
    conflitos = [{"unidade": k, "valores": v.most_common(3)} for k, v in unidades.items() if len(v) > 1]
    sem = lambda s: _re.sub(r"\s+", "", s)  # noqa: E731
    candidatos = {"binarios": BINARIOS, "unarios": UNARIOS, "funcoes": FUNCOES}
    for _ in range(4):
        pendentes = {cod for *_, ach in casos for cod in ach if cod[1] not in tab[cod[0]]}
        for chave, cod in sorted(pendentes):
            placar = collections.Counter()
            for cand in candidatos[chave]:
                teste = dict(tab, **{chave: dict(tab[chave], **{cod: cand})})
                for no, grafo, nomes, alvo, ach in casos:
                    if (chave, cod) in ach:
                        try:
                            placar[cand] += sem(renderizar(no, grafo, nomes, teste)) == sem(alvo)
                        except ErroFormula:
                            pass
            melhores = placar.most_common(2)
            if melhores and melhores[0][1] > 0 and (len(melhores) == 1 or melhores[0][1] > melhores[1][1]):
                tab[chave][cod] = melhores[0][0]
    return tab, conflitos


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    codigo = main(*sys.argv[1:3])
    sys.exit(codigo)
