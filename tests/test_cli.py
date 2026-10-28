import os
import pathlib
import subprocess
import sysconfig

from leitor_rfa.cli import main

EXE = pathlib.Path(sysconfig.get_path("scripts")) / ("ler-rfa.exe" if os.name == "nt" else "ler-rfa")


def test_exe_escreve_erro_em_utf8(tmp_path):
    r = subprocess.run([str(EXE), str(tmp_path / "não.rfa")], capture_output=True)
    assert r.returncode == 2
    assert "não encontrado".encode("utf-8") in r.stderr


def test_cli_versao(capsys):
    assert main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out


def test_cli_arquivo_inexistente(capsys, tmp_path):
    assert main([str(tmp_path / "nao-existe.rfa"), "-o", str(tmp_path / "x.json")]) == 2
    assert "não encontrado" in capsys.readouterr().err
