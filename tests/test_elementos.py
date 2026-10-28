import collections
import json
import pathlib

import pytest

from conftest import ARQUIVOS_DIR, requer_arquivo

from leitor_rfa.compressao import inflar_stream
from leitor_rfa.contenedor import abrir
from leitor_rfa.documento import ler
from leitor_rfa.elementos import ler_elementos
from leitor_rfa.esquema import ler_esquema

COM_GABARITO = ("r2012_pa2010", "r2012", "r2012_sem_previa", "r2013", "r2014", "r2018")
SEM_PARTICOES = ARQUIVOS_DIR / "r2010_sem_partatom.rfa"


def _elementos(caminho):
    with abrir(caminho) as c:
        e = ler_esquema(inflar_stream("Formats/Latest", c.ler("Formats/Latest")))
        return ler_elementos(c, e)


def _gab(fixtura, nome):
    return json.loads((fixtura(nome) / "familia.json").read_text(encoding="utf-8"))


def esperado(gab):
    return {"planos": len(gab["planos_referencia"]), "cotas": len(gab["cotas"]),
            "aninhadas": sum(a["quantidade"] for a in gab["aninhadas"]),
            "formas": dict(collections.Counter(f["tipo"] for f in gab["formas"]))}


@pytest.mark.parametrize("nome", COM_GABARITO)
def test_contagens_iguais_ao_gabarito(fixtura, nome):
    assert _elementos(fixtura(nome) / "familia.rfa").contagens() == esperado(_gab(fixtura, nome))


def test_raiz_e_documento(fixtura):
    el = _elementos(fixtura("r2012") / "familia.rfa")
    assert el.classe[el.raiz] == "Family" and el.dono[el.raiz] is None
    doc = el.documento()
    assert doc and all(el.familia_de(i) == el.raiz for i in doc)


def test_herda_pelo_esquema(fixtura):
    el = _elementos(fixtura("r2012") / "familia.rfa")
    assert el.herda("LinearDimString", "Dimension") and el.herda("Alignment", "Dimension")
    assert not el.herda("RefPlane", "Dimension")


def test_documento_traz_elementos_na_cobertura(fixtura):
    cob = ler(fixtura("r2018") / "familia.rfa")["cobertura"]
    assert cob["secoes"]["elementos"]["estado"] == "decifrado"
    el = cob["elementos"]
    assert el["largura_id"] == 4 and el["documento"] > 0 and el["raiz"] is not None
    assert el["contagens"] == esperado(_gab(fixtura, "r2018"))
    assert el["por_classe"]["RefPlane"] == el["contagens"]["planos"]


@requer_arquivo("r2010_sem_partatom.rfa")
def test_sem_particoes_legiveis_fica_nao_decifrado():
    s = ler(SEM_PARTICOES)["cobertura"]["secoes"]["elementos"]
    assert s["estado"] == "nao_decifrado" and "partições" in s["nota"]
