// Las tres propuestas en evaluación (blanco, negro y azul): axe (WCAG 2.1 A y AA) en la landing y en el chat de cada una.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { claimMessage, login, say } from "./helpers";

async function audit(page: Page, name: string) {
  await page.waitForTimeout(900);
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${name}: ${v.id} (${v.nodes.length}) ${v.nodes.map((n) => n.target).slice(0, 3).join(" | ")}`)).toEqual([]);
}

for (const look of ["1", "2", "3"]) {
  test(`propuesta ${look}: landing y chat sin violaciones serias`, async ({ page }) => {
    await page.goto(`/preview/${look}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 80)); } });
    await audit(page, `landing ${look}`);
    await login(page, "demo_cargos_parecidos_2");
    await page.goto(`/preview/${look}/chat`);
    await expect(page.locator(".messages > .msg.assistant").first()).toBeVisible();
    await say(page, "No reconozco un cargo");
    await say(page, await claimMessage(page));
    await audit(page, `chat ${look}`);
  });
}
