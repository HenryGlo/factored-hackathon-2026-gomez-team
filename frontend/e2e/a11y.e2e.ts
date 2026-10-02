// Accesibilidad automática (axe, WCAG 2.1 A y AA) de cada pantalla, en escritorio y celular, y foco visible con teclado.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers";

async function audit(page: Page, name: string) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${name}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target}`)).toEqual([]);
}

test("pantallas públicas sin violaciones serias", async ({ page }) => {
  await page.goto("/");
  await audit(page, "landing");
  await page.goto("/login");
  await audit(page, "login");
});

test("pantallas del cliente sin violaciones serias", async ({ page }) => {
  await login(page, "demo_cargos_parecidos_2");
  await expect(page.locator(".messages > .msg.assistant").nth(1)).toBeVisible();
  await audit(page, "chat");
  for (const path of ["/conversaciones", "/movimientos", "/reclamos"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await audit(page, path);
  }
});

test("portal de agentes y panel admin sin violaciones serias", async ({ page }) => {
  await login(page, "admin_1", true);
  await expect(page.locator(".slo").first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  await audit(page, "admin");
  await page.goto("/agentes");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await audit(page, "agentes");
});

test("teclado: el enlace para saltar al contenido y el foco visible", async ({ page, isMobile }) => {
  test.skip(isMobile, "teclado físico: solo escritorio");
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Saltar al contenido" })).toBeFocused();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle);
  expect(outline).toBe("solid");
});
