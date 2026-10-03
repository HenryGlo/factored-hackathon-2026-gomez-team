// Auditoría responsive: recorre cada pantalla en anchos de celular, tablet y escritorio y reporta lo que se rompe.
//
//   DEMO_PASSWORD=… BASE_URL=http://127.0.0.1:5173 node scripts/responsive-audit.mjs [carpeta de capturas]
//
// Por cada pantalla y ancho: desborde horizontal de la página (y qué elemento lo causa), objetivos de menos de 44 px en
// pantallas táctiles (24 px con mouse) y texto cortado. Deja una captura de cada combinación. Termina con código 1 si encontró problemas.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:5173";
const PASSWORD = process.env.DEMO_PASSWORD ?? "";
const out = process.argv[2] ?? "responsive";
mkdirSync(out, { recursive: true });

const WIDTHS = [
  ["phone-360", 360, 740, true], ["phone-390", 390, 844, true], ["tablet-768", 768, 1024, true],
  ["tablet-820", 820, 1180, true], ["tablet-1024", 1024, 768, true], ["laptop-1280", 1280, 800, false],
];
const SCREENS = [
  ["landing", null, "/"], ["login", null, "/login"], ["login-agentes", null, "/login?perfil=agente"],
  ["chat", "demo_cargos_parecidos_2", "/chat"], ["conversaciones", "demo_cargos_parecidos_2", "/conversaciones"],
  ["movimientos", "demo_cargos_parecidos_2", "/movimientos"], ["reclamos", "demo_cargos_parecidos_2", "/reclamos"],
  ["tickets", "analista_1", "/agentes"], ["ticket", "analista_1", "TICKET"], ["admin", "admin_1", "/admin"], ["sistema", null, "/sistema"],
];

async function login(page, user) {
  for (let attempt = 0; ; attempt += 1) {
    await page.goto(`${BASE}/login${user.startsWith("demo_") ? "" : "?perfil=agente"}`);
    await page.locator('input[autocomplete="username"]').fill(user);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    try { await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 8000 }); return; } catch (e) {
      if (attempt >= 3) throw e;
      await page.waitForTimeout(20000);
    }
  }
}

/** Lo que se rompe en la página actual (se mide en el navegador). */
const inspect = (minTarget) => {
  const vw = document.documentElement.clientWidth;
  const issues = [];
  if (document.documentElement.scrollWidth > vw + 1) {
    const culprits = [...document.querySelectorAll("body *")].filter((el) => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.right <= vw + 1) return false;
      // un elemento dentro de algo que ya se desplaza por su cuenta no rompe la página
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const o = getComputedStyle(p).overflowX;
        if (o === "auto" || o === "scroll" || o === "hidden" || o === "clip") return false;
      }
      return true;
    }).slice(0, 4).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join(".")} (→${Math.round(el.getBoundingClientRect().right)}px)`);
    issues.push(`desborde horizontal: página ${document.documentElement.scrollWidth}px > ${vw}px ${culprits.join(", ")}`);
  }
  const small = [...document.querySelectorAll("a, button, select, input, textarea, [role=button]")].filter((el) => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || cs.visibility === "hidden" || el.closest(".sr-only, .skip")) return false;
    if (el.tagName === "A" && cs.display === "inline" && el.closest("p, li, td, dd")) return false;   // enlace dentro de un texto
    if (el.type === "checkbox") return false;
    return r.height < minTarget || r.width < minTarget;
  }).map((el) => `${el.tagName.toLowerCase()}${el.className ? "." + String(el.className).split(" ").join(".") : ""} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 24)}" ${Math.round(el.getBoundingClientRect().width)}×${Math.round(el.getBoundingClientRect().height)}`);
  if (small.length) issues.push(`objetivos de menos de ${minTarget} px: ${[...new Set(small)].slice(0, 6).join(" | ")}`);
  const clipped = [...document.querySelectorAll("h1, h2, h3, .btn, .nav, .pill, .chip, .option, .tx-label, .tx-amount")].filter((el) => {
    const cs = getComputedStyle(el);
    return el.scrollWidth > el.clientWidth + 1 && cs.overflow !== "visible" && cs.textOverflow !== "ellipsis";
  }).map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join(".")} "${el.textContent.trim().slice(0, 24)}"`);
  if (clipped.length) issues.push(`texto cortado: ${clipped.slice(0, 4).join(" | ")}`);
  return issues;
};

const browser = await chromium.launch();
let problems = 0;
for (const [name, user, path] of SCREENS) {
  for (const [label, width, height, touch] of WIDTHS) {
    const ctx = await browser.newContext({ viewport: { width, height }, hasTouch: touch, isMobile: touch, locale: "es" });
    const page = await ctx.newPage();
    try {
      if (user) await login(page, user);
      let target = path;
      if (path === "TICKET") {
        await page.goto(`${BASE}/agentes`);
        await page.locator(".ticket-row").first().click();
        await page.locator(".ticket-header").waitFor();
        target = null;
      }
      if (target) await page.goto(`${BASE}${target}`);
      await page.waitForLoadState("networkidle");
      await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } window.scrollTo(0, 0); });
      await page.waitForTimeout(700);
      const issues = await page.evaluate(inspect, touch ? 44 : 24);       // 44 px en pantallas táctiles; 24 px con mouse (WCAG 2.2)
      await page.screenshot({ path: join(out, `${name}-${label}.png`), fullPage: true });
      if (issues.length) { problems += 1; console.log(`✘ ${name} @ ${label}\n   - ${issues.join("\n   - ")}`); }
      else console.log(`✓ ${name} @ ${label}`);
    } catch (e) {
      problems += 1;
      console.log(`✘ ${name} @ ${label}: ${String(e).split("\n")[0]}`);
    }
    await ctx.close();
  }
}
await browser.close();
console.log(problems ? `\n${problems} combinaciones con problemas` : "\nSin problemas");
process.exit(problems ? 1 : 0);
