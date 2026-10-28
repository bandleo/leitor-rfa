import datetime as dt
import hashlib
import json
import shutil

from leitor_rfa.cli import main
from leitor_rfa.documento import ler


def test_chaves_iguais_ao_extrator_mais_cobertura(fixtura):
    doc = ler(fixtura("r2012") / "familia.rfa")
    gab = json.loads((fixtura("r2012") / "familia.json").read_text(encoding="utf-8"))
    assert set(doc) == set(gab) | {"cobertura", "partatom"}
    assert doc["versao_esquema"] == 1


def test_origem_com_sha256_e_tamanho(fixtura):
    f = fixtura("r2012") / "familia.rfa"
    doc = ler(f)
    assert doc["origem"]["sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert doc["origem"]["tamanho"] == f.stat().st_size
    assert doc["origem"]["caminho"] == str(f)


def test_extraido_em_iso_com_fuso(fixtura):
    doc = ler(fixtura("r2012") / "familia.rfa")
    assert dt.datetime.fromisoformat(doc["extraido_em"]).tzinfo is not None


def test_fora_do_leitor_sai_nulo(fixtura):
    doc = ler(fixtura("r2012") / "familia.rfa")
    assert doc["geometria"] is None and doc["importacoes"] is None and doc["ifc"] is None


def test_cobertura_lista_todas_as_secoes_e_versao_do_leitor(fixtura):
    cob = ler(fixtura("r2012") / "familia.rfa")["cobertura"]
    assert cob["leitor"] == "0.1.0"
    assert set(cob["secoes"]) == {"familia", "tipos", "parametros", "aninhadas", "planos_referencia",
                                  "cotas", "formas", "miniatura", "esquema", "particoes", "elementos"}
    assert all(s["estado"] in ("decifrado", "parcial", "nao_decifrado", "ausente") for s in cob["secoes"].values())
    assert cob["erros"] == []


def test_cli_grava_o_documento(fixtura, tmp_path):
    saida = tmp_path / "familia.json"
    assert main([str(fixtura("r2012") / "familia.rfa"), "-o", str(saida)]) == 0
    assert json.loads(saida.read_text(encoding="utf-8"))["versao_esquema"] == 1


def test_caminho_com_acento_e_espaco(fixtura, tmp_path):
    d = tmp_path / "Família Ç"
    d.mkdir()
    f = shutil.copy(fixtura("r2012") / "familia.rfa", d / "Válvula de teste.rfa")
    assert main([str(f), "-o", str(d / "saída.json")]) == 0
    assert json.loads((d / "saída.json").read_text(encoding="utf-8"))["origem"]["caminho"] == str(f)


def test_cli_arquivo_nao_ole_sai_1_sem_traceback(tmp_path, capsys):
    f = tmp_path / "x.rfa"
    f.write_bytes(b"lixo")
    assert main([str(f), "-o", str(tmp_path / "x.json")]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and "não é um contêiner OLE" in err
