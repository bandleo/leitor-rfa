from leitor_rfa.triangular import area, triangular


def _area_tris(pts, tris):
    return sum(abs(area([pts[a], pts[b], pts[c]])) for a, b, c in tris)


def _dentro(p, a, b, c):
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
    return (d1 > 0 and d2 > 0 and d3 > 0) or (d1 < 0 and d2 < 0 and d3 < 0)


def test_quadrado():
    pts = [(0, 0), (1, 0), (1, 1), (0, 1)]
    tris = triangular(pts, [list(range(4))])
    assert len(tris) == 2 and abs(_area_tris(pts, tris) - 1) < 1e-12


def test_poligono_concavo_em_l():
    pts = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
    tris = triangular(pts, [list(range(6))])
    assert len(tris) == 4 and abs(_area_tris(pts, tris) - 3) < 1e-12


def test_furo_fica_vazio_e_a_area_desconta():
    pts = [(0, 0), (4, 0), (4, 4), (0, 4), (1, 1), (1, 3), (3, 3), (3, 1)]
    tris = triangular(pts, [[0, 1, 2, 3], [4, 5, 6, 7]])
    assert abs(_area_tris(pts, tris) - 12) < 1e-9
    assert not any(_dentro((2, 2), pts[a], pts[b], pts[c]) for a, b, c in tris)


def test_dois_furos_e_sentido_horario_no_contorno():
    pts = [(0, 0), (0, 3), (6, 3), (6, 0),
           (1, 1), (2, 1), (2, 2), (1, 2), (4, 1), (5, 1), (5, 2), (4, 2)]
    tris = triangular(pts, [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]])
    assert abs(_area_tris(pts, tris) - 16) < 1e-9


def test_pontos_colineares_no_contorno():
    pts = [(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1)]
    tris = triangular(pts, [list(range(6))])
    assert abs(_area_tris(pts, tris) - 2) < 1e-12
