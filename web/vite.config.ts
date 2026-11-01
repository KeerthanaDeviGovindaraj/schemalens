import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In API mode (default) the dev server proxies /api to the local FastAPI app.
// In static mode (VITE_DATA_MODE=static) the UI loads /bundle.json instead.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  build: {
    outDir: "dist",
  },
});
