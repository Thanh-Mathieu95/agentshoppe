import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": backend,
      "/mock": backend,
      "/demo_photos": backend,
      "/ws": { target: backend, ws: true },
    },
  },
});
