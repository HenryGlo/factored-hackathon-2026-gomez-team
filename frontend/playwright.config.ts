// e2e de los tres recorridos (prompt 08, B9). Corre contra una app ya levantada:
//   BASE_URL (por defecto http://127.0.0.1:5173) con un backend LLM_PROVIDER=fake sobre una base *_test con los usuarios demo
//   y el estado de demo limpio (scripts/dev_up.sh --reset-demo). DEMO_PASSWORD solo por entorno.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,          // deja margen para reintentar el login si el límite por IP responde 429
  reporter: [["list"]],
  use: { baseURL: process.env.BASE_URL ?? "http://127.0.0.1:5173", locale: "es", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: "**/a11y.e2e.ts" },
  ],
});
