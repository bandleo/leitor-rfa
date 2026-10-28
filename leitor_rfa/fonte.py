"""Ponto único para quem consome famílias: o familia.json v1 de um .rfa.

Cada seção vem do leitor quando ele a decifra; senão, de uma extração feita dentro do Revit, se houver
`<extracao>/<sha256 do .rfa>/familia.json` no mesmo esquema v1 (opcional). Geometria, importações e IFC só
uma extração assim tem. `cobertura.origem`
diz de onde veio cada seção ('leitor' ou 'extrator').
"""
import json
import pathlib

from .documento import ler_com_miniatura

SECOES = ("familia", "tipos", "parametros", "aninhadas", "planos_referencia", "cotas", "formas")
SO_DO_EXTRATOR = ("geometria", "importacoes", "ifc")


def _extracao(pasta, sha):
    if not pasta:
        return None
    arquivo = pathlib.Path(pasta) / sha / "familia.json"
    if not arquivo.is_file():
        return None
    ext = json.loads(arquivo.read_text(encoding="utf-8"))
    return ext if ext.get("versao_esquema") == 1 else None


def ler_familia(caminho, extracao=None, nome_arquivo=None):
    """(documento v1, png | None). `extracao`: pasta com os JSONs do extrator por sha256."""
    doc, png = ler_com_miniatura(caminho, nome_arquivo)
    ext = _extracao(extracao, doc["origem"]["sha256"])
    secoes, origem = doc["cobertura"]["secoes"], {}
    for secao in SECOES:
        if ext is not None and secao in ext and secoes[secao]["estado"] != "decifrado":
            doc[secao] = ext[secao]
            origem[secao] = "extrator"
        else:
            origem[secao] = "leitor"
    for chave in SO_DO_EXTRATOR:
        if ext is not None:
            doc[chave] = ext.get(chave)
        origem[chave] = "leitor" if ext is None else "extrator"
    doc["cobertura"]["origem"] = origem
    return doc, png
