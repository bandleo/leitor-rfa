import { defineConfig } from "vitest/config";

// A página pronta vai para dentro do pacote Python (leitor_rfa/web), que o `ler-rfa visualizar` serve.
// Em desenvolvimento (`npm run dev`), o /api vai para um `ler-rfa visualizar --porta 8765` rodando ao lado.
export default defineConfig({
  base: "./",
  build: { outDir: "../leitor_rfa/web", emptyOutDir: true, chunkSizeWarningLimit: 1000 },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { include: ["tests/**/*.test.ts"], environment: "node" },
});
