import collections

from leitor_rfa.cli import main
from leitor_rfa.glb import ler_glb
from leitor_rfa.malha import para_glb, partes


def _fechada(p):
    usos = collections.Counter((a, b) for t in p["triangulos"] for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
    return all(usos.get((b, a), 0) == n for (a, b), n in usos.items())


def _volume(p):
    v = p["vertices"]
    return sum(v[a][0] * (v[b][1] * v[c][2] - v[b][2] * v[c][1]) - v[a][1] * (v[b][0] * v[c][2] - v[b][2] * v[c][0])
               + v[a][2] * (v[b][0] * v[c][1] - v[b][1] * v[c][0]) for a, b, c in p["triangulos"]) / 6


def test_formas_viram_solidos_fechados_do_b_rep_salvo(fixtura):
    r = partes(fixtura("r2014") / "familia.rfa")
    formas = [p for p in r["partes"] if p["origem"] == "forma"]
    # a extrusão 1537 é a laje de referência do gabarito (fica em `ocultas`)
    assert sorted(p["classe"] for p in formas) == ["Revolution", "Revolution", "Sweep"]
    for p in formas:
        assert p["fonte"] == "brep_salvo" and not p["faces_nao_suportadas"]
        assert _fechada(p) and _volume(p) > 0


def test_caixa_da_parte_contem_a_caixa_gravada_pelo_revit(fixtura):
    # o Revit grava a caixa da sua tesselação grosseira (polígono inscrito): a da superfície exata a contém
    # e passa dela no máximo uns 5% (círculo em 10 lados: cos 18° = 0,951)
    for p in partes(fixtura("r2014") / "familia.rfa")["partes"]:
        xs = list(zip(*p["vertices"]))
        (mn, mx), (rmn, rmx) = ([min(e) for e in xs], [max(e) for e in xs]), p["caixa_revit_mm"]
        for k in range(3):
            folga = max(1.0, 0.06 * (rmx[k] - rmn[k]))
            assert rmn[k] - folga <= mn[k] <= rmn[k] + 0.01 and rmx[k] - 0.01 <= mx[k] <= rmx[k] + folga, p["classe"]


def test_hospedeiro_simulado_fica_fora_do_3d(fixtura):
    # gabarito baseado em piso: a laje de referência (2438 × 1666 × 305 mm) leva AddGeomToHostInFamEnvGStep
    r = partes(fixtura("r2018") / "familia.rfa")
    assert 1412989 not in [p["id"] for p in r["partes"]]
    assert r["completude"]["ocultas"] == [{"id": 1412989, "classe": "Extrusion", "motivo": "hospedeiro simulado"}]
    for p in r["partes"]:
        assert max(max(e) - min(e) for e in zip(*p["vertices"])) < 300


def test_laje_do_gabarito_sem_o_bit_2_tambem_fica_fora(fixtura):
    # até 2014 a laje de referência (id 1537 do gabarito) não leva o passo de 2018, mas o GeomStepList dela
    # tem m_flags 9 (bit 2 apagado), contra 11 nas formas da família
    r = partes(fixtura("r2012") / "familia.rfa")
    assert 1537 not in [p["id"] for p in r["partes"]]
    assert [o["id"] for o in r["completude"]["ocultas"]] == [1537]


def test_completude_diz_o_que_falta(fixtura):
    r = partes(fixtura("r2018_aninhadas") / "familia.rfa")
    assert r["completude"]["estado"] == "parcial"
    assert any("aninhada" in f for f in r["completude"]["faltando"])


def test_cli_grava_glb_com_um_no_por_parte(fixtura, tmp_path):
    saida = tmp_path / "f.glb"
    assert main([str(fixtura("r2014") / "familia.rfa"), "-o", str(tmp_path / "f.json"), "--glb", str(saida)]) == 0
    gltf, nos = ler_glb(saida.read_bytes())
    assert len(nos) == len(partes(fixtura("r2014") / "familia.rfa")["partes"])
    assert all(n["extras"]["fonte"] == "brep_salvo" for n in gltf["nodes"])


def test_ocultas_entram_marcadas_quando_pedidas(fixtura):
    r = partes(fixtura("r2018") / "familia.rfa", incluir_ocultas=True)
    laje = [p for p in r["partes"] if p["id"] == 1412989]
    assert len(laje) == 1 and laje[0]["visivel_3d"] is False and laje[0]["motivo"] == "hospedeiro simulado"
    assert laje[0]["triangulos"] and r["completude"]["estado"] == "completo"
    visiveis = [p for p in r["partes"] if p["visivel_3d"] is not False]
    assert r["completude"]["triangulos"] == sum(len(p["triangulos"]) for p in visiveis)


def test_arestas_do_b_rep_sem_costura_nem_tangente(fixtura):
    # as linhas que o Revit desenha: bordas entre faces que dobram; a costura do cilindro e a junção de duas
    # faces tangentes ficam de fora
    r = partes(fixtura("r2014") / "familia.rfa")
    for p in r["partes"]:
        assert p["arestas"], p["id"]
        for linha in p["arestas"]:
            assert len(linha) >= 2 and all(0 <= i < len(p["vertices"]) for i in linha)
    gltf, _ = ler_glb(para_glb(r))
    prims = gltf["meshes"][0]["primitives"]
    assert [pr.get("mode", 4) for pr in prims] == [4, 1]
    assert prims[1]["attributes"]["POSITION"] == prims[0]["attributes"]["POSITION"]
