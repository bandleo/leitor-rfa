"""Contêiner OLE/CFB do .rfa: lista e lê os streams."""
import pathlib

import olefile


class ErroArquivo(Exception):
    """O arquivo não existe ou não é um contêiner OLE legível."""


class Contenedor:
    def __init__(self, ole):
        self._ole = ole

    def streams(self):
        return ["/".join(partes) for partes in self._ole.listdir()]

    def ler(self, nome):
        if not self._ole.exists(nome):
            return None
        return self._ole.openstream(nome).read()

    def fechar(self):
        self._ole.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fechar()


def abrir(caminho):
    caminho = pathlib.Path(caminho)
    try:
        if not olefile.isOleFile(str(caminho)):
            raise ErroArquivo(f"não é um contêiner OLE: {caminho}")
        return Contenedor(olefile.OleFileIO(str(caminho)))
    except ErroArquivo:
        raise
    except Exception as exc:  # olefile levanta vários tipos para arquivo ruim
        raise ErroArquivo(f"{type(exc).__name__}: {exc}") from exc
