// Contrato Python → página: o GLB que `leitor_rfa.malha.para_glb` escreve (gerado por tests/test_glb.py, que
// também confere que este arquivo está em dia) abre no GLTFLoader do three.js com os nós, extras e unidades.
import { readFileSync } from "node:fs";
import { Box3, LineSegments, Mesh, type Object3D } from "three";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { describe, expect, it } from "vitest";
import { parteDoNo } from "../visualizador/cena";

function abrir(): Promise<GLTF> {
  const b = readFileSync(new URL("./dados/contrato.glb", import.meta.url));
  const buf = b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
  return new Promise((ok, falha) => new GLTFLoader().parse(buf, "", ok, falha));
}

describe("contrato do GLB", () => {
  it("um nó por parte, com o nome e os extras do Python", async () => {
    const gltf = await abrir();
    const nos: Object3D[] = gltf.scene.children;
    expect(nos.map((n) => n.name)).toEqual(["Extrusão_101", "Extrusão_1537"]);
    const partes = nos.map((n) => parteDoNo(n.name, n.userData as never));
    expect(partes.map((p) => [p.nome, p.oculta])).toEqual([["Extrusão 101", false], ["Extrusão 1537", true]]);
  });

  it("completude nos extras da cena", async () => {
    const gltf = await abrir();
    expect(gltf.scene.userData.completude).toMatchObject({ estado: "parcial", ocultas: [{ id: 1537 }] });
  });

  it("arestas do B-rep numa segunda primitiva (LINES): as 12 do cubo; a laje vem sem", async () => {
    const gltf = await abrir();
    const [cubo, laje] = gltf.scene.children;
    const linhas = cubo.children.filter((o) => o instanceof LineSegments) as LineSegments[];
    expect(linhas).toHaveLength(1);
    expect(linhas[0].geometry.index!.count).toBe(24);
    expect(cubo.children.filter((o) => o instanceof Mesh && !(o instanceof LineSegments))).toHaveLength(1);
    expect(laje).toBeInstanceOf(Mesh);
  });

  it("metros com Y para cima: o cubo de 100 × 200 × 300 mm", async () => {
    const gltf = await abrir();
    const cubo = gltf.scene.children[0];
    const malha = cubo.children.find((o) => o instanceof Mesh) as Mesh;
    const c = new Box3().setFromObject(cubo);
    expect([c.min.x, c.min.y, c.min.z]).toEqual([0, 0, expect.closeTo(-0.2, 6)]);
    expect([c.max.x, c.max.y, c.max.z].map((v) => +v.toFixed(6))).toEqual([0.1, 0.3, 0]);
    expect((malha.material as { side: number }).side).toBe(2); // DoubleSide
  });
});
