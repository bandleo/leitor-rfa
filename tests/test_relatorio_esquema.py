import json

from conftest import FIXTURES_DIR, requer_fixtures

from leitor_rfa.lote import processar
from leitor_rfa.relatorio_esquema import main, resumir_esquemas


def linha(v, classes=3154, sha="a", variante="sem_opaco", esquema="decifrado", particoes="decifrado"):
    lido = esquema == "decifrado"
    return {"versao_formato": v, "variante_esquema": variante if lido else None,
            "estados": {"esquema": esquema, "particoes": particoes},
            "esquema": {"classes": classes, "sha256": sha} if lido else None, "erro": None}


def test_resumo_por_versao():
    linhas = [linha(2012), linha(2012, sha="b"), linha(2018, 4024, "c", "com_opaco", particoes="parcial"),
              linha(None, esquema="nao_decifrado", particoes="nao_decifrado"),
              {"versao_formato": None, "erro": "ErroArquivo: x", "estados": {}}]
    r = {x["versao"]: x for x in resumir_esquemas(linhas)}
    assert r["2012"] == {"versao": "2012", "arquivos": 2, "esquema_lido": 2, "variantes": {"sem_opaco": 2},
                         "classes": [3154, 3154], "esquemas_distintos": 2, "particoes": {"decifrado": 2},
                         "erros_abertura": 0}
    assert r["2018"]["particoes"] == {"parcial": 1}
    assert (r["desconhecida"]["arquivos"], r["desconhecida"]["esquema_lido"], r["desconhecida"]["erros_abertura"]) == (2, 0, 1)


@requer_fixtures
def test_lote_grava_esquema_e_particoes_por_arquivo():
    a = processar([FIXTURES_DIR])["arquivos"][0]
    assert a["esquema"]["classes"] > 0 and len(a["esquema"]["sha256"]) == 64
    assert a["particoes"]["lidas"] == a["particoes"]["particoes"]


@requer_fixtures
def test_main_sobre_relatorio_do_lote(tmp_path, capsys):
    rel = tmp_path / "lote.json"
    rel.write_text(json.dumps(processar([FIXTURES_DIR]), ensure_ascii=False), encoding="utf-8")
    assert main([str(rel), "-o", str(tmp_path / "esq.json")]) == 0
    out = capsys.readouterr().out
    assert "2012" in out and "2018" in out
    linhas = json.loads((tmp_path / "esq.json").read_text(encoding="utf-8"))
    assert sum(l["esquema_lido"] for l in linhas) == 8
