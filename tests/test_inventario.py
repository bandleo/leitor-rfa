import json
import shutil

from conftest import FIXTURES_DIR, requer_fixtures

from leitor_rfa.inventario import inventariar, main, resumir

pytestmark = requer_fixtures


def test_inventario_das_fixtures():
    linhas = inventariar([FIXTURES_DIR])
    assert len(linhas) == 8
    r = resumir(linhas)
    assert r["por_versao"] == {2012: 4, 2013: 1, 2014: 1, 2018: 2}
    assert r["por_versao_partatom"]["2012/2010"] == 2
    assert r["erros"] == 0


def test_arquivo_ruim_vira_linha_de_erro_e_nao_para(tmp_path):
    shutil.copytree(FIXTURES_DIR, tmp_path / "f")
    (tmp_path / "f" / "lixo.rfa").write_bytes(b"lixo")
    linhas = inventariar([tmp_path / "f"])
    assert len(linhas) == 9
    ruim = [l for l in linhas if l["erro"]]
    assert len(ruim) == 1 and ruim[0]["caminho"].endswith("lixo.rfa")
    assert resumir(linhas)["erros"] == 1


def test_main_grava_relatorio(tmp_path, capsys):
    saida = tmp_path / "inv.json"
    assert main([str(FIXTURES_DIR), "-o", str(saida)]) == 0
    rel = json.loads(saida.read_text(encoding="utf-8"))
    assert rel["resumo"]["total"] == 8 and len(rel["arquivos"]) == 8
    assert "2012" in capsys.readouterr().out
