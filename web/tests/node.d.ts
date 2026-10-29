// O mínimo de node:fs que os testes usam, sem instalar @types/node só para isso
declare module "node:fs" {
  export function readFileSync(caminho: URL | string): Uint8Array;
}
