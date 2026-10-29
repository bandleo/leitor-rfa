import json
import shutil
import subprocess

import pytest

from leitor_rfa.bimcraft import BIMCRAFT_CLI, converter, main
from leitor_rfa.fonte import ler_familia

QUADRADO = [[[0.0, 0.0, 10.0], [100.0, 0.0, 10.0], [100.0, 0.0, 10.0], [100.0, 50.0, 10.0], [100.0, 50.0, 10.0],
             [0.0, 50.0, 10.0], [0.0, 50.0, 10.0], [0.0, 0.0, 10.0]]]


def _par(nome, tipo_dado, **kw):
    return {"nome": nome, "grupo": None, "instancia": False, "compartilhado": False, "guid": None,
            "tipo_dado": tipo_dado, "formula": None, "reporting": False, **kw}


def _forma(**kw):
    f = {"tipo": "Extrusion", "solido": True, "parametro_visivel": None, "parametro_material": None,
         "esboco_mm": QUADRADO, "inicio_mm": 0.0, "fim_mm": 100.0,
         "plano": {"origem_mm": [0.0, 0.0, 10.0], "x": [1, 0, 0], "y": [0, 1, 0], "normal": [0.0, 0.0, 1.0]}}
    f.update(kw)
    return f


def _doc(parametros=(), tipos=None, formas=(), categoria_id=-2001160):
    return {"versao_esquema": 1, "familia": {"nome": "Peça", "categoria_id": categoria_id},
            "parametros": list(parametros), "tipos": tipos or {"T": {}}, "formas": list(formas)}


def test_categoria_pela_categoria_do_revit():
    assert converter(_doc())[0]["category"] == "plumbing"  # Peças hidrossanitárias
    assert converter(_doc(categoria_id=-2008049))[0]["category"] == "generic"


def test_parametros_tipos_e_dados_de_texto():
    pars = [_par("Altura", "autodesk.spec.aec:length-2.0.1"), _par("Furo", "autodesk.spec:spec.bool-1.0.0"),
            _par("Peso", "autodesk.spec.aec:number-2.0.0"), _par("Acabamento", "autodesk.spec.aec:material-1.0.0"),
            _par("Fabricante", "autodesk.spec:spec.string-2.0.0", instancia=False)]
    tipos = {"P": {"Altura": {"bruto": 0.5, "mm": 152.4}, "Furo": {"bruto": 1}, "Peso": {"bruto": 2.5},
                   "Fabricante": {"bruto": "Fabricante X"}},
             "G": {"Altura": {"bruto": 1.0, "mm": 304.8}, "Furo": {"bruto": 0}, "Peso": {"bruto": 3.0},
                   "Fabricante": {"bruto": "Fabricante X"}}}
    fam, rel = converter(_doc(pars, tipos))
    kinds = {p["name"]: p["kind"] for p in fam["parameters"]}
    assert kinds == {"Altura": "length", "Furo": "yesno", "Peso": "number", "Acabamento": "material"}
    assert fam["types"]["G"] == {"Altura": 304.8, "Furo": False, "Peso": 3.0}
    assert rel["dados"] == {"P": {"Fabricante": "Fabricante X"}, "G": {"Fabricante": "Fabricante X"}}


def test_formula_em_mm_passa_e_a_sem_traducao_fica_no_relatorio():
    pars = [_par("A", "autodesk.spec.aec:length-2.0.1"),
            _par("B", "autodesk.spec.aec:length-2.0.1", formula="A / 2 + 7.5 mm"),
            _par("C", "autodesk.spec.aec:length-2.0.1", formula="size_lookup(T, \"C\", 1 mm, A)")]
    fam, rel = converter(_doc(pars, {"T": {"A": {"bruto": 1, "mm": 304.8}}}))
    formulas = {p["name"]: p.get("formula") for p in fam["parameters"]}
    assert formulas == {"A": None, "B": "A / 2 + 7.5", "C": None}
    assert [f["parametro"] for f in rel["formulas_fora"]] == ["C"]


def test_nome_de_parametro_fora_da_regra_do_bimcraft_e_ajustado():
    pars = [_par("Peso Liquido (Kg)", "autodesk.spec.aec:number-2.0.0"),
            _par("2a Saída", "autodesk.spec.aec:length-2.0.1"),
            _par("Dobro", "autodesk.spec.aec:length-2.0.1", formula="2a Saída * 2")]
    fam, rel = converter(_doc(pars, {"T": {"Peso Liquido (Kg)": {"bruto": 0.58}, "2a Saída": {"bruto": 0.1, "mm": 30.48}}}))
    assert [p["name"] for p in fam["parameters"]] == ["Peso Liquido Kg", "P 2a Saída", "Dobro"]
    assert fam["parameters"][2]["formula"] == "P 2a Saída * 2" and fam["types"]["T"]["Peso Liquido Kg"] == 0.58
    assert rel["nomes"] == {"Peso Liquido (Kg)": "Peso Liquido Kg", "2a Saída": "P 2a Saída"}


def test_extrusao_no_plano_xy_varre_ao_longo_da_normal():
    forma = converter(_doc(formas=[_forma()]))[0]["forms"][0]
    assert forma["plane"] == "xy" and forma["profile"] == [[0, 0], [100, 0], [100, 50], [0, 50]]
    assert (forma["from"], forma["to"]) == (10, 110)
    para_baixo = converter(_doc(formas=[_forma(plano=dict(_forma()["plano"], normal=[0, 0, -1]))]))[0]["forms"][0]
    assert (para_baixo["from"], para_baixo["to"]) == (-90, 10)


def test_plano_vertical_xz():
    esboco = [[[x, 30.0, z] for x, _, z in [[0, 0, 0], [100, 0, 0], [100, 0, 50], [0, 0, 50]]]]
    plano = {"origem_mm": [0.0, 30.0, 0.0], "x": [1, 0, 0], "y": [0, 0, 1], "normal": [0.0, -1.0, 0.0]}
    forma = converter(_doc(formas=[_forma(esboco_mm=esboco, plano=plano, inicio_mm=0.0, fim_mm=20.0)]))[0]["forms"][0]
    assert forma["plane"] == "xz" and forma["profile"] == [[0, 0], [100, 0], [100, 50], [0, 50]]
    assert (forma["from"], forma["to"]) == (10, 30)


def test_revolucao_com_eixo_e_angulos():
    rev = _forma(tipo="Revolution", inicio_mm=None, fim_mm=None, eixo_mm=[[0.0, 0.0, 10.0], [0.0, 50.0, 10.0]],
                 angulo_inicio=0.0, angulo_fim=360.0)
    forma = converter(_doc(formas=[rev]))[0]["forms"][0]
    assert forma["axis"] == [[0, 0], [0, 50]] and (forma["from"], forma["to"]) == (0, 360)


def test_vazio_furo_material_e_o_que_fica_fora():
    furo = QUADRADO + [[[20.0, 20.0, 10.0], [40.0, 20.0, 10.0], [40.0, 30.0, 10.0], [20.0, 30.0, 10.0], [20.0, 20.0, 10.0]]]
    formas = [_forma(solido=False), _forma(esboco_mm=furo, parametro_material="Acabamento"),
              {"tipo": "Sweep", "solido": True, "esboco_mm": []}]
    pars = [_par("Acabamento", "autodesk.spec.aec:material-1.0.0")]
    fam, rel = converter(_doc(pars, formas=formas))
    assert [(f.get("void", False), f.get("material")) for f in fam["forms"]] == [
        (False, "Acabamento"), (True, None), (True, None)]  # sólido, furo dele, e os vazios no fim
    assert rel["formas"]["convertidas"] == 2 and [f["tipo"] for f in rel["formas"]["fora"]] == ["Sweep"]


def test_revolucao_ponto_no_eixo_com_ruido_vai_para_o_eixo():
    perfil = [[[0.0002, 0.0, 10.0], [30.0, 0.0, 10.0], [30.0, 50.0, 10.0], [-0.0001, 50.0, 10.0], [0.0002, 0.0, 10.0]]]
    rev = _forma(tipo="Revolution", esboco_mm=perfil, inicio_mm=None, fim_mm=None,
                 eixo_mm=[[0.0, 0.0, 10.0], [0.0, 50.0, 10.0]], angulo_inicio=0.0, angulo_fim=360.0)
    forma = converter(_doc(formas=[rev]))[0]["forms"][0]
    assert [p[0] for p in forma["profile"]] == [0.001, 30, 30, 0.001]  # do lado do perfil, a 0,001 mm do eixo
    cruza = dict(rev, esboco_mm=[[[-5.0, 0.0, 10.0], [30.0, 0.0, 10.0], [30.0, 50.0, 10.0], [-5.0, 50.0, 10.0]]])
    fam, rel = converter(_doc(formas=[cruza]))
    assert fam["forms"] == [] and "cruza o eixo" in rel["formas"]["fora"][0]["motivo"]


def test_familia_real_lida_pelo_leitor_vira_familia_bimcraft(fixtura, tmp_path):
    doc, _ = ler_familia(fixtura("r2014") / "familia.rfa")
    entrada = tmp_path / "familia.json"
    entrada.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert main([str(entrada), "-o", str(tmp_path / "bim.json"), "--dados", str(tmp_path / "dados.json")]) == 0
    fam = json.loads((tmp_path / "bim.json").read_text(encoding="utf-8"))
    assert fam["name"] == "familia" and fam["category"] == "plumbing" and fam["forms"]


@pytest.mark.skipif(not BIMCRAFT_CLI.is_file(), reason="BIMCraft não instalado")
def test_bimcraft_carrega_a_familia_convertida(fixtura, tmp_path):
    doc, _ = ler_familia(fixtura("r2014") / "familia.rfa")
    fam, _ = converter(doc)
    (tmp_path / "bim.json").write_text(json.dumps(fam, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([str(BIMCRAFT_CLI), "run", "--cmd", "family " + json.dumps({"path": str(tmp_path / "bim.json")})],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.splitlines()[0])["name"] == "familia"


def test_hospedeiro_simulado_nao_entra_na_familia_bimcraft():
    fam, rel = converter(_doc(formas=[_forma(), _forma(hospedeiro_simulado=True)]))
    assert len(fam["forms"]) == 1 and rel["formas"]["convertidas"] == 1
    assert rel["formas"]["fora"] == [{"indice": 1, "tipo": "Extrusion",
                                      "motivo": "hospedeiro simulado: a laje/parede de referência do gabarito"}]


def test_acha_o_bimcraft_cli_instalado_antes_do_portatil(tmp_path):
    from leitor_rfa.bimcraft import achar_cli
    instalado = tmp_path / "pf" / "BIMCraft" / "bimcraft-cli.exe"
    portatil = tmp_path / "local" / "Programs" / "BIMCraft" / "bimcraft-0.8.0-windows-x64-portable" / "bimcraft-cli.exe"
    portatil.parent.mkdir(parents=True)
    portatil.write_bytes(b"")
    ambiente = {"ProgramFiles": str(tmp_path / "pf"), "LOCALAPPDATA": str(tmp_path / "local"), "PATH": ""}
    assert achar_cli(ambiente) == portatil
    instalado.parent.mkdir(parents=True)
    instalado.write_bytes(b"")
    assert achar_cli(ambiente) == instalado
    assert achar_cli({**ambiente, "BIMCRAFT_CLI": str(tmp_path / "outro.exe")}) == tmp_path / "outro.exe"
