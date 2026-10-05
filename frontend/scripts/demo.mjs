// Recorrido del video: deja el sistema listo para grabar los 3 recorridos sin pasos manuales (docs/demo-script.md).
//
//   DEMO_PASSWORD=… BASE_URL=https://localhost:8443 node scripts/demo.mjs check     # ¿está todo listo para grabar?
//   DEMO_PASSWORD=… BASE_URL=…                      node scripts/demo.mjs open      # abre 5 ventanas ya con sesión, para grabar a mano
//   DEMO_PASSWORD=… BASE_URL=…                      node scripts/demo.mjs record    # graba los 3 recorridos solo (demo-videos/*.webm)
//
// - La contraseña demo llega solo por entorno: nunca se teclea frente a la cámara ni queda en el repo.
// - No inventa datos: los mensajes del cliente se arman con un movimiento real de "Mis movimientos" de ese usuario.
// - Usuarios (se pueden cambiar con DEMO_CLARO, DEMO_AMBIGUO, DEMO_RIESGO): los `_2`, que la prueba de humo no toca.
// - BASE_URL por defecto: http://127.0.0.1:5173. Con el certificado local de prodlike se ignoran los errores de TLS.
import { chromium } from "@playwright/test";
import { mkdirSync, renameSync } from "node:fs";
import { join } from "node:path";

const BASE = (process.env.BASE_URL ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const PASSWORD = process.env.DEMO_PASSWORD ?? "";
const USERS = {
  claro: process.env.DEMO_CLARO ?? "demo_cargo_claro_2",
  ambiguo: process.env.DEMO_AMBIGUO ?? "demo_cargos_parecidos_2",
  riesgo: process.env.DEMO_RIESGO ?? "demo_fraude_alto_2",
  agente: "analista_1",
  admin: "admin_1",
};
const OUT = process.env.DEMO_OUT ?? "demo-videos";
const VIEWPORT = { width: 1440, height: 900 };
const TURN_TIMEOUT = 120_000;          // con un LLM real un turno puede tardar bastante
const mode = process.argv[2] ?? "check";
const pause = (page, ms = 1400) => page.waitForTimeout(ms);

if (!PASSWORD) { console.error("Falta DEMO_PASSWORD en el entorno."); process.exit(2); }

async function login(page, username, agent = false) {
  await page.goto(`${BASE}/login${agent ? "?perfil=agente" : ""}`);
  await page.locator('input[autocomplete="username"]').fill(username);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
}

const api = async (page, path) => (await page.request.get(`${BASE}${path}`)).json();
const idle = (page) => page.locator('.messages[aria-busy="false"]').waitFor({ timeout: TURN_TIMEOUT });

async function say(page, text) {
  const box = page.locator("#msg");
  await box.click();
  await box.pressSequentially(text, { delay: 35 });
  await pause(page, 500);
  await page.keyboard.press("Enter");
  await page.locator('.messages[aria-busy="true"]').waitFor({ timeout: 5000 }).catch(() => undefined);
  await idle(page);
  await pause(page);
}

/** Avanza la conversación con los botones que ofrezca el asistente hasta llegar a un resultado o a un traspaso. */
async function advance(page, { confirm = true } = {}) {
  for (let i = 0; i < 6; i += 1) {
    if (await page.locator(".result, .card.handoff").last().isVisible().catch(() => false)) {
      const last = page.locator(".messages > .msg.assistant").last();
      if (await last.locator(".result, .card.handoff").count()) return;
    }
    const next = [page.locator(".choice:enabled").first(), page.getByRole("button", { name: /Sí, es este|Sim, é esta/ }).and(page.locator(":enabled")),
      ...(confirm ? [page.getByRole("button", { name: "Confirmar", exact: true }).and(page.locator(":enabled"))] : [])];
    let clicked = false;
    for (const b of next) {
      if (await b.isVisible().catch(() => false)) {
        await pause(page, 1600);
        await b.click();
        await idle(page);
        await pause(page);
        clicked = true;
        break;
      }
    }
    if (!clicked) return;
  }
}

async function firstMovement(page) {
  const d = await api(page, "/api/me/transactions?lang=es");
  if (!d.transactions?.length) throw new Error("ese usuario no tiene movimientos en los últimos 30 días");
  return d.transactions[0];
}

// ---------------------------------------------------------------- recorridos
async function clearCharge(page) {
  await page.goto(`${BASE}/`);
  await pause(page, 2500);
  await page.getByRole("link", { name: "Tengo un reclamo" }).click();
  await login(page, USERS.claro);
  await page.locator(".bubble.assistant").first().waitFor();
  await pause(page, 2000);
  const tx = await firstMovement(page);
  await say(page, `No reconozco el cargo de ${tx.amount_label} del ${tx.date_label} en ${tx.label}`);
  await advance(page);
  await page.locator(".result.ok").waitFor({ timeout: TURN_TIMEOUT });
  const ref = (await page.locator(".result.ok code").innerText()).trim();
  await pause(page, 2500);
  await page.getByRole("button", { name: "No, gracias" }).click();
  await page.getByRole("heading", { name: "¿Te ayudé?" }).waitFor({ timeout: TURN_TIMEOUT });
  await pause(page);
  await page.getByRole("button", { name: /Sí, me ayudó/ }).click();
  await pause(page, 800);
  await page.getByRole("button", { name: "Enviar valoración" }).click();
  await pause(page, 1800);
  await page.getByRole("link", { name: "Reclamos" }).click();
  await page.locator(".case-cards").waitFor();
  await pause(page, 2500);
  await page.getByRole("link", { name: "Conversaciones" }).click();
  await page.locator(".conv-card").first().waitFor();
  await pause(page, 2500);
  return `reclamo ${ref}`;
}

async function ambiguous(page) {
  await login(page, USERS.ambiguo);
  await page.locator(".bubble.assistant").first().waitFor();
  await pause(page, 1500);
  // primero sin datos: el asistente pide uno (no muestra movimientos); después, solo el monto aproximado
  await say(page, "No reconozco un cargo en mi tarjeta");
  await pause(page, 2500);
  const tx = await firstMovement(page);
  await say(page, `Es uno de como ${tx.amount_label}`);
  const options = await page.locator(".choice").count();
  await pause(page, 2500);                       // que se vea la lista: el asistente pregunta cuál y no actúa todavía
  await advance(page);
  await pause(page, 2500);
  const ref = await page.locator(".result.ok code").last().innerText().catch(() => "");
  return `${options} candidatas${ref ? `, reclamo ${ref.trim()}` : ""}`;
}

async function highRisk(page) {
  await login(page, USERS.riesgo);
  await page.locator(".bubble.assistant").first().waitFor();
  await pause(page, 1500);
  const tx = await firstMovement(page);
  await say(page, `No reconozco el cargo de ${tx.amount_label} del ${tx.date_label}, yo no lo hice`);
  await advance(page, { confirm: false });        // riesgo alto: no se abre un reclamo automático, pasa a una persona
  let escalated = await page.locator(".card.handoff").last().isVisible().catch(() => false);
  if (!escalated) {
    console.log("   AVISO: en este entorno el cargo no escaló por riesgo alto; se pide una persona para seguir el recorrido.");
    await page.getByRole("button", { name: "Hablar con una persona" }).click();
    await page.locator(".card.handoff").last().waitFor({ timeout: TURN_TIMEOUT });
  }
  const ref = (await page.locator(".card.handoff code").last().innerText()).trim();
  await pause(page, 3000);
  return { ref, escalated };
}

async function agent(page, ref) {
  await page.goto(`${BASE}/`);
  await pause(page, 1200);
  await page.getByRole("link", { name: "Inicio de sesión de agentes de soporte" }).click();
  await login(page, USERS.agente, true);
  const row = page.locator(".ticket-row", { hasText: ref });
  await row.waitFor();
  const priority = (await row.locator(".pill").first().innerText()).trim();
  await pause(page, 2500);
  await row.click();
  await page.getByRole("heading", { name: "Hechos verificados" }).waitFor();
  await pause(page, 3000);
  await page.getByRole("heading", { name: "Línea de tiempo de trazas" }).scrollIntoViewIfNeeded();
  await pause(page, 3000);
  await page.getByRole("button", { name: "Tomar el ticket" }).scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: "Tomar el ticket" }).click();
  await pause(page);
  await page.getByLabel("Cambiar estado").selectOption("en_curso");
  await page.getByRole("button", { name: "Guardar" }).click();
  await pause(page);
  const note = page.getByLabel("Agregar una nota interna");
  await note.scrollIntoViewIfNeeded();
  await note.pressSequentially("Llamé al cliente y bloqueamos la tarjeta. Queda en revisión de fraude.", { delay: 25 });
  await page.getByRole("button", { name: "Agregar nota" }).click();
  await pause(page, 2500);
  return `ticket ${ref} · prioridad ${priority}`;
}

async function admin(page) {
  await login(page, USERS.admin, true);
  await page.locator(".slo").first().waitFor();
  await pause(page, 3500);
  for (const id of ["adm-out", "adm-ep", "adm-recent", "adm-logs", "adm-improve"]) {
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    await pause(page, 2200);
  }
  return `${await page.locator(".slo").count()} SLO`;
}

// ---------------------------------------------------------------- modos
const browser = await chromium.launch({ headless: mode !== "open" && process.env.HEADED !== "1" });
// el recorrido de la primera vez no aparece en la grabación
const context = async (extra = {}) => {
  const ctx = await browser.newContext({ viewport: VIEWPORT, locale: "es", ignoreHTTPSErrors: true, ...extra });
  await ctx.addInitScript(() => { try { localStorage.setItem("tour:off", "1"); } catch { /* sin almacenamiento */ } });
  return ctx;
};

async function check() {
  const problems = [];
  const ctx = await context();
  const page = await ctx.newPage();
  const ready = await api(page, "/api/ready").catch(() => null);
  console.log(`backend: ${ready?.status ?? "no responde"} · LLM: ${ready?.llm_provider ?? "?"}`);
  if (ready?.status !== "ready") problems.push("el backend no está listo (/api/ready)");
  const demo = await api(page, "/api/demo/info").catch(() => null);
  console.log(`modo demostración: ${demo?.demo_mode ? "encendido" : "apagado (el login no mostrará las tarjetas de usuarios)"}`);
  await ctx.close();
  for (const [key, user] of Object.entries(USERS)) {
    const c = await context();
    const p = await c.newPage();
    try {
      await login(p, user, key === "agente" || key === "admin");
      if (key === "agente" || key === "admin") { console.log(`ok    ${user}`); continue; }
      const cases = (await api(p, "/api/me/cases")).cases.length;
      const tx = (await api(p, "/api/me/transactions?lang=es")).transactions.length;
      console.log(`${cases === 0 && tx > 0 ? "ok   " : "FALTA"} ${user}: ${tx} movimientos, ${cases} reclamos`);
      if (cases > 0) problems.push(`${user} ya tiene ${cases} reclamo(s): limpiar la demo antes de grabar`);
      if (tx === 0) problems.push(`${user} no tiene movimientos recientes`);
    } catch {
      console.log(`FALTA ${user}: no pudo iniciar sesión`);
      problems.push(`${user} no pudo iniciar sesión (¿usuarios demo sembrados?, ¿DEMO_PASSWORD correcta?)`);
    } finally {
      await c.close();
    }
  }
  console.log(problems.length ? `\nNO está listo:\n- ${problems.join("\n- ")}\nVer "Preparación" en docs/demo-script.md.` : "\nLISTO para grabar.");
  return problems.length ? 1 : 0;
}

async function open() {
  const plan = [["claro", "/chat", false], ["ambiguo", "/chat", false], ["riesgo", "/chat", false], ["agente", "/agentes", true], ["admin", "/admin", true]];
  for (const [key, path, staff] of plan) {
    const page = await (await context({ viewport: null })).newPage();
    await login(page, USERS[key], staff);
    await page.goto(`${BASE}${path}`);
    console.log(`ventana lista: ${USERS[key]} en ${path}`);
  }
  console.log("\nCinco ventanas con sesión iniciada. Sigue el guion de docs/demo-script.md. Cierra el navegador para terminar.");
  await new Promise((resolve) => browser.on("disconnected", resolve));
  return 0;
}

async function record() {
  mkdirSync(OUT, { recursive: true });
  const take = async (name, fn) => {
    const ctx = await context({ recordVideo: { dir: OUT, size: VIEWPORT } });
    const page = await ctx.newPage();
    let result;
    try {
      result = await fn(page);
      console.log(`ok    ${name}: ${typeof result === "string" ? result : JSON.stringify(result)}`);
    } finally {
      const video = page.video();
      await ctx.close();
      if (video) renameSync(await video.path(), join(OUT, `${name}.webm`));
    }
    return result;
  };
  await take("1-cargo-claro", clearCharge);
  await take("2-caso-ambiguo", ambiguous);
  const risk = await take("3a-riesgo-alto-cliente", highRisk);
  await take("3b-agente-atiende-el-ticket", (page) => agent(page, risk.ref));
  await take("3c-admin-ve-los-slo", admin);
  console.log(`\nVideos en ${OUT}/ (webm, 1440×900).`);
  return 0;
}

let code = 1;
try {
  code = await ({ check, open, record }[mode] ?? (() => { console.error("uso: demo.mjs check | open | record"); return 2; }))();
} catch (e) {
  console.error(`FALLO: ${String(e).split("\n")[0]}`);
} finally {
  await browser.close().catch(() => undefined);
}
process.exit(code);
