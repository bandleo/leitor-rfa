import pytest

from leitor_rfa.compressao import inflar_stream
from leitor_rfa.contenedor import abrir
from leitor_rfa.documento import ler
from leitor_rfa.esquema import ErroEsquema, ler_esquema


def u16(n):
    return n.to_bytes(2, "little")


def u32(n):
    return n.to_bytes(4, "little")


def campo(nome, descritor, extra=b""):
    return u32(len(nome)) + nome + u32(descritor) + extra


def defin(nome, pai=0, campos=(), opaco=True):
    b = u16(0) + u16(len(nome)) + nome + u16(pai) + u32(1) + u32(len(campos)) + b"".join(campos)
    return b + (u32(0) if opaco else b"")


def _esquema(nome):
    with abrir(nome) as c:
        return ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))


@pytest.mark.parametrize("opaco,variante", [(True, "com_opaco"), (False, "sem_opaco")])
def test_esquema_sintetico_nas_duas_variantes(opaco, variante):
    e = ler_esquema(defin(b"A", opaco=opaco) + defin(b"B", pai=12, opaco=opaco) + bytes(8))
    assert [c.nome for c in e.classes] == ["A", "B"] and e.variante == variante
    assert e.etiqueta("B") == 13 and e.classe(13).pai == 12 and e.etiqueta("X") is None


def test_campo_com_referencia_a_outra_classe():
    m_p = campo(b"m_p", 0x0000000E, u16(12))            # base 14, modificador 0: referência à classe 12
    m_n = campo(b"m_n", 0x00001005, u32(3))             # base 5, modificador 16: arranjo de 3
    e = ler_esquema(defin(b"A") + defin(b"B", campos=(m_p, m_n)) + bytes(8))
    b = e.classe(13)
    assert [(c.nome, c.base, c.modificador, c.n_arranjo, c.referencias) for c in b.campos] == [
        ("m_p", 14, 0, None, [12]), ("m_n", 5, 16, 3, [])]


def test_composto_guarda_o_descritor_aninhado():
    m_c = campo(b"m_c", 0x0000500D, u32(4) + b"item" + u32(0x00000007))   # base 13, arranjo dinâmico de f64
    e = ler_esquema(defin(b"A", campos=(m_c,)) + bytes(8))
    c = e.classe(12).campos[0]
    assert (c.base, c.modificador, c.aninhado.base, c.aninhado.modificador) == (13, 0x50, 7, 0)


def test_definicao_em_linha_pelo_bit_15():
    # o pai de A é definido dentro dela (etiqueta 13 com o bit 15 ligado)
    dentro = u16(0) + u16(1) + b"P" + u16(0) + u32(1) + u32(0) + u32(0)
    a = u16(0) + u16(1) + b"A" + u16(0x8000 | 13) + dentro + u32(1) + u32(0) + u32(0)
    e = ler_esquema(a + bytes(8))
    assert [(c.etiqueta, c.nome, c.pai) for c in e.classes] == [(12, "A", 13), (13, "P", 0)]


@pytest.mark.parametrize("nome,n,variante", [("r2012", 3154, "sem_opaco"), ("r2012_pa2010", 3154, "sem_opaco"),
                                             ("r2013", 3519, "sem_opaco"), ("r2014", 3619, "com_opaco"),
                                             ("r2018", 4024, "com_opaco")])
def test_esquema_real(fixtura, nome, n, variante):
    e = _esquema(fixtura(nome) / "familia.rfa")
    assert (len(e.classes), e.variante) == (n, variante)


def test_etiquetas_de_marcador_2012(fixtura):
    e = _esquema(fixtura("r2012") / "familia.rfa")
    assert e.etiqueta("ContentMarker") == 639 and e.etiqueta("SegmentMarker") == 2647
    assert e.etiqueta("SignatureMarker") is None


def test_mesmo_esquema_na_mesma_versao(fixtura):
    assert _esquema(fixtura("r2012") / "familia.rfa").sha256 == _esquema(fixtura("r2012_pa2010") / "familia.rfa").sha256


def test_lixo_levanta_erro_esquema():
    with pytest.raises(ErroEsquema):
        ler_esquema(b"\x01\x02" * 50)


def test_documento_marca_esquema(fixtura):
    cob = ler(fixtura("r2013") / "familia.rfa")["cobertura"]
    assert cob["variante_esquema"] == "sem_opaco"
    assert cob["secoes"]["esquema"]["estado"] == "decifrado" and "3519 classes" in cob["secoes"]["esquema"]["nota"]
