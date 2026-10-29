"""Triangulação de polígonos planos com furos (recorte de orelhas), para as faces do B-rep em UV.

`triangular(pontos, lacos)`: os laços são listas de índices em `pontos`; contorno e furo saem da
profundidade de inclusão (par = contorno, ímpar = furo), como num B-rep com mais de um contorno por face.
Cada furo é ligado ao seu contorno por uma ponte até um vértice visível (Eberly, "Triangulation by Ear
Clipping"); depois as orelhas são cortadas. Os triângulos saem no sentido anti-horário (área positiva).
"""

EPS = 1e-14


def area(poligono):
    """Área com sinal (positiva no sentido anti-horário)."""
    n = len(poligono)
    return sum(poligono[i][0] * poligono[(i + 1) % n][1] - poligono[(i + 1) % n][0] * poligono[i][1]
               for i in range(n)) / 2


def _cruz(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _dentro_poligono(p, poligono):
    dentro, n = False, len(poligono)
    for i in range(n):
        a, b = poligono[i], poligono[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            dentro = not dentro
    return dentro


def _no_triangulo(p, a, b, c):
    return _cruz(a, b, p) >= -EPS and _cruz(b, c, p) >= -EPS and _cruz(c, a, p) >= -EPS


def _ligar(contorno, furo, pts):
    """Junta o furo (horário) ao contorno (anti-horário) por uma ponte a partir do vértice mais à direita."""
    m = max(range(len(furo)), key=lambda i: (pts[furo[i]][0], -pts[furo[i]][1]))
    mp = pts[furo[m]]
    melhor, x_melhor = None, float("inf")
    for i in range(len(contorno)):
        a, b = pts[contorno[i]], pts[contorno[(i + 1) % len(contorno)]]
        if (a[1] - mp[1]) * (b[1] - mp[1]) > 0 or a[1] == b[1]:
            continue
        x = a[0] + (mp[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        if mp[0] <= x < x_melhor:
            x_melhor = x
            melhor = i if a[0] > b[0] else (i + 1) % len(contorno)
    if melhor is None:
        raise ValueError("furo fora do contorno")
    pi_ = (x_melhor, mp[1])
    cand = pts[contorno[melhor]]
    escolhido, menor = melhor, None
    for i in range(len(contorno)):
        q = pts[contorno[i]]
        if i == melhor or q == mp:
            continue
        ant, prox = pts[contorno[i - 1]], pts[contorno[(i + 1) % len(contorno)]]
        if _cruz(ant, q, prox) > EPS:
            continue  # vértice convexo não bloqueia
        tri = (mp, pi_, cand) if _cruz(mp, pi_, cand) >= 0 else (mp, cand, pi_)
        if _no_triangulo(q, *tri):
            ang = abs(q[1] - mp[1]) / max(q[0] - mp[0], EPS)
            if menor is None or ang < menor:
                escolhido, menor = i, ang
    furo = furo[m:] + furo[:m]
    return contorno[:escolhido + 1] + furo + [furo[0], contorno[escolhido]] + contorno[escolhido + 1:]


def _orelhas(idx, pts):
    tris, idx = [], list(idx)
    tentativas = 0
    while len(idx) > 3:
        n, cortou = len(idx), False
        reflexos = [k for k in range(n) if _cruz(pts[idx[k - 1]], pts[idx[k]], pts[idx[(k + 1) % n]]) <= EPS]
        for i in range(n):
            a, b, c = pts[idx[i - 1]], pts[idx[i]], pts[idx[(i + 1) % n]]
            if _cruz(a, b, c) <= EPS:
                continue
            if any(k not in (i - 1 if i else n - 1, i, (i + 1) % n) and pts[idx[k]] not in (a, b, c)
                   and _no_triangulo(pts[idx[k]], a, b, c) for k in reflexos):
                continue
            tris.append((idx[i - 1], idx[i], idx[(i + 1) % n]))
            idx.pop(i)
            cortou = True
            break
        if not cortou:
            # nenhuma orelha limpa: tira um vértice degenerado (colinear ou repetido) ou corta a de menor dano
            k = min(range(n), key=lambda k: abs(_cruz(pts[idx[k - 1]], pts[idx[k]], pts[idx[(k + 1) % n]])))
            if abs(_cruz(pts[idx[k - 1]], pts[idx[k]], pts[idx[(k + 1) % n]])) > EPS:
                tentativas += 1
                if tentativas > n:
                    raise ValueError("polígono sem orelha")
                k = max(range(n), key=lambda k: _cruz(pts[idx[k - 1]], pts[idx[k]], pts[idx[(k + 1) % n]]))
                tris.append((idx[k - 1], idx[k], idx[(k + 1) % n]))
            idx.pop(k)
    if len(idx) == 3 and _cruz(pts[idx[0]], pts[idx[1]], pts[idx[2]]) > EPS:
        tris.append(tuple(idx))
    return tris


def triangular(pontos, lacos):
    """Triângulos (índices em `pontos`, anti-horários) que cobrem os laços: contornos menos furos."""
    lacos = [list(l) for l in lacos if len(l) >= 3]
    polis = [[pontos[i] for i in l] for l in lacos]
    prof = [sum(1 for j, q in enumerate(polis) if j != i and _dentro_poligono(p[0], q)) for i, p in enumerate(polis)]
    tris = []
    for i, laco in enumerate(lacos):
        if prof[i] % 2:
            continue
        contorno = laco if area(polis[i]) > 0 else laco[::-1]
        furos = [(lacos[j] if area(polis[j]) < 0 else lacos[j][::-1]) for j in range(len(lacos))
                 if prof[j] == prof[i] + 1 and _dentro_poligono(polis[j][0], polis[i])]
        for furo in sorted(furos, key=lambda f: -max(pontos[k][0] for k in f)):
            contorno = _ligar(contorno, furo, pontos)
        tris += _orelhas(contorno, pontos)
    return tris
