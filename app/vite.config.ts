// Baut die Terminal-App nach website/app (wird mit der Website auf GitHub Pages veröffentlicht).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "../website/app", emptyOutDir: true, chunkSizeWarningLimit: 900 },
});
