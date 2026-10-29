import math

import pytest

from leitor_rfa.brep import ErroBrep, curva, superficie
from leitor_rfa.grafo import Grafo, Objeto


def _ob(classe, **campos):
    return Objeto(classe, 0, 0, campos)


def _perto(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_reta_e_arco():
    reta = curva(_ob("GLine", m_origin=[1, 2, 3], m_dirVec=[1, 0, 0], m_endParams=[0, 5]))
    assert _perto(reta(2.5), (3.5, 2, 3))
    arco = curva(_ob("GArc", m_center=[0, 0, 0], m_xVec=[1, 0, 0], m_yVec=[0, 1, 0], m_radius=2.0, m_endParams=[0, 1]))
    assert _perto(arco(math.pi / 2), (0, 2, 0))


def test_elipse_usa_os_dois_semieixos():
    el = curva(_ob("GEllipse", m_center=[0, 0, 0], m_xVec=[1, 0, 0], m_yVec=[0, 0, 1], m_xLen=3.0, m_yLen=1.0,
                   m_endParams=[0, math.pi]))
    assert _perto(el(0), (3, 0, 0)) and _perto(el(math.pi / 2), (0, 0, 1))


def test_spline_de_hermite_passa_pelos_nos_e_segue_a_tangente():
    nos = [{"m_iParametr": 0.0, "m_iPoint": [0, 0, 0], "m_iTangent": [1, 0, 0]},
           {"m_iParametr": 2.0, "m_iPoint": [2, 0, 0], "m_iTangent": [1, 0, 0]}]
    h = curva(_ob("GHermiteSpline", m_NodeArray=nos, m_endParams=[0, 2], m_Periodic=False))
    assert _perto(h(0), (0, 0, 0)) and _perto(h(2), (2, 0, 0)) and _perto(h(1), (1, 0, 0))


def test_nurbs_racional_de_grau_2_desenha_o_quarto_de_circulo():
    w = math.sqrt(0.5)
    pts = [{"m_w": 1.0, "m_Point": [1, 0, 0]}, {"m_w": w, "m_Point": [1, 1, 0]}, {"m_w": 1.0, "m_Point": [0, 1, 0]}]
    n = curva(_ob("GNurbSpline", m_Degree=2, m_Rational=True, m_ctrlPoints=pts, m_Knots=[0, 0, 0, 1, 1, 1],
                  m_endParams=[0, 1], m_Closed=False))
    for t in (0.0, 0.3, 0.5, 0.8, 1.0):
        x, y, _ = n(t)
        assert abs(math.hypot(x, y) - 1) < 1e-12


def test_plano_e_cilindro():
    pl = superficie(_ob("Plane", m_origin=[1, 1, 0], m_xVec=[1, 0, 0], m_yVec=[0, 0, 1]), None)
    assert _perto(pl(2, 3), (3, 1, 3))
    cil = superficie(_ob("CylSurf", m_center=[0, 0, 0], m_xVec=[1, 0, 0], m_yVec=[0, 1, 0], m_zVec=[0, 0, 1],
                         m_radius=2.0), None)
    assert _perto(cil(math.pi, 5), (-2, 0, 5))


def test_revolucao_gira_o_perfil_em_torno_do_eixo_z_local():
    perfil = Objeto("GLine", 0, 1, {"m_origin": [1, 0, 0], "m_dirVec": [0, 0, 1], "m_endParams": [0, 1]})
    rev = Objeto("SurfRev", 0, 0, {"m_center": [0, 0, 10], "m_xVec": [1, 0, 0], "m_yVec": [0, 1, 0],
                                    "m_zVec": [0, 0, 1], "m_pProfileCurve": {"indice": 1}})
    f = superficie(rev, Grafo([rev, perfil]))
    assert _perto(f(math.pi / 2, 0.5), (0, 1, 10.5))


def test_cone_mede_v_pela_geratriz_a_partir_do_vertice():
    a = math.radians(30)
    cone = superficie(_ob("ConeSurf", m_center=[0, 0, 0], m_xVec=[1, 0, 0], m_yVec=[0, 1, 0], m_zVec=[0, 0, 1],
                          m_halfAngle=a), None)
    assert _perto(cone(math.pi / 2, 2.0), (0, 2 * math.sin(a), 2 * math.cos(a)))


def test_superficie_desconhecida_e_erro():
    with pytest.raises(ErroBrep):
        superficie(_ob("TorusSurf"), None)


def _viola(tris, pontos, uvs, borda):
    """Arestas internas que ainda pedem giro (ângulos opostos > 180° e giro possível)."""
    from leitor_rfa.brep import _angulo
    from leitor_rfa.triangular import _cruz
    lado = {(t[k], t[(k + 1) % 3]): t[(k + 2) % 3] for t in tris for k in range(3)}
    ruins = []
    for (a, b), c in lado.items():
        d = lado.get((b, a))
        if d is None or (min(a, b), max(a, b)) in borda or a > b:
            continue
        if _angulo(pontos[c], pontos[a], pontos[b]) + _angulo(pontos[d], pontos[b], pontos[a]) > math.pi + 1e-6 \
                and _cruz(uvs[a], uvs[d], uvs[c]) > 0 and _cruz(uvs[d], uvs[b], uvs[c]) > 0:
            ruins.append((a, b))
    return ruins


def test_giro_deixa_a_elipse_de_delaunay_e_preserva_area():
    from leitor_rfa.brep import _girar
    from leitor_rfa.triangular import area, triangular
    n = 400
    uvs = [(math.cos(2 * math.pi * i / n), 0.3 * math.sin(2 * math.pi * i / n)) for i in range(n)]  # elipse: não cocircular
    tris = triangular(uvs, [list(range(n))])  # recorte de orelhas: leque de triângulos finos
    pontos = [(u, v, 0.0) for u, v in uvs]
    borda = {(min(i, (i + 1) % n), max(i, (i + 1) % n)) for i in range(n)}
    assert _viola(tris, pontos, uvs, borda)
    girados = _girar(tris, uvs, pontos, borda)
    assert len(girados) == len(tris) and not _viola(girados, pontos, uvs, borda)
    soma = sum(area([uvs[a], uvs[b], uvs[c]]) for a, b, c in girados)
    assert soma == pytest.approx(area(uvs)) and all(area([uvs[a], uvs[b], uvs[c]]) > 0 for a, b, c in girados)


def test_faixa_de_cilindro_vira_tiras_sem_ponto_novo():
    # recorte de orelhas faz leque do canto de cima para toda a borda de baixo (reta no UV); girando no UV
    # com a métrica da superfície o leque vira tiras, e a corda de cada tira já fica dentro da flecha
    from leitor_rfa.brep import Malha, _refinar
    from leitor_rfa.triangular import triangular
    r, h, n = 210 / 304.8, 75 / 304.8, 27
    uvs = [(math.pi * i / (n - 1), 0.0) for i in range(n)] + [(math.pi * i / (n - 1), h) for i in reversed(range(n))]
    def avaliar(u, v):
        return (r * math.cos(u), r * math.sin(u), v)
    malha = Malha()
    verts = [malha.vertice(avaliar(*uv)) for uv in uvs]
    borda = {(min(i, (i + 1) % len(uvs)), max(i, (i + 1) % len(uvs))) for i in range(len(uvs))}
    tris = triangular(uvs, [list(range(len(uvs)))])
    saida = _refinar(tris, uvs, verts, borda, avaliar, malha, flecha=0.66 / 304.8)
    assert len(uvs) == 2 * n and len(saida) == 2 * n - 2
    assert all(any(uvs[i][1] == 0 for i in t) and any(uvs[i][1] == h for i in t) for t in saida)


def test_polo_entra_no_laco_no_u_de_cada_vizinho():
    # cone com vértice em v = 1 (todos os u são o mesmo ponto): o laço salvo passa pelo polo uma vez e vai em
    # diagonal para o outro lado do retângulo UV, deixando furos de fora; repetindo o polo, o retângulo fecha
    from leitor_rfa.brep import _polos
    def cone(u, v):
        return ((v - 1) * math.cos(u), (v - 1) * math.sin(u), v)
    laco = [(10, (0.0, 2.0)), (11, (0.0, 1.0)), (12, (math.pi, 2.0))]
    assert _polos(laco, cone) == [(10, (0.0, 2.0)), (11, (0.0, 1.0)), (11, (math.pi, 1.0)), (12, (math.pi, 2.0))]
    assert _polos([(1, (0.0, 2.0)), (2, (1.0, 2.0)), (3, (1.0, 3.0))], cone) == [(1, (0.0, 2.0)), (2, (1.0, 2.0)), (3, (1.0, 3.0))]
