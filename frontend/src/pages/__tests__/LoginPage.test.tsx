import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { DemoInfo } from "../../api/types";
import { resetDemoInfo } from "../../lib/demo";
import { SessionProvider } from "../../lib/session";
import LoginPage from "../LoginPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); resetDemoInfo(); });

const demo: DemoInfo = {
  demo_mode: true,
  notice: { es: "Entorno de demostración con datos ficticios.", pt: "Ambiente de demonstração com dados fictícios." },
  password_hint: { es: "La contraseña está en la documentación de entrega del equipo.", pt: "A senha está na documentação de entrega." },
  users: [
    { username: "demo_cargo_claro_1", role: "customer", display_name: "Carmen R.", scenario: "cargo_claro", rank: 1, description: { es: "Cargo claro: reclámalo de punta a punta.", pt: "Cobrança clara." } },
    { username: "demo_cargo_claro_2", role: "customer", display_name: "Hugo O.", scenario: "cargo_claro", rank: 2, description: { es: "Cargo claro: reclámalo de punta a punta.", pt: "Cobrança clara." } },
    { username: "analista_1", role: "analyst", display_name: "Analista 1", scenario: null, rank: null, description: { es: "Agente de soporte: bandeja de tickets.", pt: "Agente de suporte." } },
    { username: "admin_1", role: "admin", display_name: "Administrador", scenario: null, rank: null, description: { es: "Administrador: SLO, métricas, costos y logs.", pt: "Administrador." } },
  ],
};

function at(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><SessionProvider><LoginPage /></SessionProvider></MemoryRouter>);
}

describe("LoginPage in demo mode", () => {
  it("shows the demo notice and the customer cards with their scenario, and says where the password is documented", async () => {
    vi.spyOn(api, "demoInfo").mockResolvedValue(demo);
    const { container } = at("/login");
    const card = await screen.findByRole("button", { name: "Cargo claro: demo_cargo_claro_1" });
    expect(container.querySelectorAll(".demo-group")).toHaveLength(1);              // un grupo por escenario, con sus dos usuarios
    expect(screen.getByRole("button", { name: "Cargo claro: demo_cargo_claro_2" })).toBeTruthy();
    expect(screen.getByText(/reclámalo de punta a punta/)).toBeTruthy();
    expect(screen.getByRole("note").textContent).toBe("Entorno de demostración con datos ficticios.");
    expect(screen.getByText(/documentación de entrega del equipo/)).toBeTruthy();
    expect(screen.queryByText(/Agente de soporte/)).toBeNull();                     // los agentes tienen su propio acceso
    fireEvent.click(card);
    expect((screen.getByLabelText("Usuario") as HTMLInputElement).value).toBe("demo_cargo_claro_1");
    expect((container.querySelector('input[type="password"]') as HTMLInputElement).value).toBe("");   // nunca se rellena la contraseña
  });

  it("shows agents and the admin on the agents login", async () => {
    vi.spyOn(api, "demoInfo").mockResolvedValue(demo);
    at("/login?perfil=agente");
    await screen.findByRole("button", { name: "Agente de soporte: analista_1" });
    expect(screen.getByRole("button", { name: "Administrador: admin_1" })).toBeTruthy();
    expect(screen.queryByText(/Cargo claro/)).toBeNull();
  });

  it("shows no notice and no cards when demo mode is off or the request fails", async () => {
    vi.spyOn(api, "demoInfo").mockRejectedValue(new Error("down"));
    at("/login");
    await screen.findByRole("button", { name: "Entrar" });
    await Promise.resolve();
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByText("Usuarios de demostración")).toBeNull();
  });
});
