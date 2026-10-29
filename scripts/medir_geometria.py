"""Mede o 3D do leitor (B-rep salvo, `leitor_rfa.malha.partes`) contra o IFC que o próprio Revit exportou.

uso: python -I -X utf8 scripts/medir_geometria.py <gabarito> <extracao> <saida.json> [prefixo-do-sha]
  <gabarito>/<sha>/familia.rfa e <extracao>/<sha>/familia.ifc. Precisa de numpy e ifcopenshell (extra [3d]).

Por família: o IFC tem uma instância por tipo; o .rfa guarda um estado só (o tipo corrente ao salvar),
então vale o tipo mais parecido. Métricas, em mm:
  - caixa: maior diferença entre os cantos das caixas;
  - leitor→IFC e IFC→leitor: P95 da distância de pontos amostrados na superfície de um até a superfície
    do outro (distância ponto–triângulo exata, sobre os triângulos candidatos mais próximos);
  - volume (diagnóstico).
"fiel" = P95 nos dois sentidos ≤ TOL_MM. Sobra (leitor→IFC alto) = algo que o Revit não mostra; falta
(IFC→leitor alto) = algo que o leitor ainda não gera.
"""
import json
import os
import pathlib
import sys
import time

# numpy e ifcopenshell podem vir de outro site-packages da mesma versão do Python (MEDIR_SITE), sem instalar
# nada no ambiente do leitor nem largar o -I
sys.path += [p for p in os.environ.get("MEDIR_SITE", "").split(os.pathsep) if p]

import ifcopenshell  # noqa: E402
import ifcopenshell.geom  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from leitor_rfa.malha import partes  # noqa: E402

TOL_MM = 1.0
AMOSTRAS = 3000
VIZINHOS = 6
rng = np.random.default_rng(7)


def _amostrar(v, t, n):
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if areas.sum() <= 0:
        return np.zeros((0, 3)), np.zeros(0, int)
    idx = rng.choice(len(t), size=n, p=areas / areas.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    p = (1 - s)[:, None] * a[idx] + (s * (1 - r2))[:, None] * b[idx] + (s * r2)[:, None] * c[idx]
    return p, idx


def _ponto_triangulo(p, a, b, c):
    """Distância de cada ponto p[i] ao triângulo (a[i], b[i], c[i]) — Ericson, vetorizado."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-30, 1e-30, den)
    v, w = vb / den, vc / den
    q = a + ab * v[:, None] + ac * w[:, None]  # interior
    with np.errstate(divide="ignore", invalid="ignore"):
        casos = [
            ((d1 <= 0) & (d2 <= 0), a),
            ((d3 >= 0) & (d4 <= d3), b),
            ((d6 >= 0) & (d5 <= d6), c),
            ((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + ab * np.nan_to_num(d1 / (d1 - d3))[:, None]),
            ((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + ac * np.nan_to_num(d2 / (d2 - d6))[:, None]),
            ((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0),
             b + (c - b) * np.nan_to_num((d4 - d3) / ((d4 - d3) + (d5 - d6)))[:, None]),
        ]
    for m, alvo in reversed(casos):
        q = np.where(m[:, None], alvo, q)
    return np.linalg.norm(p - q, axis=1)


def _distancias(pontos, v, t):
    """Distância de cada ponto à superfície (v, t): candidatos pelos pontos amostrados mais próximos."""
    amostra, tri = _amostrar(v, t, 4 * AMOSTRAS)
    alvo = np.vstack([amostra, v[t].mean(1)])
    tri = np.concatenate([tri, np.arange(len(t))])
    saida = np.empty(len(pontos))
    for i in range(0, len(pontos), 256):
        q = pontos[i:i + 256]
        d2 = ((q[:, None, :] - alvo[None, :, :]) ** 2).sum(-1)
        k = min(VIZINHOS, len(alvo))
        cand = tri[np.argpartition(d2, k - 1, axis=1)[:, :k]]
        rep = np.repeat(q, k, axis=0)
        ci = cand.ravel()
        d = _ponto_triangulo(rep, v[t[ci, 0]], v[t[ci, 1]], v[t[ci, 2]]).reshape(len(q), k)
        saida[i:i + 256] = d.min(1)
    return saida


def _volume(v, t):
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


def _comparar(va, ta, vb, tb):
    pa, _ = _amostrar(va, ta, AMOSTRAS)
    pb, _ = _amostrar(vb, tb, AMOSTRAS)
    ab, ba = _distancias(pa, vb, tb), _distancias(pb, va, ta)
    caixa = float(max(np.abs(va.min(0) - vb.min(0)).max(), np.abs(va.max(0) - vb.max(0)).max()))
    return {"caixa_mm": round(caixa, 2), "leitor_ifc_p95": round(float(np.percentile(ab, 95)), 3),
            "ifc_leitor_p95": round(float(np.percentile(ba, 95)), 3),
            "volume_leitor_cm3": round(_volume(va, ta) / 1000, 2), "volume_ifc_cm3": round(_volume(vb, tb) / 1000, 2)}


def ifc_por_tipo(caminho):
    f = ifcopenshell.open(str(caminho))
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", False)
    tipos = {}
    for p in f.by_type("IfcProduct"):
        if not p.Representation or p.is_a("IfcSpatialStructureElement") or p.is_a("IfcOpeningElement"):
            continue
        try:
            g = ifcopenshell.geom.create_shape(s, p).geometry
        except RuntimeError:
            continue
        v = np.array(g.verts).reshape(-1, 3) * 1000.0
        t = np.array(g.faces).reshape(-1, 3)
        if len(t):
            vs, ts = tipos.setdefault(p.ObjectType or p.Name, ([], []))
            ts.append(t + sum(len(x) for x in vs))
            vs.append(v)
    return {k: (np.vstack(vs), np.vstack(ts)) for k, (vs, ts) in tipos.items()}


def medir(rfa, ifc):
    r = partes(rfa)
    vs, ts, n = [], [], 0
    for p in r["partes"]:
        if p["triangulos"]:
            vs.append(np.array(p["vertices"]))
            ts.append(np.array(p["triangulos"]) + n)
            n += len(p["vertices"])
    linha = {"estado": r["completude"]["estado"], "faltando": r["completude"]["faltando"],
             "ocultas": len(r["completude"]["ocultas"])}
    if not vs:
        return {**linha, "fiel": False, "causa": "leitor sem 3D"}
    va, ta = np.vstack(vs), np.vstack(ts)
    melhor = None
    tipos = ifc_por_tipo(ifc)

    def caixa(vb):
        return max(np.abs(va.min(0) - vb.min(0)).max(), np.abs(va.max(0) - vb.max(0)).max())
    # só os dois tipos de caixa mais parecida passam pela medida de distância (a cara)
    for tipo in sorted(tipos, key=lambda k: caixa(tipos[k][0]))[:2]:
        vb, tb = tipos[tipo]
        m = {"tipo": tipo, "tipos_ifc": len(tipos), **_comparar(va, ta, vb, tb)}
        if melhor is None or max(m["leitor_ifc_p95"], m["ifc_leitor_p95"]) < max(melhor["leitor_ifc_p95"],
                                                                                  melhor["ifc_leitor_p95"]):
            melhor = m
    if melhor is None:
        return {**linha, "fiel": False, "causa": "IFC sem geometria"}
    fiel = melhor["leitor_ifc_p95"] <= TOL_MM and melhor["ifc_leitor_p95"] <= TOL_MM
    causa = None if fiel else ("sobra" if melhor["leitor_ifc_p95"] > TOL_MM else "") + \
        ("+" if melhor["leitor_ifc_p95"] > TOL_MM and melhor["ifc_leitor_p95"] > TOL_MM else "") + \
        ("falta" if melhor["ifc_leitor_p95"] > TOL_MM else "")
    return {**linha, **melhor, "fiel": fiel, "causa": causa}


def _uma(args):
    d, ifc = args
    t = time.time()
    try:
        linha = medir(d / "familia.rfa", ifc)
    except Exception as exc:  # noqa: BLE001 — uma família ruim não para a medição
        linha = {"fiel": False, "causa": f"erro: {type(exc).__name__}: {exc}"[:200]}
    return {"sha": d.name, "segundos": round(time.time() - t, 1), **linha}


def main(gabarito, extracao, saida, prefixo=""):
    from concurrent.futures import ProcessPoolExecutor
    tarefas = [(d, pathlib.Path(extracao) / d.name / "familia.ifc")
               for d in sorted(p for p in pathlib.Path(gabarito).iterdir() if p.is_dir() and p.name.startswith(prefixo))]
    tarefas = [t for t in tarefas if t[1].is_file()]
    linhas = []
    with ProcessPoolExecutor(max_workers=max(1, min(8, (os.cpu_count() or 2) - 1))) as ex:
        for linha in ex.map(_uma, tarefas):
            linhas.append(linha)
            print(json.dumps({k: linha.get(k) for k in ("sha", "fiel", "causa", "caixa_mm", "leitor_ifc_p95",
                                                         "ifc_leitor_p95", "segundos")}, ensure_ascii=False), flush=True)
    pathlib.Path(saida).write_text(json.dumps(linhas, ensure_ascii=False, indent=1), encoding="utf-8")
    fieis = sum(1 for x in linhas if x["fiel"])
    print(f"\nfiéis {fieis}/{len(linhas)} (P95 ≤ {TOL_MM} mm nos dois sentidos)")
    causas = {}
    for x in linhas:
        if not x["fiel"]:
            causas[x.get("causa")] = causas.get(x.get("causa"), 0) + 1
    print("causas:", causas)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:5])
