// Los tres recorridos del producto, de punta a punta contra el backend real (LLM falso).
import { expect, test } from "@playwright/test";
import { claimMessage, login, logout, say } from "./helpers";

test.describe.configure({ mode: "serial" });

let claimRef = "";
let ticketRef = "";

test("cliente con un cargo claro: de la landing al reclamo verificado, con historial y valoración", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("BankyFicticious");
  await page.getByRole("link", { name: "Tengo un reclamo" }).click();
  await expect(page).toHaveURL(/\/login/);                                  // sin sesión, el chat pasa por el login
  await page.getByRole("textbox", { name: "Usuario" }).fill("demo_cargo_claro_2");
  await page.locator('input[type="password"]').fill(process.env.DEMO_PASSWORD ?? "");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/chat/);

  // una sola bienvenida (Banky se presenta y dice qué puede hacer); con la voz apagada no hay botón de voz ni aviso
  await expect(page.locator(".messages > .msg.assistant")).toHaveCount(1);
  await expect(page.locator(".bubble.welcome")).toContainText("¡Hola! Soy Banky, tu asistente.");
  await expect(page.getByText(/Hablar por voz/)).toHaveCount(0);

  // sin monto, comercio ni fecha el asistente NO busca: pide un dato y no muestra movimientos
  await say(page, "No reconozco un cargo");
  await expect(page.locator(".clarify.need-detail")).toBeVisible();
  await expect(page.locator(".choice, .tx-card")).toHaveCount(0);
  // un comercio que no está en sus movimientos: lo dice, con lo que buscó, y ofrece opciones
  await say(page, "Es un cargo de Facebook");
  await expect(page.locator(".clarify.no-match")).toContainText("Facebook");
  await expect(page.getByRole("button", { name: /Hablar con una persona/ }).last()).toBeEnabled();
  // con un dato real, encuentra el movimiento
  await say(page, await claimMessage(page));
  const first = page.locator(".choice").first();
  if (await first.isVisible()) await first.click();                           // varios candidatos: elige el primero
  await page.getByRole("button", { name: "Sí, es este" }).click();

  // la acción se confirma SIEMPRE con el botón de la tarjeta
  const confirm = page.getByRole("button", { name: "Confirmar", exact: true });
  await expect(page.getByText(/No es una devolución/).first()).toBeVisible();
  await confirm.click();

  const result = page.locator(".result.ok");
  await expect(result).toContainText("Verificado");
  claimRef = (await result.locator("code").innerText()).trim();
  expect(claimRef).toMatch(/^RCL-[0-9A-F]{6}$/);
  await expect(page.locator(".chat-id .banky")).toHaveAttribute("data-state", "happy");

  await page.getByRole("button", { name: "No, gracias" }).click();
  await expect(page.getByRole("heading", { name: "¿Te ayudé?" })).toBeVisible();
  await page.getByRole("button", { name: /Sí, me ayudó/ }).click();
  await page.getByRole("button", { name: "Enviar valoración" }).click();
  await expect(page.getByText(/quedó registrada/)).toBeVisible();

  await page.getByRole("link", { name: "Reclamos" }).click();
  await expect(page.locator(".case-cards")).toContainText(claimRef);
  await page.getByRole("link", { name: "Conversaciones" }).click();
  await page.locator(".conv-card", { hasText: claimRef }).click();
  await expect(page.getByText("Conversación en solo lectura.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continuar sobre este tema" })).toBeEnabled();
});

test("agente que atiende un ticket: lo toma, cambia el estado y deja una nota", async ({ page }) => {
  // un cliente pide una persona: eso crea el ticket
  await login(page, "demo_pendiente_1");
  await expect(page.locator(".messages > .msg.assistant").first()).toBeVisible();
  await page.getByRole("button", { name: "Hablar con una persona" }).click();
  const notice = page.locator(".card.handoff");
  await expect(notice).toBeVisible();
  ticketRef = (await notice.locator("code").innerText()).trim();
  expect(ticketRef).toMatch(/^ATN-/);
  await logout(page);

  await page.goto("/");
  await page.getByRole("link", { name: "Inicio de sesión de agentes de soporte" }).click();
  await expect(page.getByRole("heading", { name: "Acceso de agentes de soporte" })).toBeVisible();
  await page.getByRole("textbox", { name: "Usuario" }).fill("analista_1");
  await page.locator('input[type="password"]').fill(process.env.DEMO_PASSWORD ?? "");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/agentes$/);

  await page.locator(".ticket-row", { hasText: ticketRef }).click();
  await expect(page.getByRole("heading", { name: "Lo que dice el cliente" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hechos verificados" })).toBeVisible();
  await expect(page.locator(".trace-steps li").first()).toBeVisible();

  await page.getByRole("button", { name: "Tomar el ticket" }).click();
  await expect(page.locator(".ticket-actions")).toContainText("analista_1");
  await page.getByLabel("Cambiar estado").selectOption("en_curso");
  await page.getByRole("button", { name: "Guardar" }).click();
  await expect(page.locator(".ticket-header .conv-meta")).toContainText("En curso");
  await page.getByLabel("Agregar una nota interna").fill("Contacté al cliente por teléfono.");
  await page.getByRole("button", { name: "Agregar nota" }).click();
  await expect(page.locator(".events")).toContainText("Contacté al cliente por teléfono.");
  await expect(page.locator(".events li")).toHaveCount(3);                  // asignación, estado y nota: todo auditado

  await page.getByRole("link", { name: /Volver a la bandeja/ }).click();
  await page.getByLabel("Asignado").selectOption("me");
  await expect(page.locator(".ticket-row", { hasText: ticketRef })).toBeVisible();
});

test("admin que revisa los SLO, los resultados y los logs", async ({ page }) => {
  await login(page, "admin_1", true);
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.locator(".slo")).toHaveCount(3);
  for (const name of ["Latencia del turno", "Primera respuesta humana", "Disponibilidad"]) await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.locator(".slo").first()).toContainText(/Cumple|No cumple/);
  await expect(page.locator(".slo").first()).toContainText("Presupuesto de error consumido");
  await expect(page.getByRole("heading", { name: "¿Cómo terminan las conversaciones?" })).toBeVisible();
  await expect(page.locator(".bars").first()).toContainText(/\d+\/\d+/);     // resultados con n/N
  await expect(page.getByRole("heading", { name: "¿Cuánto gastamos hoy frente al presupuesto?" })).toBeVisible();

  await page.getByLabel("Ruta").fill("/api/tickets");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(page.locator(".logs tbody tr").first()).toContainText("/api/tickets");
  await expect(page.getByRole("link", { name: "Ver los PR propuestos en GitHub" })).toHaveAttribute("href", /github\.com/);

  await page.getByRole("link", { name: "Tickets" }).click();                 // el admin también entra a la bandeja
  await expect(page.getByRole("heading", { name: "Bandeja de tickets" })).toBeVisible();
});
