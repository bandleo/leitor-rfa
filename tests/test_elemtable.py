import pathlib

import pytest

from leitor_rfa.compressao import inflar_stream
from leitor_rfa.contenedor import abrir
from leitor_rfa.elemtable import ErroElemTable, ler_elemtable
from leitor_rfa.esquema import ler_esquema

RVT2025 = pathlib.Path(r"C:\ProgramData\Autodesk\RVT 2025\Libraries")
AUTODESK_2025 = next(RVT2025.rglob("*.rfa"), None) if RVT2025.exists() else None


def _brutos(caminho):
    with abrir(caminho) as c:
        e = ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))
        return inflar_stream("Global/ElemTable", c.ler("Global/ElemTable")), e


@pytest.mark.parametrize("nome,n", [("r2012", 1872), ("r2013", 2061), ("r2014", 2212), ("r2018", 1911)])
def test_elemtable_de_32_bits(fixtura, nome, n):
    et = ler_elemtable(*_brutos(fixtura(nome) / "familia.rfa"))
    ids = list(et.donos)
    assert et.largura_id == 4 and len(ids) == n and ids == sorted(ids)


def test_dono_ausente_vira_none(fixtura):
    et = ler_elemtable(*_brutos(fixtura("r2012") / "familia.rfa"))
    assert None in et.donos.values()
    assert 0xFFFFFFFF not in et.donos.values() and 0 not in et.donos.values()


@pytest.mark.skipif(AUTODESK_2025 is None, reason="biblioteca Autodesk 2025 ausente")
def test_elemtable_de_64_bits_em_2025():
    et = ler_elemtable(*_brutos(AUTODESK_2025))
    ids = list(et.donos)
    assert et.largura_id == 8 and len(ids) > 100 and ids == sorted(ids)


def test_etiqueta_diferente_do_esquema_levanta(fixtura):
    bruto, e = _brutos(fixtura("r2012") / "familia.rfa")
    with pytest.raises(ErroElemTable, match="etiqueta"):
        ler_elemtable((1).to_bytes(2, "little") + bruto[2:], e)


def test_rabo_longo_de_familia_ainda_fecha(fixtura):
    _, e = _brutos(fixtura("r2012") / "familia.rfa")
    reg = lambda i, dono: i.to_bytes(8, "little") + bytes(12) + i.to_bytes(8, "little") + dono.to_bytes(8, "little") + bytes(4)
    dados = e.etiqueta("ElemTable").to_bytes(2, "little") + (2).to_bytes(4, "little") + reg(0, 17) + reg(17, 0) + bytes(280)
    et = ler_elemtable(dados, e)
    assert (et.largura_id, et.donos, et.sobra) == (8, {0: 17, 17: None}, 280)


def test_rabo_de_31_kb_das_steel_connections_ainda_fecha(fixtura):
    _, e = _brutos(fixtura("r2012") / "familia.rfa")
    reg = lambda i: i.to_bytes(8, "little") + bytes(12) + i.to_bytes(8, "little") + (17).to_bytes(8, "little") + bytes(4)
    dados = e.etiqueta("ElemTable").to_bytes(2, "little") + (3).to_bytes(4, "little") + reg(0) + reg(5) + reg(9) + bytes(31352)
    et = ler_elemtable(dados, e)
    assert (et.largura_id, list(et.donos), et.sobra) == (8, [0, 5, 9], 31352)


def test_nenhuma_largura_cabe_levanta(fixtura):
    _, e = _brutos(fixtura("r2012") / "familia.rfa")
    dados = e.etiqueta("ElemTable").to_bytes(2, "little") + (1000).to_bytes(4, "little") + bytes(50)
    with pytest.raises(ErroElemTable, match="largura"):
        ler_elemtable(dados, e)
