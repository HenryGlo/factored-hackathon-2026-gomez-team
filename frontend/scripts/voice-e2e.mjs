// Prueba de punta a punta del modo voz manos libres, contra un entorno con voz real (prodlike: STT y TTS de ElevenLabs).
//
//   DEMO_PASSWORD=… BASE_URL=https://localhost:8443 node scripts/voice-e2e.mjs [carpeta de salida]
//
// El micrófono es simulado: se reemplaza getUserMedia por un flujo de audio al que la prueba le "habla" frases grabadas
// con la voz del sistema (say de macOS). Todo lo demás es real: VAD en el navegador, transcripción, turnos con el LLM del
// entorno, respuesta hablada. Recorrido: "no reconozco un cargo" → "ver mis últimos movimientos" → "el de <comercio>" →
// "sí, es ese" → botón Confirmar (la acción solo se confirma con el botón). Deja capturas de cada paso y un video (webm) en la carpeta de salida.
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, renameSync } from "node:fs";
import { join } from "node:path";

const BASE = (process.env.BASE_URL ?? "https://localhost:8443").replace(/\/$/, "");
const USER = process.env.VOICE_USER ?? "demo_revertido_2";
const MERCHANT = process.env.VOICE_MERCHANT ?? "servicios públicos";
const out = process.argv[2] ?? "voice-e2e";
mkdirSync(out, { recursive: true });
const TURN = 150_000;

function phrase(name, text) {
  const aiff = join(out, `${name}.aiff`);
  const wav = join(out, `${name}.wav`);
  execFileSync("say", ["-v", "Paulina", "-o", aiff, text]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", aiff, "-ar", "16000", "-ac", "1", wav]);
  return readFileSync(wav).toString("base64");
}
const phrases = {
  sinDatos: phrase("1-sin-datos", "No reconozco un cargo"),
  movimientos: phrase("2-movimientos", "Ver mis últimos movimientos"),
  comercio: phrase("3-comercio", `El de ${MERCHANT}`),
  si: phrase("4-si", "Sí, es ese"),
};

const browser = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1280, height: 800 }, locale: "es", recordVideo: { dir: out, size: { width: 1280, height: 800 } } });
// micrófono simulado: un MediaStream al que window.__say() le reproduce una frase
await context.addInitScript(() => {
  let ctx, dest;
  const ensure = () => { ctx ??= new AudioContext(); dest ??= ctx.createMediaStreamDestination(); return { ctx, dest }; };
  navigator.mediaDevices.getUserMedia = async () => ensure().dest.stream;
  window.__say = async (b64) => {
    const { ctx: c, dest: d } = ensure();
    await c.resume();
    const bytes = Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
    const buffer = await c.decodeAudioData(bytes.buffer);
    const src = c.createBufferSource();
    src.buffer = buffer;
    src.connect(d);
    src.start();
    await new Promise((r) => { src.onended = r; });
  };
});
const page = await context.newPage();
const shot = (n) => page.screenshot({ path: join(out, `${n}.png`) });
const status = page.locator(".vm-status");
const listening = () => page.waitForFunction(() => /Te escucho|Banky está hablando/.test(document.querySelector(".vm-status")?.textContent ?? ""), null, { timeout: TURN });
const say = async (b64) => { await listening(); await page.evaluate((b) => window.__say(b), b64); };

let ok = false;
try {
  await page.goto(`${BASE}/login`);
  await page.locator('input[autocomplete="username"]').fill(USER);
  await page.locator('input[type="password"]').fill(process.env.DEMO_PASSWORD ?? "");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/\/chat/);
  await page.locator(".bubble.assistant").first().waitFor();
  await page.getByRole("button", { name: "Modo voz" }).click();
  await status.filter({ hasText: /Te escucho/ }).waitFor({ timeout: 60_000 });
  await shot("1-escuchando");

  await say(phrases.sinDatos);
  await page.locator(".vm-heard", { hasText: /reconozco/i }).waitFor({ timeout: TURN });
  await page.locator(".vm-answer", { hasText: /dato|monto|comercio/i }).waitFor({ timeout: TURN });
  await page.waitForTimeout(1500);
  await shot("2-pide-un-dato");

  await say(phrases.movimientos);
  await page.locator(".vm-answer", { hasText: /últimos movimientos/i }).waitFor({ timeout: TURN });
  await page.waitForTimeout(1500);
  await shot("3-movimientos");

  await say(phrases.comercio);
  // el asistente muestra el cargo y pregunta si es ese: se responde por voz (confirmar el MOVIMIENTO no es una acción)
  await page.locator(".vm-answer", { hasText: /es este el movimiento/i }).waitFor({ timeout: TURN });
  await page.waitForTimeout(1500);
  await shot("4-es-este");
  await say(phrases.si);
  await page.locator(".vm-confirm-btn").waitFor({ timeout: TURN });
  await page.waitForTimeout(1500);
  await shot("5-confirmar");
  await page.locator(".vm-confirm-btn").click();
  await page.locator(".vm-answer", { hasText: /RCL-/ }).waitFor({ timeout: TURN });
  await page.waitForTimeout(2500);
  await shot("6-reclamo-registrado");
  console.log(`OK · ${(await page.locator(".vm-answer").innerText()).slice(0, 160)}`);
  ok = true;
} catch (e) {
  await shot("fallo").catch(() => undefined);
  console.log(`FALLO: ${String(e).split("\n")[0]}`);
  console.log(`estado: ${await status.innerText().catch(() => "?")}`);
  console.log(`respuesta: ${await page.locator(".vm-answer").innerText().catch(() => "?")}`);
} finally {
  const video = page.video();
  await context.close();
  if (video) renameSync(await video.path(), join(out, "modo-voz.webm"));
  await browser.close();
}
process.exit(ok ? 0 : 1);
