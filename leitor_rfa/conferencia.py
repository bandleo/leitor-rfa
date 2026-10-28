"""Compara a saída do leitor com o gabarito (familia.json do extrator), seção a seção.

uso: python -m leitor_rfa.conferencia --gabarito <pasta> [-o relatorio.json]
"""
import argparse
import collections
import json
import math
import pathlib
import re
import sys
from dataclasses import dataclass

from .cli import utf8_no_console
from .documento import ler

CAMPOS_PARAMETRO = ("nome", "grupo", "instancia", "compartilhado", "guid", "tipo_dado", "reporting")
# listas comparadas campo a campo, item a item na ordem do extrator (id do elemento)
CAMPOS_LISTA = {
    "planos_referencia": ("nome", "referencia"),
    "planos.extremos": ("inicio_mm", "fim_mm"),
    "cotas": ("rotulo", "valor_mm", "referencias"),
    "aninhadas": ("familia", "tipo", "categoria", "compartilhada", "quantidade"),
    "formas": ("tipo", "solido", "parametro_visivel", "parametro_material", "inicio_mm", "fim_mm"),
}
TOLERANCIA_MM = 1e-6
TOLERANCIA_ESBOCO_MM = 0.1
ORDEM = ("familia.nome", "tipos.nomes", "tipos.valores", "parametros", "formulas") + tuple(CAMPOS_LISTA) + (
    "formas.esboco", "contagem.planos", "contagem.cotas", "contagem.formas", "contagem.aninhadas", "contagem.todas")


@dataclass(frozen=True)
class Resultado:
    iguais: int
    total: int
    estado: str


def _estado(doc, secao):
    return doc.get("cobertura", {}).get("secoes", {}).get(secao, {}).get("estado", "nao_decifrado")


def _igual(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return a == b


def _igual_mm(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_igual_mm(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b, rel_tol=0, abs_tol=TOLERANCIA_MM)
    return a == b


def _lista(doc, gab, secao, campos, estado):
    """Itens na mesma posição, campo a campo; item a mais ou a menos conta todos os seus campos contra."""
    g, d = gab[secao], doc.get(secao) or []
    total = max(len(g), len(d)) * len(campos)
    if estado == "nao_decifrado":
        return Resultado(0, total, estado)
    iguais = sum((_igual_mm if c.endswith("_mm") else _igual)(a.get(c), b.get(c))
                 for a, b in zip(d, g) for c in campos)
    return Resultado(iguais, total, estado)


def _cobre(a, b, tol2):
    return all(any((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 <= tol2 for q in b) for p in a)


def esboco_igual(lido, esperado, tol=TOLERANCIA_ESBOCO_MM):
    """Mesmo nº de laços e cada laço do gabarito com um laço lido de vértices iguais (dos dois lados, até `tol` mm).
    Não depende do ponto inicial nem do sentido do laço, nem da ordem dos laços."""
    lido, esperado = lido or [], esperado or []
    if len(lido) != len(esperado):
        return False
    livres = list(lido)
    for laco in esperado:
        for k, outro in enumerate(livres):
            if _cobre(laco, outro, tol * tol) and _cobre(outro, laco, tol * tol):
                del livres[k]
                break
        else:
            return False
    return True


def _sem_espacos(texto):
    return re.sub(r"\s+", "", texto or "")


def comparar(doc, gab):
    r = {}
    nd = lambda secao: _estado(doc, secao) == "nao_decifrado"  # noqa: E731
    if "familia" in gab:
        igual = (doc.get("familia") or {}).get("nome") == gab["familia"].get("nome")
        r["familia.nome"] = Resultado(0 if nd("familia") else int(igual), 1, _estado(doc, "familia"))
    if "tipos" in gab:
        gt, dt = gab["tipos"], doc.get("tipos") or {}
        iguais = 0 if nd("tipos") else len(set(gt) & set(dt))
        r["tipos.nomes"] = Resultado(iguais, len(set(gt) | set(dt)), _estado(doc, "tipos"))
        total = sum(len(ps) for ps in gt.values())
        iguais = 0
        if not nd("tipos"):
            for tipo, ps in gt.items():
                for nome, valor in ps.items():
                    lido = (dt.get(tipo) or {}).get(nome)
                    iguais += bool(lido) and _igual(lido.get("bruto"), valor.get("bruto"))
        r["tipos.valores"] = Resultado(iguais, total, _estado(doc, "tipos"))
    if "parametros" in gab:
        gp = gab["parametros"]
        dp = {p.get("nome"): p for p in doc.get("parametros") or []}
        iguais = 0
        if not nd("parametros"):
            for p in gp:
                lido = dp.get(p.get("nome"))
                if lido:
                    iguais += sum(_igual(lido.get(c), p.get(c)) for c in CAMPOS_PARAMETRO)
        r["parametros"] = Resultado(iguais, len(gp) * len(CAMPOS_PARAMETRO), _estado(doc, "parametros"))
        com_formula = [p for p in gp if p.get("formula")]
        iguais = 0
        if not nd("parametros"):
            iguais = sum(_sem_espacos((dp.get(p["nome"]) or {}).get("formula")) == _sem_espacos(p["formula"])
                         for p in com_formula)
        r["formulas"] = Resultado(iguais, len(com_formula), _estado(doc, "parametros"))
    for linha in CAMPOS_LISTA:
        secao = "planos_referencia" if linha == "planos.extremos" else linha
        if secao in gab:
            estado = _estado(doc, secao)
            if linha == "planos.extremos" and estado != "decifrado":
                estado = "nao_decifrado"  # extremos só contam quando a seção de planos estiver inteira
            r[linha] = _lista(doc, gab, secao, CAMPOS_LISTA[linha], estado)
    if "formas" in gab:
        g, d, estado = gab["formas"], doc.get("formas") or [], _estado(doc, "formas")
        iguais = 0 if estado == "nao_decifrado" else sum(
            esboco_igual(a.get("esboco_mm"), b.get("esboco_mm")) for a, b in zip(d, g))
        r["formas.esboco"] = Resultado(iguais, max(len(g), len(d)), estado)
    if all(k in gab for k in ("planos_referencia", "cotas", "formas", "aninhadas")):
        r.update(_contagens(doc, gab))
    return r


def _contagens(doc, gab):
    """Contagem por classe: uma linha por família, igual ou não ao extrator."""
    estado = _estado(doc, "elementos")
    lidas = ((doc.get("cobertura") or {}).get("elementos") or {}).get("contagens")
    esperadas = {"planos": len(gab["planos_referencia"]), "cotas": len(gab["cotas"]),
                 "formas": dict(collections.Counter(f["tipo"] for f in gab["formas"])),
                 "aninhadas": sum(a.get("quantidade", 1) for a in gab["aninhadas"])}
    r, todas = {}, True
    for chave, esperado in esperadas.items():
        ok = estado != "nao_decifrado" and lidas is not None and lidas.get(chave) == esperado
        todas &= ok
        r[f"contagem.{chave}"] = Resultado(int(ok), 1, estado)
    r["contagem.todas"] = Resultado(int(todas), 1, estado)
    return r


# Oráculo fraco (fora do gabarito): o PartAtom traz, por tipo, o valor de exibição de cada parâmetro.
PARA_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "ft": 304.8, "in": 25.4}
SIM_NAO = {"yes": 1, "sim": 1, "true": 1, "1": 1, "no": 0, "não": 0, "nao": 0, "false": 0, "0": 0}


def _numero(texto):
    """(valor, meia unidade da última casa exibida) ou None se o texto não é um número."""
    t = (texto or "").strip().replace(",", ".")
    m = re.fullmatch(r"-?\d+(?:\.(\d+))?", t)
    if not m:
        return None
    return float(t), 0.5 * 10 ** -len(m.group(1) or "") + 1e-9


def _valor_partatom(pa, lido):
    """'igual', 'diferente' ou o motivo de não dar para comparar."""
    if lido is None:
        return "sem_par"
    bruto = lido.get("bruto")
    if bruto is None:
        return "sem_valor_lido"
    unidade, valor = pa.get("unidade"), pa.get("valor") or ""
    if (pa.get("tipo_parametro") or "").lower() in ("yes/no", "sim/não"):
        esperado = SIM_NAO.get(valor.strip().lower())
        if esperado is None:
            return "valor_sem_traducao"
        return "igual" if int(bruto) == esperado else "diferente"
    if unidade or isinstance(bruto, (int, float)):
        texto = valor.strip().removesuffix(unidade).strip() if unidade else valor  # 2025 repete a unidade: "9 cm"
        n = _numero(texto)
        if n is None:
            return "valor_sem_traducao"
        if unidade in PARA_MM and lido.get("mm") is not None:
            lido_na_unidade = lido["mm"] / PARA_MM[unidade]
        elif unidade in ("°", "deg") and isinstance(bruto, float):
            lido_na_unidade = math.degrees(bruto)
        elif unidade:
            return "unidade_sem_conversao"
        else:
            lido_na_unidade = bruto
        return "igual" if abs(lido_na_unidade - n[0]) <= n[1] else "diferente"
    texto = str(bruto).replace("\r\n", "\n").strip()  # o PartAtom é XML: \r\n vira \n
    return "igual" if texto == valor.strip() else "diferente"


def conferir_partatom(doc):
    """Tipos (nomes) e valores por tipo contra o PartAtom do próprio arquivo; None se não há PartAtom.
    'fora' conta o que não dá para comparar: nome sem par (parâmetro de sistema em outro idioma, não lido),
    valor que o leitor ainda não lê, unidade sem conversão, valor de exibição sem tradução, tipo implícito."""
    pa = doc.get("partatom")
    if not pa:
        return None
    estado = _estado(doc, "tipos")
    dt, pat = doc.get("tipos") or {}, dict(pa["tipos"])
    cont = collections.Counter()
    nome_familia = (doc.get("familia") or {}).get("nome")
    if len(pat) == 1 and next(iter(pat)) not in dt and (not dt or list(dt) == [nome_familia]):
        # tipo implícito (sem nome, ou tabela de tipos vazia): o PartAtom o chama por um nome interno
        # (hash ou '<arquivo>.rfa_N'); os valores dele são comparados com os do tipo único lido
        cont["tipo_implicito"] += 1
        pat = {nome_familia: next(iter(pat.values()))} if dt else {}
        r = {"tipos": Resultado(0, 0, estado)}
    else:
        r = {"tipos": Resultado(len(set(pat) & set(dt)), len(set(pat) | set(dt)), estado)}
    for tipo, params in pat.items():
        if tipo not in dt:
            continue
        for nome, v in params.items():
            cont[_valor_partatom(v, dt[tipo].get(nome))] += 1
    iguais, diferentes = cont.pop("igual", 0), cont.pop("diferente", 0)
    r["valores"] = Resultado(iguais, iguais + diferentes, estado)
    r["fora"] = {k: n for k, n in sorted(cont.items()) if n}
    return r


def agregar(itens):
    tab = {}
    for versao, resultados in itens:
        for secao, x in resultados.items():
            c = tab.setdefault(versao, {}).setdefault(secao, {"iguais": 0, "total": 0, "arquivos": 0, "estados": {}})
            c["iguais"] += x.iguais
            c["total"] += x.total
            c["arquivos"] += 1
            c["estados"][x.estado] = c["estados"].get(x.estado, 0) + 1
    return tab


def _celula(c):
    if not c:
        return "-"
    if set(c["estados"]) == {"nao_decifrado"}:
        return f"{c['iguais']}/{c['total']} nd"
    pct = 100 * c["iguais"] / c["total"] if c["total"] else 100.0
    return f"{c['iguais']}/{c['total']} {pct:.0f}%"


def tabela(tab):
    versoes = sorted(tab, key=lambda v: (v is None, str(v)))
    total = {}
    for v in versoes:
        for secao, c in tab[v].items():
            t = total.setdefault(secao, {"iguais": 0, "total": 0, "arquivos": 0, "estados": {}})
            t["iguais"] += c["iguais"]
            t["total"] += c["total"]
            t["arquivos"] += c["arquivos"]
            for e, n in c["estados"].items():
                t["estados"][e] = t["estados"].get(e, 0) + n
    colunas = [(v, tab[v]) for v in versoes] + [("total", total)]
    cab = ["seção"] + [f"{'?' if v is None else v} (n={max((c['arquivos'] for c in d.values()), default=0)})"
                       for v, d in colunas]
    linhas = [cab] + [[s] + [_celula(d.get(s)) for _, d in colunas] for s in ORDEM]
    larg = [max(len(l[i]) for l in linhas) for i in range(len(cab))]
    out = ["  ".join(x.ljust(larg[i]) for i, x in enumerate(l)) for l in linhas]
    out.insert(1, "  ".join("-" * w for w in larg))
    return "\n".join(out) + "\n(nd = seção ainda não decifrada pelo leitor; não conta como erro)"


def main(argv=None):
    utf8_no_console()
    p = argparse.ArgumentParser(prog="python -m leitor_rfa.conferencia")
    p.add_argument("--gabarito", required=True, help="pasta com <sha>/familia.rfa + familia.json")
    p.add_argument("-o", "--saida", help="relatório JSON")
    a = p.parse_args(argv)
    raiz = pathlib.Path(a.gabarito)
    pastas = sorted(d for d in raiz.iterdir() if (d / "familia.rfa").is_file() and (d / "familia.json").is_file())
    itens, erros = [], []
    for d in pastas:
        gab = json.loads((d / "familia.json").read_text(encoding="utf-8"))
        try:  # a cópia do gabarito chama-se familia.rfa; o nome da família é o do arquivo original
            doc = ler(d / "familia.rfa", nome_arquivo=pathlib.PureWindowsPath(gab["origem"]["caminho"]).name)
        except Exception as exc:  # um arquivo ruim não derruba a conferência
            erros.append({"pasta": d.name, "erro": f"{type(exc).__name__}: {exc}"})
            continue
        itens.append((doc["cobertura"]["versao_formato"], comparar(doc, gab)))
    tab = agregar(itens)
    print(tabela(tab))
    print(f"arquivos: {len(pastas)}  conferidos: {len(itens)}  erros: {len(erros)}")
    for e in erros:
        print("  ERRO", e["pasta"], e["erro"])
    if a.saida:
        rel = {"arquivos": len(pastas), "erros": erros,
               "por_versao": {str(v): s for v, s in tab.items()}}
        pathlib.Path(a.saida).write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
