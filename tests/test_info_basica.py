import pathlib
import re

import pytest

from leitor_rfa.contenedor import abrir
from leitor_rfa.documento import ler
from leitor_rfa.info_basica import ler_info_basica

RVT2025 = pathlib.Path(r"C:\ProgramData\Autodesk\RVT 2025\Libraries")
AUTODESK_2025 = next(RVT2025.rglob("*.rfa"), None) if RVT2025.exists() else None


def _info(caminho):
    with abrir(caminho) as c:
        return ler_info_basica(c.ler("BasicFileInfo"))


@pytest.mark.parametrize("nome,versao", [("r2012_pa2010", 2012), ("r2012", 2012), ("r2013", 2013),
                                         ("r2014", 2014), ("r2018", 2018)])
def test_versao_do_basic_file_info(fixtura, nome, versao):
    assert _info(fixtura(nome) / "familia.rfa").versao_formato == versao


def test_produto_build_e_caminho_2012(fixtura):
    i = _info(fixtura("r2012") / "familia.rfa")
    assert i.produto == "Autodesk Revit Architecture 2012"
    assert re.fullmatch(r"\d{8}_\d{4}\(x64\)", i.build)
    assert i.caminho_salvo.lower().endswith(".rfa")
    assert i.versao_estrutura == 3


def test_bytes_truncados_nao_levantam():
    i = ler_info_basica(b"\x03\x00")
    assert i.versao_formato is None and i.build is None


def test_none_nao_levanta():
    assert ler_info_basica(None).versao_formato is None


def test_documento_traz_versao_e_build(fixtura):
    cob = ler(fixtura("r2012_pa2010") / "familia.rfa")["cobertura"]
    assert cob["versao_formato"] == 2012 and cob["build"]


@pytest.mark.skipif(AUTODESK_2025 is None, reason="biblioteca Autodesk 2025 ausente")
def test_versao_e_build_2025():
    i = _info(AUTODESK_2025)
    assert i.versao_formato == 2025
    assert re.search(r"\d{8}_\d{4}\(x64\)$", i.build)
