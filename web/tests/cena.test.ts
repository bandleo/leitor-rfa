import { describe, expect, it } from "vitest";
import { enquadrar, EstadoPartes, parteDoNo, selo, VISTAS } from "../visualizador/cena";

const caixa = { min: [-1, 0, -0.5], max: [1, 2, 0.5] } as const;

describe("vistas", () => {
  it("seguem as vistas do Revit no glTF (Revit (x, y, z) → glTF (x, z, −y))", () => {
    // Frente do Revit olha de −Y (Revit) = +Z (glTF); Topo olha de cima com o Norte do projeto para cima
    expect(VISTAS.frente.direcao).toEqual([0, 0, 1]);
    expect(VISTAS.direita.direcao).toEqual([1, 0, 0]);
    expect(VISTAS.topo).toMatchObject({ direcao: [0, 1, 0], cima: [0, 0, -1] });
    expect(VISTAS.iso.direcao).toEqual([1, 1, 1]);
  });

  it("enquadrar põe a caixa inteira no campo de visão, olhando para o centro", () => {
    const q = enquadrar(caixa, "frente", 45, 1.5);
    expect(q.alvo).toEqual([0, 1, 0]);
    expect(q.posicao[0]).toBeCloseTo(0);
    expect(q.posicao[1]).toBeCloseTo(1);
    const raio = Math.hypot(2, 2, 1) / 2;
    expect(q.posicao[2]).toBeGreaterThan(raio / Math.sin((45 * Math.PI) / 360));
    expect(q.perto).toBeLessThan(q.posicao[2] - raio);
    expect(q.longe).toBeGreaterThan(q.posicao[2] + raio);
  });

  it("enquadrar em tela estreita afasta mais (o campo horizontal manda)", () => {
    const larga = enquadrar(caixa, "frente", 45, 2);
    const estreita = enquadrar(caixa, "frente", 45, 0.5);
    expect(estreita.posicao[2]).toBeGreaterThan(larga.posicao[2]);
  });

  it("caixa vazia ou de um ponto não quebra", () => {
    const q = enquadrar({ min: [1, 1, 1], max: [1, 1, 1] }, "iso", 45, 1);
    expect(q.posicao.every(Number.isFinite)).toBe(true);
    expect(q.perto).toBeGreaterThan(0);
  });
});

describe("partes", () => {
  it("nome em português a partir dos extras do nó", () => {
    const p = parteDoNo("Extrusion 101", { id: 101, origem: "forma", classe: "Extrusion", fonte: "brep_salvo", visivel_3d: null });
    expect(p).toMatchObject({ chave: "101", nome: "Extrusão 101", oculta: false });
    const c = parteDoNo("x", { id: 7, origem: "combinacao", classe: "Combinação", fonte: "brep_salvo", visivel_3d: null });
    expect(c.nome).toBe("Combinação 7");
  });

  it("o que o Revit oculta vem marcado, com o motivo", () => {
    const p = parteDoNo("", { id: 1537, origem: "forma", classe: "Extrusion", fonte: "brep_salvo", visivel_3d: false, motivo: "hospedeiro simulado" });
    expect(p).toMatchObject({ oculta: true, motivo: "hospedeiro simulado" });
  });

  it("nó sem extras ainda vira parte", () => {
    expect(parteDoNo("Objeto", undefined)).toMatchObject({ chave: "Objeto", nome: "Objeto", oculta: false });
  });

  it("estado: oculta só aparece com 'mostrar o que o Revit oculta'; desligar uma parte vale sempre", () => {
    const partes = [parteDoNo("", { id: 1, origem: "forma", classe: "Sweep", fonte: "brep_salvo", visivel_3d: null }),
      parteDoNo("", { id: 2, origem: "forma", classe: "Extrusion", fonte: "brep_salvo", visivel_3d: false, motivo: "hospedeiro simulado" })];
    const e = new EstadoPartes(partes);
    expect(e.naCena("1")).toBe(true);
    expect(e.naCena("2")).toBe(false);
    e.mostrarOcultas = true;
    expect(e.naCena("2")).toBe(true);
    e.alternar("1");
    expect(e.naCena("1")).toBe(false);
    e.alternar("1");
    expect(e.naCena("1")).toBe(true);
  });

  it("destacar alterna: a mesma parte de novo tira o destaque", () => {
    const e = new EstadoPartes([parteDoNo("a", undefined)]);
    e.destacar("a");
    expect(e.destacada).toBe("a");
    e.destacar("a");
    expect(e.destacada).toBeNull();
  });
});

describe("selo de completude", () => {
  it("completo", () => {
    expect(selo({ estado: "completo", faltando: [] })).toMatchObject({ rotulo: "3D completo", tom: "ok", detalhes: [] });
  });

  it("parcial lista o que falta e o que o Revit oculta", () => {
    const s = selo({ estado: "parcial", faltando: ["1 instância de família aninhada ainda sem 3D"],
      ocultas: [{ id: 1537, classe: "Extrusion", motivo: "hospedeiro simulado" }] });
    expect(s.rotulo).toBe("3D parcial");
    expect(s.tom).toBe("aviso");
    expect(s.detalhes).toEqual(["1 instância de família aninhada ainda sem 3D",
      "1 forma que o Revit não mostra no projeto (hospedeiro simulado)"]);
  });

  it("sem 3D e sem completude", () => {
    expect(selo({ estado: "sem_3d", faltando: ["família raiz não identificada"] })).toMatchObject({ rotulo: "Sem 3D", tom: "erro" });
    expect(selo(undefined)).toMatchObject({ rotulo: "Sem 3D", tom: "erro" });
  });
});
