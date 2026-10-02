// Capturas de todas las pantallas en escritorio (1440 px) y celular (390 px), para la auditoría y los PR.
//
//   DEMO_PASSWORD=… node scripts/screenshots.mjs [carpeta de salida, por defecto ../docs/screenshots] [pantalla…]
//
// Variables: BASE_URL (por defecto http://127.0.0.1:5183). La contraseña demo solo llega por entorno.
// Necesita un backend con LLM_PROVIDER=fake y los usuarios demo (scripts/seed_demo_users.py), sobre una base *_test.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:5183";
const PASSWORD = process.env.DEMO_PASSWORD;
const [out = "../docs/screenshots", ...only] = process.argv.slice(2);
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };

async function login(page, username) {
  if (!PASSWORD) throw new Error("falta DEMO_PASSWORD en el entorno");
  for (let attempt = 0; ; attempt += 1) {
    await page.goto(`${BASE}/login`);
    await page.locator('input[autocomplete="username"]').fill(username);
    await page.locator('input[autocomplete="current-password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    try {
      await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 8000 });
      return;
    } catch (e) {
      if (attempt >= 3) throw e;
      await page.waitForTimeout(20000);          // límite de logins por IP (429): esperar y reintentar
    }
  }
}

/** Un cliente pide una persona: deja un ticket en la bandeja (una sola vez por corrida). */
let seeded = false;
async function seedTicket(page) {
  if (seeded) return;
  seeded = true;
  await login(page, "demo_pendiente_1");
  await page.locator(".bubble.assistant").nth(1).waitFor();
  await page.locator("textarea").fill("No reconozco un cobro, yo no hice esa compra");
  await page.keyboard.press("Enter");
  await page.locator('.messages[aria-busy="false"]').waitFor();
  await page.getByRole("button", { name: /Hablar con una persona|Falar com uma pessoa/ }).click();
  await page.locator(".card.handoff").waitFor();
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
  // modo voz con el proveedor simulado en el navegador (el backend de pruebas tiene VOICE_ENABLED=false): solo para la captura
  "chat-voz": {
    user: "demo_cargo_claro_2",
    go: async (page) => {
      await page.route("**/api/voice/config", (r) => r.fulfill({ json: { enabled: true, reason: null, max_audio_bytes: 2000000, max_tts_chars: 700, audio_types: ["audio/webm"] } }));
      await page.route("**/api/voice/stt*", (r) => r.fulfill({ json: { text: "No reconozco un cobro de la farmacia", language_code: "es", seconds: 2.1, truncated: false } }));
      await page.goto(`${BASE}/chat`);
      await page.locator(".bubble.assistant").nth(1).waitFor();
      await page.locator(".chip", { hasText: /voz/ }).click();
      await page.getByRole("button", { name: /Permitir/ }).click();
      await page.locator(".mic.on").waitFor();
      await page.waitForTimeout(900);
      await page.locator(".mic.on").dispatchEvent("pointerdown");
      await page.locator("#voice-text").waitFor();
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
  tickets: { user: "analista_1", setup: seedTicket, go: async (page) => { await page.goto(`${BASE}/agentes`); await page.locator(".ticket-row").first().waitFor(); } },
  ticket: {
    user: "analista_1",
    setup: seedTicket,
    go: async (page) => {
      await page.goto(`${BASE}/agentes`);
      await page.locator(".ticket-row").last().click();
      await page.locator(".trace-steps, .events").first().waitFor();
    },
  },
  admin: { user: "admin_1", go: async (page) => { await page.goto(`${BASE}/admin`); await page.locator(".slo").first().waitFor(); await page.locator(".logs").waitFor(); } },
  "login-agentes": { user: null, go: async (page) => { await page.goto(`${BASE}/login?perfil=agente`); } },
};

mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] });
let failed = 0;
for (const [name, screen] of Object.entries(SCREENS)) {
  if (only.length && !only.includes(name)) continue;
  for (const [vp, viewport] of Object.entries(VIEWPORTS)) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: vp === "mobile" ? 2 : 1, isMobile: vp === "mobile", locale: "es" });
    const page = await context.newPage();
    try {
      if (screen.setup) {
        const prep = await browser.newContext({ viewport, locale: "es" });
        await screen.setup(await prep.newPage());
        await prep.close();
      }
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
