"""PartAtom: XML Atom com título, categoria, versão e os tipos da família.

Os valores do PartAtom são de exibição (arredondados, com nome de parâmetro de
sistema no idioma do Revit que salvou). Servem de oráculo fraco: os nomes dos
tipos são confiáveis; os valores não substituem os das partições.
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ATOM = "{http://www.w3.org/2005/Atom}"
PA = "{urn:schemas-autodesk-com:partatom}"


class ErroPartAtom(Exception):
    """XML do PartAtom ilegível."""


@dataclass(frozen=True)
class ParametroPA:
    nome: str
    valor: str
    tipo: str | None
    guid: str | None
    tipo_parametro: str | None
    unidade: str | None


@dataclass(frozen=True)
class PartAtom:
    titulo: str | None
    categoria: str | None
    versao_produto: str | None
    omniclass: str | None
    tipos: dict


def _nome_local(tag):
    return tag.rsplit("}", 1)[-1]


def ler_partatom(dados):
    try:
        raiz = ET.fromstring(dados)
    except ET.ParseError as exc:
        raise ErroPartAtom(f"XML inválido: {exc}") from exc
    categoria = omniclass = None
    for cat in raiz.findall(f"{ATOM}category"):
        esquema, termo = cat.findtext(f"{ATOM}scheme"), cat.findtext(f"{ATOM}term")
        if esquema == "adsk:revit:grouping" and categoria is None:
            categoria = termo
        elif esquema == "std:oc1" and omniclass is None:
            omniclass = termo
    tipos = {}
    for parte in raiz.iter(f"{PA}part"):
        tipos[parte.findtext(f"{ATOM}title")] = [
            ParametroPA(nome=el.get("displayName") or _nome_local(el.tag), valor=el.text or "",
                        tipo=el.get("type"), guid=el.get("id"), tipo_parametro=el.get("typeOfParameter"),
                        unidade=el.get("units"))
            for el in parte if el.tag != f"{ATOM}title"
        ]
    return PartAtom(titulo=raiz.findtext(f"{ATOM}title"), categoria=categoria,
                    versao_produto=raiz.findtext(f".//{PA}design-file/{PA}product-version"),
                    omniclass=omniclass, tipos=tipos)
