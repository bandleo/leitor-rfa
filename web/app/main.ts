// Página do leitor: soltar um .rfa → dados (abas) + 3D ao lado da miniatura do Revit → exportar para o BIMCraft.
import "./estilo.css";
import { selo, VISTAS, type NomeVista, type Parte } from "../visualizador/cena";
import { Visualizador } from "../visualizador/visualizador";
import { cobertura, formas, formulas, parametros, resumo, tiposPorParametros, type Familia } from "./abas";
import { ler, lido, modelo, urlBimcraft, urlMiniatura, type Lido } from "./api";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

/** Elemento com texto (nunca HTML vindo do arquivo). */
function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, ...filhos: (Node | string)[]) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  el.append(...filhos);
  return el;
}

const numero = (n: number, casas = 0) => n.toLocaleString("pt-BR", { maximumFractionDigits: casas });
const escuro = matchMedia("(prefers-color-scheme: dark)").matches;
let visualizador: Visualizador | null = null;
let atual: Lido | null = null;

// ——— abas ———
type Aba = { id: string; rotulo: string; contagem?: (d: Familia) => number; tabela?: (d: Familia) => HTMLElement };

function tabela(cabecalho: string[], linhas: string[][], classe = ""): HTMLElement {
  if (!linhas.length) return h("p", { class: "nada" }, "Nada nesta seção.");
  const corpo = h("tbody", {}, ...linhas.map((l) => h("tr", {}, ...l.map((c) => h("td", {}, c)))));
  return h("div", { class: `rolar ${classe}` }, h("table", {}, h("thead", {}, h("tr", {}, ...cabecalho.map((c) => h("th", {}, c)))), corpo));
}

function tabelaTipos(d: Familia): HTMLElement {
  const t = tiposPorParametros(d);
  if (!t.grupos.length) return h("p", { class: "nada" }, "Nada nesta seção.");
  const corpo = h("tbody");
  for (const g of t.grupos) {
    corpo.append(h("tr", { class: "grupo" }, h("th", { colspan: String(t.tipos.length + 1), scope: "rowgroup" }, g.grupo)));
    for (const l of g.linhas) {
      const nome = h("th", { scope: "row" }, l.nome);
      if (l.instancia) nome.append(h("span", { class: "etiqueta" }, "instância"));
      if (l.formula) nome.append(h("code", { class: "formula", title: "Fórmula" }, `= ${l.formula}`));
      corpo.append(h("tr", {}, nome, ...l.valores.map((v) => h("td", {}, v))));
    }
  }
  const cab = h("thead", {}, h("tr", {}, h("th", {}, "Parâmetro"), ...t.tipos.map((n) => h("th", {}, n))));
  return h("div", { class: "rolar matriz" }, h("table", {}, cab, corpo));
}

const ABAS: Aba[] = [
  { id: "resumo", rotulo: "Resumo e 3D" },
  { id: "tipos", rotulo: "Tipos × Parâmetros", contagem: (d) => Object.keys(d.tipos ?? {}).length, tabela: tabelaTipos },
  {
    id: "parametros", rotulo: "Parâmetros", contagem: (d) => (d.parametros ?? []).length,
    tabela: (d) => tabela(["Nome", "Grupo", "Tipo de dado", "Instância/Tipo", "Compartilhado", "Fórmula"],
      parametros(d).map((p) => [p.nome, p.grupo, p.tipo, p.escopo, p.compartilhado, p.formula])),
  },
  {
    id: "formulas", rotulo: "Fórmulas", contagem: (d) => formulas(d).length,
    tabela: (d) => tabela(["Parâmetro", "Fórmula"], formulas(d).map((f) => [f.nome, f.formula]), "codigo"),
  },
  {
    id: "formas", rotulo: "Formas", contagem: (d) => (d.formas ?? []).length,
    tabela: (d) => tabela(["Forma", "Sólido/Vazio", "Visível", "Material", "Início → fim", "Esboço"],
      formas(d).map((f) => [f.tipo, f.natureza, f.visivel, f.material, f.extensao, f.esboco])),
  },
  {
    id: "cobertura", rotulo: "Cobertura",
    tabela: (d) => {
      const c = cobertura(d);
      return h("div", {}, h("dl", { class: "fatos largo" }, ...c.fatos.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
        tabela(["Seção", "Estado", "Nota"], c.secoes.map((s) => [s.secao, s.estado, s.nota])));
    },
  },
];

function montarAbas(d: Familia): void {
  const barra = $("abas");
  barra.replaceChildren(...ABAS.map((a, i) => {
    const b = h("button", { type: "button", role: "tab", "aria-selected": String(i === 0), "data-aba": a.id }, a.rotulo);
    if (a.contagem) b.append(h("span", { class: "contagem" }, String(a.contagem(d))));
    b.addEventListener("click", () => mostrarAba(a.id));
    return b;
  }));
}

function mostrarAba(id: string): void {
  for (const b of $("abas").querySelectorAll("button")) b.setAttribute("aria-selected", String(b.dataset.aba === id));
  const resumoVisivel = id === "resumo";
  $("painel-resumo").hidden = !resumoVisivel;
  const painel = $("painel-tabela");
  painel.hidden = resumoVisivel;
  if (!resumoVisivel && atual) painel.replaceChildren(ABAS.find((a) => a.id === id)!.tabela!(atual.familia));
}

// ——— 3D ———
function montarVistas(): void {
  $("vistas").replaceChildren(...(Object.keys(VISTAS) as NomeVista[]).map((nome) => {
    const b = h("button", { type: "button", "aria-pressed": String(nome === "iso") }, VISTAS[nome].rotulo);
    b.addEventListener("click", () => {
      for (const o of $("vistas").children) o.setAttribute("aria-pressed", String(o === b));
      visualizador?.vista(nome);
    });
    return b;
  }));
}

function listarPartes(partes: Parte[]): void {
  const lista = $("partes");
  if (!partes.length) return lista.replaceChildren(h("li", { class: "nada" }, "Nenhuma parte com 3D."));
  lista.replaceChildren(...partes.map((p) => {
    const caixa = h("input", { type: "checkbox", "aria-label": `Mostrar ${p.nome}` }) as HTMLInputElement;
    caixa.checked = true;
    caixa.addEventListener("change", () => visualizador?.alternar(p.chave));
    const nome = h("button", { type: "button", class: "nome", "data-chave": p.chave }, p.nome);
    nome.addEventListener("click", () => destacar(p.chave));
    const li = h("li", { "data-chave": p.chave }, caixa, nome);
    if (p.oculta) li.append(h("span", { class: "etiqueta", title: p.motivo ?? "" }, "oculta pelo Revit"));
    return li;
  }));
}

function destacar(chave: string | null): void {
  visualizador?.destacar(chave);
  const ativa = visualizador?.estado.destacada ?? null;
  for (const li of $("partes").children) li.classList.toggle("ativa", (li as HTMLElement).dataset.chave === ativa);
}

async function carregar3D(id: string): Promise<void> {
  const aguarde = $("aguarde");
  aguarde.hidden = false;
  $("aguarde-texto").textContent = "Gerando o 3D…";
  $("selo").replaceChildren();
  $("detalhes").replaceChildren();
  $("medida").textContent = "";
  const inicio = performance.now();
  try {
    if (!visualizador) {
      visualizador = new Visualizador($("tela"), escuro ? { peca: "#aab1ba", aresta: "#1b1e22" } : {});
      visualizador.aoEscolher(destacar);
    }
    const m = await visualizador.carregar(await modelo(id));
    const segundos = (performance.now() - inicio) / 1000;
    const s = selo(m.completude);
    $("selo").replaceChildren(h("span", { class: `tom-${s.tom}` }, s.rotulo));
    $("detalhes").replaceChildren(...s.detalhes.map((d) => h("li", {}, d)));
    const triangulos = m.completude?.triangulos ?? 0;
    $("medida").textContent = `${numero(triangulos)} triângulos · ${numero(segundos, 1)} s`;
    document.body.dataset.tempo3d = segundos.toFixed(2);
    listarPartes(m.partes);
    ($("ocultas") as HTMLInputElement).checked = false;
    for (const o of $("vistas").children) o.setAttribute("aria-pressed", String(o.textContent === VISTAS.iso.rotulo));
    aguarde.hidden = true;
  } catch (e) {
    $("aguarde-texto").textContent = `Sem 3D: ${(e as Error).message}`;
    aguarde.querySelector(".giro")?.remove();
  }
}

// ——— família ———
function mostrar(r: Lido): void {
  atual = r;
  history.replaceState(null, "", `#${r.id}`);
  document.title = `${r.familia.familia.nome} — Leitor RFA`;
  const cob = r.familia.cobertura ?? {};
  const tamanho = r.familia.origem?.tamanho;
  $("arquivo").replaceChildren(h("strong", {}, r.nome),
    ...(cob.versao_formato ? [h("span", { class: "chip" }, `Revit ${cob.versao_formato}`)] : []),
    ...(tamanho ? [h("span", { class: "chip" }, `${numero(tamanho / 1024)} KB`)] : []));
  $("arquivo").hidden = false;
  const exportar = $<HTMLAnchorElement>("exportar");
  exportar.href = urlBimcraft(r.id);
  exportar.removeAttribute("aria-disabled");
  $("fatos").replaceChildren(...resumo(r.familia).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
  const img = $<HTMLImageElement>("miniatura");
  img.closest("figure")!.hidden = !r.miniatura;
  if (r.miniatura) img.src = urlMiniatura(r.id);
  montarAbas(r.familia);
  mostrarAba("resumo");
  $("vazio").hidden = true;
  $("familia").hidden = false;
  void carregar3D(r.id);
}

function erro(msg: string): void {
  $("vazio").hidden = false;
  $("familia").hidden = true;
  const p = $("erro-vazio");
  p.textContent = msg;
  p.hidden = false;
}

async function abrir(arquivo: File): Promise<void> {
  if (!/\.rfa$/i.test(arquivo.name)) return erro(`“${arquivo.name}” não é um .rfa.`);
  $("erro-vazio").hidden = true;
  document.body.classList.add("lendo");
  try {
    mostrar(await ler(arquivo));
  } catch (e) {
    erro(`Não deu para ler “${arquivo.name}”: ${(e as Error).message}`);
  } finally {
    document.body.classList.remove("lendo");
  }
}

// ——— entrada: botão, arrastar e soltar, endereço #id ———
const escolher = $<HTMLInputElement>("escolher");
for (const id of ["abrir", "escolher-vazio"]) $(id).addEventListener("click", () => escolher.click());
escolher.addEventListener("change", () => {
  if (escolher.files?.[0]) void abrir(escolher.files[0]);
  escolher.value = "";
});
$("exportar").addEventListener("click", (e) => {
  if ($("exportar").getAttribute("aria-disabled")) e.preventDefault();
});
$("ocultas").addEventListener("change", (e) => visualizador?.mostrarOcultas((e.target as HTMLInputElement).checked));

let arrastando = 0;
addEventListener("dragenter", (e) => {
  if (!e.dataTransfer?.types.includes("Files")) return;
  arrastando++;
  $("cobrir").hidden = false;
});
addEventListener("dragleave", () => {
  if (--arrastando <= 0) $("cobrir").hidden = true;
});
addEventListener("dragover", (e) => e.preventDefault());
addEventListener("drop", (e) => {
  e.preventDefault();
  arrastando = 0;
  $("cobrir").hidden = true;
  const arquivo = e.dataTransfer?.files[0];
  if (arquivo) void abrir(arquivo);
});

montarVistas();
const doEndereco = location.hash.slice(1);
if (/^[0-9a-f]{16}$/.test(doEndereco)) lido(doEndereco).then(mostrar, () => history.replaceState(null, "", location.pathname));
