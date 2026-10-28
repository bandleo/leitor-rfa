"""Planos de referência e aninhadas do documento principal.

RefPlane: m_text = nome; m_refName = código da referência, traduzido pela tabela
'referencia_plano' (aprendida do gabarito). Os extremos (m_bubbleEnd/m_freeEnd)
estão em outro referencial que o do extrator e saem vazios até serem decifrados.

Cotas (classes que herdam Dimension): rótulo = m_ArrSegInfo[0].m_paramId → nome do parâmetro;
referências = nº de m_witnessRefs; valor_mm = m_lockedValue (pés) só na cota linear de um segmento,
como o Dimension.Value do extrator (nulo nas de vários segmentos, alinhamento, raio, ângulo).

Aninhadas: FamilyInstance.m_masterSymbolId -> FamilySymbol (tipo = SymbolInfo.m_name) -> m_familyId -> Family
(m_name, m_bShared, m_categoryId -> nome pela tabela 'categoria'), agrupadas como no extrator.
"""
from .grafo import ErroGrafo, decodificar, id_elemento
from .parametros import PES_PARA_MM, TABELAS

LINEARES = ("LinearDimString",)  # DimensionShape.Linear no extrator


def ler_planos(el, corpos, esquema, tabelas=TABELAS):
    planos = []
    for i in el.documento():
        if el.classe[i] != "RefPlane" or i not in corpos:
            continue
        c = decodificar(corpos[i], esquema).raiz.campos
        nome = c["m_text"] or tabelas["referencia_plano"].get("nome_vazio")
        planos.append({"nome": nome, "referencia": tabelas["referencia_plano"].get(str(c["m_refName"])),
                       "inicio_mm": None, "fim_mm": None})
    return planos


def ler_cotas(el, corpos, esquema, nomes):
    """Devolve (cotas, falhas): falhas = ids de cotas que o grafo não decodifica."""
    cotas, falhas = [], []
    for i in el.documento():
        if not el.herda(el.classe[i], "Dimension") or i not in corpos:
            continue
        try:
            c = decodificar(corpos[i], esquema).raiz.campos
        except ErroGrafo:
            falhas.append(i)
            continue
        segs = c["m_ArrSegInfo"]
        pid = id_elemento(segs[0]["m_paramId"]) if segs else -1
        valor = segs[0]["m_lockedValue"] * PES_PARA_MM if len(segs) == 1 and el.classe[i] in LINEARES else None
        cotas.append({"rotulo": nomes.get(pid), "valor_mm": valor, "referencias": len(c["m_witnessRefs"])})
    return cotas, falhas


def _id(valor):
    return id_elemento(valor)


def ler_aninhadas(el, corpos, esquema, tabelas=TABELAS):
    """Devolve (aninhadas, falhas). Agrupa por (família, tipo, categoria) na ordem do primeiro id, como o
    GroupBy do extrator; `compartilhada` vem da família do grupo."""
    grupos, falhas = {}, []
    for i in el.documento():
        if el.classe[i] != "FamilyInstance":
            continue
        try:
            fi = decodificar(corpos[i], esquema).raiz.campos
            simbolo = decodificar(corpos[_id(fi["m_masterSymbolId"])], esquema)
            tipo = simbolo.alvo(simbolo.raiz.campos["m_symbolInfo"]).campos["m_name"]
            fam = decodificar(corpos[_id(simbolo.raiz.campos["m_familyId"])], esquema).raiz.campos
        except (ErroGrafo, KeyError):
            falhas.append(i)
            continue
        categoria = tabelas["categoria"].get(str(_id(fam["m_categoryId"])))
        chave = (fam["m_name"], tipo, categoria)
        if chave not in grupos:
            grupos[chave] = {"familia": fam["m_name"], "tipo": tipo, "categoria": categoria,
                             "compartilhada": fam["m_bShared"], "quantidade": 0}
        grupos[chave]["quantidade"] += 1
    return list(grupos.values()), falhas
