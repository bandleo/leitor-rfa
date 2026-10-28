import json
import math
import pathlib

import pytest

from leitor_rfa.conferencia import esboco_igual
from leitor_rfa.documento import ler
from leitor_rfa.formas import encadear, segmentos_arco, tesselar

COM_GABARITO = ("r2012_pa2010", "r2012", "r2012_sem_previa", "r2013", "r2014", "r2018", "r2012_aninhada",
                "r2018_aninhadas")
MM = 1 / 304.8  # pés


def _doc_e_gab(fixtura, nome):
    gab = json.loads((fixtura(nome) / "familia.json").read_text(encoding="utf-8"))
    doc = ler(fixtura(nome) / "familia.rfa", nome_arquivo=pathlib.PureWindowsPath(gab["origem"]["caminho"]).name)
    return doc, gab


@pytest.mark.parametrize("raio_mm, graus, esperado", [
    (50.0, 180, 7), (13.0, 180, 4), (600.0, 180, 22), (400.0, 50.99, 5), (3.0, 180, 2), (0.85, 180, 2)])
def test_segmentos_do_arco_como_o_revit(raio_mm, graus, esperado):
    assert segmentos_arco(raio_mm * MM, math.radians(graus)) == esperado


def test_circulo_vira_duas_metades():
    circulo = {"tipo": "arco", "centro": (0.0, 0.0, 0.0), "raio": 5 * MM, "x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0),
               "t": (0.0, 0.0)}
    pontos = tesselar(circulo)
    assert len(pontos) == 5  # 2 + 2 segmentos; o primeiro ponto volta no fim
    assert pontos[0] == pytest.approx(pontos[-1])


def test_encadear_linhas_fora_de_ordem_e_invertidas():
    def linha(a, b):
        return {"tipo": "linha", "p0": a, "p1": b}
    q = [linha((0, 0, 0), (1, 0, 0)), linha((1, 1, 0), (0, 1, 0)), linha((1, 1, 0), (1, 0, 0)), linha((0, 0, 0), (0, 1, 0))]
    lacos = encadear(q)
    assert len(lacos) == 1 and len(lacos[0]) == 4
    pontos = [p for c, invertida in lacos[0] for p in (tesselar(c)[::-1] if invertida else tesselar(c))]
    assert all(pontos[i] == pytest.approx(pontos[i + 1]) for i in range(1, len(pontos) - 1, 2))  # pontas coincidem


@pytest.mark.parametrize("nome", COM_GABARITO)
def test_formas_iguais_ao_gabarito(fixtura, nome):
    doc, gab = _doc_e_gab(fixtura, nome)
    assert len(doc["formas"]) == len(gab["formas"])
    for lida, esperada in zip(doc["formas"], gab["formas"]):  # mesma ordem: id do elemento
        for campo in ("tipo", "solido", "parametro_visivel", "parametro_material"):
            assert lida[campo] == esperada[campo], campo
        for campo in ("inicio_mm", "fim_mm"):
            if esperada[campo] is None:
                assert lida[campo] is None
            else:
                assert lida[campo] == pytest.approx(esperada[campo], abs=1e-6)
        assert esboco_igual(lida["esboco_mm"], esperada["esboco_mm"]), esperada["tipo"]
    assert doc["cobertura"]["secoes"]["formas"]["estado"] == "decifrado"


def test_extrusao_traz_o_plano_do_esboco(fixtura):
    f = ler(fixtura("r2012") / "familia.rfa")["formas"][0]  # extrusão no plano de referência (z = 0)
    assert f["tipo"] == "Extrusion"
    assert f["plano"]["normal"] == pytest.approx([0, 0, 1], abs=1e-9)
    assert f["plano"]["origem_mm"] == pytest.approx([0, 0, 0], abs=1e-6)


def test_revolucao_traz_eixo_e_angulos(fixtura):
    f = ler(fixtura("r2012") / "familia.rfa")["formas"][1]
    assert f["tipo"] == "Revolution"
    (x0, y0, z0), (x1, y1, z1) = f["eixo_mm"]
    assert x0 == pytest.approx(0, abs=1e-6) and x1 == pytest.approx(0, abs=1e-6)  # eixo vertical em x = 0
    assert sorted([y0, y1]) == pytest.approx([122.516, 132.516], abs=1e-3) and z0 == pytest.approx(z1)
    assert (f["angulo_inicio"], f["angulo_fim"]) == pytest.approx((0, 360))
    assert f["plano"]["normal"] == pytest.approx([0, 0, 1], abs=1e-9)
