"""Formas (GenericForm) do documento principal, no formato do extrator.

Classe -> tipo: ExtrusionElem, RevolutionElem, SweepElem, BlendElem, SweptBlendElem. Sólido = não m_cutting.
Parâmetro associado: {m_famParamId, m_elemPropId} em m_famParamDrivenData (até 2013) ou na célula
FamilyParametrizedElemParamsCell.m_paramDrivenData (2014+); a propriedade (m_elemPropId) vira o campo pela tabela
'vinculo_forma' (aprendida do gabarito). Início/fim (só Extrusion): ParamValueSetDouble com
EXTRUSION_START_PARAM/EXTRUSION_END_PARAM, em pés.

Esboço (só Extrusion e Revolution, como no extrator): CurveElem filhos do VarSketch filho da forma, sem o eixo da
revolução (RevolutionCurveData.m_axis). As curvas estão em coordenadas do modelo, em pés: GLine (origem + direção·t),
GArc (centro + raio·(cos t·x + sen t·y); parâmetros iguais = círculo, que o Revit divide em duas metades) e GEllipse.
Laços: curvas encadeadas pelas pontas. Tesselação como a do Revit (Curve.Tessellate): flecha de no máximo 1/16" por
segmento e pelo menos 2 segmentos por arco — confere com 859 dos 882 arcos do gabarito.

Além do esquema v1 (para quem reconstrói a forma em outro modelador): `plano` (origem, eixos e normal do plano do esboço), e na revolução
`eixo_mm` (as pontas do eixo) e `angulo_inicio`/`angulo_fim` em graus.
"""
import collections
import math

from .grafo import ErroGrafo, decodificar, id_elemento
from .parametros import PES_PARA_MM, TABELAS

TIPOS = {"ExtrusionElem": "Extrusion", "RevolutionElem": "Revolution", "SweepElem": "Sweep", "BlendElem": "Blend",
         "SweptBlendElem": "SweptBlend"}
COM_ESBOCO = ("Extrusion", "Revolution")
INICIO, FIM = -1001800, -1001801  # EXTRUSION_START_PARAM, EXTRUSION_END_PARAM
ANGULO_INICIO, ANGULO_FIM = -1001802, -1001803  # REVOLUTION_START_ANGLE, REVOLUTION_END_ANGLE (radianos)
FLECHA = 1 / 16 / 12  # 1/16" em pés
JUNTA = 0.0005233  # pés: tolerância de vértice do Revit (Application.VertexTolerance)


class ErroForma(Exception):
    """Curva do esboço de uma classe sem tradução."""


def _id(valor):
    return id_elemento(valor)


def _soma(*termos):
    return tuple(sum(c * v[k] for c, v in termos) for k in range(3))


def segmentos_arco(raio, angulo):
    passo = 2 * math.acos(1 - FLECHA / raio) if FLECHA < 2 * raio else 2 * math.pi
    return max(2, math.ceil(angulo / passo - 1e-9))


def _ponto(c, t):
    if c["tipo"] == "arco":
        return _soma((1, c["centro"]), (c["raio"] * math.cos(t), c["x"]), (c["raio"] * math.sin(t), c["y"]))
    return _soma((1, c["centro"]), (c["rx"] * math.cos(t), c["x"]), (c["ry"] * math.sin(t), c["y"]))


def _pontas(c):
    if c["tipo"] == "linha":
        return c["p0"], c["p1"]
    return _ponto(c, c["t"][0]), _ponto(c, c["t"][1])


def tesselar(c):
    """Pontos da curva no sentido dela, em pés."""
    if c["tipo"] == "linha":
        return [c["p0"], c["p1"]]
    t0, t1 = c["t"]
    if t1 <= t0:
        t1 += 2 * math.pi  # parâmetros iguais: círculo inteiro
    raio = c["raio"] if c["tipo"] == "arco" else max(c["rx"], c["ry"])
    if math.isclose(t1 - t0, 2 * math.pi):
        n = 2 * segmentos_arco(raio, math.pi)
    else:
        n = segmentos_arco(raio, t1 - t0)
    return [_ponto(c, t0 + (t1 - t0) * k / n) for k in range(n + 1)]


def _metades(c):
    """O Revit guarda o círculo como uma curva só, mas o perfil do esboço tem duas metades."""
    if c["tipo"] == "linha" or not math.isclose(*c["t"]):
        return [c]
    t0 = c["t"][0]
    return [dict(c, t=(t0, t0 + math.pi)), dict(c, t=(t0 + math.pi, t0 + 2 * math.pi))]


def _perto(a, b):
    return math.dist(a, b) <= JUNTA


def encadear(curvas):
    """Agrupa as curvas em laços pelas pontas; devolve [[(curva, invertida), ...], ...]."""
    livres, lacos = list(curvas), []
    while livres:
        c = livres.pop(0)
        laco = [(c, False)]
        inicio, fim = _pontas(c)
        while not _perto(fim, inicio):
            for k, d in enumerate(livres):
                a, b = _pontas(d)
                if _perto(a, fim) or _perto(b, fim):
                    invertida = not _perto(a, fim)
                    laco.append((d, invertida))
                    fim = a if invertida else b
                    del livres[k]
                    break
            else:
                break  # laço aberto: fica como está
        lacos.append(laco)
    return lacos


def _curva(gc):
    crv = gc.alvo(gc.alvo(gc.raiz.campos["m_pCurveDriver"]).campos["m_pCrv"])
    c = crv.campos
    if crv.classe == "GLine":
        t0, t1 = c["m_endParams"]
        return {"tipo": "linha", "p0": _soma((1, c["m_origin"]), (t0, c["m_dirVec"])),
                "p1": _soma((1, c["m_origin"]), (t1, c["m_dirVec"]))}
    if crv.classe == "GArc":
        return {"tipo": "arco", "centro": tuple(c["m_center"]), "raio": c["m_radius"], "x": tuple(c["m_xVec"]),
                "y": tuple(c["m_yVec"]), "t": tuple(c["m_endParams"])}
    if crv.classe == "GEllipse":
        return {"tipo": "elipse", "centro": tuple(c["m_center"]), "rx": c["m_xLen"], "ry": c["m_yLen"],
                "x": tuple(c["m_xVec"]), "y": tuple(c["m_yVec"]), "t": tuple(c["m_endParams"])}
    raise ErroForma(f"curva {crv.classe} sem tradução")


def _eixo(gc):
    dados = gc.alvo(gc.raiz.campos["m_data"]["m_oUserData"])
    return dados is not None and dados.campos.get("m_axis") is True


def _mm(p):
    return [x * PES_PARA_MM for x in p]


def _plano(gc, corpos, esquema):
    """Plano do esboço pela matriz do SketchPlane (m_oTrf): colunas = eixos x, y e z, m_or = origem (pés).
    Confere com o Plane (m_xVec, m_yVec, m_origin) onde ele existe; no 2014 o SketchPlane aponta o plano
    por outra referência, mas a matriz está sempre lá. normal = x × y."""
    sp = decodificar(corpos[_id(gc.raiz.campos["m_sketchPlaneId"])], esquema)
    trf = sp.alvo(sp.raiz.campos["m_oTrf"]).campos
    m = trf["m_3x3"]
    x, y = [m[0][0], m[1][0], m[2][0]], [m[0][1], m[1][1], m[2][1]]
    normal = [x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]]
    return {"origem_mm": _mm(trf["m_or"]), "x": x, "y": y, "normal": normal}


def _esboco(i, el, corpos, esquema, filhos):
    """(laços em mm, eixo da revolução em mm ou None, CurveElem decodificada de referência)."""
    curvas, eixo, ref = [], None, None
    for sk in filhos[i]:
        if el.classe[sk] != "VarSketch":
            continue
        for cid in sorted(filhos[sk]):
            if el.classe[cid] != "CurveElem":
                continue
            gc = decodificar(corpos[cid], esquema)
            ref = ref or gc
            if _eixo(gc):
                c = _curva(gc)
                eixo = [_mm(c["p0"]), _mm(c["p1"])] if c["tipo"] == "linha" else None
            else:
                curvas.extend(_metades(_curva(gc)))
    lacos = [[tuple(x * PES_PARA_MM for x in p) for c, invertida in laco
              for p in (tesselar(c)[::-1] if invertida else tesselar(c))] for laco in encadear(curvas)]
    return lacos, eixo, ref


def vinculos(g):
    """[(id do parâmetro da família, id da propriedade do elemento)] de um elemento decodificado."""
    itens = list(g.raiz.campos.get("m_famParamDrivenData") or [])
    for o in g.objetos:
        if o.classe == "FamilyParametrizedElemParamsCell":
            itens += o.campos["m_paramDrivenData"]
    return [(_id(v["m_famParamId"]), _id(v["m_elemPropId"])) for v in itens]


# passo de geometria da laje/parede de referência dos gabaritos "baseado em piso/parede/teto": o Revit
# a desenha no editor da família, mas ela é o hospedeiro simulado e não faz parte da família no projeto
HOSPEDEIRO = "AddGeomToHostInFamEnvGStep"


def hospedeiro_simulado(gr):
    """Forma do ambiente do hospedeiro (laje/parede de referência do gabarito), não da família.

    2018+: o passo AddGeomToHostInFamEnvGStep. Em todas as versões (2012–2018): o primeiro passo de geometria
    da forma (ExtrusionGStep…) tem m_flags sem o bit 0x80000 — 0x19F3D/0x39F3D nas lajes e paredes de
    referência (93 nas 106 do gabarito, quase todas a extrusão 1537 que o próprio gabarito cria), contra
    0xB9F7D/0xBDF7D em todas as 672 formas da família."""
    if any(o.classe == HOSPEDEIRO for o in gr.objetos):
        return True
    passo = next((o for o in gr.objetos if o.classe.endswith("GStep")), None)
    return passo is not None and passo.campos.get("m_flags") is not None and not passo.campos["m_flags"] & 0x80000


def ler_formas(el, corpos, esquema, nomes, tabelas=TABELAS):
    """Devolve (formas, falhas). Forma que não decodifica entra só com o tipo, para não desalinhar a lista."""
    filhos = collections.defaultdict(list)
    for i, dono in el.dono.items():
        filhos[dono].append(i)
    formas, falhas = [], []
    for i in el.documento():
        tipo = TIPOS.get(el.classe[i])
        if tipo is None:
            continue
        forma = {"tipo": tipo, "solido": None, "parametro_visivel": None, "parametro_material": None,
                 "esboco_mm": [], "inicio_mm": None, "fim_mm": None}
        formas.append(forma)
        try:
            g = decodificar(corpos[i], esquema)
            c = g.raiz.campos
            forma["solido"] = not c["m_cutting"]
            if hospedeiro_simulado(g):
                forma["hospedeiro_simulado"] = True  # além do v1: o Revit não a mostra no projeto
            for parametro, propriedade in vinculos(g):
                campo = tabelas["vinculo_forma"].get(str(propriedade))
                if campo:
                    forma[campo] = nomes.get(parametro)
            if tipo == "Extrusion":
                valores = {_id(p["m_paramId"]): p["m_value"]
                           for p in g.alvo(c["m_pParamValueSetDouble"]).campos["m_paramSet"]}
                forma["inicio_mm"] = valores[INICIO] * PES_PARA_MM
                forma["fim_mm"] = valores[FIM] * PES_PARA_MM
            if tipo in COM_ESBOCO:
                forma["esboco_mm"], eixo, ref = _esboco(i, el, corpos, esquema, filhos)
                _extras(forma, g, eixo, ref, corpos, esquema)
        except (ErroGrafo, ErroForma, KeyError, AttributeError):
            falhas.append(i)
    return formas, falhas


def _extras(forma, g, eixo, ref, corpos, esquema):
    """Além do esquema v1 (para reconstruir a forma): plano do esboço; eixo e ângulos da revolução.
    Opcionais: se não decodificam, a forma fica sem eles."""
    try:
        if ref is not None:
            forma["plano"] = _plano(ref, corpos, esquema)
        if forma["tipo"] == "Revolution":
            valores = {_id(p["m_paramId"]): p["m_value"]
                       for p in g.alvo(g.raiz.campos["m_pParamValueSetDouble"]).campos["m_paramSet"]}
            forma["eixo_mm"] = eixo
            forma["angulo_inicio"] = math.degrees(valores[ANGULO_INICIO])
            forma["angulo_fim"] = math.degrees(valores[ANGULO_FIM])
    except (ErroGrafo, KeyError, AttributeError, TypeError):
        pass
