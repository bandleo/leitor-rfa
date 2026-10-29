"""ler-rfa arquivo.rfa -o familia.json  |  ler-rfa visualizar [arquivo.rfa]"""
import argparse
import json
import pathlib
import sys

from . import __version__
from .contenedor import ErroArquivo
from .documento import ler_com_miniatura


def utf8_no_console():
    # o ler-rfa.exe não recebe -X utf8: sem isso o console do Windows escreve cp1252
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    utf8_no_console()
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["visualizar"]:
        from .servir import main as visualizar
        return visualizar(argv[1:])
    p = argparse.ArgumentParser(prog="ler-rfa", description="Lê uma família do Revit (.rfa) sem o Revit. "
                                "`ler-rfa visualizar` abre a página com os dados e o 3D.")
    p.add_argument("arquivo", nargs="?")
    p.add_argument("-o", "--saida", help="JSON de saída (padrão: imprime na tela)")
    p.add_argument("--miniatura", help="grava a miniatura PNG neste arquivo")
    p.add_argument("--glb", help="grava o 3D (B-rep salvo pelo Revit) neste GLB")
    p.add_argument("--version", action="store_true", help="mostra a versão")
    a = p.parse_args(argv)
    if a.version:
        print(f"ler-rfa {__version__}")
        return 0
    if not a.arquivo:
        p.print_usage(sys.stderr)
        return 2
    arquivo = pathlib.Path(a.arquivo)
    if not arquivo.is_file():
        print(f"ler-rfa: arquivo não encontrado: {arquivo}", file=sys.stderr)
        return 2
    try:
        doc, png = ler_com_miniatura(arquivo)
    except ErroArquivo as exc:
        print(f"ler-rfa: {exc}", file=sys.stderr)
        return 1
    if a.miniatura:
        if png:
            pathlib.Path(a.miniatura).write_bytes(png)
        else:
            print(f"ler-rfa: sem miniatura ({doc['cobertura']['secoes']['miniatura']['nota']})", file=sys.stderr)
    if a.glb:
        from .malha import para_glb, partes
        r = partes(arquivo)
        pathlib.Path(a.glb).write_bytes(para_glb(r))
        if r["completude"]["estado"] != "completo":
            print(f"ler-rfa: 3D {r['completude']['estado']}: {'; '.join(r['completude']['faltando'][:3])}",
                  file=sys.stderr)
    texto = json.dumps(doc, ensure_ascii=False, indent=1)
    if a.saida:
        pathlib.Path(a.saida).write_text(texto, encoding="utf-8")
    else:
        print(texto)
    return 0
