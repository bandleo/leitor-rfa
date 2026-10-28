"""Segmentos das partições: o enquadramento que separa os grupos de elementos.

Porte de rvt-rs (Apache-2.0) src/native_segments.rs::walk_inflated. A partição
preparada (sem checksum de página) tem 8 B de cabeçalho e uma sequência de
marcadores u16 cujas etiquetas vêm do esquema do próprio arquivo:
ContentMarker, SegmentMarker, SegmentCheckback e, de 2014 em diante,
SignatureMarker. Cada SegmentMarker carrega um membro gzip; segmentos podem
continuar uns nos outros e formam um grupo por canal.
"""
from dataclasses import dataclass

from .compressao import PAGINA, ErroCompressao, inflar_membro

LIMITE_GRUPO = 64 * 1024 * 1024


class ErroSegmento(Exception):
    """A partição não segue o enquadramento esperado."""


@dataclass(frozen=True)
class Grupo:
    canal: int
    chave_conteudo: bytes | None
    n_elementos: int | None
    n_segmentos: int
    objetos_declarados: int
    dados: bytes


@dataclass(frozen=True)
class Particao:
    grupos: list
    segmentos: int
    secoes_conteudo: int
    bytes_inflados: int
    bytes_terminais: int


class _Leitor:
    def __init__(self, dados):
        self.b, self.p = dados, 0

    def take(self, n):
        if self.p + n > len(self.b):
            raise ErroSegmento(f"partição truncada no byte {self.p}: faltam {n} B")
        r = self.b[self.p:self.p + n]
        self.p += n
        return r

    def u16(self):
        return int.from_bytes(self.take(2), "little")

    def u32(self):
        return int.from_bytes(self.take(4), "little")

    def u64(self):
        return int.from_bytes(self.take(8), "little")


def _etiqueta(esquema, nome):
    e = esquema.etiqueta(nome)
    if e is None:
        raise ErroSegmento(f"a classe {nome} não existe no esquema deste arquivo")
    return e


def percorrer_particao(preparado, esquema, limite_grupo=LIMITE_GRUPO):
    conteudo = _etiqueta(esquema, "ContentMarker")
    chave_tag = _etiqueta(esquema, "ContentKey")
    segmento = _etiqueta(esquema, "SegmentMarker")
    checkback = _etiqueta(esquema, "SegmentCheckback")
    assinatura = esquema.etiqueta("SignatureMarker")  # não existe em 2010–2013
    r = _Leitor(preparado)
    r.take(8)
    grupos, segmentos, secoes, inflados = [], 0, 0, 0
    chave = n_elementos = ultimo_tam = ativo = None
    while True:
        pos, marcador = r.p, r.u16()
        if marcador == conteudo:
            if ativo:
                raise ErroSegmento(f"fronteira de conteúdo no meio de um segmento continuado (byte {pos})")
            token = r.u32()
            if token == 0:
                chave = n_elementos = None
                if r.u32() == 0xFFFFFFFF:
                    terminais = len(preparado) - r.p
                    if terminais > PAGINA:
                        raise ErroSegmento(f"resto final de {terminais} B passa de uma página (byte {pos})")
                    return Particao(grupos, segmentos, secoes, inflados, terminais)
            elif token == 0xFFFFFFFF:
                if r.u16() != chave_tag:
                    raise ErroSegmento(f"ponteiro de chave de conteúdo não suportado (byte {pos})")
                n_elementos = r.u32()
                chave = r.take(16)
            else:
                raise ErroSegmento(f"token de conteúdo {token:#x} não suportado (byte {pos})")
            secoes += 1
        elif marcador == segmento:
            flags, n_objetos, tam, _corpo = r.u32(), r.u32(), r.u32(), r.u32()
            if tam == 0:
                if flags or n_objetos or _corpo or ativo:
                    raise ErroSegmento(f"segmento vazio inválido (byte {pos})")
                continue
            if flags >> 2 == 0 or tam < 18:
                raise ErroSegmento(f"flags {flags:#x} / tamanho {tam} de segmento não suportados (byte {pos})")
            canal = r.u64()
            comprimido = r.take(tam - 8)
            try:
                dados, consumido = inflar_membro(comprimido, 0, limite_grupo)
            except ErroCompressao as exc:
                raise ErroSegmento(f"segmento do byte {pos}: {exc}") from exc
            if consumido != len(comprimido):
                raise ErroSegmento(f"o gzip não ocupa o segmento inteiro (byte {pos})")
            segmentos += 1
            inflados += len(dados)
            ultimo_tam = tam
            if bool(flags & 1) != (ativo is not None):
                raise ErroSegmento(f"continuação de segmento inconsistente (byte {pos})")
            if ativo:
                if ativo["canal"] != canal or ativo["chave"] != chave:
                    raise ErroSegmento(f"continuação muda de canal ou de conteúdo (byte {pos})")
                if len(ativo["dados"]) + len(dados) > limite_grupo:
                    raise ErroSegmento(f"grupo passa do limite de {limite_grupo} B (byte {pos})")
                ativo["dados"] += dados
                ativo["n"] += 1
                ativo["objetos"] += n_objetos
            else:
                ativo = {"canal": canal, "chave": chave, "n_elementos": n_elementos, "n": 1,
                         "objetos": n_objetos, "dados": bytearray(dados)}
            if not flags & 2:
                grupos.append(Grupo(ativo["canal"], ativo["chave"], ativo["n_elementos"], ativo["n"],
                                    ativo["objetos"], bytes(ativo["dados"])))
                ativo = None
        elif marcador == checkback:
            valor = r.u32()
            if valor != ultimo_tam:
                raise ErroSegmento(f"checkback {valor} difere do tamanho do último segmento {ultimo_tam} (byte {pos})")
            ultimo_tam = None
        elif assinatura is not None and marcador == assinatura:
            if ativo:
                raise ErroSegmento(f"assinatura no meio de um segmento continuado (byte {pos})")
            r.take(r.u32())
            r.take(2 * r.u32())
        else:
            raise ErroSegmento(f"marcador desconhecido {marcador} no byte {pos}")
