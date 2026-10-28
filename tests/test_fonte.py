import hashlib
import json
import pathlib
import shutil

from leitor_rfa.fonte import ler_familia


def _extracao(tmp_path, pasta):
    """Monta <extracao>/<sha256>/familia.json como o extrator grava."""
    sha = hashlib.sha256((pasta / "familia.rfa").read_bytes()).hexdigest()
    destino = tmp_path / "extracao" / sha
    destino.mkdir(parents=True)
    shutil.copy(pasta / "familia.json", destino / "familia.json")
    return tmp_path / "extracao"


def _nome(pasta):
    gab = json.loads((pasta / "familia.json").read_text(encoding="utf-8"))
    return pathlib.PureWindowsPath(gab["origem"]["caminho"]).name, gab


def test_sem_extracao_tudo_vem_do_leitor(fixtura):
    doc, png = ler_familia(fixtura("r2012") / "familia.rfa")
    assert set(doc["cobertura"]["origem"].values()) == {"leitor"}
    assert png[:4] == b"\x89PNG"


def test_o_que_o_leitor_nao_decifra_vem_do_extrator(fixtura, tmp_path):
    pasta = fixtura("r2012")
    nome, gab = _nome(pasta)
    doc, _ = ler_familia(pasta / "familia.rfa", extracao=_extracao(tmp_path, pasta), nome_arquivo=nome)
    origem = doc["cobertura"]["origem"]
    assert origem["planos_referencia"] == "extrator" and doc["planos_referencia"] == gab["planos_referencia"]
    assert origem["cotas"] == "leitor" and origem["formas"] == "leitor"  # decifradas pelo leitor
    assert origem["familia"] == "extrator" and doc["familia"]["categoria"] == gab["familia"]["categoria"]
    assert origem["geometria"] == "extrator" and doc["geometria"] == gab["geometria"]
    assert doc["versao_esquema"] == 1 and set(doc) == set(gab) | {"cobertura", "partatom"}


def test_extracao_sem_esta_familia_nao_muda_nada(fixtura, tmp_path):
    vazio = tmp_path / "extracao"
    vazio.mkdir()
    doc, _ = ler_familia(fixtura("r2012") / "familia.rfa", extracao=vazio)
    assert set(doc["cobertura"]["origem"].values()) == {"leitor"}
