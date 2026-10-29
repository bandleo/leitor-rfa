// O familia.json (esquema v1 do leitor-rfa) vira os dados de cada aba, com os nomes e unidades do Revit.
// Funções puras: a página só põe isto em tabelas.

export interface Valor {
  bruto: unknown;
  texto: string | null;
  mm: number | null;
}

export interface Parametro {
  nome: string;
  grupo?: string | null;
  compartilhado?: boolean;
  guid?: string | null;
  tipo_dado?: string | null;
  instancia?: boolean;
  formula?: string | null;
}

export interface Forma {
  tipo: string;
  solido: boolean;
  hospedeiro_simulado?: boolean; // laje/parede de referência do gabarito: o Revit não mostra no projeto
  parametro_visivel?: string | null;
  parametro_material?: string | null;
  esboco_mm?: unknown[][] | null;
  inicio_mm?: number | null;
  fim_mm?: number | null;
  plano?: unknown;
}

export interface Familia {
  familia: { nome: string; categoria?: string | null; categoria_id?: number | null };
  origem?: { sha256?: string; tamanho?: number };
  parametros?: Parametro[] | null;
  tipos?: Record<string, Record<string, Valor>> | null;
  formas?: Forma[] | null;
  aninhadas?: unknown[] | null;
  planos_referencia?: unknown[] | null;
  cotas?: unknown[] | null;
  partatom?: { titulo?: string | null; categoria?: string | null; omniclass?: string | null } | null;
  cobertura?: {
    versao_formato?: number | null;
    build?: string | null;
    leitor?: string;
    secoes?: Record<string, { estado: string; nota?: string | null }>;
  } | null;
}

const PES_MM = 304.8;
const numero = (v: number, casas = 2) => v.toLocaleString("pt-BR", { maximumFractionDigits: casas });

const TIPOS_DADO: [RegExp, string][] = [
  [/:length-/, "Comprimento"],
  [/:angle-/, "Ângulo"],
  [/:area-/, "Área"],
  [/:volume-/, "Volume"],
  [/spec\.bool-/, "Sim/Não"],
  [/spec\.int64-|:integer-/, "Inteiro"],
  [/:number-|spec\.double-/, "Número"],
  [/string:url-/, "URL"],
  [/spec\.string-/, "Texto"],
  [/:material-/, "Material"],
  [/:currency-/, "Moeda"],
  [/:image-/, "Imagem"],
  [/piping:pipeSize-/, "Tamanho do tubo"],
  [/piping:pressure-/, "Pressão"],
  [/piping:flow-/, "Vazão"],
  [/electrical:potential-/, "Potencial elétrico"],
  [/electrical:current-/, "Corrente"],
  [/electrical:power-/, "Potência"],
];

export function nomeTipoDado(tipo: string | null | undefined): string {
  if (!tipo) return "";
  return TIPOS_DADO.find(([re]) => re.test(tipo))?.[1] ?? tipo.replace(/^autodesk\.spec[.:\w]*?:/, "").replace(/-[\d.]+$/, "");
}

/** Valor de um parâmetro como a caixa Tipos de família mostra (mm com vírgula, Sim/Não, graus). */
export function valorParametro(v: Valor | undefined, tipo: string | null | undefined): string {
  if (!v) return "";
  const t = tipo ?? "";
  if (/:length-/.test(t) && v.mm != null) return `${numero(v.mm)} mm`;
  if (/piping:pipeSize-/.test(t) && typeof v.bruto === "number") return `${numero(v.bruto * PES_MM)} mm`;
  if (/:angle-/.test(t) && typeof v.bruto === "number") return `${numero((v.bruto * 180) / Math.PI)}°`;
  if (/spec\.bool-/.test(t) && v.bruto != null) return v.bruto ? "Sim" : "Não";
  if (v.texto) return v.texto;
  if (v.mm != null) return `${numero(v.mm)} mm`;
  if (typeof v.bruto === "number") return numero(v.bruto, 4);
  return v.bruto == null ? "" : String(v.bruto);
}

// tipo do Revit → [nome, singular, plural]
const FORMAS: Record<string, [string, string, string]> = {
  Extrusion: ["Extrusão", "extrusão", "extrusões"],
  Revolution: ["Revolução", "revolução", "revoluções"],
  Sweep: ["Varredura", "varredura", "varreduras"],
  Blend: ["Mescla", "mescla", "mesclas"],
  SweptBlend: ["Mescla de varredura", "mescla de varredura", "mesclas de varredura"],
};

function contarFormas(formas: Forma[]): string {
  if (!formas.length) return "0";
  const n = new Map<string, number>();
  for (const f of formas) n.set(f.tipo, (n.get(f.tipo) ?? 0) + 1);
  const partes = [...n].map(([tipo, k]) => `${k} ${FORMAS[tipo]?.[k === 1 ? 1 : 2] ?? tipo}`);
  const vazios = formas.filter((f) => !f.solido).length;
  return partes.join(", ") + (vazios ? ` (${vazios} ${vazios === 1 ? "vazio" : "vazios"})` : "");
}

export function resumo(doc: Familia): [string, string][] {
  const cob = doc.cobertura ?? {};
  const parametros = doc.parametros ?? [];
  const linhas: [string, string][] = [
    ["Família", doc.familia.nome],
    ["Categoria", doc.partatom?.categoria ?? doc.familia.categoria ?? "—"],
    ["Versão do Revit", cob.versao_formato != null ? String(cob.versao_formato) : "—"],
    ["Tipos", String(Object.keys(doc.tipos ?? {}).length)],
    ["Parâmetros", String(parametros.length)],
    ["Fórmulas", String(parametros.filter((p) => p.formula).length)],
    ["Formas", contarFormas(doc.formas ?? [])],
    ["Aninhadas", String((doc.aninhadas ?? []).length)],
  ];
  if (doc.partatom?.omniclass) linhas.push(["OmniClass", doc.partatom.omniclass]);
  return linhas;
}

export interface LinhaTipos {
  nome: string;
  formula: string | null;
  instancia: boolean;
  valores: string[];
}

/** Matriz tipos × parâmetros, agrupada por grupo (como a caixa Tipos de família do Revit). */
export function tiposPorParametros(doc: Familia): { tipos: string[]; grupos: { grupo: string; linhas: LinhaTipos[] }[] } {
  const tipos = Object.keys(doc.tipos ?? {});
  const grupos = new Map<string, LinhaTipos[]>();
  for (const p of doc.parametros ?? []) {
    const grupo = p.grupo || "Outros";
    const valores = tipos.map((t) => valorParametro(doc.tipos?.[t]?.[p.nome], p.tipo_dado));
    if (!grupos.has(grupo)) grupos.set(grupo, []);
    grupos.get(grupo)!.push({ nome: p.nome, formula: p.formula ?? null, instancia: !!p.instancia, valores });
  }
  return {
    tipos,
    grupos: [...grupos].sort(([a], [b]) => a.localeCompare(b, "pt-BR")).map(([grupo, linhas]) => ({ grupo, linhas })),
  };
}

export function parametros(doc: Familia) {
  return (doc.parametros ?? []).map((p) => ({
    nome: p.nome,
    grupo: p.grupo ?? "",
    tipo: nomeTipoDado(p.tipo_dado),
    escopo: p.instancia ? "Instância" : "Tipo",
    compartilhado: p.compartilhado ? `Sim${p.guid ? ` (${p.guid})` : ""}` : "Não",
    formula: p.formula ?? "",
  }));
}

export function formulas(doc: Familia) {
  return (doc.parametros ?? []).filter((p) => p.formula).map((p) => ({ nome: p.nome, formula: p.formula as string }));
}

const mm = (v: number) => `${v < 0 ? "−" : ""}${numero(Math.abs(v), 1)}`;

export function formas(doc: Familia) {
  return (doc.formas ?? []).map((f) => {
    const lacos = (f.esboco_mm ?? []) as unknown[][];
    const pontos = lacos.reduce((s, l) => s + l.length, 0);
    return {
      tipo: FORMAS[f.tipo]?.[0] ?? f.tipo,
      natureza: f.hospedeiro_simulado ? "Hospedeiro simulado" : f.solido ? "Sólido" : "Vazio",
      visivel: f.parametro_visivel ?? "",
      material: f.parametro_material ?? "",
      extensao: f.inicio_mm != null && f.fim_mm != null ? `${mm(f.inicio_mm)} → ${mm(f.fim_mm)} mm` : "",
      esboco: lacos.length ? `${lacos.length} ${lacos.length === 1 ? "laço" : "laços"}, ${pontos} pontos` : "—",
    };
  });
}

export function cobertura(doc: Familia) {
  const c = doc.cobertura ?? {};
  const fatos: [string, string][] = [];
  if (c.versao_formato != null) fatos.push(["Formato", `${c.versao_formato}${c.build ? ` (${c.build})` : ""}`]);
  if (c.leitor) fatos.push(["Leitor", c.leitor]);
  const secoes = Object.entries(c.secoes ?? {}).map(([secao, s]) => ({ secao, estado: s.estado, nota: s.nota ?? "" }));
  return { fatos, secoes };
}
