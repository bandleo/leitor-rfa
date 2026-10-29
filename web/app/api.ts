// API do `ler-rfa visualizar` (leitor_rfa/servir.py). Endereços relativos: a página funciona em qualquer caminho.
import type { Familia } from "./abas";

export interface Lido {
  id: string;
  nome: string;
  familia: Familia;
  miniatura: boolean;
}

async function json<T>(r: Response): Promise<T> {
  const corpo = await r.json().catch(() => ({ erro: `${r.status} ${r.statusText}` }));
  if (!r.ok) throw new Error((corpo as { erro?: string }).erro ?? `${r.status}`);
  return corpo as T;
}

export async function ler(arquivo: File): Promise<Lido> {
  const r = await fetch("api/ler", {
    method: "POST",
    body: arquivo,
    headers: { "X-Nome": encodeURIComponent(arquivo.name), "Content-Type": "application/octet-stream" },
  });
  return json<Lido>(r);
}

export async function lido(id: string): Promise<Lido> {
  return json<Lido>(await fetch(`api/${id}`));
}

export async function modelo(id: string): Promise<ArrayBuffer> {
  const r = await fetch(`api/${id}/modelo.glb`);
  if (!r.ok) await json(r);
  return r.arrayBuffer();
}

export const urlMiniatura = (id: string) => `api/${id}/miniatura.png`;
export const urlBimcraft = (id: string) => `api/${id}/bimcraft.zip`;
