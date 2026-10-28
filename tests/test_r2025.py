"""Revit 2024+: ElementId com 64 bits ({'m_id': {'m_id64': n}}). Sem gabarito: o PartAtom é o oráculo."""
from conftest import ARQUIVOS_DIR, requer_arquivo

from leitor_rfa.conferencia import conferir_partatom
from leitor_rfa.documento import ler
from leitor_rfa.grafo import id_elemento

R2025 = ARQUIVOS_DIR / "r2025_vazio_redondo.rfa"  # biblioteca da Autodesk, pt-BR


def test_id_elemento_aceita_32_e_64_bits():
    assert id_elemento({"m_id": {"m_id": 5}}) == 5
    assert id_elemento({"m_id": {"m_id64": -2000150}}) == -2000150


@requer_arquivo("r2025_vazio_redondo.rfa")
def test_2025_le_sem_queda_e_decifra_parametros_cotas_e_formas():
    doc = ler(R2025)
    secoes = doc["cobertura"]["secoes"]
    assert doc["cobertura"]["erros"] == []
    assert secoes["parametros"]["estado"] in ("decifrado", "parcial") and doc["parametros"]
    assert doc["familia"]["categoria_id"] is not None
    for secao in ("tipos", "cotas", "formas"):
        assert secoes[secao]["estado"] == "decifrado", secao
    assert doc["cotas"] and doc["formas"]


@requer_arquivo("r2025_vazio_redondo.rfa")
def test_2025_tipos_e_valores_batem_com_o_partatom():
    r = conferir_partatom(ler(R2025))
    assert r["tipos"].iguais == r["tipos"].total
    assert r["valores"].total > 0 and r["valores"].iguais == r["valores"].total
