// Lighthouse de la landing y del chat (con sesión iniciada) sobre el build de producción.
//
//   npm run build && VITE_API_PROXY=http://127.0.0.1:8000 npx vite preview --port 4173 &   # backend con LLM_PROVIDER=fake
//   DEMO_PASSWORD=… BASE_URL=http://127.0.0.1:4173 node scripts/lighthouse.mjs [carpeta de salida]
//
// Inicia sesión como cliente demo en un perfil temporal de Chrome (Playwright) y deja la cookie de sesión guardada en ese
// perfil; Lighthouse abre después su propio Chrome sobre el mismo perfil, sin borrar el almacenamiento, así el chat se mide
// con la sesión abierta. Imprime los puntajes en celular y escritorio, con la ruta realmente medida.
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:4173";
const out = process.argv[2] ?? "lighthouse";
mkdirSync(out, { recursive: true });
const profile = mkdtempSync(join(tmpdir(), "lh-profile-"));

const ctx = await chromium.launchPersistentContext(profile, { channel: "chrome", headless: true });
const page = ctx.pages()[0] ?? (await ctx.newPage());
await page.goto(`${BASE}/login`);
await page.locator('input[autocomplete="username"]').fill(process.env.DEMO_USER ?? "demo_cargos_parecidos_2");
await page.locator('input[type="password"]').fill(process.env.DEMO_PASSWORD ?? "");
await page.locator('button[type="submit"]').click();
await page.waitForURL(/\/chat/);
await page.locator(".bubble.assistant").first().waitFor();
// las cookies de sesión no se guardan al cerrar: se reescriben con vencimiento para que queden en el perfil
const cookies = (await ctx.cookies()).map((c) => ({ ...c, expires: Math.floor(Date.now() / 1000) + 3600 }));
await ctx.addCookies(cookies);
await ctx.close();

const rows = [];
for (const [name, path] of [["landing", "/"], ["chat", "/chat"]]) {
  for (const mode of ["mobile", "desktop"]) {
    const file = join(out, `${name}-${mode}.json`);
    execFileSync("npx", ["-y", "lighthouse", `${BASE}${path}`, "--only-categories=performance,accessibility,best-practices", ...(mode === "desktop" ? ["--preset=desktop"] : []),
      "--disable-storage-reset", `--chrome-flags=--headless=new --user-data-dir=${profile}`, "--output=json", `--output-path=${file}`, "--quiet"],
      { stdio: ["ignore", "ignore", "inherit"], timeout: 180_000 });
    const r = JSON.parse(readFileSync(file, "utf8"));
    const s = (k) => Math.round(r.categories[k].score * 100);
    rows.push(`| ${name} | ${mode} | ${s("performance")} | ${s("accessibility")} | ${s("best-practices")} | ${new URL(r.finalDisplayedUrl).pathname} |`);
  }
}
rmSync(profile, { recursive: true, force: true });
console.log("| Pantalla | Modo | Rendimiento | Accesibilidad | Buenas prácticas | Ruta medida |\n|---|---|---|---|---|---|\n" + rows.join("\n"));
