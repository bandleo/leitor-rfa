import collections
import struct

import pytest

from leitor_rfa.compressao import inflar_stream, preparar
from leitor_rfa.contenedor import abrir
from leitor_rfa.esquema import Campo, Classe, Esquema, ler_esquema
from leitor_rfa.grafo import ErroGrafo, decodificar
from leitor_rfa.registros import objetos
from leitor_rfa.segmentos import percorrer_particao


def C(nome, base, mod=0, arr=None, refs=(), sub=None, flags=0):
    return Campo(nome, base | (mod << 8) | (flags << 16), base, mod, arr, list(refs), sub)


ESQ = Esquema([
    Classe(12, "Base", 0, 1, [C("m_ok", 1)]),
    Classe(13, "A", 12, 1, [C("m_i", 4), C("m_d", 7), C("m_s", 8, 0x60), C("m_g", 9), C("m_v", 5, 0x50),
                            C("m_f", 7, 0x10, 3), C("m_p", 14, 1), C("m_in", 14, 0, refs=[14]), C("m_t", 1, flags=2)]),
    Classe(14, "B", 0, 1, [C("m_x", 4)]),
], "com_opaco", "x")


def corpo_a(token=7):
    s = "olá"
    b = (13).to_bytes(2, "little") + b"\x01" + struct.pack("<i", -5) + struct.pack("<d", 2.5)
    b += struct.pack("<I", len(s)) + s.encode("utf-16-le") + bytes(range(16))
    b += struct.pack("<I", 2) + struct.pack("<II", 10, 20) + struct.pack("<3d", 1, 2, 3)
    b += struct.pack("<I", token) + ((14).to_bytes(2, "little") if token else b"")
    b += struct.pack("<i", 99)          # m_in: B em linha
    if token:
        b += struct.pack("<i", 42)      # o B apontado, lido depois do objeto raiz
    return b


def test_objeto_com_heranca_ponteiro_e_campos():
    g = decodificar(corpo_a(), ESQ)
    r = g.raiz
    assert r.classe == "A" and r.campos["m_ok"] is True and r.campos["m_i"] == -5 and r.campos["m_d"] == 2.5
    assert r.campos["m_s"] == "olá" and r.campos["m_g"] == bytes(range(16))
    assert r.campos["m_v"] == [10, 20] and r.campos["m_f"] == [1.0, 2.0, 3.0]
    assert r.campos["m_in"] == {"m_x": 99} and "m_t" not in r.campos
    alvo = g.alvo(r.campos["m_p"])
    assert alvo.classe == "B" and alvo.campos == {"m_x": 42}


def test_ponteiro_nulo_nao_cria_objeto():
    g = decodificar(corpo_a(token=0), ESQ)
    assert g.alvo(g.raiz.campos["m_p"]) is None and len(g.objetos) == 1


def test_sobra_no_fim_levanta():
    with pytest.raises(ErroGrafo, match="sobra"):
        decodificar(corpo_a() + b"x", ESQ)


def test_corpo_truncado_levanta():
    with pytest.raises(ErroGrafo):
        decodificar(corpo_a()[:-3], ESQ)


def _corpos(caminho, classes):
    with abrir(caminho) as c:
        e = ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))
        grupos = [g for n in c.streams() if n.startswith("Partitions/")
                  for g in percorrer_particao(preparar(n, c.ler(n)), e).grupos if g.chave_conteudo is None]
    out = collections.defaultdict(list)
    for g in grupos:
        if g.canal == 102:
            for o in objetos(g.dados, 4):
                nome = e.classe(o.etiqueta).nome
                if nome in classes:
                    out[nome].append(o.corpo)
    return e, out


@pytest.mark.parametrize("nome", ["r2012", "r2013", "r2014", "r2018"])
def test_parametros_reais_decodificam_o_corpo_inteiro(fixtura, nome):
    e, corpos = _corpos(fixtura(nome) / "familia.rfa", {"ParamElemFamily", "ParamElemExternal"})
    assert corpos["ParamElemExternal"]
    for classe, lista in corpos.items():
        for corpo in lista:
            g = decodificar(corpo, e)
            assert g.raiz.classe == classe
            assert g.alvo(g.raiz.campos["m_pParamDef"]) is not None
