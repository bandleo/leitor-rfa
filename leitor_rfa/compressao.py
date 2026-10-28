"""Descompressão dos streams do .rfa.

Porte de rvt-rs (Apache-2.0) src/compression.rs: os streams paginados guardam
cada página completa como 64.896 B de dados + 353 B de checksum, que saem
antes de inflar; a última página, curta, fica inteira.
"""
import re
import zlib

PAGINA = 65_249
CARGA = 64_896
LIMITE = 256 * 1024 * 1024
GZIP = b"\x1f\x8b\x08"


class ErroCompressao(Exception):
    """Membro gzip ausente, truncado, com CRC/ISIZE errado ou maior que o limite."""

_PAGINADOS_GLOBAL = {"Formats/Latest", "Global/ContentDocuments", "Global/DocumentIncrementTable",
                     "Global/ElemTable", "Global/History", "Global/Latest", "Global/PartitionTable"}


def stream_paginado(nome):
    return nome in _PAGINADOS_GLOBAL or re.fullmatch(r"Partitions/[^/]+", nome) is not None


def tirar_checksum_paginas(dados):
    completas = len(dados) // PAGINA
    partes = [dados[i * PAGINA:i * PAGINA + CARGA] for i in range(completas)]
    partes.append(dados[completas * PAGINA:])
    return b"".join(partes)


def _tamanho_cabecalho(dados, pos):
    if dados[pos:pos + 3] != GZIP or len(dados) < pos + 10:
        raise ErroCompressao(f"sem assinatura gzip no byte {pos}")
    flg, p = dados[pos + 3], pos + 10
    if flg & 0x04:  # FEXTRA
        p += 2 + int.from_bytes(dados[p:p + 2], "little")
    for bit in (0x08, 0x10):  # FNAME, FCOMMENT
        if flg & bit:
            fim = dados.find(b"\0", p)
            if fim < 0:
                raise ErroCompressao(f"cabeçalho gzip truncado no byte {pos}")
            p = fim + 1
    if flg & 0x02:  # FHCRC
        p += 2
    if p > len(dados):
        raise ErroCompressao(f"cabeçalho gzip truncado no byte {pos}")
    return p - pos


def inflar_membro(dados, pos=0, limite=LIMITE):
    """Infla o membro gzip que começa em `pos`, conferindo CRC32 e ISIZE.
    Devolve (dados inflados, bytes consumidos do membro, trailer incluído)."""
    inicio = pos + _tamanho_cabecalho(dados, pos)
    z = zlib.decompressobj(-15)
    try:
        out = z.decompress(memoryview(dados)[inicio:], limite + 1)
    except zlib.error as exc:
        raise ErroCompressao(f"DEFLATE inválido no membro do byte {pos}: {exc}") from exc
    if len(out) > limite:
        raise ErroCompressao(f"membro do byte {pos} passa do limite de {limite} B")
    if not z.eof:
        raise ErroCompressao(f"membro gzip do byte {pos} incompleto")
    resto = z.unused_data
    if len(resto) < 8:
        raise ErroCompressao(f"trailer gzip do byte {pos} truncado")
    if int.from_bytes(resto[:4], "little") != zlib.crc32(out):
        raise ErroCompressao(f"CRC32 do membro do byte {pos} não confere")
    if int.from_bytes(resto[4:8], "little") != len(out) & 0xFFFFFFFF:
        raise ErroCompressao(f"ISIZE do membro do byte {pos} não confere")
    return out, len(dados) - len(resto) - pos + 8


def preparar(nome, guardado):
    return tirar_checksum_paginas(guardado) if stream_paginado(nome) else guardado


def inflar_stream(nome, guardado, limite=LIMITE):
    """Formats/Latest começa no gzip; os Global/* têm 8 B de prefixo antes dele."""
    return inflar_membro(preparar(nome, guardado), 8 if nome.startswith("Global/") else 0, limite)[0]
