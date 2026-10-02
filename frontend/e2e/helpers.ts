import { expect, type Page } from "@playwright/test";

export const PASSWORD = process.env.DEMO_PASSWORD ?? "";

export async function login(page: Page, username: string, agent = false) {
  expect(PASSWORD, "DEMO_PASSWORD debe venir por entorno").not.toBe("");
  await page.goto(agent ? "/login?perfil=agente" : "/login");
  await page.getByRole("textbox", { name: "Usuario" }).fill(username);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
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
