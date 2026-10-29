"""Contrato `partes`: a geometria 3D da família, parte por parte, em mm com Z para cima.

`partes(caminho)` → {"partes": [...], "completude": {...}}. Cada parte vem de um elemento do documento
principal: as formas sólidas e as combinações (junções) saem do B-rep que o Revit gravou (`brep.py`). Os
vazios ficam de fora (o corte já está no B-rep do sólido) e os membros de uma combinação também (a
combinação é a geometria deles já juntada).

Parte: {id, origem: forma|combinacao, classe, fonte: brep_salvo, visivel_3d, solido, vertices [(x, y, z) mm],
triangulos [(a, b, c)], arestas [[índices]], faces, faces_nao_suportadas, caixa_revit_mm}. `arestas`: as linhas
que o Revit desenha (bordas entre faces que dobram), como polilinhas sobre os mesmos vértices. `visivel_3d` é None enquanto a
visibilidade (nível de detalhe) não for decifrada; com `incluir_ocultas=True` o que o Revit não mostra no
projeto (hospedeiro simulado) entra também, com `visivel_3d: False` e o `motivo`.

Completude: estado `completo` | `parcial` (com `faltando`, em termos do Revit) | `sem_3d`.
"""
import functools

from . import __version__
from .brep import ErroBrep, Malha, geometrias, grafos_103, malha_geometria
from .compressao import ErroCompressao, inflar_stream, preparar
from .contenedor import abrir
from .elementos import FORMAS, montar_elementos
from .elemtable import ErroElemTable, ler_elemtable
from .esquema import ErroEsquema, ler_esquema
from .formas import hospedeiro_simulado
from .glb import escrever_glb
from .grafo import ErroGrafo, decodificar, id_elemento
from .registros import ErroRegistro, objetos
from .segmentos import ErroSegmento, percorrer_particao

PES = 304.8
IMPORTACOES = ("ImportInstance", "MasterImportSymbol")
NOMES = {"Extrusion": "Extrusão", "Revolution": "Revolução", "Sweep": "Varredura", "Blend": "Mescla",
         "SweptBlend": "Mescla de varredura"}
EXTRAS = ("id", "origem", "classe", "fonte", "visivel_3d", "motivo")


def _mm(p):
    return tuple(c * PES for c in p)


def _ler(c):
    esquema = ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))
    grupos = [g for n in c.streams() if n.startswith("Partitions/")
              for g in percorrer_particao(preparar(n, c.ler(n)), esquema).grupos]
    et = ler_elemtable(inflar_stream("Global/ElemTable", c.ler("Global/ElemTable")), esquema)
    bruto = c.ler("Global/Latest")
    el = montar_elementos(grupos, et, esquema, inflar_stream("Global/Latest", bruto) if bruto else b"")
    return esquema, grupos, et, el


def partes(caminho, incluir_ocultas=False):
    with abrir(caminho) as c:
        try:
            esquema, grupos, et, el = _ler(c)
        except (ErroCompressao, ErroEsquema, ErroSegmento, ErroElemTable, ErroRegistro, KeyError) as exc:
            return {"partes": [], "completude": {"estado": "sem_3d", "faltando": [f"partições ilegíveis: {exc}"[:200]]}}
    doc = set(el.documento())
    if el.raiz is None or not doc:
        return {"partes": [], "completude": {"estado": "sem_3d", "faltando": ["família raiz não identificada"]}}
    objetos_de = functools.partial(objetos, largura=et.largura_id)
    corpos = {o.id: o.corpo for g in grupos if g.canal == 102 and g.chave_conteudo is None
              for o in objetos_de(g.dados) if o.id in doc}
    formas, combinacoes, membros, vazios, ocultas = [], [], set(), 0, []
    for i in sorted(doc):
        classe = el.classe.get(i)
        if classe in FORMAS:
            gr = decodificar(corpos[i], esquema)
            if gr.raiz.campos.get("m_cutting"):
                vazios += 1
            elif hospedeiro_simulado(gr):
                ocultas.append({"id": i, "classe": FORMAS[classe], "motivo": "hospedeiro simulado"})
            else:
                formas.append(i)
        elif classe == "FamilyGeomCombination":
            combinacoes.append(i)
            for par in decodificar(corpos[i], esquema).raiz.campos.get("m_svMap", []):
                membros.add(id_elemento(par["first"]))
    escolhidos = [(i, "forma", FORMAS[el.classe[i]]) for i in formas if i not in membros]
    escolhidos += [(i, "combinacao", "Combinação") for i in combinacoes]
    motivos = {o["id"]: o["motivo"] for o in ocultas} if incluir_ocultas else {}
    escolhidos += [(o["id"], "forma", o["classe"]) for o in ocultas if o["id"] in motivos]
    grafos = grafos_103(grupos, objetos_de, esquema, {i for i, *_ in escolhidos})
    saida, faltando = [], []
    for i, origem, classe in escolhidos:
        gr = grafos.get(i)
        if gr is None:
            faltando.append(f"{classe} {i}: sem geometria salva")
            continue
        malha = Malha()
        try:
            for g in geometrias(gr):
                malha_geometria(gr, g, malha)
        except (ErroBrep, ErroGrafo) as exc:
            malha.faces_ruins.append(str(exc))
        caixa = gr.raiz.campos.get("m_bBox")
        saida.append({"id": i, "origem": origem, "classe": classe, "fonte": "brep_salvo",
                      "visivel_3d": False if i in motivos else None,
                      "solido": True, "vertices": [_mm(p) for p in malha.vertices], "triangulos": malha.triangulos,
                      "arestas": malha.arestas,
                      "faces": malha.faces, "faces_nao_suportadas": malha.faces_ruins,
                      "caixa_revit_mm": [list(_mm(p)) for p in caixa] if caixa else None,
                      **({"motivo": motivos[i]} if i in motivos else {})})
        if i in motivos:
            continue
        if malha.faces_ruins:
            n = len(malha.faces_ruins)
            faltando.append(f"{NOMES.get(classe, classe)} {i}: {_contar(n, 'face', 'faces')} sem malha "
                            f"({malha.faces_ruins[0][:80]})")
    aninhadas = sum(1 for i in doc if el.classe.get(i) == "FamilyInstance")
    if aninhadas:
        faltando.append(f"{_contar(aninhadas, 'instância de família aninhada', 'instâncias de famílias aninhadas')} "
                        "ainda sem 3D")
    importacoes = sum(1 for i in doc if el.classe.get(i) in IMPORTACOES)
    if importacoes:
        faltando.append(f"{_contar(importacoes, 'elemento', 'elementos')} de CAD importado ainda sem 3D")
    visiveis = [p for p in saida if p["visivel_3d"] is not False]
    estado = "sem_3d" if not any(p["triangulos"] for p in visiveis) else ("parcial" if faltando else "completo")
    return {"partes": saida, "completude": {"estado": estado, "faltando": faltando, "vazios": vazios, "ocultas": ocultas,
                                            "triangulos": sum(len(p["triangulos"]) for p in visiveis)}}


def _contar(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def para_glb(resultado, gerador=f"leitor-rfa {__version__}"):
    """GLB do resultado de `partes`: um nó por parte ("Extrusão 1412989", com os extras do contrato) e a
    completude nos extras da cena."""
    return escrever_glb([{"nome": f"{NOMES.get(p['classe'], p['classe'])} {p['id']}", "vertices": p["vertices"],
                          "triangulos": p["triangulos"], "arestas": p.get("arestas"),
                          "extras": {k: p[k] for k in EXTRAS if k in p}}
                         for p in resultado["partes"]], gerador, extras={"completude": resultado["completude"]})
