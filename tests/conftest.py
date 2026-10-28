import os
import pathlib

import pytest

# Os .rfa reais (de fabricantes e da Autodesk) e o gabarito extraído pelo Revit não vão para o repositório
# aberto. Ficam numa pasta com fixtures/<nome>/familia.{rfa,json} e arquivos/*.rfa, apontada por
# LEITOR_RFA_FIXTURES (sem ela, vale tests/ mesmo). Faltando, os testes que dependem deles são pulados.
RAIZ = pathlib.Path(os.environ["LEITOR_RFA_FIXTURES"]) if os.environ.get("LEITOR_RFA_FIXTURES") else pathlib.Path(__file__).parent
FIXTURES_DIR = RAIZ / "fixtures"
ARQUIVOS_DIR = RAIZ / "arquivos"
FIXTURES = {p.name: p for p in sorted(FIXTURES_DIR.iterdir()) if p.is_dir()} if FIXTURES_DIR.is_dir() else {}
SEM_ARQUIVOS = "arquivos reais ausentes (defina LEITOR_RFA_FIXTURES)"
requer_fixtures = pytest.mark.skipif(not FIXTURES, reason=SEM_ARQUIVOS)


def requer_arquivo(nome):
    return pytest.mark.skipif(not (ARQUIVOS_DIR / nome).is_file(), reason=SEM_ARQUIVOS)


@pytest.fixture
def fixtura():
    def _pasta(nome):
        if nome not in FIXTURES:
            pytest.skip(SEM_ARQUIVOS)
        return FIXTURES[nome]
    return _pasta
