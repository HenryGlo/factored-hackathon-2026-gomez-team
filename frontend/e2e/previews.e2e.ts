// Las tres direcciones visuales en evaluación: contraste AA y demás reglas de axe en la landing y en el chat de cada una.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers";

async function audit(page: Page, name: string) {
  await page.waitForTimeout(900);          // deja terminar la entrada (opacidad) antes de medir el contraste
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${name}: ${v.id} (${v.nodes.length}) ${v.nodes.map((n) => n.target).slice(0, 3).join(" | ")}`)).toEqual([]);
}

for (const theme of ["a", "b", "c"]) {
  test(`dirección ${theme.toUpperCase()}: landing y chat sin violaciones serias`, async ({ page }) => {
    await page.goto(`/preview/${theme}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await audit(page, `landing ${theme}`);
    await login(page, "demo_cargos_parecidos_2");
    await page.goto(`/preview/${theme}/chat`);
    await expect(page.locator(".messages > .msg.assistant").nth(1)).toBeVisible();
    await page.getByLabel("Escribe tu mensaje…").fill("Tengo un cobro que no reconozco");
    await page.keyboard.press("Enter");
    await expect(page.locator('.messages[aria-busy="false"] .choice').first()).toBeVisible();
    await audit(page, `chat ${theme}`);
  });
}
