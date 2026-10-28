import gzip

import pytest

from leitor_rfa.compressao import (CARGA, PAGINA, ErroCompressao, inflar_membro, inflar_stream,
                                   stream_paginado, tirar_checksum_paginas)
from leitor_rfa.contenedor import abrir


def test_constantes_da_pagina():
    assert (PAGINA, CARGA, PAGINA - CARGA) == (65_249, 64_896, 353)


def test_tira_trailer_das_paginas_completas():
    pag = bytes(range(256)) * 254 + bytes(range(225))  # 65_249 B
    assert len(pag) == PAGINA
    dados = pag + pag + b"resto"
    out = tirar_checksum_paginas(dados)
    assert len(out) == 2 * CARGA + 5
    assert out[:CARGA] == pag[:CARGA] and out[CARGA:2 * CARGA] == pag[:CARGA]
    assert out.endswith(b"resto")


def test_menor_que_uma_pagina_fica_igual():
    assert tirar_checksum_paginas(b"abc") == b"abc"


def test_exatamente_uma_pagina():
    assert len(tirar_checksum_paginas(bytes(PAGINA))) == CARGA


@pytest.mark.parametrize("nome", ["Partitions/105", "Partitions/0", "Formats/Latest", "Global/Latest",
                                  "Global/ElemTable", "Global/PartitionTable", "Global/History",
                                  "Global/DocumentIncrementTable", "Global/ContentDocuments"])
def test_streams_paginados(nome):
    assert stream_paginado(nome)


@pytest.mark.parametrize("nome", ["PartAtom", "RevitPreview4.0", "BasicFileInfo", "Contents",
                                  "TransmissionData", "Partitions/", "Partitions/1/x"])
def test_streams_nao_paginados(nome):
    assert not stream_paginado(nome)


def test_inflar_membro_confere_crc_e_tamanho():
    g = gzip.compress(b"leitor" * 100)
    assert inflar_membro(g) == (b"leitor" * 100, len(g))


def test_inflar_membro_a_partir_de_uma_posicao():
    g = gzip.compress(b"abc")
    assert inflar_membro(b"xxxx" + g + b"lixo", 4) == (b"abc", len(g))


def test_cabecalho_com_nome_de_arquivo():
    g = bytearray(gzip.compress(b"abc"))
    g[3] |= 0x08  # FNAME
    g = bytes(g[:10]) + b"nome.bin\0" + bytes(g[10:])
    assert inflar_membro(g)[0] == b"abc"


def test_crc_errado_levanta():
    g = bytearray(gzip.compress(b"x" * 50))
    g[-8] ^= 0xFF
    with pytest.raises(ErroCompressao, match="CRC"):
        inflar_membro(bytes(g))


def test_sem_assinatura_gzip_levanta():
    with pytest.raises(ErroCompressao, match="gzip"):
        inflar_membro(b"\x00\x01\x02" * 10)


def test_membro_truncado_levanta():
    g = gzip.compress(bytes(range(256)) * 40)
    with pytest.raises(ErroCompressao):
        inflar_membro(g[:len(g) // 2])


def test_limite_de_tamanho():
    with pytest.raises(ErroCompressao, match="limite"):
        inflar_membro(gzip.compress(bytes(10_000)), limite=1_000)


@pytest.mark.parametrize("nome,tam", [("r2012", 293461), ("r2012_pa2010", 293461), ("r2013", 334630),
                                      ("r2014", 367595), ("r2018", 418793)])
def test_formats_latest_infla_no_tamanho_medido(fixtura, nome, tam):
    with abrir(fixtura(nome) / "familia.rfa") as c:
        assert len(inflar_stream("Formats/Latest", c.ler("Formats/Latest"))) == tam


def test_global_latest_tem_prefixo_de_8_bytes(fixtura):
    with abrir(fixtura("r2012") / "familia.rfa") as c:
        bruto = c.ler("Global/Latest")
    assert bruto[8:11] == b"\x1f\x8b\x08"
    assert len(inflar_stream("Global/Latest", bruto)) > 0
