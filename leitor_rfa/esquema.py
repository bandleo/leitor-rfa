"""Esquema Formats/Latest: as classes do formato e seus campos, na ordem em que aparecem.

Porte de rvt-rs (Apache-2.0) src/schema_registry.rs::parse. O rvt-rs só cobre
2016+; em 2012 e 2013 a definição de classe não tem o u32 final da contagem
de entradas opacas de 16 B (variante "sem_opaco"). A variante é detectada
lendo: vale a única que termina exatamente nos 8 zeros. A etiqueta de uma
classe é 12 + a ordem em que foi definida, e muda de versão para versão.
"""
import hashlib
from dataclasses import dataclass

PRIMEIRA_ETIQUETA = 12
MODIFICADORES = {0, 1, 2, 3, 4, 16, 17, 18, 19, 80, 81, 82, 83, 84, 96}


class ErroEsquema(Exception):
    """O Formats/Latest não segue nenhuma variante conhecida."""


@dataclass(frozen=True)
class Campo:
    nome: str
    descritor: int
    base: int
    modificador: int
    n_arranjo: int | None
    referencias: list
    aninhado: "Campo | None" = None  # descritor do item de um composto (base 13)


@dataclass(frozen=True)
class Classe:
    etiqueta: int
    nome: str
    pai: int
    versao: int
    campos: list


class Esquema:
    def __init__(self, classes, variante, sha256):
        self.classes, self.variante, self.sha256 = classes, variante, sha256
        self._por_nome = {}
        for c in classes:
            self._por_nome.setdefault(c.nome, c.etiqueta)

    def etiqueta(self, nome):
        return self._por_nome.get(nome)

    def classe(self, etiqueta):
        i = etiqueta - PRIMEIRA_ETIQUETA
        return self.classes[i] if 0 <= i < len(self.classes) else None


class _Leitor:
    def __init__(self, dados, opaco):
        self.b, self.p, self.opaco, self.classes, self.profundidade = dados, 0, opaco, [], 0

    def take(self, n):
        if self.p + n > len(self.b):
            raise ErroEsquema(f"esquema truncado no byte {self.p}: faltam {n} B")
        r = self.b[self.p:self.p + n]
        self.p += n
        return r

    def u16(self):
        return int.from_bytes(self.take(2), "little")

    def u32(self):
        return int.from_bytes(self.take(4), "little")

    def texto(self, n):
        if not 1 <= n <= 4096:
            raise ErroEsquema(f"tamanho de nome inválido ({n}) no byte {self.p}")
        try:
            return self.take(n).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ErroEsquema(f"nome não é texto no byte {self.p - n}") from exc

    def referencia(self):
        pos, bruto = self.p, self.u16()
        etiqueta = bruto & 0x7FFF
        proxima = PRIMEIRA_ETIQUETA + len(self.classes)
        if bruto & 0x8000:
            if etiqueta != proxima:
                raise ErroEsquema(f"definição fora de ordem ({etiqueta}, esperada {proxima}) no byte {pos}")
            self.definicao()
        elif etiqueta >= proxima:
            raise ErroEsquema(f"referência a classe ainda não definida ({etiqueta}) no byte {pos}")
        return etiqueta

    def campo(self, profundidade=0):
        if profundidade > 64:
            raise ErroEsquema(f"campo aninhado demais no byte {self.p}")
        nome = self.texto(self.u32())
        pos, descritor = self.p, self.u32()
        base, modificador = descritor & 0xFF, (descritor >> 8) & 0xFF
        if not (1 <= base <= 14 and modificador in MODIFICADORES):
            raise ErroEsquema(f"descritor {descritor:#010x} não suportado no byte {pos} ({nome})")
        n_arranjo = None
        if 16 <= modificador <= 19:
            n_arranjo = self.u32()
            if not 1 <= n_arranjo <= 1_000_000:
                raise ErroEsquema(f"arranjo de {n_arranjo} no byte {self.p - 4}")
        referencias, sub = [], None
        if base == 14 and modificador in (0, 16, 80):
            referencias.append(self.referencia())
        if base == 13:
            sub = self.campo(profundidade + 1)
            referencias.extend(sub.referencias)
            repeticoes = (n_arranjo or 1) - 1
            if n_arranjo is None and sub.base == 14 and sub.n_arranjo is not None:
                repeticoes += 1  # composto simples sobre arranjo de referências (SiteSurface.m_facets, 2018)
            for _ in range(repeticoes):
                for esperada in sub.referencias:
                    pos = self.p
                    if self.referencia() != esperada:
                        raise ErroEsquema(f"referência repetida diferente no byte {pos}")
                    referencias.append(esperada)
        return Campo(nome, descritor, base, modificador, n_arranjo, referencias, sub)

    def definicao(self):
        self.profundidade += 1
        if self.profundidade > 128 or len(self.classes) >= 32_756:
            raise ErroEsquema(f"definições aninhadas demais no byte {self.p}")
        pos = self.p
        if self.u16() != 0:
            raise ErroEsquema(f"cabeçalho de classe inválido no byte {pos}")
        nome = self.texto(self.u16())
        ordem = len(self.classes)
        self.classes.append(None)  # a classe se registra antes das que ela define em linha
        pai = self.referencia()
        versao = self.u32()
        n_campos = self.u32()
        if n_campos > 100_000:
            raise ErroEsquema(f"{n_campos} campos na classe {nome}")
        campos = [self.campo() for _ in range(n_campos)]
        if self.opaco:
            k = self.u32()
            if k > 1_000_000:
                raise ErroEsquema(f"{k} entradas opacas na classe {nome}")
            self.take(16 * k)
        self.classes[ordem] = Classe(PRIMEIRA_ETIQUETA + ordem, nome, pai, versao, campos)
        self.profundidade -= 1


def _ler(dados, opaco):
    r = _Leitor(dados, opaco)
    while len(dados) - r.p > 8:
        r.definicao()
    if dados[r.p:] != bytes(8):
        raise ErroEsquema(f"o esquema não termina em 8 zeros (byte {r.p})")
    return r.classes


def ler_esquema(inflado):
    erros = []
    for variante, opaco in (("com_opaco", True), ("sem_opaco", False)):
        try:
            classes = _ler(inflado, opaco)
        except ErroEsquema as exc:
            erros.append(f"{variante}: {exc}")
            continue
        return Esquema(classes, variante, hashlib.sha256(inflado).hexdigest())
    raise ErroEsquema("nenhuma variante lê o esquema — " + "; ".join(erros))
