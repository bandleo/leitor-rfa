"""Relatório do esquema e das partições por versão, a partir de relatórios do lote.

uso: python -m leitor_rfa.relatorio_esquema lote-a.json [lote-b.json ...] [-o resumo.json]
"""
import argparse
import json
import pathlib
import sys

from .cli import utf8_no_console


def resumir_esquemas(linhas):
    por = {}
    for l in linhas:
        v = "desconhecida" if l.get("versao_formato") is None else str(l["versao_formato"])
        r = por.setdefault(v, {"versao": v, "arquivos": 0, "esquema_lido": 0, "variantes": {}, "classes": None,
                               "esquemas_distintos": set(), "particoes": {}, "erros_abertura": 0})
        r["arquivos"] += 1
        if l.get("erro"):
            r["erros_abertura"] += 1
            continue
        estados = l.get("estados", {})
        if estados.get("esquema") == "decifrado" and l.get("esquema"):
            r["esquema_lido"] += 1
            r["variantes"][l["variante_esquema"]] = r["variantes"].get(l["variante_esquema"], 0) + 1
            n = l["esquema"]["classes"]
            r["classes"] = [min(r["classes"][0], n), max(r["classes"][1], n)] if r["classes"] else [n, n]
            r["esquemas_distintos"].add(l["esquema"]["sha256"])
        if estados.get("particoes"):
            r["particoes"][estados["particoes"]] = r["particoes"].get(estados["particoes"], 0) + 1
    saida = []
    for v in sorted(por, key=lambda v: (v == "desconhecida", v)):
        r = por[v]
        r["esquemas_distintos"] = len(r["esquemas_distintos"])
        saida.append(r)
    return saida


def imprimir(resumo):
    cab = f"{'versão':<13}{'arquivos':>9}{'esquema lido':>14}  {'variante':<12}{'classes':<12}{'esquemas':>9}  partições (estado: arquivos)      erros"
    print(cab)
    print("-" * len(cab))
    for r in resumo:
        classes = "-" if not r["classes"] else (str(r["classes"][0]) if r["classes"][0] == r["classes"][1]
                                                 else f"{r['classes'][0]}–{r['classes'][1]}")
        variantes = ", ".join(r["variantes"]) or "-"
        part = " · ".join(f"{e}: {n}" for e, n in sorted(r["particoes"].items())) or "-"
        print(f"{r['versao']:<13}{r['arquivos']:>9}{r['esquema_lido']:>14}  {variantes:<12}{classes:<12}"
              f"{r['esquemas_distintos']:>9}  {part:<33}{r['erros_abertura']:>5}")
    tot = {k: sum(r[k] for r in resumo) for k in ("arquivos", "esquema_lido", "erros_abertura")}
    print(f"{'total':<13}{tot['arquivos']:>9}{tot['esquema_lido']:>14}{'':>59}{tot['erros_abertura']:>5}")


def completo(resumo):
    return all(r["esquema_lido"] == r["arquivos"] - r["erros_abertura"] and set(r["particoes"]) <= {"decifrado"}
               and r["erros_abertura"] == 0 for r in resumo)


def main(argv=None):
    utf8_no_console()
    p = argparse.ArgumentParser(prog="python -m leitor_rfa.relatorio_esquema")
    p.add_argument("relatorios", nargs="+", help="relatórios JSON do leitor_rfa.lote")
    p.add_argument("-o", "--saida")
    a = p.parse_args(argv)
    linhas = []
    for rel in a.relatorios:
        linhas += json.loads(pathlib.Path(rel).read_text(encoding="utf-8"))["arquivos"]
    resumo = resumir_esquemas(linhas)
    imprimir(resumo)
    if a.saida:
        pathlib.Path(a.saida).write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if completo(resumo) else 1


if __name__ == "__main__":
    sys.exit(main())
