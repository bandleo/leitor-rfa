import { describe, expect, it } from "vitest";
import { cobertura, formas, formulas, parametros, resumo, tiposPorParametros, valorParametro } from "../app/abas";
import type { Familia } from "../app/abas";

const doc: Familia = {
  familia: { nome: "Cuba X", categoria: null, categoria_id: -2001160 },
  parametros: [
    { nome: "Largura", grupo: "Cotas", compartilhado: false, guid: null, tipo_dado: "autodesk.spec.aec:length-2.0.1", instancia: false, formula: null },
    { nome: "Raio", grupo: "Cotas", compartilhado: false, guid: null, tipo_dado: "autodesk.spec.aec:length-2.0.1", instancia: true, formula: "Largura / 2" },
    { nome: "Fabricante", grupo: "Dados de identidade", compartilhado: true, guid: "aaaa-bbbb", tipo_dado: "autodesk.spec:spec.string-2.0.0", instancia: false, formula: null },
    { nome: "Com válvula", grupo: "Construção", compartilhado: false, guid: null, tipo_dado: "autodesk.spec:spec.bool-1.0.0", instancia: false, formula: null },
  ],
  tipos: {
    "400 x 300": { Largura: { bruto: 1.3123, texto: null, mm: 400 }, Raio: { bruto: 0.656, texto: null, mm: 200 },
      Fabricante: { bruto: "Fabricante X", texto: null, mm: null }, "Com válvula": { bruto: 1, texto: null, mm: null } },
    "500 x 300": { Largura: { bruto: 1.64, texto: null, mm: 500.25 }, Raio: { bruto: 0.82, texto: null, mm: 250.125 },
      Fabricante: { bruto: "Fabricante X", texto: null, mm: null }, "Com válvula": { bruto: 0, texto: null, mm: null } },
  },
  formas: [
    { tipo: "Extrusion", solido: true, parametro_visivel: null, parametro_material: "Material", esboco_mm: [[[0, 0, 0], [1, 0, 0], [1, 1, 0]]], inicio_mm: 0, fim_mm: -304.8, plano: { normal: [0, 0, 1] } },
    { tipo: "Revolution", solido: false, parametro_visivel: "Com válvula", parametro_material: null, esboco_mm: [], inicio_mm: null, fim_mm: null, plano: null },
  ],
  aninhadas: [{ familia: "Válvula" }],
  partatom: { titulo: "CUBA X", categoria: "Peças hidrossanitárias", omniclass: "23.65.70.11.11" },
  cobertura: { versao_formato: 2018, build: "20170223_1515(x64)", secoes: { tipos: { estado: "lido", nota: null }, miniatura: { estado: "ausente", nota: "sem PNG" } } },
};

describe("valores como o Revit mostra", () => {
  it("comprimento em mm com vírgula", () => {
    expect(valorParametro({ bruto: 1.64, texto: null, mm: 500.25 }, "autodesk.spec.aec:length-2.0.1")).toBe("500,25 mm");
    expect(valorParametro({ bruto: 0.049, texto: "15.0", mm: 15 }, "autodesk.spec.aec:length-2.0.1")).toBe("15 mm");
  });
  it("sim/não, ângulo, tamanho de tubo, texto e vazio", () => {
    expect(valorParametro({ bruto: 1, texto: null, mm: null }, "autodesk.spec:spec.bool-1.0.0")).toBe("Sim");
    expect(valorParametro({ bruto: 0, texto: null, mm: null }, "autodesk.spec:spec.bool-1.0.0")).toBe("Não");
    expect(valorParametro({ bruto: Math.PI / 6, texto: null, mm: null }, "autodesk.spec.aec:angle-2.0.0")).toBe("30°");
    expect(valorParametro({ bruto: 0.13123359580052493, texto: null, mm: null }, "autodesk.spec.aec.piping:pipeSize-2.0.0")).toBe("40 mm");
    expect(valorParametro({ bruto: 0, texto: "0.000 psi", mm: null }, "autodesk.spec.aec.piping:pressure-2.0.0")).toBe("0.000 psi");
    expect(valorParametro({ bruto: "Metal", texto: null, mm: null }, "autodesk.spec:spec.string-2.0.0")).toBe("Metal");
    expect(valorParametro(undefined, undefined)).toBe("");
    expect(valorParametro({ bruto: null, texto: null, mm: null }, "autodesk.spec.aec:material-1.0.0")).toBe("");
  });
});

describe("abas", () => {
  it("resumo: os fatos que importam, com nomes do Revit", () => {
    const r = Object.fromEntries(resumo(doc));
    expect(r["Família"]).toBe("Cuba X");
    expect(r["Categoria"]).toBe("Peças hidrossanitárias");
    expect(r["Versão do Revit"]).toBe("2018");
    expect(r["Tipos"]).toBe("2");
    expect(r["Formas"]).toBe("1 extrusão, 1 revolução (1 vazio)");
    expect(r["Aninhadas"]).toBe("1");
    expect(r["OmniClass"]).toBe("23.65.70.11.11");
  });

  it("formas no plural do Revit", () => {
    const f = (tipo: string, solido = true) => ({ tipo, solido });
    const d: Familia = { familia: { nome: "x" }, formas: [f("Extrusion"), f("Extrusion"), f("SweptBlend"), f("SweptBlend", false), f("Blend")] };
    expect(Object.fromEntries(resumo(d))["Formas"]).toBe("2 extrusões, 2 mesclas de varredura, 1 mescla (1 vazio)");
  });

  it("tipos × parâmetros agrupa como a caixa Tipos de família", () => {
    const t = tiposPorParametros(doc);
    expect(t.tipos).toEqual(["400 x 300", "500 x 300"]);
    expect(t.grupos.map((g) => g.grupo)).toEqual(["Construção", "Cotas", "Dados de identidade"]);
    const cotas = t.grupos.find((g) => g.grupo === "Cotas")!;
    expect(cotas.linhas[0]).toEqual({ nome: "Largura", formula: null, instancia: false, valores: ["400 mm", "500,25 mm"] });
    expect(cotas.linhas[1]).toMatchObject({ nome: "Raio", formula: "Largura / 2", instancia: true });
  });

  it("parâmetros: tipo de dado, instância/tipo e compartilhado", () => {
    const p = parametros(doc);
    expect(p[0]).toEqual({ nome: "Largura", grupo: "Cotas", tipo: "Comprimento", escopo: "Tipo", compartilhado: "Não", formula: "" });
    expect(p[2]).toMatchObject({ tipo: "Texto", compartilhado: "Sim (aaaa-bbbb)" });
    expect(p[3]).toMatchObject({ tipo: "Sim/Não" });
  });

  it("fórmulas: só os parâmetros que têm", () => {
    expect(formulas(doc)).toEqual([{ nome: "Raio", formula: "Largura / 2" }]);
  });

  it("formas: tipo em português, sólido/vazio, vínculos e esboço", () => {
    const f = formas(doc);
    expect(f[0]).toEqual({ tipo: "Extrusão", natureza: "Sólido", visivel: "", material: "Material", extensao: "0 → −304,8 mm", esboco: "1 laço, 3 pontos" });
    expect(f[1]).toMatchObject({ tipo: "Revolução", natureza: "Vazio", visivel: "Com válvula", extensao: "", esboco: "—" });
    const laje = formas({ familia: { nome: "x" }, formas: [{ tipo: "Extrusion", solido: true, hospedeiro_simulado: true }] });
    expect(laje[0].natureza).toBe("Hospedeiro simulado");
  });

  it("cobertura: versão e estado de cada seção", () => {
    const c = cobertura(doc);
    expect(c.fatos).toContainEqual(["Formato", "2018 (20170223_1515(x64))"]);
    expect(c.secoes).toEqual([{ secao: "tipos", estado: "lido", nota: "" }, { secao: "miniatura", estado: "ausente", nota: "sem PNG" }]);
  });

  it("documento mínimo (2010/2011: só metadados) não quebra nenhuma aba", () => {
    const vazio: Familia = { familia: { nome: "Antiga" }, cobertura: { versao_formato: 2010 } };
    expect(Object.fromEntries(resumo(vazio))["Tipos"]).toBe("0");
    expect(tiposPorParametros(vazio)).toEqual({ tipos: [], grupos: [] });
    expect(parametros(vazio)).toEqual([]);
    expect(formulas(vazio)).toEqual([]);
    expect(formas(vazio)).toEqual([]);
    expect(cobertura(vazio).secoes).toEqual([]);
  });
});
