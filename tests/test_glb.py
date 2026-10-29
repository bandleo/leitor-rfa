import json
import pathlib
import struct

from leitor_rfa.glb import escrever_glb, ler_glb


def _parte(nome="caixa", **extras):
    return {"nome": nome, "vertices": [(0, 0, 0), (1000, 0, 0), (0, 2000, 0), (0, 0, 3000)],
            "triangulos": [(0, 1, 2), (0, 1, 3)], "cor": (0.8, 0.8, 0.8, 1.0), "extras": extras}


def test_cabecalho_e_blocos():
    dados = escrever_glb([_parte()])
    magia, versao, total = struct.unpack_from("<4sII", dados, 0)
    assert magia == b"glTF" and versao == 2 and total == len(dados)
    n_json, tipo_json = struct.unpack_from("<I4s", dados, 12)
    assert tipo_json == b"JSON" and n_json % 4 == 0
    gltf = json.loads(dados[20:20 + n_json])
    assert gltf["asset"]["version"] == "2.0"
    n_bin, tipo_bin = struct.unpack_from("<I4s", dados, 20 + n_json)
    assert tipo_bin == b"BIN\x00" and n_bin % 4 == 0


def test_mm_com_z_para_cima_vira_metro_com_y_para_cima():
    gltf, partes = ler_glb(escrever_glb([_parte()]))
    pos = partes[0]["posicoes"]
    assert pos[1] == (1.0, 0.0, 0.0)
    assert pos[2] == (0.0, 0.0, -2.0)
    assert pos[3] == (0.0, 3.0, 0.0)
    acc = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert acc["min"] == [0.0, 0.0, -2.0] and acc["max"] == [1.0, 3.0, 0.0]


def test_um_no_por_parte_com_extras_e_material_de_dois_lados():
    gltf, partes = ler_glb(escrever_glb([_parte("a", origem="forma", id=7), _parte("b", origem="combinacao")]))
    assert [n["name"] for n in gltf["nodes"]] == ["a", "b"]
    assert gltf["nodes"][0]["extras"] == {"origem": "forma", "id": 7}
    assert all(m["doubleSided"] for m in gltf["materials"])
    assert partes[1]["triangulos"] == [(0, 1, 2), (0, 1, 3)]


def test_parte_vazia_fica_de_fora():
    gltf, partes = ler_glb(escrever_glb([_parte(), {"nome": "nada", "vertices": [], "triangulos": []}]))
    assert len(gltf["nodes"]) == 1 and len(partes) == 1


def test_extras_da_cena_levam_a_completude():
    gltf, _ = ler_glb(escrever_glb([_parte()], extras={"completude": {"estado": "parcial", "faltando": ["x"]}}))
    assert gltf["scenes"][0]["extras"] == {"completude": {"estado": "parcial", "faltando": ["x"]}}


CONTRATO = pathlib.Path(__file__).resolve().parents[1] / "web" / "tests" / "dados" / "contrato.glb"


def glb_do_contrato():
    """GLB que os testes da página (web/tests/contrato.test.ts) leem com o GLTFLoader do three.js."""
    from leitor_rfa.malha import para_glb
    cubo = [(x, y, z) for z in (0, 300) for y in (0, 200) for x in (0, 100)]
    faces = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
             (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
    laje = [(x, y, z) for z in (-300, 0) for y in (-500, 500) for x in (-500, 500)]
    r = {"partes": [{"id": 101, "origem": "forma", "classe": "Extrusion", "fonte": "brep_salvo", "visivel_3d": None,
                     "vertices": cubo, "triangulos": faces,
                     "arestas": [[0, 1, 3, 2, 0], [4, 5, 7, 6, 4], [0, 4], [1, 5], [2, 6], [3, 7]]},
                    {"id": 1537, "origem": "forma", "classe": "Extrusion", "fonte": "brep_salvo", "visivel_3d": False,
                     "motivo": "hospedeiro simulado", "vertices": laje, "triangulos": faces}],
         "completude": {"estado": "parcial", "faltando": ["1 instância de família aninhada ainda sem 3D"],
                        "vazios": 0, "ocultas": [{"id": 1537, "classe": "Extrusion", "motivo": "hospedeiro simulado"}],
                        "triangulos": 12}}
    return para_glb(r, gerador="leitor-rfa contrato")


def test_glb_do_contrato_da_pagina_esta_em_dia():
    # se mudar, regerar: python -I -X utf8 -c "from tests.test_glb import *; CONTRATO.write_bytes(glb_do_contrato())"
    assert CONTRATO.read_bytes() == glb_do_contrato()


def test_para_glb_nomeia_em_portugues_e_marca_o_que_o_revit_oculta():
    gltf, nos = ler_glb(glb_do_contrato())
    assert [n["name"] for n in gltf["nodes"]] == ["Extrusão 101", "Extrusão 1537"]
    assert gltf["nodes"][1]["extras"] == {"id": 1537, "origem": "forma", "classe": "Extrusion", "fonte": "brep_salvo",
                                          "visivel_3d": False, "motivo": "hospedeiro simulado"}
    assert gltf["scenes"][0]["extras"]["completude"]["estado"] == "parcial"
    assert len(nos[0]["triangulos"]) == 12
