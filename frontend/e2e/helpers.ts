import { expect, type Page } from "@playwright/test";

export const PASSWORD = process.env.DEMO_PASSWORD ?? "";

/** Inicia sesión. Si el límite de logins por IP responde 429 (muchas pruebas seguidas), espera y reintenta. */
export async function login(page: Page, username: string, agent = false) {
  expect(PASSWORD, "DEMO_PASSWORD debe venir por entorno").not.toBe("");
  await page.addInitScript(() => { try { localStorage.setItem("tour:off", "1"); } catch { /* sin almacenamiento */ } });      // el recorrido de la primera vez no aparece en las pruebas
  for (let attempt = 0; ; attempt += 1) {
    await page.goto(agent ? "/login?perfil=agente" : "/login");
    await page.getByRole("textbox", { name: "Usuario" }).fill(username);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.getByRole("button", { name: "Entrar" }).click();
    try {
      await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 8000 });
      return;
    } catch (e) {
      if (attempt >= 2) throw e;
      await page.waitForTimeout(25_000);
    }
  }
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: "Salir" }).click();
  await page.waitForURL(/\/login/);
}

/** Envía un mensaje en el chat y espera a que termine el turno. */
export async function say(page: Page, text: string) {
  const before = await page.locator(".messages > .msg.assistant").count();
  await page.getByLabel("Escribe tu mensaje…").fill(text);
  await page.getByRole("button", { name: "Enviar" }).click();
  await expect(page.locator(".messages")).toHaveAttribute("aria-busy", "false");      // el indicador de espera ya no está
  await expect(page.locator(".messages > .msg.assistant")).toHaveCount(before + 1);
}

/** Mensaje de reclamo con un dato real del usuario (monto, fecha y comercio de su movimiento más reciente). */
export async function claimMessage(page: Page): Promise<string> {
  const d = await (await page.request.get("/api/me/transactions?lang=es")).json();
  const tx = d.transactions[0];
  return `No reconozco el cargo de ${tx.amount_label} del ${tx.date_label} en ${tx.label}`;
}
