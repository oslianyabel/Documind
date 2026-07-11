import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In dev, proxy /api to the local backend so the browser stays same-origin
// (no CORS). In production, nginx serves the SPA and proxies /api → api:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API_TARGET ?? "http://localhost:8010",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
