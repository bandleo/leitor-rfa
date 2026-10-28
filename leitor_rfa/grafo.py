"""Motor genérico: decodifica o corpo de um objeto guiado pelo esquema do arquivo.

Porte de rvt-rs (Apache-2.0) src/native_parameters.rs (decode_graph). O corpo
começa com o u16 da classe; os campos vêm da classe mais básica para a mais
derivada. Ponteiro (base 14, modificador 1–3): u32 token e, se não nulo e não
externo (modificador 3), u16 da classe; o objeto apontado é lido depois do
atual, em fila, e o mesmo token é o mesmo objeto. String: u32 n + n unidades
UTF-16. Arranjo 0x10–0x13: contagem fixa do esquema; 0x50–0x53: u32 de contagem.
Campo com a flag 2 é transitório e não é gravado. O corpo é consumido inteiro.
"""
import dataclasses
import math
import struct
from collections import deque
from dataclasses import dataclass

LIMITE_OBJETOS = 100_000
LIMITE_VALORES = 5_000_000
LIMITE_PROFUNDIDADE = 256
SEM_TOKEN = 0xFFFFFFFF
_ESCALARES = {2: ("<B", 1), 3: ("<h", 2), 4: ("<i", 4), 5: ("<I", 4), 6: ("<f", 4), 7: ("<d", 8), 11: ("<q", 8)}


class ErroGrafo(Exception):
    """O corpo não segue o esquema (truncado, sobra, tipo não suportado)."""


@dataclass
class Objeto:
    classe: str
    etiqueta: int
    token: int
    campos: dict


class Grafo:
    def __init__(self, objetos):
        self.objetos = objetos

    @property
    def raiz(self):
        return self.objetos[0]

    def alvo(self, valor):
        if not isinstance(valor, dict) or "indice" not in valor:
            return None
        return self.objetos[valor["indice"]]


class _Cursor:
    def __init__(self, corpo, esquema):
        self.b, self.p, self.e = corpo, 0, esquema
        self.pendentes, self.valores = [], 0

    def take(self, n):
        if self.p + n > len(self.b):
            raise ErroGrafo(f"corpo truncado no byte {self.p}: faltam {n} B")
        r = self.b[self.p:self.p + n]
        self.p += n
        return r

    def u16(self):
        return int.from_bytes(self.take(2), "little")

    def u32(self):
        return int.from_bytes(self.take(4), "little")

    def classe(self, etiqueta, prof):
        linhagem, t = [], etiqueta
        while True:
            c = self.e.classe(t)
            if c is None:
                raise ErroGrafo(f"classe {t} ausente do esquema")
            linhagem.append(c)
            if len(linhagem) + prof > LIMITE_PROFUNDIDADE:
                raise ErroGrafo("herança profunda demais")
            t = c.pai
            if t < 12:
                break
        contagem = {}
        for c in linhagem:
            for f in c.campos:
                if not (f.descritor >> 16) & 2:
                    contagem[f.nome] = contagem.get(f.nome, 0) + 1
        valores = {}
        for distancia, c in reversed(list(enumerate(linhagem))):
            for f in c.campos:
                flags = f.descritor >> 16
                if flags & 2:
                    continue
                if flags and not (c.nome == "VarExpr" and f.nome == "m_refCt" and flags == 4):
                    raise ErroGrafo(f"flags {flags} não suportadas em {c.nome}.{f.nome}")
                chave = f"{c.nome}::{f.nome}" if contagem[f.nome] > 1 else f.nome
                try:
                    valores[chave] = self._valor_de(c, f, prof + distancia + 1)
                except ErroGrafo as exc:
                    raise ErroGrafo(f"{c.nome}.{f.nome}: {exc}") from None
        return valores

    def _valor_de(self, c, f, prof):
        if c.nome == "ClassDefinitionRef" and f.nome == "m_ref" and f.base == 10 and f.modificador == 0:
            t = self.u16()
            ref = self.e.classe(t)
            return {"classe_ref": ref.nome if ref else None}
        if c.nome == "VarSketchObj" and f.nome == "m_params" and f.base == 14 and f.modificador == 0x54:
            f = dataclasses.replace(f, modificador=0x51)
        return self.campo(f, prof)

    def campo(self, f, prof):
        if prof > LIMITE_PROFUNDIDADE:
            raise ErroGrafo("campo aninhado demais")
        self.valores += 1
        if self.valores > LIMITE_VALORES:
            raise ErroGrafo("limite de valores excedido")
        mod = f.modificador
        if f.base == 14 and mod in (1, 2, 3):
            return self.ponteiro(mod == 3)
        if f.base == 8 and mod == 0x60:
            n = self.u32()
            try:
                return self.take(2 * n).decode("utf-16-le")
            except UnicodeDecodeError as exc:
                raise ErroGrafo(f"texto UTF-16 inválido no byte {self.p}") from exc
        if mod in (0x10, 0x11, 0x12, 0x13, 0x50, 0x51, 0x52, 0x53):
            n = f.n_arranjo if mod < 0x50 else self.u32()
            if n is None or n > 1_000_000:
                raise ErroGrafo(f"arranjo de {n} itens")
            item = dataclasses.replace(f, modificador=mod & 0xF, n_arranjo=None)
            return [self.campo(item, prof + 1) for _ in range(n)]
        if mod != 0:
            raise ErroGrafo(f"modificador {mod:#x} não suportado (base {f.base})")
        if f.base == 1:
            b = self.take(1)[0]
            if b > 1:
                raise ErroGrafo(f"booleano inválido ({b}) no byte {self.p - 1}")
            return bool(b)
        if f.base in _ESCALARES:
            fmt, n = _ESCALARES[f.base]
            v = struct.unpack(fmt, self.take(n))[0]
            if f.base in (6, 7) and not math.isfinite(v):
                raise ErroGrafo(f"número não finito no byte {self.p - n}")
            return v
        if f.base == 9:
            return self.take(16)
        if f.base == 13:
            if f.aninhado is None:
                raise ErroGrafo("composto sem descritor aninhado")
            return self.campo(f.aninhado, prof + 1)
        if f.base == 14:
            if len(f.referencias) != 1:
                raise ErroGrafo("classe em linha sem referência única")
            return self.classe(f.referencias[0], prof + 1)
        raise ErroGrafo(f"tipo base {f.base} não suportado")

    def ponteiro(self, externo):
        token = self.u32()
        valor = {"ponteiro": token, "classe": None}
        if token != 0 and not externo:
            t = self.u16()
            c = self.e.classe(t)
            if c is None:
                raise ErroGrafo(f"ponteiro para classe desconhecida {t}")
            valor["classe"] = c.nome
            self.pendentes.append((token, t, valor))
        return valor


def id_elemento(valor):
    """Número de um ElementId decodificado: {'m_id': {'m_id': n}} até 2023, {'m_id': {'m_id64': n}} a partir de 2024."""
    v = valor["m_id"]
    return v["m_id"] if "m_id" in v else v["m_id64"]


def decodificar(corpo, esquema):
    if len(corpo) < 2:
        raise ErroGrafo("corpo sem etiqueta de classe")
    cursor = _Cursor(corpo, esquema)
    raiz = cursor.u16()
    objetos, fila, vistos = [], deque([(0, raiz)]), {}
    while fila:
        token, etiqueta = fila.popleft()
        if len(objetos) >= LIMITE_OBJETOS:
            raise ErroGrafo("limite de objetos excedido")
        inicio = len(cursor.pendentes)
        campos = cursor.classe(etiqueta, 0)
        objetos.append(Objeto(esquema.classe(etiqueta).nome, etiqueta, token, campos))
        for tok, t, valor in cursor.pendentes[inicio:]:
            if tok != SEM_TOKEN and tok in vistos:
                indice, t0 = vistos[tok]
                if t0 != t:
                    raise ErroGrafo(f"o token {tok} muda de classe ({t0} → {t})")
            else:
                indice = len(objetos) + len(fila)
                fila.append((tok, t))
                if tok != SEM_TOKEN:
                    vistos[tok] = (indice, t)
            valor["indice"] = indice
    if cursor.p != len(corpo):
        raise ErroGrafo(f"sobra de {len(corpo) - cursor.p} B no fim do corpo")
    return Grafo(objetos)
