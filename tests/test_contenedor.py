import pytest

from leitor_rfa.contenedor import ErroArquivo, abrir


def test_streams_da_familia_2012(fixtura):
    with abrir(fixtura("r2012") / "familia.rfa") as c:
        s = c.streams()
    assert {"BasicFileInfo", "PartAtom", "Formats/Latest", "Global/Latest", "Global/ElemTable"} <= set(s)
    assert any(n.startswith("Partitions/") for n in s)


def test_ler_stream_devolve_bytes(fixtura):
    with abrir(fixtura("r2012") / "familia.rfa") as c:
        dados = c.ler("PartAtom")
    assert dados.startswith(b"<?xml")


def test_stream_ausente_devolve_none(fixtura):
    with abrir(fixtura("r2014") / "familia.rfa") as c:
        assert c.ler("RevitPreview4.0") is None


def test_arquivo_nao_ole_levanta_erro_arquivo(tmp_path):
    f = tmp_path / "x.rfa"
    f.write_bytes(b"nao sou ole")
    with pytest.raises(ErroArquivo):
        abrir(f)


def test_arquivo_vazio_levanta_erro_arquivo(tmp_path):
    f = tmp_path / "vazio.rfa"
    f.write_bytes(b"")
    with pytest.raises(ErroArquivo):
        abrir(f)
