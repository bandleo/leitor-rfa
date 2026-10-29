// Lógica pura do visualizador (sem WebGL, testável no node): vistas, enquadramento, partes e o selo de
// completude. O glTF vem em metros com Y para cima; o Revit é Z para cima: (x, y, z) Revit → (x, z, −y) glTF.

export type Vetor = readonly [number, number, number];
export interface Caixa {
  min: Vetor;
  max: Vetor;
}
export type NomeVista = "frente" | "direita" | "topo" | "iso";

/** De onde a câmera olha (do alvo para a câmera) e o "para cima" de cada vista, já no glTF. */
export const VISTAS: Record<NomeVista, { rotulo: string; direcao: Vetor; cima: Vetor }> = {
  frente: { rotulo: "Frente", direcao: [0, 0, 1], cima: [0, 1, 0] }, // a Frente do Revit olha de −Y
  direita: { rotulo: "Direita", direcao: [1, 0, 0], cima: [0, 1, 0] },
  topo: { rotulo: "Topo", direcao: [0, 1, 0], cima: [0, 0, -1] }, // planta: +Y do Revit para cima na tela
  iso: { rotulo: "3D", direcao: [1, 1, 1], cima: [0, 1, 0] }, // como a vista {3D} padrão: frente, direita, topo
};

export interface Enquadramento {
  alvo: Vetor;
  posicao: Vetor;
  cima: Vetor;
  perto: number;
  longe: number;
}

/** Câmera em perspectiva que mostra a caixa inteira na vista pedida (a esfera da caixa cabe no menor campo). */
export function enquadrar(caixa: Caixa, vista: NomeVista, fovGraus: number, aspecto: number): Enquadramento {
  const { direcao, cima } = VISTAS[vista];
  const alvo = [0, 1, 2].map((k) => (caixa.min[k] + caixa.max[k]) / 2) as unknown as Vetor;
  const raio = Math.max(Math.hypot(...[0, 1, 2].map((k) => caixa.max[k] - caixa.min[k])) / 2, 1e-3);
  const vertical = (fovGraus * Math.PI) / 180;
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * aspecto);
  const distancia = (raio / Math.sin(Math.min(vertical, horizontal) / 2)) * 1.08;
  const n = Math.hypot(...direcao);
  const posicao = [0, 1, 2].map((k) => alvo[k] + (direcao[k] / n) * distancia) as unknown as Vetor;
  return { alvo, posicao, cima, perto: Math.max((distancia - raio) / 10, raio / 1000), longe: (distancia + raio) * 10 };
}

/** Extras de cada nó, como `leitor_rfa.malha.para_glb` grava. */
export interface ExtrasParte {
  id: number;
  origem: string;
  classe: string;
  fonte: string;
  visivel_3d: boolean | null;
  motivo?: string;
}

export interface Parte {
  chave: string;
  nome: string;
  oculta: boolean; // o Revit não mostra no projeto (hospedeiro simulado, por exemplo)
  motivo?: string;
  extras?: ExtrasParte;
}

const CLASSES: Record<string, string> = {
  Extrusion: "Extrusão",
  Revolution: "Revolução",
  Sweep: "Varredura",
  Blend: "Mescla",
  SweptBlend: "Mescla de varredura",
};

export function parteDoNo(nome: string, extras: ExtrasParte | undefined): Parte {
  if (!extras || extras.id === undefined) return { chave: nome, nome, oculta: false };
  const oculta = extras.visivel_3d === false;
  return {
    chave: String(extras.id),
    nome: `${CLASSES[extras.classe] ?? extras.classe} ${extras.id}`,
    oculta,
    ...(extras.motivo ? { motivo: extras.motivo } : {}),
    extras,
  };
}

/** O que está na cena: o que o Revit oculta só entra com `mostrarOcultas`; cada parte pode ser desligada. */
export class EstadoPartes {
  mostrarOcultas = false;
  destacada: string | null = null;
  private desligadas = new Set<string>();
  private ocultas: Set<string>;

  constructor(partes: Parte[]) {
    this.ocultas = new Set(partes.filter((p) => p.oculta).map((p) => p.chave));
  }

  alternar(chave: string): void {
    if (!this.desligadas.delete(chave)) this.desligadas.add(chave);
  }

  ligada(chave: string): boolean {
    return !this.desligadas.has(chave);
  }

  naCena(chave: string): boolean {
    return this.ligada(chave) && (this.mostrarOcultas || !this.ocultas.has(chave));
  }

  destacar(chave: string | null): void {
    this.destacada = chave === this.destacada ? null : chave;
  }
}

export interface Completude {
  estado: "completo" | "parcial" | "sem_3d";
  faltando: string[];
  vazios?: number;
  ocultas?: { id: number; classe: string; motivo: string }[];
  triangulos?: number;
}

export interface Selo {
  rotulo: string;
  tom: "ok" | "aviso" | "erro";
  detalhes: string[];
}

/** Selo do 3D com o que falta, em termos do Revit. */
export function selo(c: Completude | undefined): Selo {
  if (!c || c.estado === "sem_3d") return { rotulo: "Sem 3D", tom: "erro", detalhes: c?.faltando ?? [] };
  const detalhes = [...c.faltando];
  const motivos = new Map<string, number>();
  for (const o of c.ocultas ?? []) motivos.set(o.motivo, (motivos.get(o.motivo) ?? 0) + 1);
  for (const [motivo, n] of motivos) {
    detalhes.push(`${n} ${n === 1 ? "forma" : "formas"} que o Revit não mostra no projeto (${motivo})`);
  }
  return c.estado === "completo"
    ? { rotulo: "3D completo", tom: "ok", detalhes }
    : { rotulo: "3D parcial", tom: "aviso", detalhes };
}
