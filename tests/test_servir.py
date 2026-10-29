import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pytest

from leitor_rfa.cli import main
from leitor_rfa.glb import ler_glb
from leitor_rfa.servir import criar_servidor, nome_seguro

OLE = bytes.fromhex("D0CF11E0A1B11AE1")


@pytest.fixture
def servidor(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Leitor RFA</title>", encoding="utf-8")
    (web / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("não", encoding="utf-8")
    srv = criar_servidor(porta=0, pasta_web=web, processos=False)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()
    srv.biblioteca.fechar()


def _get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.status, r.headers, r.read()


def _post(url, corpo, nome="familia.rfa"):
    req = urllib.request.Request(url, data=corpo, method="POST",
                                 headers={"X-Nome": urllib.parse.quote(nome), "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _erro(fn, *a):
    with pytest.raises(urllib.error.HTTPError) as e:
        fn(*a)
    return e.value.code, json.loads(e.value.read().decode("utf-8"))


def test_pagina_e_assets(servidor):
    status, cab, corpo = _get(servidor + "/")
    assert status == 200 and cab["Content-Type"].startswith("text/html") and b"Leitor RFA" in corpo
    status, cab, _ = _get(servidor + "/assets/app.js")
    assert cab["Content-Type"].startswith("text/javascript")


@pytest.mark.parametrize("caminho", ["/../segredo.txt", "/%2e%2e/segredo.txt", "/assets/..%2f..%2fsegredo.txt",
                                     "/..%5csegredo.txt", "/nada.js"])
def test_nao_sai_da_pasta_da_pagina(servidor, caminho):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(servidor + caminho)
    assert e.value.code == 404


def test_recusa_o_que_nao_e_rfa(servidor):
    codigo, corpo = _erro(_post, servidor + "/api/ler", b"isto nao e um arquivo do revit")
    assert codigo == 400 and ".rfa" in corpo["erro"]


def test_ole_que_nao_e_familia_vira_erro_legivel(servidor):
    codigo, corpo = _erro(_post, servidor + "/api/ler", OLE + b"\x00" * 600)
    assert codigo == 422 and corpo["erro"]


def test_id_desconhecido(servidor):
    for rota in ("/api/0123456789abcdef", "/api/0123456789abcdef/modelo.glb", "/api/zz/../modelo.glb"):
        with pytest.raises(urllib.error.HTTPError) as e:
            _get(servidor + rota)
        assert e.value.code == 404


def test_le_familia_real_e_entrega_dados_3d_miniatura_e_bimcraft(servidor, fixtura):
    rfa = (fixtura("r2018") / "familia.rfa").read_bytes()
    status, r = _post(servidor + "/api/ler", rfa, "Ralo Linear 2018.rfa")
    assert status == 200 and len(r["id"]) == 16 and r["nome"] == "Ralo Linear 2018.rfa" and r["miniatura"]
    assert r["familia"]["familia"]["nome"] == "Ralo Linear 2018"
    assert r["familia"]["origem"]["caminho"] == "Ralo Linear 2018.rfa"  # nada da pasta temporária
    assert _get(f"{servidor}/api/{r['id']}")[2] == json.dumps(r, ensure_ascii=False).encode("utf-8")

    _, cab, glb = _get(f"{servidor}/api/{r['id']}/modelo.glb")
    assert cab["Content-Type"] == "model/gltf-binary"
    gltf, nos = ler_glb(glb)
    assert gltf["scenes"][0]["extras"]["completude"]["estado"] == "completo"
    ocultas = [n["extras"] for n in gltf["nodes"] if n["extras"]["visivel_3d"] is False]
    assert ocultas == [{"id": 1412989, "origem": "forma", "classe": "Extrusion", "fonte": "brep_salvo",
                        "visivel_3d": False, "motivo": "hospedeiro simulado"}]

    _, cab, png = _get(f"{servidor}/api/{r['id']}/miniatura.png")
    assert cab["Content-Type"] == "image/png" and png.startswith(b"\x89PNG")

    _, cab, z = _get(f"{servidor}/api/{r['id']}/bimcraft.zip")
    assert "Ralo%20Linear%202018-bimcraft.zip" in cab["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(z)) as arq:
        assert sorted(arq.namelist()) == ["Ralo Linear 2018-dados.json", "Ralo Linear 2018.json"]
        fam = json.loads(arq.read("Ralo Linear 2018.json"))
        dados = json.loads(arq.read("Ralo Linear 2018-dados.json"))
    assert fam["name"] == "Ralo Linear 2018" and fam["forms"]
    assert dados["entrada"] == "Ralo Linear 2018.rfa" and len(dados["rfa_sha256"]) == 64


def test_mesmo_arquivo_duas_vezes_e_o_mesmo_id(servidor, fixtura):
    rfa = (fixtura("r2012") / "familia.rfa").read_bytes()
    assert _post(servidor + "/api/ler", rfa)[1]["id"] == _post(servidor + "/api/ler", rfa)[1]["id"]


def test_nome_seguro():
    assert nome_seguro(urllib.parse.quote("Cuba Modelo A L.830.rfa")) == "Cuba Modelo A L.830.rfa"
    assert nome_seguro(urllib.parse.quote("..\\..\\pasta/x<y>:z.RFA")) == "x_y__z.RFA"
    assert nome_seguro(urllib.parse.quote("notas.txt")) == "notas.txt.rfa"
    assert nome_seguro("") == "familia.rfa" and nome_seguro(urllib.parse.quote("..")) == "familia.rfa"
    assert len(nome_seguro("a" * 500)) <= 124


def test_cli_tem_o_comando_visualizar(capsys):
    with pytest.raises(SystemExit) as e:
        main(["visualizar", "--help"])
    assert e.value.code == 0 and "--porta" in capsys.readouterr().out


def test_3d_feito_em_outro_processo_e_o_mesmo(fixtura):
    from leitor_rfa.servir import Biblioteca
    rfa = (fixtura("r2018") / "familia.rfa").read_bytes()
    com, sem = Biblioteca(processos=True), Biblioteca(processos=False)
    try:
        a, b = com.ler(rfa, "f.rfa"), sem.ler(rfa, "f.rfa")
        assert "futuro" in com.itens[a["id"]]
        assert com.glb(a["id"]) == sem.glb(b["id"])
    finally:
        com.fechar()
        sem.fechar()
