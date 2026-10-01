/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo la API va por el proxy de Vite: mismo origen, así la cookie httpOnly y el CSRF funcionan sin CORS.
const API = process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: API, changeOrigin: false } } },
  preview: { port: 4173, proxy: { "/api": { target: API, changeOrigin: false } } },
  test: { environment: "jsdom", globals: false },
});
