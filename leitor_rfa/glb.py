"""GLB (glTF 2.0 binário) sem dependências: um nó por parte, com `extras`.

Entrada em mm com Z para cima (como o Revit); o glTF é em metros com Y para cima: (x, y, z) mm →
(x, z, −y) / 1000. Material de dois lados (faces de família nem sempre fecham) e sem normais: o
GLTFLoader do three.js sombreia plano, o que mostra as arestas como no Revit.
"""
import json
import struct

GLB, JSON_, BIN = 0x46546C67, 0x4E4F534A, 0x004E4942
FLOAT, UINT32 = 5126, 5125
ARESTA = (0.12, 0.13, 0.15, 1.0)  # cor das linhas


def _alinhar(b, enchimento):
    return b + enchimento * (-len(b) % 4)


def _gltf_pos(p):
    x, y, z = p
    return (x / 1000.0, z / 1000.0, -y / 1000.0)


def escrever_glb(partes, gerador="leitor-rfa", extras=None):
    """Bytes do GLB. Cada parte: {nome, vertices [(x,y,z) mm], triangulos [(a,b,c)], arestas [[índices]] (opcional),
    cor (rgba), extras}; `extras` vai na cena (a completude, por exemplo). As arestas viram uma segunda
    primitiva (LINES) da mesma malha, sobre as mesmas posições."""
    gltf = {"asset": {"version": "2.0", "generator": gerador}, "scene": 0, "scenes": [{"nodes": []}],
            "nodes": [], "meshes": [], "materials": [], "accessors": [], "bufferViews": [], "buffers": []}
    if extras:
        gltf["scenes"][0]["extras"] = extras
    binario, materiais = bytearray(), {}
    for parte in partes:
        if not parte.get("triangulos"):
            continue
        pos = [_gltf_pos(p) for p in parte["vertices"]]
        bloco = struct.pack(f"<{3 * len(pos)}f", *(c for p in pos for c in p))
        vista_pos = len(gltf["bufferViews"])
        gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(binario), "byteLength": len(bloco), "target": 34962})
        binario += bloco
        idx = struct.pack(f"<{3 * len(parte['triangulos'])}I", *(i for t in parte["triangulos"] for i in t))
        vista_idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(binario), "byteLength": len(idx), "target": 34963})
        binario += idx
        # o min/max do accessor sai dos float32 gravados, para bater com o que o leitor lê
        gravados = struct.unpack(f"<{3 * len(pos)}f", bloco)
        eixos = [gravados[k::3] for k in range(3)]
        acc_pos = len(gltf["accessors"])
        gltf["accessors"].append({"bufferView": vista_pos, "componentType": FLOAT, "count": len(pos), "type": "VEC3",
                                  "min": [min(e) for e in eixos], "max": [max(e) for e in eixos]})
        gltf["accessors"].append({"bufferView": vista_idx, "componentType": UINT32,
                                  "count": 3 * len(parte["triangulos"]), "type": "SCALAR"})
        cor = tuple(parte.get("cor") or (0.75, 0.75, 0.75, 1.0))
        if cor not in materiais:
            materiais[cor] = len(gltf["materials"])
            gltf["materials"].append({"pbrMetallicRoughness": {"baseColorFactor": list(cor), "metallicFactor": 0.0,
                                                               "roughnessFactor": 0.8},
                                      "doubleSided": True, **({"alphaMode": "BLEND"} if cor[3] < 1 else {})})
        primitivas = [{"attributes": {"POSITION": acc_pos}, "indices": acc_pos + 1, "material": materiais[cor]}]
        pares = [i for linha in parte.get("arestas") or [] for a, b in zip(linha, linha[1:]) if a != b for i in (a, b)]
        if pares:
            bloco = struct.pack(f"<{len(pares)}I", *pares)
            gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(binario), "byteLength": len(bloco), "target": 34963})
            binario += bloco
            gltf["accessors"].append({"bufferView": len(gltf["bufferViews"]) - 1, "componentType": UINT32,
                                      "count": len(pares), "type": "SCALAR"})
            if ARESTA not in materiais:
                materiais[ARESTA] = len(gltf["materials"])
                gltf["materials"].append({"name": "aresta", "pbrMetallicRoughness": {"baseColorFactor": list(ARESTA),
                                                                                     "metallicFactor": 0.0}})
            primitivas.append({"attributes": {"POSITION": acc_pos}, "indices": len(gltf["accessors"]) - 1, "mode": 1,
                               "material": materiais[ARESTA]})
        gltf["meshes"].append({"primitives": primitivas})
        no = {"name": parte.get("nome", f"parte {len(gltf['nodes'])}"), "mesh": len(gltf["meshes"]) - 1}
        if parte.get("extras"):
            no["extras"] = parte["extras"]
        gltf["scenes"][0]["nodes"].append(len(gltf["nodes"]))
        gltf["nodes"].append(no)
    gltf["buffers"].append({"byteLength": len(binario)})
    js = _alinhar(json.dumps(gltf, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), b" ")
    bn = _alinhar(bytes(binario), b"\x00")
    total = 12 + 8 + len(js) + 8 + len(bn)
    return (struct.pack("<III", GLB, 2, total) + struct.pack("<II", len(js), JSON_) + js
            + struct.pack("<II", len(bn), BIN) + bn)


def ler_glb(dados):
    """(gltf, [{nome, posicoes (m, Y para cima), triangulos}]) — leitor mínimo, para testes e conferência."""
    magia, versao, total = struct.unpack_from("<III", dados, 0)
    if magia != GLB or versao != 2 or total != len(dados):
        raise ValueError("não é GLB 2.0")
    n_json, _ = struct.unpack_from("<II", dados, 12)
    gltf = json.loads(dados[20:20 + n_json])
    ini_bin = 20 + n_json + 8
    partes = []
    for no in gltf["nodes"]:
        prim = gltf["meshes"][no["mesh"]]["primitives"][0]

        def acc(i, fmt, largura):
            a = gltf["accessors"][i]
            v = gltf["bufferViews"][a["bufferView"]]
            n = a["count"] * largura
            return struct.unpack_from(f"<{n}{fmt}", dados, ini_bin + v["byteOffset"])

        p = acc(prim["attributes"]["POSITION"], "f", 3)
        t = acc(prim["indices"], "I", 1)
        partes.append({"nome": no.get("name"), "posicoes": [tuple(p[i:i + 3]) for i in range(0, len(p), 3)],
                       "triangulos": [tuple(t[i:i + 3]) for i in range(0, len(t), 3)]})
    return gltf, partes
