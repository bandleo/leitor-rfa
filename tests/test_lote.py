import json
import pathlib
import shutil

from conftest import ARQUIVOS_DIR, FIXTURES_DIR, requer_arquivo, requer_fixtures

from leitor_rfa.lote import main, processar

pytestmark = requer_fixtures


def _com_lixo(tmp_path):
    shutil.copytree(FIXTURES_DIR, tmp_path / "f")
    (tmp_path / "f" / "lixo.rfa").write_bytes(b"lixo")
    return tmp_path / "f"


def test_arquivo_ruim_nao_para_o_lote(tmp_path):
    rel = processar([_com_lixo(tmp_path)])
    r = rel["resumo"]
    assert (r["total"], r["abertos"], r["com_erro"]) == (9, 8, 1)
    ruim = next(a for a in rel["arquivos"] if a["erro"])
    assert ruim["caminho"].endswith("lixo.rfa") and "OLE" in ruim["erro"]


def test_estados_por_secao_e_versao():
    r = processar([FIXTURES_DIR])["resumo"]
    assert r["por_versao"]["2012"]["arquivos"] == 4
    assert r["por_versao"]["2012"]["secoes"]["miniatura"] == {"decifrado": 3, "ausente": 1}
    assert r["por_versao"]["2018"]["secoes"]["tipos"] == {"decifrado": 2}


def test_main_grava_relatorio_e_jsons(tmp_path, capsys):
    saida, jsons = tmp_path / "lote.json", tmp_path / "jsons"
    assert main([str(FIXTURES_DIR), "-o", str(saida), "--jsons", str(jsons)]) == 0
    rel = json.loads(saida.read_text(encoding="utf-8"))
    assert rel["resumo"]["abertos"] == 8
    assert len(list(jsons.glob("*.json"))) == 8
    assert "abertos: 8" in capsys.readouterr().out


def test_main_com_erro_sai_1(tmp_path):
    assert main([str(_com_lixo(tmp_path)), "-o", str(tmp_path / "l.json")]) == 1


def test_cada_arquivo_tem_o_tempo_de_leitura():
    arquivos = processar([FIXTURES_DIR])["arquivos"]
    assert all(isinstance(a["segundos"], float) and a["segundos"] >= 0 for a in arquivos)



@requer_arquivo("r2010_sem_partatom.rfa")
def test_linha_traz_partatom_e_o_que_foi_conferido():
    rel = processar([FIXTURES_DIR])
    a = next(a for a in rel["arquivos"] if pathlib.PureWindowsPath(a["caminho"]).parent.name == "r2014")
    assert a["partatom"]["tipos"] == [1, 1] and a["partatom"]["valores"][1] > 0
    assert a["conferencia"]["tipos"] == "partatom" and a["conferencia"]["cotas"] == "nao_conferido"
    sem = processar([ARQUIVOS_DIR])["arquivos"][0]  # 2010 sem PartAtom
    assert sem["partatom"] is None and sem["conferencia"]["tipos"] == "nao_conferido"


def test_arquivo_do_gabarito_conta_como_conferido():
    rel = processar([FIXTURES_DIR], gabarito=FIXTURES_DIR)
    assert all(set(a["conferencia"].values()) == {"gabarito"} for a in rel["arquivos"])


def test_resumo_soma_partatom_e_conferencia_por_versao():
    v = processar([FIXTURES_DIR])["resumo"]["por_versao"]["2014"]
    assert v["partatom"]["arquivos"] == 1 and v["partatom"]["tipos"] == [1, 1]
    assert v["conferencia"]["tipos"] == {"partatom": 1} and v["conferencia"]["cotas"] == {"nao_conferido": 1}
