"""Roda o leitor em pastas inteiras e resume a cobertura por versão.

uso: python -m leitor_rfa.lote RAIZ... -o relatorio.json [--jsons DIR] [--gabarito DIR]

Cada seção de cada arquivo sai com o que a conferiu: 'gabarito' (arquivo do gabarito do extrator),
'partatom' (tipos, contra o PartAtom do próprio arquivo) ou 'nao_conferido'.
"""
import argparse
import json
import pathlib
import sys
import time

from .cli import utf8_no_console
from .conferencia import conferir_partatom
from .documento import ler
from .inventario import listar_rfa


def _conferencia(doc, gabarito):
    if doc["origem"]["sha256"] in gabarito:
        return {s: "gabarito" for s in doc["cobertura"]["secoes"]}
    pa = doc.get("partatom") and doc["cobertura"]["secoes"]["tipos"]["estado"] != "nao_decifrado"
    return {s: "partatom" if s == "tipos" and pa else "nao_conferido" for s in doc["cobertura"]["secoes"]}


def _partatom(doc):
    r = conferir_partatom(doc)
    if r is None:
        return None
    return {"tipos": [r["tipos"].iguais, r["tipos"].total], "valores": [r["valores"].iguais, r["valores"].total],
            "fora": r["fora"]}


def _linha(caminho, doc, gabarito=frozenset()):
    cob = doc["cobertura"]
    return {
        "caminho": str(caminho),
        "versao_formato": cob["versao_formato"],
        "build": cob["build"],
        "versao_partatom": cob["versao_partatom"],
        "variante_esquema": cob["variante_esquema"],
        "esquema": cob["esquema"],
        "particoes": cob["particoes"],
        "estados": {s: v["estado"] for s, v in cob["secoes"].items()},
        "notas": {s: v["nota"] for s, v in cob["secoes"].items() if v["nota"]},
        "erros": cob["erros"],
        "partatom": _partatom(doc),
        "conferencia": _conferencia(doc, gabarito),
        "erro": None,
    }


def resumir(arquivos):
    abertos = [a for a in arquivos if not a["erro"]]
    por_versao = {}
    for a in abertos:
        v = por_versao.setdefault(str(a["versao_formato"]), {"arquivos": 0, "secoes": {}})
        v["arquivos"] += 1
        for secao, estado in a["estados"].items():
            cont = v["secoes"].setdefault(secao, {})
            cont[estado] = cont.get(estado, 0) + 1
        for secao, origem in (a.get("conferencia") or {}).items():
            cont = v.setdefault("conferencia", {}).setdefault(secao, {})
            cont[origem] = cont.get(origem, 0) + 1
        if a.get("partatom"):
            pa = v.setdefault("partatom", {"arquivos": 0, "tipos": [0, 0], "valores": [0, 0], "fora": {}})
            pa["arquivos"] += 1
            for k in ("tipos", "valores"):
                pa[k] = [pa[k][0] + a["partatom"][k][0], pa[k][1] + a["partatom"][k][1]]
            for motivo, n in a["partatom"]["fora"].items():
                pa["fora"][motivo] = pa["fora"].get(motivo, 0) + n
    return {"total": len(arquivos), "abertos": len(abertos), "com_erro": len(arquivos) - len(abertos),
            "por_versao": dict(sorted(por_versao.items()))}


def shas_do_gabarito(pasta):
    """sha256 dos arquivos do gabarito (<pasta>/*/familia.json, campo origem.sha256)."""
    if not pasta:
        return frozenset()
    return frozenset(json.loads(f.read_text(encoding="utf-8"))["origem"]["sha256"]
                     for f in pathlib.Path(pasta).glob("*/familia.json"))


def processar(raizes, jsons=None, gabarito=None):
    arquivos, shas = [], shas_do_gabarito(gabarito)
    if jsons:
        pathlib.Path(jsons).mkdir(parents=True, exist_ok=True)
    for f in listar_rfa(raizes):
        inicio = time.monotonic()
        try:
            doc = ler(f)
        except Exception as exc:  # um arquivo ruim vira linha de erro; o lote segue
            arquivos.append({"caminho": str(f), "versao_formato": None, "estados": {}, "erro":
                             f"{type(exc).__name__}: {exc}", "segundos": round(time.monotonic() - inicio, 3)})
            continue
        arquivos.append(dict(_linha(f, doc, shas), segundos=round(time.monotonic() - inicio, 3)))
        if jsons:
            destino = pathlib.Path(jsons) / f"{doc['origem']['sha256']}.json"
            destino.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"raizes": [str(r) for r in raizes], "resumo": resumir(arquivos), "arquivos": arquivos}


def imprimir(rel, segundos):
    r = rel["resumo"]
    print("raízes:", *rel["raizes"], sep="\n  ")
    print(f"total: {r['total']}   abertos: {r['abertos']}   com erro: {r['com_erro']}   ({segundos:.0f} s)")
    secoes = sorted({s for v in r["por_versao"].values() for s in v["secoes"]})
    for versao, v in r["por_versao"].items():
        print(f"versão {versao}: {v['arquivos']} arquivos")
        for s in secoes:
            estados = " · ".join(f"{e} {n}" for e, n in sorted(v["secoes"].get(s, {}).items()))
            conferida = " · ".join(f"{e} {n}" for e, n in sorted(v.get("conferencia", {}).get(s, {}).items()))
            print(f"   {s:<18} {estados:<44} | {conferida}")
        pa = v.get("partatom")
        if pa:
            t, val = pa["tipos"], pa["valores"]
            fora = " · ".join(f"{k} {n}" for k, n in pa["fora"].items())
            print(f"   PartAtom ({pa['arquivos']} arq.): tipos {t[0]}/{t[1]} · valores {val[0]}/{val[1]}"
                  f"{f' ({100 * val[0] / val[1]:.1f}%)' if val[1] else ''} · fora: {fora}")
    for a in [a for a in rel["arquivos"] if a["erro"]][:20]:
        print("  ERRO", a["caminho"], "→", a["erro"])


def main(argv=None):
    utf8_no_console()
    p = argparse.ArgumentParser(prog="python -m leitor_rfa.lote")
    p.add_argument("raizes", nargs="+")
    p.add_argument("-o", "--saida")
    p.add_argument("--jsons", help="grava o JSON de cada família nesta pasta (<sha256>.json)")
    p.add_argument("--gabarito", help="pasta do gabarito: os arquivos dele contam como conferidos")
    a = p.parse_args(argv)
    inicio = time.monotonic()
    rel = processar(a.raizes, a.jsons, a.gabarito)
    imprimir(rel, time.monotonic() - inicio)
    if a.saida:
        pathlib.Path(a.saida).write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if rel["resumo"]["com_erro"] else 0


if __name__ == "__main__":
    sys.exit(main())
