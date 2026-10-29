"""Ponte BIMCraft: o familia.json v1 (o que `ler-rfa` grava) vira uma família do BIMCraft 0.8
(comando `family {"path": ...}`).

uso: python -I -X utf8 -m leitor_rfa.bimcraft FAMILIA.json -o SAIDA.json [--dados DADOS.json]

- Parâmetros: comprimento, ângulo, número, sim/não e material passam, com o valor de cada tipo em mm/graus;
  fórmula passa se só usa o que o BIMCraft tem (mm, if/and/or/not/min/max/abs/sqrt/round…/sin/cos/tan).
  Texto e URL não existem na família do BIMCraft: vão para DADOS, por tipo, para virar parâmetro de projeto.
- Formas: extrusão e revolução em plano paralelo a xy, xz ou yz. O perfil é o laço do esboço no plano;
  laço dentro de outro é furo (`void` logo depois); forma vazia do Revit vira `void` no fim da lista.
  Varredura e mescla ficam de fora (o BIMCraft não varre por caminho), listadas no relatório.
- Categoria: Peças hidrossanitárias -> plumbing; o resto -> generic.
"""
import argparse
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import sys

def achar_cli(ambiente=os.environ):
    """bimcraft-cli: BIMCRAFT_CLI, senão o do PATH, senão a instalação do .msi (Program Files\\BIMCraft), senão a
    pasta portátil mais nova em %LOCALAPPDATA%\\Programs\\BIMCraft. Sem nenhum, o caminho da instalação (inexistente)."""
    if ambiente.get("BIMCRAFT_CLI"):
        return pathlib.Path(ambiente["BIMCRAFT_CLI"])
    no_path = shutil.which("bimcraft-cli", path=ambiente.get("PATH"))
    if no_path:
        return pathlib.Path(no_path)
    candidatos = [pathlib.Path(ambiente.get("ProgramFiles") or r"C:\Program Files", "BIMCraft", "bimcraft-cli.exe")]
    if ambiente.get("LOCALAPPDATA"):
        pasta = pathlib.Path(ambiente["LOCALAPPDATA"], "Programs", "BIMCraft")
        candidatos += sorted(pasta.glob("bimcraft-*-portable/bimcraft-cli.exe"), reverse=True)
    return next((c for c in candidatos if c.is_file()), candidatos[0])


BIMCRAFT_CLI = achar_cli()
CATEGORIAS = {-2001160: "plumbing"}  # OST_PlumbingFixtures (Peças hidrossanitárias)
FUNCOES = {"if", "and", "or", "not", "min", "max", "abs", "sqrt", "round", "roundup", "rounddown", "sin", "cos", "tan"}
PLANOS = {2: ("xy", (0, 1)), 1: ("xz", (0, 2)), 0: ("yz", (1, 2))}  # eixo da normal -> plano e coordenadas do perfil
JUNTA = 1e-6


def _kind(tipo_dado):
    base = (tipo_dado or "").rsplit("-", 1)[0]
    if not base:
        return None
    if base in ("autodesk.spec.aec:length", "autodesk.spec.aec.piping:pipeSize"):
        return "length"
    if base == "autodesk.spec.aec:angle":
        return "angle"
    if base == "autodesk.spec:spec.bool":
        return "yesno"
    if base == "autodesk.spec.aec:material":
        return "material"
    if base in ("autodesk.spec:spec.string", "autodesk.spec.string:url"):
        return "texto"
    return "number"


def _valor(kind, v):
    if not v or v.get("bruto") is None:
        return None
    bruto = v["bruto"]
    if kind == "length":
        return round(v["mm"] if v.get("mm") is not None else bruto * 304.8, 6)
    if kind == "angle":
        return round(math.degrees(bruto), 6)
    if kind == "yesno":
        return bool(bruto)
    if kind in ("material", "texto"):
        return bruto if isinstance(bruto, str) else None
    return bruto


def _formula(texto, fora_da_familia):
    """Fórmula do Revit no formato do BIMCraft, ou (None, motivo)."""
    f = re.sub(r"(\d)\s*mm\b", r"\1", texto)
    if re.search(r"\d\s*(m|cm|ft|in|°)\b|\"|'", f):
        return None, "unidade ou texto que o BIMCraft não lê"
    desconhecidas = {n.lower() for n in re.findall(r"([A-Za-z_]\w*)\s*\(", f)} - FUNCOES
    if desconhecidas:
        return None, f"função sem equivalente: {', '.join(sorted(desconhecidas))}"
    citados = [n for n in fora_da_familia if n in f]
    if citados:
        return None, f"usa parâmetro que não vai para a família: {', '.join(citados)}"
    return f, None


def _nomes(originais):
    """Nome no BIMCraft: começa com letra e só tem letras, dígitos, `_` e espaços (até 256)."""
    novos, usados = {}, set()
    for nome in originais:
        novo = re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", nome)).strip()[:250] or "Parametro"
        if not novo[0].isalpha():
            novo = f"P {novo}"
        base, n = novo, 2
        while novo in usados:
            novo, n = f"{base} {n}", n + 1
        usados.add(novo)
        novos[nome] = novo
    return novos


def _renomear(texto, nomes):
    for antigo in sorted(nomes, key=len, reverse=True):
        if nomes[antigo] != antigo:
            texto = texto.replace(antigo, nomes[antigo])
    return texto


def _parametros(doc, rel):
    kinds = {p["nome"]: _kind(p["tipo_dado"]) for p in doc["parametros"]}
    nomes = _nomes([n for n, k in kinds.items() if k not in (None, "texto")])
    rel["nomes"] = {a: n for a, n in nomes.items() if a != n}
    fora = [n for n, k in kinds.items() if k in (None, "texto")]
    rel["parametros"] = {"texto": [n for n, k in kinds.items() if k == "texto"],
                         "sem_tipo_de_dado": [n for n, k in kinds.items() if k is None]}
    primeiro = next(iter(doc["tipos"].values()), {})
    params, com_formula = [], set()
    for p in doc["parametros"]:
        kind = kinds[p["nome"]]
        if kind in (None, "texto"):
            continue
        item = {"name": nomes[p["nome"]], "kind": kind}
        if p.get("instancia"):
            item["instance"] = True
        valor = _valor(kind, primeiro.get(p["nome"]))
        if valor is not None:
            item["value"] = valor
        if p.get("formula"):
            formula, motivo = _formula(p["formula"], fora)
            if formula is None:
                rel["formulas_fora"].append({"parametro": p["nome"], "formula": p["formula"], "motivo": motivo})
            else:
                item["formula"] = _renomear(formula, nomes)
                com_formula.add(item["name"])
        params.append(item)
    tipos, dados = {}, {}
    por_tipo = [a for a, n in nomes.items()
                if n not in com_formula and not next(p for p in params if p["name"] == n).get("instance")]
    for tipo, valores in doc["tipos"].items():
        tipos[tipo] = {nomes[a]: v for a in por_tipo if (v := _valor(kinds[a], valores.get(a))) is not None}
        dados[tipo] = {n: v for n in rel["parametros"]["texto"] if (v := _valor("texto", valores.get(n))) is not None}
    rel["dados"] = dados
    return params, tipos, {a: (nomes[a], kinds[a]) for a in nomes}


def _laco(pontos):
    """Laço sem os pontos repetidos (as junções do extrator e o fechamento)."""
    saida = []
    for p in pontos:
        if not saida or math.dist(p, saida[-1]) > JUNTA:
            saida.append(p)
    if len(saida) > 1 and math.dist(saida[0], saida[-1]) <= JUNTA:
        saida.pop()
    return saida


def _dentro(ponto, poligono):
    x, y = ponto
    dentro = False
    for (x0, y0), (x1, y1) in zip(poligono, poligono[1:] + poligono[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            dentro = not dentro
    return dentro


def _num(v):
    return round(v, 4) + 0.0


def _plano(forma):
    """(nome do plano, coordenadas do perfil, eixo da normal, sinal, coordenada do plano) ou motivo (str)."""
    pontos = [p for laco in forma["esboco_mm"] for p in laco]
    plano = forma.get("plano")
    if plano:
        normal, origem = plano["normal"], plano["origem_mm"]
    else:  # JSON do extrator: o plano é o eixo em que todos os pontos têm a mesma coordenada; normal suposta +
        planos = [k for k in range(3) if max(p[k] for p in pontos) - min(p[k] for p in pontos) < 1e-6]
        if not planos:
            return "plano do esboço inclinado"
        normal = [1.0 if k == planos[0] else 0.0 for k in range(3)]
        origem = pontos[0]
    k = max(range(3), key=lambda i: abs(normal[i]))
    if abs(abs(normal[k]) - 1) > 1e-6:
        return "plano do esboço inclinado"
    nome, coords = PLANOS[k]
    return nome, coords, k, math.copysign(1, normal[k]), origem[k]


def _no_eixo(lacos, eixo):
    """Ponto a até 0,01 mm do eixo (ruído) vai para 0,001 mm dele, do lado do perfil: o BIMCraft recusa ponto
    que o arredondamento deixe do outro lado. Devolve None se o perfil cruza o eixo."""
    (ax, ay), (bx, by) = eixo
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy)
    dist = [[((p[0] - ax) * dy - (p[1] - ay) * dx) / n for p in laco] for laco in lacos]
    lados = {d > 0 for ds in dist for d in ds if abs(d) > 0.01}
    if len(lados) > 1:
        return None
    lado = 1 if lados == {True} else -1
    for laco, ds in zip(lacos, dist):
        for p, d in zip(laco, ds):
            if abs(d) <= 0.01:
                t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / (n * n)
                p[0] = _num(ax + t * dx + lado * 0.001 * dy / n)
                p[1] = _num(ay + t * dy - lado * 0.001 * dx / n)
    return lacos


def _formas(doc, kinds, rel):
    solidas, vazias = [], []
    for indice, forma in enumerate(doc["formas"]):
        if forma.get("hospedeiro_simulado"):
            rel["formas"]["fora"].append({"indice": indice, "tipo": forma["tipo"],
                                          "motivo": "hospedeiro simulado: a laje/parede de referência do gabarito"})
            continue
        if forma["tipo"] not in ("Extrusion", "Revolution"):
            rel["formas"]["fora"].append({"indice": indice, "tipo": forma["tipo"],
                                          "motivo": "o BIMCraft não varre ao longo de caminho nem mescla perfis"})
            continue
        if not forma.get("esboco_mm"):
            rel["formas"]["fora"].append({"indice": indice, "tipo": forma["tipo"], "motivo": "sem esboço lido"})
            continue
        plano = _plano(forma)
        if isinstance(plano, str):
            rel["formas"]["fora"].append({"indice": indice, "tipo": forma["tipo"], "motivo": plano})
            continue
        nome, (a, b), k, sinal, c0 = plano
        base = {"plane": nome}
        if forma["tipo"] == "Extrusion":
            ini, fim = c0 + sinal * forma["inicio_mm"], c0 + sinal * forma["fim_mm"]
            base["from"], base["to"] = _num(min(ini, fim)), _num(max(ini, fim))
        else:
            if not forma.get("eixo_mm"):
                rel["formas"]["fora"].append({"indice": indice, "tipo": "Revolution",
                                              "motivo": "revolução sem eixo (o JSON do extrator não traz)"})
                continue
            base["axis"] = [[_num(p[a]), _num(p[b])] for p in forma["eixo_mm"]]
            base["from"], base["to"] = _num(forma["angulo_inicio"]), _num(forma["angulo_fim"])
        material = kinds.get(forma.get("parametro_material"), (None, None))
        visivel = kinds.get(forma.get("parametro_visivel"), (None, None))
        lacos = [[[_num(p[a]), _num(p[b])] for p in _laco(laco)] for laco in forma["esboco_mm"]]
        lacos = [l for l in lacos if len(l) >= 3]
        if "axis" in base and _no_eixo(lacos, base["axis"]) is None:
            rel["formas"]["fora"].append({"indice": indice, "tipo": forma["tipo"],
                                          "motivo": "o perfil da revolução cruza o eixo"})
            continue
        externos = [l for l in lacos if sum(_dentro(l[0], o) for o in lacos if o is not l) % 2 == 0]
        for externo in externos:
            item = dict(base, profile=externo)
            if forma["solido"] is False:
                item["void"] = True
            elif material[1] == "material":
                item["material"] = material[0]
            if visivel[1] == "yesno":
                item["visible"] = visivel[0]
            furos = [dict(base, profile=l, void=True) for l in lacos if l is not externo and _dentro(l[0], externo)]
            (vazias if forma["solido"] is False else solidas).extend([item] + ([] if forma["solido"] is False else furos))
        rel["formas"]["convertidas"] += 1
    return solidas + vazias


def converter(doc):
    """(família do BIMCraft, relatório: formas fora, fórmulas fora, dados de texto por tipo)."""
    rel = {"formas": {"convertidas": 0, "fora": []}, "formulas_fora": []}
    params, tipos, kinds = _parametros(doc, rel)
    familia = {"name": doc["familia"]["nome"],
               "category": CATEGORIAS.get(doc["familia"].get("categoria_id"), "generic"),
               "parameters": params, "types": tipos, "forms": _formas(doc, kinds, rel)}
    rel["categoria"] = familia["category"]
    return familia, rel


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m leitor_rfa.bimcraft")
    p.add_argument("familia", help="familia.json v1 (saída do ler-rfa)")
    p.add_argument("-o", "--saida", required=True, help="família do BIMCraft (.json)")
    p.add_argument("--dados", help="relatório + dados de texto por tipo (.json)")
    a = p.parse_args(argv)
    entrada = pathlib.Path(a.familia)
    if not entrada.is_file():
        print(f"recusado: {entrada} não existe", file=sys.stderr)
        return 2
    bruto = entrada.read_bytes()
    familia, rel = converter(json.loads(bruto.decode("utf-8")))
    pathlib.Path(a.saida).write_text(json.dumps(familia, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.dados:
        rel = {"entrada": str(entrada), "entrada_sha256": hashlib.sha256(bruto).hexdigest(), **rel}
        pathlib.Path(a.dados).write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"familia": familia["name"], "formas": len(familia["forms"]),
                      "fora": len(rel["formas"]["fora"]), "formulas_fora": len(rel["formulas_fora"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
