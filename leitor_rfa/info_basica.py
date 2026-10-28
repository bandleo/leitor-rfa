"""BasicFileInfo: versão do formato, build e caminho em que o arquivo foi salvo.

Layout medido nas versões 2012–2025: u32 versão da estrutura, 10 B, e então
strings UTF-16LE com prefixo u32 de tamanho (em caracteres). Até 2018 a
primeira é "Autodesk Revit [Produto] AAAA (Build: B)"; em 2025 ela é só "AAAA"
e o build vem na seguinte. Depois vem o caminho salvo.
"""
import re
from dataclasses import dataclass

_INICIO_TEXTOS = 14
_PRODUTO = re.compile(r"^(Autodesk Revit(?: [A-Za-z]+)? (\d{4})) \(Build: (.+)\)$")


@dataclass(frozen=True)
class InfoBasica:
    versao_estrutura: int | None = None
    versao_formato: int | None = None
    produto: str | None = None
    build: str | None = None
    caminho_salvo: str | None = None


def _textos(dados, pos, quantos):
    out = []
    for _ in range(quantos):
        if pos + 4 > len(dados):
            break
        n = int.from_bytes(dados[pos:pos + 4], "little")
        fim = pos + 4 + 2 * n
        if n > 4096 or fim > len(dados):
            break
        out.append(dados[pos + 4:fim].decode("utf-16-le", errors="replace"))
        pos = fim
    return out


def ler_info_basica(dados):
    if not dados or len(dados) < 4:
        return InfoBasica()
    estrutura = int.from_bytes(dados[:4], "little")
    textos = _textos(dados, _INICIO_TEXTOS, 3)
    if not textos:
        return InfoBasica(versao_estrutura=estrutura)
    primeiro = textos[0]
    if re.fullmatch(r"\d{4}", primeiro):
        return InfoBasica(estrutura, int(primeiro), None,
                          textos[1] if len(textos) > 1 else None,
                          textos[2] if len(textos) > 2 else None)
    m = _PRODUTO.match(primeiro)
    if m:
        return InfoBasica(estrutura, int(m.group(2)), m.group(1), m.group(3),
                          textos[1] if len(textos) > 1 else None)
    return InfoBasica(versao_estrutura=estrutura)
