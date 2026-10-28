"""Global/ElemTable: o índice dos ElementIds do arquivo, com o dono de cada um.

Porte de rvt-rs (Apache-2.0) src/elem_table.rs. Depois de um u16 (a etiqueta da
classe ElemTable no esquema do próprio arquivo) e de um u32 com o número de
registros vêm os registros: 28 B com ids de 32 bits até 2023
([u32 id][u32 id][16 B][u32 dono]) e 40 B com ids de 64 bits a partir de 2024
([u64 id][12 B][u64 id][u64 dono][u32]). A largura é a que fecha: os registros
cabem e os ids sobem estritamente; se as duas fecharem, a de menor rabo. O rabo
não tem teto: 19 B em 2012–2018, até 280 B nas famílias de 2025 e de 8 a 31 KB
nas Steel Connections 2025, que trazem outra estrutura depois dos registros.
Dono 0 ou todo 0xFF = sem dono.
"""
from dataclasses import dataclass

LAYOUTS = {4: (28, 24, 4), 8: (40, 28, 8)}  # largura do id: (tamanho do registro, posição do dono, bytes do dono)
SEM_DONO = (0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF)


class ErroElemTable(Exception):
    """O ElemTable não fecha em nenhuma largura conhecida."""


@dataclass(frozen=True)
class ElemTable:
    largura_id: int
    donos: dict
    sobra: int


def _ler(inflado, n, largura):
    tam, pos_dono, bytes_dono = LAYOUTS[largura]
    donos, anterior = {}, -1
    for i in range(n):
        base = 6 + tam * i
        id_ = int.from_bytes(inflado[base:base + largura], "little")
        if id_ <= anterior:
            return None
        anterior = id_
        dono = int.from_bytes(inflado[base + pos_dono:base + pos_dono + bytes_dono], "little")
        donos[id_] = None if dono in SEM_DONO else dono
    return donos


def ler_elemtable(inflado, esquema):
    if len(inflado) < 6:
        raise ErroElemTable(f"ElemTable truncado ({len(inflado)} B)")
    etiqueta, esperada = int.from_bytes(inflado[:2], "little"), esquema.etiqueta("ElemTable")
    if etiqueta != esperada:
        raise ErroElemTable(f"etiqueta {etiqueta} difere da de ElemTable no esquema ({esperada})")
    n = int.from_bytes(inflado[2:6], "little")
    validas = []
    for largura, (tam, _, _) in LAYOUTS.items():
        sobra = len(inflado) - 6 - tam * n
        if sobra >= 0:
            donos = _ler(inflado, n, largura)
            if donos is not None:
                validas.append(ElemTable(largura, donos, sobra))
    if validas:
        return min(validas, key=lambda et: et.sobra)
    raise ErroElemTable(f"nenhuma largura de registro (28 B ou 40 B) fecha {n} registros em {len(inflado)} B")
