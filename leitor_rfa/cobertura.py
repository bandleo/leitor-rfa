"""O que o leitor conseguiu decifrar, por seção."""
from . import __version__

ESTADOS = ("decifrado", "parcial", "nao_decifrado", "ausente")
SECOES = ("familia", "tipos", "parametros", "aninhadas", "planos_referencia",
          "cotas", "formas", "miniatura", "esquema", "particoes", "elementos")


class Cobertura:
    def __init__(self):
        self.versao_formato = None
        self.build = None
        self.versao_partatom = None
        self.variante_esquema = None
        self.esquema = None
        self.particoes = None
        self.elementos = None
        self.parametros_inferidos = []
        self._secoes = {s: {"estado": "nao_decifrado", "nota": None} for s in SECOES}
        self._erros = []

    def marcar(self, secao, estado, nota=None):
        if secao not in self._secoes:
            raise KeyError(f"seção desconhecida: {secao}")
        if estado not in ESTADOS:
            raise ValueError(f"estado inválido: {estado}")
        self._secoes[secao] = {"estado": estado, "nota": nota}

    def erro(self, secao, exc):
        self._erros.append({"secao": secao, "tipo": type(exc).__name__, "mensagem": str(exc)})

    def como_dict(self):
        return {
            "leitor": __version__,
            "versao_formato": self.versao_formato,
            "build": self.build,
            "versao_partatom": self.versao_partatom,
            "variante_esquema": self.variante_esquema,
            "esquema": self.esquema,
            "particoes": self.particoes,
            "elementos": self.elementos,
            "parametros_inferidos": list(self.parametros_inferidos),
            "secoes": {s: dict(v) for s, v in self._secoes.items()},
            "erros": list(self._erros),
        }
