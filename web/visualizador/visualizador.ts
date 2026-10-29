// Visualizador 3D de família: three.js puro (sem React), para usar em qualquer página.
//   const v = new Visualizador(div); const info = await v.carregar(glb); v.vista("frente"); v.destacar("101")
// Desenha sob demanda (só quando a câmera ou a cena mudam). As linhas são as arestas do B-rep que vêm no GLB
// (as que o Revit desenha); um GLB sem elas ganha arestas calculadas pelo ângulo entre triângulos.
import {
  Box3, Color, DoubleSide, EdgesGeometry, LineBasicMaterial, LineSegments, Mesh, MeshStandardMaterial, PerspectiveCamera,
  PMREMGenerator, Raycaster, Scene, SRGBColorSpace, Vector2, WebGLRenderer, type Object3D,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { enquadrar, EstadoPartes, parteDoNo, type Completude, type ExtrasParte, type NomeVista, type Parte } from "./cena";

export interface Modelo {
  partes: Parte[];
  completude?: Completude;
}

export interface Cores {
  peca: string;
  destaque: string;
  aresta: string;
  oculta: string;
}

const CORES: Cores = { peca: "#c9ccd1", destaque: "#2f7fd8", aresta: "#30343a", oculta: "#9aa3ad" };
const FOV = 35;
const ANGULO_ARESTA = 25; // graus, só para GLB sem arestas: dobras mais suaves que isso não viram linha

interface NaCena {
  parte: Parte;
  no: Object3D;
  malhas: Mesh[];
  linhas: LineSegments[];
}

export class Visualizador {
  estado = new EstadoPartes([]);
  private renderizador: WebGLRenderer;
  private cena = new Scene();
  private camera = new PerspectiveCamera(FOV, 1, 0.01, 1000);
  private controles: OrbitControls;
  private itens = new Map<string, NaCena>();
  private materiais: Record<"peca" | "destaque" | "oculta", MeshStandardMaterial>;
  private materialAresta: LineBasicMaterial;
  private materialArestaOculta: LineBasicMaterial;
  private observador: ResizeObserver;
  private pedido = 0;
  private ouvintes: ((chave: string | null) => void)[] = [];
  private vistaAtual: NomeVista = "iso";

  constructor(private el: HTMLElement, cores: Partial<Cores> = {}) {
    const c = { ...CORES, ...cores };
    this.renderizador = new WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderizador.outputColorSpace = SRGBColorSpace;
    this.renderizador.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(this.renderizador.domElement);
    const pmrem = new PMREMGenerator(this.renderizador);
    this.cena.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();
    // flatShading: o GLB vem sem normais (o glTF manda calcular normais planas), e facetado lembra o Revit
    const base = { metalness: 0, roughness: 0.75, side: DoubleSide, flatShading: true, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 };
    this.materiais = {
      peca: new MeshStandardMaterial({ ...base, color: new Color(c.peca) }),
      destaque: new MeshStandardMaterial({ ...base, color: new Color(c.destaque), emissive: new Color(c.destaque), emissiveIntensity: 0.25 }),
      oculta: new MeshStandardMaterial({ ...base, color: new Color(c.oculta), transparent: true, opacity: 0.35, depthWrite: false }),
    };
    this.materialAresta = new LineBasicMaterial({ color: new Color(c.aresta) });
    this.materialArestaOculta = new LineBasicMaterial({ color: new Color(c.aresta), transparent: true, opacity: 0.3 });
    this.controles = new OrbitControls(this.camera, this.renderizador.domElement);
    this.controles.addEventListener("change", () => this.desenhar());
    this.observador = new ResizeObserver(() => this.redimensionar());
    this.observador.observe(el);
    this.ligarEscolha();
    this.redimensionar();
  }

  /** Carrega o GLB do leitor (um nó por parte, extras do contrato, completude nos extras da cena). */
  async carregar(glb: ArrayBuffer): Promise<Modelo> {
    const gltf = await new GLTFLoader().parseAsync(glb, "");
    this.limpar();
    const partes: Parte[] = [];
    for (const no of [...gltf.scene.children]) {
      // um nó por parte: Mesh (só triângulos) ou Group com a Mesh e as LineSegments das arestas
      const malhas: Mesh[] = [];
      const linhas: LineSegments[] = [];
      no.traverse((o: Object3D) => {
        if (o instanceof LineSegments) linhas.push(o);
        else if (o instanceof Mesh) malhas.push(o);
      });
      if (!malhas.length) continue;
      const parte = parteDoNo(no.name.replace(/_/g, " "), no.userData as ExtrasParte);
      for (const m of malhas) m.userData.chave = parte.chave;
      if (!linhas.length) {
        for (const m of malhas) {
          const l = new LineSegments(new EdgesGeometry(m.geometry, ANGULO_ARESTA), this.materialAresta);
          m.add(l);
          linhas.push(l);
        }
      }
      this.cena.add(no);
      this.itens.set(parte.chave, { parte, no, malhas, linhas });
      partes.push(parte);
    }
    this.estado = new EstadoPartes(partes);
    this.aplicar();
    this.vista(this.vistaAtual);
    return { partes, completude: gltf.scene.userData.completude as Completude | undefined };
  }

  /** Vista do Revit (Frente, Direita, Topo, 3D), enquadrando o que está na cena. */
  vista(nome: NomeVista): void {
    this.vistaAtual = nome;
    const caixa = this.caixa();
    if (caixa.isEmpty()) return this.desenhar();
    const q = enquadrar({ min: caixa.min.toArray(), max: caixa.max.toArray() }, nome, FOV, this.aspecto());
    this.camera.position.set(...q.posicao);
    this.camera.up.set(...q.cima);
    this.camera.near = q.perto;
    this.camera.far = q.longe;
    this.camera.updateProjectionMatrix();
    this.controles.target.set(...q.alvo);
    this.controles.update();
    this.desenhar();
  }

  alternar(chave: string): void {
    this.estado.alternar(chave);
    this.aplicar();
  }

  mostrarOcultas(sim: boolean): void {
    this.estado.mostrarOcultas = sim;
    this.aplicar();
  }

  destacar(chave: string | null): void {
    this.estado.destacar(chave);
    this.aplicar();
  }

  /** Chamado quando se clica numa parte (ou no vazio, com null). */
  aoEscolher(fn: (chave: string | null) => void): void {
    this.ouvintes.push(fn);
  }

  /** PNG do que está na tela (para prints e miniaturas). */
  imagem(): string {
    this.renderizador.render(this.cena, this.camera);
    return this.renderizador.domElement.toDataURL("image/png");
  }

  descartar(): void {
    this.observador.disconnect();
    this.controles.dispose();
    this.limpar();
    Object.values(this.materiais).forEach((m) => m.dispose());
    this.materialAresta.dispose();
    this.materialArestaOculta.dispose();
    this.cena.environment?.dispose();
    this.renderizador.dispose();
    this.renderizador.domElement.remove();
  }

  private aplicar(): void {
    for (const [chave, { parte, no, malhas, linhas }] of this.itens) {
      no.visible = this.estado.naCena(chave);
      const material = this.estado.destacada === chave ? this.materiais.destaque : parte.oculta ? this.materiais.oculta : this.materiais.peca;
      for (const m of malhas) m.material = material;
      for (const l of linhas) l.material = parte.oculta ? this.materialArestaOculta : this.materialAresta;
    }
    this.desenhar();
  }

  private caixa(): Box3 {
    const caixa = new Box3();
    for (const { no } of this.itens.values()) if (no.visible) caixa.expandByObject(no);
    return caixa;
  }

  private aspecto(): number {
    return Math.max(this.el.clientWidth, 1) / Math.max(this.el.clientHeight, 1);
  }

  private redimensionar(): void {
    const w = Math.max(this.el.clientWidth, 1);
    const h = Math.max(this.el.clientHeight, 1);
    this.renderizador.setSize(w, h, false);
    this.renderizador.domElement.style.width = "100%";
    this.renderizador.domElement.style.height = "100%";
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.desenhar();
  }

  private desenhar(): void {
    if (this.pedido) return;
    this.pedido = requestAnimationFrame(() => {
      this.pedido = 0;
      this.renderizador.render(this.cena, this.camera);
    });
  }

  private ligarEscolha(): void {
    const tela = this.renderizador.domElement;
    const raio = new Raycaster();
    let inicio: Vector2 | null = null;
    tela.addEventListener("pointerdown", (e) => (inicio = new Vector2(e.clientX, e.clientY)));
    tela.addEventListener("pointerup", (e) => {
      if (!inicio || inicio.distanceTo(new Vector2(e.clientX, e.clientY)) > 4) return; // arrastou: girou a câmera
      const r = tela.getBoundingClientRect();
      raio.setFromCamera(new Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), this.camera);
      const malhas = [...this.itens.values()].filter((i) => i.no.visible).flatMap((i) => i.malhas);
      const chave = (raio.intersectObjects(malhas, false)[0]?.object.userData.chave as string | undefined) ?? null;
      for (const fn of this.ouvintes) fn(chave);
    });
  }

  private limpar(): void {
    for (const { no, malhas, linhas } of this.itens.values()) {
      this.cena.remove(no);
      for (const o of [...malhas, ...linhas]) o.geometry.dispose();
    }
    this.itens.clear();
  }
}

