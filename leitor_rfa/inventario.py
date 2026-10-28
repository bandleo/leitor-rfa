"""Inventário de versões (BasicFileInfo + PartAtom) de pastas de .rfa.

uso: python -m leitor_rfa.inventario RAIZ... -o relatorio.json
"""
import argparse
import collections
import json
import pathlib
import re
import sys

from .cli import utf8_no_console
from .contenedor import abrir
from .info_basica import ler_info_basica

_VERSAO_PARTATOM = re.compile(rb"<A:product-version>\s*(\d+)\s*<")


def listar_rfa(raizes):
    for raiz in map(pathlib.Path, raizes):
        if raiz.is_file():
            yield raiz
        else:
            yield from sorted(p for p in raiz.rglob("*") if p.is_file() and p.suffix.lower() == ".rfa")


def inventariar(raizes):
    linhas = []
    for f in listar_rfa(raizes):
        linha = {"caminho": str(f), "tamanho": f.stat().st_size, "versao_estrutura": None, "versao_formato": None,
                 "build": None, "versao_partatom": None, "erro": None}
        try:
            with abrir(f) as c:
                info = ler_info_basica(c.ler("BasicFileInfo"))
                partatom = c.ler("PartAtom") or b""
            m = _VERSAO_PARTATOM.search(partatom)
            linha.update(versao_estrutura=info.versao_estrutura, versao_formato=info.versao_formato,
                         build=info.build, versao_partatom=m.group(1).decode() if m else None)
        except Exception as exc:  # um arquivo ruim vira linha de erro; o inventário segue
            linha["erro"] = f"{type(exc).__name__}: {exc}"
        linhas.append(linha)
    return linhas


def resumir(linhas):
    ok = [l for l in linhas if not l["erro"]]
    por_versao = collections.Counter(l["versao_formato"] for l in ok)
    return {
        "total": len(linhas),
        "erros": len(linhas) - len(ok),
        "por_versao": dict(sorted(por_versao.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))),
        "por_versao_partatom": dict(sorted(collections.Counter(
            f"{l['versao_formato']}/{l['versao_partatom']}" for l in ok).items())),
        "por_versao_estrutura": dict(sorted(collections.Counter(
            f"{l['versao_formato']}/{l['versao_estrutura']}" for l in ok).items())),
    }


def imprimir(raizes, linhas, r):
    print("raízes:", *raizes, sep="\n  ")
    print(f"total: {r['total']}   abertos: {r['total'] - r['erros']}   erros: {r['erros']}")
    print(f"{'versão':<8}{'arquivos':>9}   PartAtom (versão: arquivos)            estrutura BFI")
    for versao, n in r["por_versao"].items():
        chave = f"{versao}/"
        pa = " · ".join(f"{k.split('/')[1]}: {v}" for k, v in r["por_versao_partatom"].items() if k.startswith(chave))
        est = ", ".join(k.split("/")[1] for k in r["por_versao_estrutura"] if k.startswith(chave))
        print(f"{'?' if versao is None else versao:<8}{n:>9}   {pa:<38} {est}")
    for l in [l for l in linhas if l["erro"]][:20]:
        print("  ERRO", l["caminho"], "→", l["erro"])


def main(argv=None):
    utf8_no_console()
    p = argparse.ArgumentParser(prog="python -m leitor_rfa.inventario")
    p.add_argument("raizes", nargs="+")
    p.add_argument("-o", "--saida")
    a = p.parse_args(argv)
    linhas = inventariar(a.raizes)
    if not linhas:
        print("nenhum .rfa encontrado", file=sys.stderr)
        return 2
    r = resumir(linhas)
    imprimir(a.raizes, linhas, r)
    if a.saida:
        rel = {"raizes": a.raizes, "resumo": {k: ({str(x): y for x, y in v.items()} if isinstance(v, dict) else v)
                                               for k, v in r.items()}, "arquivos": linhas}
        pathlib.Path(a.saida).write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
