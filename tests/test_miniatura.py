from leitor_rfa.cli import main
from leitor_rfa.contenedor import abrir
from leitor_rfa.documento import ler, ler_com_miniatura
from leitor_rfa.miniatura import extrair_png

ASSINATURA = b"\x89PNG\r\n\x1a\n"
FIM_IEND = b"IEND\xaeB`\x82"


def test_extrai_png_completo(fixtura):
    with abrir(fixtura("r2012") / "familia.rfa") as c:
        png = extrair_png(c.ler("RevitPreview4.0"))
    assert png.startswith(ASSINATURA) and png.endswith(FIM_IEND)


def test_sem_dados_ou_sem_png_devolve_none():
    assert extrair_png(None) is None
    assert extrair_png(b"cabecalho sem png") is None
    assert extrair_png(b"xx" + ASSINATURA + b"sem fim") is None


def test_documento_marca_miniatura(fixtura):
    assert ler(fixtura("r2012") / "familia.rfa")["cobertura"]["secoes"]["miniatura"]["estado"] == "decifrado"
    assert ler(fixtura("r2014") / "familia.rfa")["cobertura"]["secoes"]["miniatura"]["estado"] == "ausente"


def test_ler_com_miniatura_devolve_o_png(fixtura):
    doc, png = ler_com_miniatura(fixtura("r2012") / "familia.rfa")
    assert doc["versao_esquema"] == 1 and png.startswith(ASSINATURA)


def test_cli_grava_miniatura(fixtura, tmp_path):
    destino = tmp_path / "m.png"
    assert main([str(fixtura("r2012") / "familia.rfa"), "-o", str(tmp_path / "f.json"), "--miniatura", str(destino)]) == 0
    assert destino.read_bytes().startswith(ASSINATURA)


def test_cli_sem_miniatura_avisa_e_nao_cria(fixtura, tmp_path, capsys):
    destino = tmp_path / "m.png"
    assert main([str(fixtura("r2014") / "familia.rfa"), "-o", str(tmp_path / "f.json"), "--miniatura", str(destino)]) == 0
    assert not destino.exists()
    assert "sem miniatura" in capsys.readouterr().err
