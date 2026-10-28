import gzip

import pytest

from leitor_rfa.documento import ler
from leitor_rfa.esquema import Classe, Esquema
from leitor_rfa.segmentos import ErroSegmento, percorrer_particao

CONTENT, CHAVE, SEGMENTO, CHECKBACK = 12, 13, 14, 15
FIM = (CONTENT).to_bytes(2, "little") + bytes(4) + b"\xff" * 4


def u16(n):
    return n.to_bytes(2, "little")


def u32(n):
    return n.to_bytes(4, "little")


@pytest.fixture
def esquema_sintetico():
    nomes = ["ContentMarker", "ContentKey", "SegmentMarker", "SegmentCheckback"]
    return Esquema([Classe(12 + i, n, 0, 1, []) for i, n in enumerate(nomes)], "com_opaco", "x")


def segmento(corpo, flags=1 << 2, canal=101, n=3):
    g = gzip.compress(corpo)
    return u16(SEGMENTO) + u32(flags) + u32(n) + u32(len(g) + 8) + u32(len(corpo)) + canal.to_bytes(8, "little") + g


def conteudo(n=2):
    return u16(CONTENT) + bytes(4) + u32(n)


def test_particao_sintetica(esquema_sintetico):
    p = percorrer_particao(bytes(8) + conteudo() + segmento(b"corpo") + FIM, esquema_sintetico)
    assert [(g.canal, g.dados, g.n_segmentos, g.objetos_declarados) for g in p.grupos] == [(101, b"corpo", 1, 3)]
    assert (p.segmentos, p.secoes_conteudo, p.bytes_inflados) == (1, 1, 5)


def test_continuacao_junta_os_segmentos(esquema_sintetico):
    dados = (bytes(8) + conteudo() + segmento(b"abc", flags=(1 << 2) | 2) + segmento(b"def", flags=(1 << 2) | 1)
             + FIM)
    p = percorrer_particao(dados, esquema_sintetico)
    assert [(g.dados, g.n_segmentos) for g in p.grupos] == [(b"abcdef", 2)]


def test_checkback_confere_o_tamanho_do_ultimo_segmento(esquema_sintetico):
    seg = segmento(b"corpo")
    tam = int.from_bytes(seg[10:14], "little")
    ok = bytes(8) + conteudo() + seg + u16(CHECKBACK) + u32(tam) + FIM
    assert len(percorrer_particao(ok, esquema_sintetico).grupos) == 1
    ruim = bytes(8) + conteudo() + seg + u16(CHECKBACK) + u32(tam + 1) + FIM
    with pytest.raises(ErroSegmento, match="checkback"):
        percorrer_particao(ruim, esquema_sintetico)


def test_chave_de_conteudo(esquema_sintetico):
    chave = bytes(range(16))
    marcador = u16(CONTENT) + b"\xff" * 4 + u16(CHAVE) + u32(7) + chave
    p = percorrer_particao(bytes(8) + marcador + segmento(b"x") + FIM, esquema_sintetico)
    assert (p.grupos[0].chave_conteudo, p.grupos[0].n_elementos) == (chave, 7)


def test_marcador_desconhecido_levanta(esquema_sintetico):
    with pytest.raises(ErroSegmento, match="marcador"):
        percorrer_particao(bytes(8) + u16(999) + bytes(20), esquema_sintetico)


def test_continuacao_sem_segmento_anterior_levanta(esquema_sintetico):
    with pytest.raises(ErroSegmento, match="continuação"):
        percorrer_particao(bytes(8) + conteudo() + segmento(b"x", flags=(1 << 2) | 1) + FIM, esquema_sintetico)


def test_gzip_menor_que_o_segmento_levanta(esquema_sintetico):
    seg = bytearray(segmento(b"corpo"))
    seg[10:14] = u32(int.from_bytes(seg[10:14], "little") + 4)
    with pytest.raises(ErroSegmento):
        percorrer_particao(bytes(8) + conteudo() + bytes(seg) + b"lixo" + FIM, esquema_sintetico)


def test_sem_marcador_final_levanta(esquema_sintetico):
    with pytest.raises(ErroSegmento, match="truncad"):
        percorrer_particao(bytes(8) + conteudo() + segmento(b"x"), esquema_sintetico)


@pytest.mark.parametrize("nome", ["r2012_pa2010", "r2012", "r2012_sem_previa", "r2013", "r2014", "r2018"])
def test_particoes_reais_chegam_ao_terminal(fixtura, nome):
    cob = ler(fixtura(nome) / "familia.rfa")["cobertura"]
    assert cob["secoes"]["particoes"]["estado"] == "decifrado", cob["erros"]
    assert cob["particoes"]["lidas"] == cob["particoes"]["particoes"] >= 1
    assert cob["particoes"]["grupos"] > 0 and set(cob["particoes"]["canais"]) <= {"101", "102", "103"}
