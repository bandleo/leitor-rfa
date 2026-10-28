"""Registros de elementos dentro dos grupos das partições.

Canal 101: a cadeia de cabeçalhos [id][u32 tam][corpo][u32 tam], cujo corpo
começa com a etiqueta de ElementHeader; termina com id todo 0xFF e tam 0.
Canal 102: os objetos [id][u32 hash][u32 tam][corpo][u32 tam], cujo corpo
começa com o u16 da etiqueta da classe do elemento. O id tem 4 B até 2023 e
8 B a partir de 2024 (a largura do ElemTable). Medido em 2012–2018 e 2025.
"""
from dataclasses import dataclass


class ErroRegistro(Exception):
    """O grupo não segue o encadeamento de registros esperado."""


@dataclass(frozen=True)
class Objeto:
    id: int
    etiqueta: int
    corpo: bytes


def _u(dados, pos, n):
    return int.from_bytes(dados[pos:pos + n], "little")


def cabecalhos(dados, largura, etiqueta_eh):
    ids, p, terminal = [], 0, (1 << 8 * largura) - 1
    while p + largura + 4 <= len(dados):
        id_, tam = _u(dados, p, largura), _u(dados, p + largura, 4)
        if id_ == terminal and tam == 0:
            return ids
        ini = p + largura + 4
        fim = ini + tam
        if fim + 4 > len(dados):
            raise ErroRegistro(f"cabeçalho truncado no byte {p}")
        if _u(dados, ini, 2) != etiqueta_eh:
            raise ErroRegistro(f"o registro do byte {p} não começa com a etiqueta de ElementHeader")
        if _u(dados, fim, 4) != tam:
            raise ErroRegistro(f"checkback do registro do byte {p} não confere")
        ids.append(id_)
        p = fim + 4
    if p == len(dados):  # grupo intermediário: o terminador só vem no último grupo da cadeia
        return ids
    raise ErroRegistro(f"sobra de {len(dados) - p} B no fim da cadeia de cabeçalhos (byte {p})")


def objetos(dados, largura):
    out, p, terminal = [], 0, (1 << 8 * largura) - 1
    while p < len(dados):
        if p + largura + 8 > len(dados):
            raise ErroRegistro(f"objeto truncado no byte {p}")
        id_ = _u(dados, p, largura)
        if id_ == terminal:
            break
        tam = _u(dados, p + largura + 4, 4)
        ini = p + largura + 8
        fim = ini + tam
        if tam < 2 or fim + 4 > len(dados):
            raise ErroRegistro(f"objeto truncado no byte {p}")
        if _u(dados, fim, 4) != tam:
            raise ErroRegistro(f"checkback do objeto do byte {p} não confere")
        corpo = dados[ini:fim]
        out.append(Objeto(id_, _u(corpo, 0, 2), corpo))
        p = fim + 4
    return out
