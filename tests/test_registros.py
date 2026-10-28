import pathlib

import pytest

from leitor_rfa.compressao import inflar_stream, preparar
from leitor_rfa.contenedor import abrir
from leitor_rfa.elemtable import ler_elemtable
from leitor_rfa.esquema import ler_esquema
from leitor_rfa.registros import ErroRegistro, Objeto, cabecalhos, objetos
from leitor_rfa.segmentos import percorrer_particao

EH = 1034
RVT2025 = pathlib.Path(r"C:\ProgramData\Autodesk\RVT 2025\Libraries")
AUTODESK_2025 = next(RVT2025.rglob("*.rfa"), None) if RVT2025.exists() else None


def u32(n):
    return n.to_bytes(4, "little")


def cab(i, corpo, w=4):
    return i.to_bytes(w, "little") + u32(len(corpo)) + corpo + u32(len(corpo))


def fim(w=4):
    return b"\xff" * w + bytes(8)


def obj(i, etiqueta, resto=b"x", w=4):
    corpo = etiqueta.to_bytes(2, "little") + resto
    return i.to_bytes(w, "little") + u32(7) + u32(len(corpo)) + corpo + u32(len(corpo))


CORPO_EH = EH.to_bytes(2, "little") + b"\0\0abc"


def test_cabecalhos_de_32_bits():
    assert cabecalhos(cab(5, CORPO_EH) + cab(9, CORPO_EH) + fim(), 4, EH) == [5, 9]


def test_cabecalhos_de_64_bits():
    assert cabecalhos(cab(2**40, CORPO_EH, 8) + fim(8), 8, EH) == [2**40]


def test_checkback_errado_levanta_com_o_byte():
    ruim = bytearray(cab(5, CORPO_EH) + cab(9, CORPO_EH))
    ruim[-1] ^= 1
    with pytest.raises(ErroRegistro, match="byte 19"):
        cabecalhos(bytes(ruim) + fim(), 4, EH)


def test_cabecalho_sem_element_header_levanta():
    with pytest.raises(ErroRegistro, match="ElementHeader"):
        cabecalhos(cab(5, b"\x01\x00\0\0") + fim(), 4, EH)


def test_objetos_com_etiqueta_da_classe():
    r = objetos(obj(5, 300) + obj(6, 301, b"yz"), 4)
    assert r == [Objeto(5, 300, (300).to_bytes(2, "little") + b"x"), Objeto(6, 301, (301).to_bytes(2, "little") + b"yz")]


def test_objetos_de_64_bits():
    assert [o.id for o in objetos(obj(2**33, 300, w=8), 8)] == [2**33]


def test_objeto_truncado_levanta():
    with pytest.raises(ErroRegistro):
        objetos(obj(5, 300)[:-3], 4)


def _grupos(caminho):
    with abrir(caminho) as c:
        e = ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))
        et = ler_elemtable(inflar_stream("Global/ElemTable", c.ler("Global/ElemTable")), e)
        grupos = [g for n in c.streams() if n.startswith("Partitions/")
                  for g in percorrer_particao(preparar(n, c.ler(n)), e).grupos if g.chave_conteudo is None]
    return e, et, grupos


@pytest.mark.parametrize("nome", ["r2012", "r2013", "r2014"])
def test_cadeia_real_traz_os_ids_do_elemtable(fixtura, nome):
    e, et, grupos = _grupos(fixtura(nome) / "familia.rfa")
    ids = [i for g in grupos if g.canal == 101 for i in cabecalhos(g.dados, 4, e.etiqueta("ElementHeader"))]
    assert sorted(ids) == list(et.donos)
    assert sum(len(objetos(g.dados, 4)) for g in grupos if g.canal == 102) == len(ids)


@pytest.mark.skipif(AUTODESK_2025 is None, reason="biblioteca Autodesk 2025 ausente")
def test_cadeia_de_64_bits_em_2025():
    e, et, grupos = _grupos(AUTODESK_2025)
    ids = [i for g in grupos if g.canal == 101 for i in cabecalhos(g.dados, 8, e.etiqueta("ElementHeader"))]
    assert set(ids) <= set(et.donos) and len(ids) > 100
    nomes = {e.classe(o.etiqueta).nome for g in grupos if g.canal == 102 for o in objetos(g.dados, 8)}
    assert {"RefPlane", "Family"} <= nomes
