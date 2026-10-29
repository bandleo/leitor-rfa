"""Geometria salva: o B-rep que o Revit regenerou e gravou no canal 103, em malha de triângulos.

Cada elemento com geometria tem no canal 103 um GElement → Geometry → Face/EdgeLoop/Edge. A face aponta
para a superfície (m_pSurf); o laço encadeia arestas (m_next do lado da face); a aresta guarda as pontas e
alguns pontos interiores em UV dos DOIS lados (m_firstAndLastEdgePnts / m_interiorEdgePnts, "uv"[lado]).
Não há ponto 3D na aresta: ele sai da superfície. Comprimentos em pés.

Curvas e superfícies seguem as convenções do rvt-rs (native_parametric_surface.rs, Apache-2.0) onde ele as
cobre (Plane, CylSurf, SurfRev, RuledSurf; GLine, GArc); as demais foram tiradas dos próprios arquivos e
conferidas pelo ponto da aresta, que tem de ser o mesmo nos dois lados (`conferir_arestas`).
"""
import bisect
import math

from .grafo import ErroGrafo, decodificar
from .triangular import triangular


class ErroBrep(Exception):
    """Geometria salva fora do que o leitor sabe avaliar."""


def _soma(*vs):
    return tuple(sum(c) for c in zip(*vs))


def _esc(v, s):
    return tuple(c * s for c in v)


# --- curvas: t -> ponto (pés) -------------------------------------------------------------------------------

def _hermite(p0, m0, p1, m1, h, s):
    s2, s3 = s * s, s * s * s
    return _soma(_esc(p0, 2 * s3 - 3 * s2 + 1), _esc(m0, h * (s3 - 2 * s2 + s)),
                 _esc(p1, -2 * s3 + 3 * s2), _esc(m1, h * (s3 - s2)))


def _de_boor(grau, nos, pontos, pesos, t):
    n = len(pontos)
    t = min(max(t, nos[grau]), nos[n])
    k = min(max(bisect.bisect_right(nos, t) - 1, grau), n - 1)
    d = [(*_esc(pontos[j], pesos[j]), pesos[j]) for j in range(k - grau, k + 1)]
    for r in range(1, grau + 1):
        for j in range(grau, r - 1, -1):
            i = j + k - grau
            den = nos[i + grau - r + 1] - nos[i]
            a = (t - nos[i]) / den if den else 0.0
            d[j] = tuple((1 - a) * x + a * y for x, y in zip(d[j - 1], d[j]))
    w = d[grau][3]
    return tuple(c / w for c in d[grau][:3])


def curva(ob):
    """Função t -> ponto da curva salva (GLine, GArc, GEllipse, GHermiteSpline, GNurbSpline)."""
    c = ob.campos
    if ob.classe == "GLine":
        o, d = tuple(c["m_origin"]), tuple(c["m_dirVec"])
        return lambda t: _soma(o, _esc(d, t))
    if ob.classe in ("GArc", "GEllipse"):
        ce, x, y = tuple(c["m_center"]), tuple(c["m_xVec"]), tuple(c["m_yVec"])
        rx, ry = (c["m_radius"], c["m_radius"]) if ob.classe == "GArc" else (c["m_xLen"], c["m_yLen"])
        return lambda t: _soma(ce, _esc(x, rx * math.cos(t)), _esc(y, ry * math.sin(t)))
    if ob.classe == "GHermiteSpline":
        nos = c["m_NodeArray"]
        ts = [n["m_iParametr"] for n in nos]
        ps = [tuple(n["m_iPoint"]) for n in nos]
        ms = [tuple(n["m_iTangent"]) for n in nos]

        def hermite(t):
            i = min(max(bisect.bisect_right(ts, t) - 1, 0), len(ts) - 2)
            h = ts[i + 1] - ts[i]
            return _hermite(ps[i], ms[i], ps[i + 1], ms[i + 1], h, (t - ts[i]) / h if h else 0.0)
        return hermite
    if ob.classe == "GNurbSpline":
        pts = [tuple(p["m_Point"]) for p in c["m_ctrlPoints"]]
        pesos = [p["m_w"] if c["m_Rational"] else 1.0 for p in c["m_ctrlPoints"]]
        return lambda t: _de_boor(c["m_Degree"], c["m_Knots"], pts, pesos, t)
    raise ErroBrep(f"curva {ob.classe} não suportada")


# --- superfícies: (u, v) -> ponto (pés) ---------------------------------------------------------------------

def superficie(ob, gr):
    """Função (u, v) -> ponto da superfície salva."""
    c = ob.campos
    if ob.classe == "Plane":
        o, x, y = tuple(c["m_origin"]), tuple(c["m_xVec"]), tuple(c["m_yVec"])
        return lambda u, v: _soma(o, _esc(x, u), _esc(y, v))
    if ob.classe == "CylSurf":
        ce, x, y, z, r = tuple(c["m_center"]), tuple(c["m_xVec"]), tuple(c["m_yVec"]), tuple(c["m_zVec"]), c["m_radius"]
        return lambda u, v: _soma(ce, _esc(x, r * math.cos(u)), _esc(y, r * math.sin(u)), _esc(z, v))
    if ob.classe == "SurfRev":
        ce, x, y, z = tuple(c["m_center"]), tuple(c["m_xVec"]), tuple(c["m_yVec"]), tuple(c["m_zVec"])
        perfil = curva(gr.alvo(c["m_pProfileCurve"]))

        def rev(u, v):
            q = perfil(v)
            cu, su = math.cos(u), math.sin(u)
            return _soma(ce, _esc(x, q[0] * cu - q[1] * su), _esc(y, q[0] * su + q[1] * cu), _esc(z, q[2]))
        return rev
    if ob.classe == "RuledSurf":
        c1, c2 = gr.alvo(c["m_pProfileCurve1"]), gr.alvo(c["m_pProfileCurve2"])
        f1, f2 = curva(c1), curva(c2)
        r1, r2 = c1.campos["m_endParams"], c2.campos["m_endParams"]

        def regrada(u, v):
            p1 = f1(r1[0] + u * (r1[1] - r1[0]))
            p2 = f2(r2[0] + u * (r2[1] - r2[0]))
            return _soma(_esc(p1, 1 - v), _esc(p2, v))
        return regrada
    if ob.classe == "ConeSurf":  # vértice no centro; u = ângulo, v = distância ao vértice pela geratriz
        ce, x, y, z = tuple(c["m_center"]), tuple(c["m_xVec"]), tuple(c["m_yVec"]), tuple(c["m_zVec"])
        sa, ca = math.sin(c["m_halfAngle"]), math.cos(c["m_halfAngle"])

        def cone(u, v):
            r = v * sa
            return _soma(ce, _esc(x, r * math.cos(u)), _esc(y, r * math.sin(u)), _esc(z, v * ca))
        return cone
    raise ErroBrep(f"superfície {ob.classe} não suportada")


# --- leitura do canal 103 -----------------------------------------------------------------------------------

def _pontos_aresta(e, lado):
    pts = [e.campos["m_firstAndLastEdgePnts"][0]["uv"][lado]]
    pts += [p["uv"][lado] for p in e.campos["m_interiorEdgePnts"]]
    pts.append(e.campos["m_firstAndLastEdgePnts"][1]["uv"][lado])
    return [tuple(p) for p in pts]


def conferir_arestas(gr):
    """Para cada aresta com dois lados: maior distância (pés) entre os pontos avaliados em cada lado.

    Devolve [(classe do lado 0, classe do lado 1, distância)] e a lista de erros de avaliação."""
    por_token = {o.token: o for o in gr.objetos}
    saida, erros, cache = [], [], {}
    for e in gr.objetos:
        if e.classe != "Edge":
            continue
        faces = [por_token.get(p["ponteiro"]) if p["ponteiro"] else None for p in e.campos["m_pFace"]]
        if any(f is None or f.classe != "Face" for f in faces):
            continue
        sups = [gr.alvo(f.campos["m_pSurf"]) for f in faces]
        try:
            fs = []
            for s in sups:
                if id(s) not in cache:
                    cache[id(s)] = superficie(s, gr)
                fs.append(cache[id(s)])
            pts = [[fs[k](*uv) for uv in _pontos_aresta(e, k)] for k in (0, 1)]
        except (ErroBrep, ErroGrafo, KeyError, TypeError, ZeroDivisionError, IndexError) as exc:
            erros.append(f"{sups[0].classe}/{sups[1].classe}: {exc}")
            continue
        saida.append((sups[0].classe, sups[1].classe, max(math.dist(a, b) for a, b in zip(*pts))))
    return saida, erros


def grafos_103(grupos, objetos_de, esquema, ids):
    """Grafo do GElement (canal 103, sem chave de conteúdo) de cada id pedido."""
    out = {}
    for g in grupos:
        if g.canal != 103 or g.chave_conteudo is not None:
            continue
        for o in objetos_de(g.dados):
            if o.id in ids and esquema.classe(o.etiqueta).nome == "GElement":
                out[o.id] = decodificar(o.corpo, esquema)
    return out


# --- malha --------------------------------------------------------------------------------------------------

FLECHA = 0.5 / 304.8          # afastamento máximo entre a corda e a superfície (pés)
SOLDA = 1e-6                  # pontas de aresta mais perto que isso são o mesmo vértice (pés)
TOL_UV = 1e-3                 # pontas de aresta tão perto em UV numa face são a mesma ponta
MAX_TRIANGULOS_FACE = 8_000
FLECHA_RELATIVA = 1e-3      # peça grande: a flecha cresce com a diagonal da caixa (1/1000)
MAX_DIVISOES = 10             # uma aresta interna se divide no máximo 2^10 vezes
ANGULO_LISO = 12              # graus: entre faces mais alinhadas que isso a aresta não é desenhada (Revit)


class Malha:
    """Vértices (pés) e triângulos de uma Geometry; `faces_ruins` diz o que não virou malha e por quê."""

    def __init__(self):
        self.vertices, self.triangulos, self.faces, self.faces_ruins = [], [], 0, []
        self.arestas = []  # polilinhas (índices de vértice) das arestas que o Revit desenha
        self._solda = {}

    def vertice(self, p, soldar=False):
        if soldar:
            chave = tuple(round(c / SOLDA) for c in p)
            if chave in self._solda:
                return self._solda[chave]
        self.vertices.append(p)
        if soldar:
            self._solda[chave] = len(self.vertices) - 1
        return len(self.vertices) - 1

    def volume(self):
        v = self.vertices
        return sum(_det(v[a], v[b], v[c]) for a, b, c in self.triangulos) / 6


def _det(a, b, c):
    return (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0]))


def _projetar_plano(sup, p):
    c = sup.campos
    o, x, y = c["m_origin"], c["m_xVec"], c["m_yVec"]
    d = [p[k] - o[k] for k in range(3)]
    xx, xy, yy = (sum(a * b for a, b in zip(u, w)) for u, w in ((x, x), (x, y), (y, y)))
    dx, dy = sum(a * b for a, b in zip(d, x)), sum(a * b for a, b in zip(d, y))
    det = xx * yy - xy * xy
    return ((dx * yy - dy * xy) / det, (dy * xx - dx * xy) / det)


class _Contexto:
    def __init__(self, gr, malha, flecha=FLECHA):
        self.gr, self.malha, self.flecha = gr, malha, flecha
        self.por_token = {o.token: o for o in gr.objetos}
        self._sup, self._arestas, self._objetos = {}, {}, {}

    def alvo(self, ponteiro):
        return self.por_token.get(ponteiro["ponteiro"]) if ponteiro["ponteiro"] else None

    def sup(self, face):
        s = self.gr.alvo(face.campos["m_pSurf"])
        if id(s) not in self._sup:
            self._sup[id(s)] = (s, superficie(s, self.gr))
        return self._sup[id(s)]

    def aresta(self, e):
        """Polilinha 3D da aresta, comum às duas faces: [(vértice, uv do lado 0, uv do lado 1)]."""
        if id(e) in self._arestas:
            return self._arestas[id(e)]
        faces = [self.alvo(p) for p in e.campos["m_pFace"]]
        faces = [f if f is not None and f.classe == "Face" else None for f in faces]
        sups = [self.sup(f) if f is not None else None for f in faces]
        lados = [k for k in (0, 1) if sups[k] is not None]
        if not lados:
            raise ErroBrep("aresta sem face")
        ref = next((k for k in lados if sups[k][0].classe != "Plane"), lados[0])
        outro = 1 - ref
        f_ref = sups[ref][1]
        uvs = [_pontos_aresta(e, k) for k in (0, 1)]
        amostras = [((uvs[0][i], uvs[1][i]), f_ref(*uvs[ref][i])) for i in range(len(uvs[0]))]

        def uv_outro(uv_par, p):
            if sups[outro] is not None and sups[outro][0].classe == "Plane":
                return _projetar_plano(sups[outro][0], p)
            return uv_par[outro]

        def meio(a, b):
            par = tuple(tuple((x + y) / 2 for x, y in zip(a[0][k], b[0][k])) for k in (0, 1))
            p = f_ref(*par[ref])
            par = list(par)
            par[outro] = uv_outro(par, p)
            return (tuple(par), p)

        def densa(a, b, prof=0):
            m = meio(a, b)
            corda = tuple((x + y) / 2 for x, y in zip(a[1], b[1]))
            if prof < 10 and math.dist(m[1], corda) > self.flecha:
                return densa(a, m, prof + 1) + [m] + densa(m, b, prof + 1)
            return []

        pontos = [amostras[0]]
        for a, b in zip(amostras, amostras[1:]):
            pontos += densa(a, b) + [b]
        ultimo = len(pontos) - 1
        saida = [(self.malha.vertice(p, soldar=i in (0, ultimo)), uv[0], uv[1]) for i, (uv, p) in enumerate(pontos)]
        self._arestas[id(e)] = saida
        self._objetos[id(e)] = (faces, sups)
        return saida

    def vivas(self):
        """Polilinhas das arestas que dobram (as que o Revit desenha): fora a costura de uma superfície
        periódica (a mesma face dos dois lados) e a junção de faces tangentes (normais a menos de ANGULO_LISO)."""
        saida = []
        for chave, pontos in self._arestas.items():
            faces, sups = self._objetos[chave]
            if faces[0] is not None and faces[0] is faces[1]:
                continue
            if None not in sups:
                meio = pontos[len(pontos) // 2]
                n0, n1 = (_normal(sups[k][1], meio[1 + k]) for k in (0, 1))
                if n0 and n1 and abs(sum(a * c for a, c in zip(n0, n1))) > math.cos(math.radians(ANGULO_LISO)):
                    continue
            saida.append([v for v, *_ in pontos])
        return saida


def _cruz3(u, w):
    return (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])


def _normal(avaliar, uv, h=1e-5):
    """Normal unitária da superfície em uv (diferenças finitas; None num polo)."""
    u, v = uv
    p = avaliar(u, v)
    du = [a - c for a, c in zip(avaliar(u + h, v), p)]
    dv = [a - c for a, c in zip(avaliar(u, v + h), p)]
    n = _cruz3(du, dv)
    m = math.sqrt(sum(c * c for c in n))
    return tuple(c / m for c in n) if m > 1e-14 else None


def _laco(ctx, face, laco):
    """Vértices do laço em ordem, com o UV desta face: [(vértice, uv)]."""
    pedacos, anterior = [], laco.token
    e = ctx.alvo(laco.campos["m_next"])
    vistos = set()
    while e is not None and e is not laco:
        if e.classe != "Edge" or id(e) in vistos:
            raise ErroBrep("laço quebrado")
        vistos.add(id(e))
        lados = [k for k in (0, 1) if e.campos["m_pFace"][k]["ponteiro"] == face.token]
        if len(lados) == 2:  # costura: a face dos dois lados; vale o lado que veio da aresta anterior
            lados = [k for k in lados if e.campos["m_prev"][k]["ponteiro"] == anterior] or lados[:1]
        if not lados:
            raise ErroBrep("aresta do laço não é da face")
        lado = lados[0]
        pedacos.append([(v, uv[lado]) for v, *uv in ctx.aresta(e)])
        anterior = e.token
        e = ctx.alvo(e.campos["m_next"][lado])
    if len(pedacos) < 1:
        raise ErroBrep("laço vazio")

    def folga(a, b):  # 0 se é o mesmo vértice soldado; senão a distância em UV desta face
        return 0.0 if a[0] == b[0] else math.dist(a[1], b[1])

    # encadear pelas pontas, cada pedaço no sentido cuja ponta está mais perto do fim do anterior; a primeira
    # aresta pode estar em qualquer dos dois sentidos (como no rvt-rs, ring_impl). Junções às vezes gravam
    # cantos com folga de centésimos de mm (u = 0,00018 pé contra 0): aceita até TOL_UV
    for primeiro in (pedacos[0], pedacos[0][::-1]):
        saida = list(primeiro)
        for p in pedacos[1:]:
            d0, d1 = folga(saida[-1], p[0]), folga(saida[-1], p[-1])
            if min(d0, d1) > TOL_UV:
                break
            saida += p[1:] if d0 <= d1 else p[-2::-1]
        else:
            if len(saida) > 2 and folga(saida[0], saida[-1]) <= TOL_UV:
                return saida[:-1]
    raise ErroBrep("laço não fecha nas pontas")


def _metrica(avaliar, uvs):
    """Quanto mede, em 3D, um passo de u e um de v (média em 5 pontos do retângulo UV da face; os pontos de
    polo, onde a derivada some, ficam de fora)."""
    us, vs = [uv[0] for uv in uvs], [uv[1] for uv in uvs]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    du, dv = (u1 - u0) * 1e-4 or 1e-6, (v1 - v0) * 1e-4 or 1e-6
    su, sv = [], []
    for fu, fv in ((0.5, 0.5), (0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):
        u, v = u0 + fu * (u1 - u0), v0 + fv * (v1 - v0)
        p = avaliar(u, v)
        su.append(math.dist(avaliar(u + du, v), p) / du)
        sv.append(math.dist(avaliar(u, v + dv), p) / dv)
    su, sv = [x for x in su if x > 0], [x for x in sv if x > 0]
    return (sum(su) / len(su) if su else 1.0), (sum(sv) / len(sv) if sv else 1.0)


def _refinar(tris, uvs, verts, borda, avaliar, malha, flecha=FLECHA):
    """Divide arestas internas até a corda ficar a menos de `flecha` da superfície (sem tocar a borda).

    A corda é medida entre os pontos da própria face nas pontas (e não entre os vértices da borda, que
    vêm da aresta compartilhada e podem diferir um pouco desta superfície). Perto de um polo da revolução
    (ou de uma costura periódica) a corda pode não encolher: cada ponto novo herda a profundidade das pontas
    e nenhuma aresta se divide mais de MAX_DIVISOES vezes, nem depois de ficar mais curta que a flecha.
    O giro (Lawson) vem antes, sobre o recorte de orelhas, para não refinar leques de triângulos finos. Ele é
    feito no UV escalado pela métrica da superfície (um plano, onde Lawson sempre termina): em 3D a borda reta
    no UV (o pé de uma faixa de cilindro) impede desfazer o leque, e o refino dividia tudo (28 mil triângulos
    em 5 faces de revolução de uma cuba, contra ~1 mil necessários)."""
    proprio = [avaliar(*uv) for uv in uvs]
    prof = [0] * len(uvs)
    su, sv = _metrica(avaliar, uvs)
    tris = _girar(tris, uvs, [(u * su, v * sv, 0.0) for u, v in uvs], borda)
    boas = set()  # arestas já medidas dentro da flecha: não se avaliam de novo
    pendentes = True
    while pendentes and len(tris) < MAX_TRIANGULOS_FACE:
        pendentes = False
        usadas = {}
        for t, tri in enumerate(tris):
            for k in range(3):
                a, b = tri[k], tri[(k + 1) % 3]
                usadas.setdefault((min(a, b), max(a, b)), []).append(t)
        divisoes = {}
        for (a, b), ts in usadas.items():
            if (a, b) in borda or (a, b) in boas or len(ts) != 2 or max(prof[a], prof[b]) >= MAX_DIVISOES:
                continue
            if math.dist(proprio[a], proprio[b]) < flecha:
                continue
            uv = tuple((x + y) / 2 for x, y in zip(uvs[a], uvs[b]))
            p = avaliar(*uv)
            corda = tuple((x + y) / 2 for x, y in zip(proprio[a], proprio[b]))
            if math.dist(p, corda) > flecha:
                uvs.append(uv)
                proprio.append(p)
                prof.append(max(prof[a], prof[b]) + 1)
                verts.append(malha.vertice(p))
                divisoes[(a, b)] = len(uvs) - 1
            else:
                boas.add((a, b))
        if not divisoes:
            break
        pendentes = True
        novos = []
        for tri in tris:
            pedacos = [tri]
            for k in range(3):
                a, b = tri[k], tri[(k + 1) % 3]
                m = divisoes.get((min(a, b), max(a, b)))
                if m is None:
                    continue
                # divide o pedaço que ainda contém a aresta a-b
                for j, (x, y, z) in enumerate(pedacos):
                    for r in range(3):
                        p, q, s = (x, y, z)[r], (x, y, z)[(r + 1) % 3], (x, y, z)[(r + 2) % 3]
                        if (p, q) == (a, b):
                            pedacos[j:j + 1] = [(p, m, s), (m, q, s)]
                            break
                    else:
                        continue
                    break
            novos += pedacos
        tris = novos
    # sem girar de novo aqui: a flecha foi garantida nas arestas desta malha, e girar depois cria triângulos
    # cujo meio foge da superfície (até 2,3 mm contra 0,45 mm sem o giro), além de custar metade do tempo
    return tris


def _angulo(p, a, b):
    u = [a[k] - p[k] for k in range(3)]
    w = [b[k] - p[k] for k in range(3)]
    nu, nw = math.sqrt(sum(x * x for x in u)), math.sqrt(sum(x * x for x in w))
    if nu == 0 or nw == 0:
        return 0.0
    return math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(u, w)) / (nu * nw))))


def _passa_de_180(pc, pa, pb, pd):
    """Os ângulos em c (de a-b) e em d (de b-a), medidos em 3D, somam mais de 180°? Sem acos:
    α + β > π ⇔ sen(α + β) < 0, e sen(α + β) = sen α cos β + cos α sen β (contas abertas: é o laço quente)."""
    cx, cy, cz = pc
    dx, dy, dz = pd
    ax, ay, az = pa
    bx, by, bz = pb
    ux, uy, uz, wx, wy, wz = ax - cx, ay - cy, az - cz, bx - cx, by - cy, bz - cz
    sx, sy, sz, tx, ty, tz = bx - dx, by - dy, bz - dz, ax - dx, ay - dy, az - dz
    n1 = (ux * ux + uy * uy + uz * uz) * (wx * wx + wy * wy + wz * wz)
    n2 = (sx * sx + sy * sy + sz * sz) * (tx * tx + ty * ty + tz * tz)
    if n1 == 0 or n2 == 0:
        return False
    sen1 = math.sqrt((uy * wz - uz * wy) ** 2 + (uz * wx - ux * wz) ** 2 + (ux * wy - uy * wx) ** 2)
    sen2 = math.sqrt((sy * tz - sz * ty) ** 2 + (sz * tx - sx * tz) ** 2 + (sx * ty - sy * tx) ** 2)
    cos1, cos2 = ux * wx + uy * wy + uz * wz, sx * tx + sy * ty + sz * tz
    return sen1 * cos2 + cos1 * sen2 < -1e-9 * math.sqrt(n1 * n2)


def _girar(tris, uvs, pontos, borda):
    """Troca diagonais internas (Lawson) quando os ângulos opostos, medidos em 3D, somam mais de 180°:
    o recorte de orelhas faz leques de triângulos finos; girando, a malha fica perto de Delaunay.
    Fila de arestas: depois de cada giro só se reexaminam as 4 arestas do quadrilátero. Na superfície curva
    as duas diagonais podem pedir giro: só gira se a nova não pedir também (senão ficaria indo e voltando)."""
    from .triangular import _cruz
    tris = [list(t) for t in tris]
    lado = {}  # aresta orientada -> (triângulo, vértice oposto)
    for i, (x, y, z) in enumerate(tris):
        lado[(x, y)], lado[(y, z)], lado[(z, x)] = (i, z), (i, x), (i, y)
    fila = [(a, b) for (a, b) in lado if a < b and (b, a) in lado and (a, b) not in borda]
    limite = 30 * len(tris) + len(tris) ** 2 // 4  # teto de exames, só para não girar sem fim
    while fila and limite:
        limite -= 1
        a, b = fila.pop()
        ic, jd = lado.get((a, b)), lado.get((b, a))
        if ic is None or jd is None or (min(a, b), max(a, b)) in borda:
            continue
        (i, c), (j, d) = ic, jd
        pa, pb, pc, pd = pontos[a], pontos[b], pontos[c], pontos[d]
        if c == d or not _passa_de_180(pc, pa, pb, pd) or _passa_de_180(pa, pd, pc, pb):
            continue
        if _cruz(uvs[a], uvs[d], uvs[c]) <= 0 or _cruz(uvs[d], uvs[b], uvs[c]) <= 0:
            continue  # quadrilátero côncavo em UV: girar inverteria um triângulo
        for x, y in ((a, b), (b, c), (c, a), (b, a), (a, d), (d, b)):
            del lado[(x, y)]
        tris[i], tris[j] = [a, d, c], [d, b, c]
        lado[(a, d)], lado[(d, c)], lado[(c, a)] = (i, c), (i, a), (i, d)
        lado[(d, b)], lado[(b, c)], lado[(c, d)] = (j, c), (j, d), (j, b)
        fila += [(a, d), (d, b), (b, c), (c, a)]
    return [tuple(t) for t in tris]


def _face(ctx, face):
    ponteiro = face.campos["m_pFirstLoop"]
    if not ponteiro["ponteiro"]:
        return 0  # superfície auxiliar, sem contorno
    sup, avaliar = ctx.sup(face)
    uvs, verts, lacos, borda = [], [], [], set()
    laco = ctx.alvo(ponteiro)
    vistos = set()
    while laco is not None:
        if id(laco) in vistos:
            raise ErroBrep("lista de laços em ciclo")
        vistos.add(id(laco))
        pontos = _laco(ctx, face, laco)
        if sup.classe != "Plane":
            pontos = _polos(pontos, avaliar)
        ini = len(uvs)
        for v, uv in pontos:
            uvs.append(tuple(uv))
            verts.append(v)
        idx = list(range(ini, len(uvs)))
        lacos.append(idx)
        for i in range(len(idx)):
            a, b = idx[i], idx[(i + 1) % len(idx)]
            borda.add((min(a, b), max(a, b)))
        laco = ctx.alvo(laco.campos["m_nextLoop"])
    tris = triangular(uvs, lacos)
    if not tris:
        raise ErroBrep("face sem triângulos")
    if sup.classe != "Plane":
        tris = _refinar(tris, uvs, verts, borda, avaliar, ctx.malha, ctx.flecha)
    bandeiras = face.campos.get("m_faceFlags_v9", face.campos.get("m_faceFlags", 0))  # m_faceFlags até 2013
    direto = bool(sup.campos["m_orientFlag"]) != bool(bandeiras & 2)
    tris = [t for t in tris if len({verts[i] for i in t}) == 3]  # os do lado do polo têm área zero em 3D
    for a, b, c in tris:
        ctx.malha.triangulos.append((verts[a], verts[b], verts[c]) if direto else (verts[a], verts[c], verts[b]))
    return len(tris)


def _polos(pontos, avaliar):
    """Num polo (perfil da revolução tocando o eixo, ponta do cone) todos os u são o mesmo ponto 3D. O laço
    salvo passa por ele uma vez só e segue em diagonal pelo UV, cortando o retângulo da face (e deixando de
    fora o furo do ladrão de uma cuba). Repete o polo no u de cada vizinho: o lado do polo volta ao laço."""
    n = len(pontos)
    if n < 3:
        return pontos
    saida = []
    for k, (v, uv) in enumerate(pontos):
        u0, w0 = uv
        p = avaliar(u0, w0)
        polo = all(math.dist(avaliar(u0 + du, w0), p) < 1e-9 for du in (0.5, 1.5))
        ua, ub = pontos[k - 1][1][0], pontos[(k + 1) % n][1][0]
        if polo and abs(ua - u0) > TOL_UV:
            saida.append((v, (ua, w0)))
        saida.append((v, uv))
        if polo and abs(ub - u0) > TOL_UV:
            saida.append((v, (ub, w0)))
    return saida


def malha_geometria(gr, geometria, malha=None):
    """Triângulos de todas as faces de uma Geometry (acrescenta em `malha`)."""
    malha = malha or Malha()
    caixa = gr.raiz.campos.get("m_bBox")
    flecha = max(FLECHA, FLECHA_RELATIVA * math.dist(*caixa)) if caixa else FLECHA
    ctx = _Contexto(gr, malha, flecha)
    for p in geometria.campos["m_pFaces"]:
        face = gr.alvo(p)
        try:
            if _face(ctx, face):
                malha.faces += 1
        except (ErroBrep, ErroGrafo, ValueError, KeyError, TypeError, ZeroDivisionError, IndexError) as exc:
            sup = gr.alvo(face.campos["m_pSurf"])
            malha.faces_ruins.append(f"{sup.classe if sup else '?'}: {exc}")
    malha.arestas += ctx.vivas()
    return malha


def geometrias(gr):
    """Os nós Geometry de um GElement."""
    return [o for o in gr.objetos if o.classe == "Geometry"]
