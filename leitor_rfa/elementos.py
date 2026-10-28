"""Elementos do arquivo: a classe de cada id e o que é do documento principal.

Junta o ElemTable (o dono de cada id) com os objetos do canal 102 (a classe de
cada id). Entram só os grupos sem chave de conteúdo e os ids do ElemTable: as
famílias carregadas vêm ou com uma Family aninhada como dona (2012–2014) ou em
documentos de conteúdo com chave, fora do ElemTable (2018+). O documento
principal é o que pertence à Family raiz pela cadeia de donos: a Family sem
dono e, havendo mais de uma, a cujo id aparece no cabeçalho do Global/Latest.
Medido contra o extrator nas 106 do gabarito (planos, cotas, formas, aninhadas).
"""
import collections

from .compressao import inflar_stream, preparar
from .elemtable import ler_elemtable
from .registros import objetos
from .segmentos import percorrer_particao

FORMAS = {"ExtrusionElem": "Extrusion", "RevolutionElem": "Revolution", "SweepElem": "Sweep",
          "BlendElem": "Blend", "SweptBlendElem": "SweptBlend"}
CABECALHO_GLOBAL = 128


class Elementos:
    def __init__(self, classe, dono, raiz, esquema, largura_id):
        self.classe, self.dono, self.raiz = classe, dono, raiz
        self.largura_id = largura_id
        self._esquema = esquema
        self._ancestrais = {}
        self._familia = {}

    def herda(self, nome, base):
        if nome not in self._ancestrais:
            nomes, etiqueta = set(), self._esquema.etiqueta(nome)
            while etiqueta and self._esquema.classe(etiqueta):
                nomes.add(self._esquema.classe(etiqueta).nome)
                etiqueta = self._esquema.classe(etiqueta).pai
            self._ancestrais[nome] = nomes
        return base in self._ancestrais[nome]

    def familia_de(self, id_):
        if id_ not in self._familia:
            vistos, x, achada = set(), self.dono.get(id_), None
            while x is not None and x not in vistos:
                vistos.add(x)
                if self.classe.get(x) == "Family":
                    achada = x
                    break
                x = self.dono.get(x)
            self._familia[id_] = achada
        return self._familia[id_]

    def documento(self):
        if self.raiz is None:
            return []
        return [i for i in self.classe if self.familia_de(i) == self.raiz]

    def por_classe(self):
        return dict(collections.Counter(self.classe[i] for i in self.documento()).most_common())

    def contagens(self):
        doc = self.documento()
        nomes = [self.classe[i] for i in doc]
        return {
            "planos": nomes.count("RefPlane"),
            "cotas": sum(1 for n in nomes if self.herda(n, "Dimension")),
            "aninhadas": nomes.count("FamilyInstance"),
            "formas": dict(collections.Counter(FORMAS[n] for n in nomes if n in FORMAS)),
        }


def _raiz(classe, dono, global_latest, largura_id):
    candidatas = [i for i, c in classe.items() if c == "Family" and dono.get(i) is None]
    if len(candidatas) == 1:
        return candidatas[0]
    cabecalho = (global_latest or b"")[:CABECALHO_GLOBAL]
    citadas = [i for i in candidatas if i.to_bytes(largura_id, "little") in cabecalho]
    return citadas[0] if len(citadas) == 1 else None


def montar_elementos(grupos, elemtable, esquema, global_latest):
    classe = {}
    for g in grupos:
        if g.canal != 102 or g.chave_conteudo is not None:
            continue
        for o in objetos(g.dados, elemtable.largura_id):
            if o.id in elemtable.donos:
                c = esquema.classe(o.etiqueta)
                classe[o.id] = c.nome if c else f"#{o.etiqueta}"
    raiz = _raiz(classe, elemtable.donos, global_latest, elemtable.largura_id)
    return Elementos(classe, elemtable.donos, raiz, esquema, elemtable.largura_id)


def ler_elementos(contenedor, esquema):
    grupos = [g for n in contenedor.streams() if n.startswith("Partitions/")
              for g in percorrer_particao(preparar(n, contenedor.ler(n)), esquema).grupos]
    et = ler_elemtable(inflar_stream("Global/ElemTable", contenedor.ler("Global/ElemTable")), esquema)
    return montar_elementos(grupos, et, esquema, inflar_stream("Global/Latest", contenedor.ler("Global/Latest")))
