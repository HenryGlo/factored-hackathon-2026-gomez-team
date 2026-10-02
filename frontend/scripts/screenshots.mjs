// Capturas de todas las pantallas en escritorio (1440 px) y celular (390 px), para la auditoría y los PR.
//
//   DEMO_PASSWORD=… node scripts/screenshots.mjs <carpeta de salida> [pantalla…]
//
// Variables: BASE_URL (por defecto http://127.0.0.1:5183). La contraseña demo solo llega por entorno.
// Necesita un backend con LLM_PROVIDER=fake y los usuarios demo (scripts/seed_demo_users.py), sobre una base *_test.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:5183";
const PASSWORD = process.env.DEMO_PASSWORD;
const [out = "screenshots", ...only] = process.argv.slice(2);
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };

async function login(page, username) {
  if (!PASSWORD) throw new Error("falta DEMO_PASSWORD en el entorno");
  await page.goto(`${BASE}/login`);
  await page.locator('input[autocomplete="username"]').fill(username);
  await page.locator('input[autocomplete="current-password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

/** Cada pantalla: usuario (o null si es pública) y los pasos hasta el estado que se captura. */
const SCREENS = {
  landing: { user: null, go: async (page) => { await page.goto(`${BASE}/`); } },
  sistema: { user: null, go: async (page) => { await page.goto(`${BASE}/sistema`); } },
  login: { user: null, go: async (page) => { await page.goto(`${BASE}/login`); } },
  chat: {
    user: "demo_cargo_claro_2",
    go: async (page) => {
      await page.goto(`${BASE}/chat`);
      await page.locator(".bubble.assistant").nth(1).waitFor();
      await page.locator("textarea").fill("Tengo un cobro que no reconozco");
      await page.keyboard.press("Enter");
      await page.locator(".bubble.assistant").nth(2).waitFor();
    },
  },
  "chat-cierre": {
    user: "demo_cargo_claro_1",
    go: async (page) => {
      await page.goto(`${BASE}/chat`);
      await page.locator(".bubble.assistant").nth(1).waitFor();
      await page.locator("textarea").fill("No reconozco un cobro");
      await page.keyboard.press("Enter");
      // el recorrido depende de los datos (uno o varios candidatos, reclamo ya existente): cada paso es opcional
      const steps = [page.locator(".choice"), ...[/Sí, es este|Sim, é esta/, /^Confirmar$/, /No, gracias|Não, obrigad/, /Sí, me ayudó|Sim, ajudou/].map((name) => page.getByRole("button", { name }))];
      for (const step of steps) {
        try { await step.and(page.locator(":enabled")).first().click({ timeout: 4000 }); } catch { /* ese paso no aplica en este recorrido */ }
        await page.waitForTimeout(500);
      }
    },
  },
  conversaciones: { user: "demo_cargo_claro_1", go: async (page) => { await page.goto(`${BASE}/conversaciones`); await page.locator(".conv-card").first().waitFor(); } },
  conversacion: {
    user: "demo_cargo_claro_1",
    go: async (page) => {
      await page.goto(`${BASE}/conversaciones`);
      await page.locator(".conv-card", { hasText: "RCL-" }).first().click();
      await page.locator(".transcript .bubble").first().waitFor();
    },
  },
  movimientos: { user: "demo_cargo_claro_1", go: async (page) => { await page.goto(`${BASE}/movimientos`); await page.locator(".timeline").waitFor(); } },
  reclamos: { user: "demo_cargo_claro_1", go: async (page) => { await page.goto(`${BASE}/reclamos`); await page.locator(".case-cards").waitFor(); } },
  consola: { user: "analista_1", go: async (page) => { await page.goto(`${BASE}/consola`); } },
};

mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
let failed = 0;
for (const [name, screen] of Object.entries(SCREENS)) {
  if (only.length && !only.includes(name)) continue;
  for (const [vp, viewport] of Object.entries(VIEWPORTS)) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: vp === "mobile" ? 2 : 1, isMobile: vp === "mobile", locale: "es" });
    const page = await context.newPage();
    try {
      if (screen.user) await login(page, screen.user);
      await screen.go(page);
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: join(out, `${name}-${vp}.png`), fullPage: true });
      console.log(`ok   ${name}-${vp}`);
    } catch (e) {
      failed += 1;
      console.log(`FAIL ${name}-${vp}: ${String(e).split("\n")[0]}`);
    }
    await context.close();
  }
}
await browser.close();
process.exit(failed ? 1 : 0);
