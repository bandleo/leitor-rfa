"""ler-rfa arquivo.rfa -o familia.json"""
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
    p = argparse.ArgumentParser(prog="ler-rfa", description="Lê uma família do Revit (.rfa) sem o Revit.")
    p.add_argument("arquivo", nargs="?")
    p.add_argument("-o", "--saida", help="JSON de saída (padrão: imprime na tela)")
    p.add_argument("--miniatura", help="grava a miniatura PNG neste arquivo")
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
    texto = json.dumps(doc, ensure_ascii=False, indent=1)
    if a.saida:
        pathlib.Path(a.saida).write_text(texto, encoding="utf-8")
    else:
        print(texto)
    return 0
