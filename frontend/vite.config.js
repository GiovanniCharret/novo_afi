import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: {
    outDir: "../backend/app/static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Hash de conteúdo no nome dos bundles. Cada build gera URLs únicas
        // (ex.: assets/index-a1b2c3d4.js). O index.html que o vite gera
        // referencia os nomes com hash automaticamente — e o FastAPI serve
        // o index.html com etag, então o navegador revalida o HTML e busca
        // o JS novo quando o hash muda. Sem isso, o nome fixo `app.js` fazia
        // o navegador servir um bundle velho do cache após cada deploy.
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
