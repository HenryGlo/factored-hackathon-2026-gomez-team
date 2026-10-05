import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { SessionProvider } from "../../lib/session";
import LandingPage from "../LandingPage";

afterEach(() => { cleanup(); localStorage.clear(); });

function renderLanding() {
  return render(<MemoryRouter><SessionProvider><LandingPage /></SessionProvider></MemoryRouter>);
}

describe("LandingPage", () => {
  it("has one h1, the primary action to the chat and the secondary action to the agents login", () => {
    renderLanding();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Tengo un reclamo" }).getAttribute("href")).toBe("/chat");
    expect(screen.getByRole("link", { name: "Inicio de sesión de agentes de soporte" }).getAttribute("href")).toBe("/login?perfil=agente");
  });

  it("says what the assistant cannot do and that the data is fictitious", () => {
    renderLanding();
    expect(screen.getByText(/Aprobar devoluciones ni decidir el resultado/)).toBeTruthy();
    expect(screen.getByText(/Pasarte con una persona/)).toBeTruthy();
    expect(screen.getByRole("note").textContent).toMatch(/datos sintéticos/);
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(3 + 5 + 3);
  });

  it("switches to Portuguese and sets the document language", () => {
    renderLanding();
    fireEvent.click(screen.getByRole("button", { name: /Português/ }));
    expect(screen.getByRole("link", { name: "Tenho uma reclamação" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("pt-BR");
    expect(screen.getByRole("button", { name: /Português/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("switches to English and formats the document language as en-US", () => {
    renderLanding();
    fireEvent.click(screen.getByRole("button", { name: /English/ }));
    expect(screen.getByRole("link", { name: "I have a dispute" }).getAttribute("href")).toBe("/chat");
    expect(screen.getByRole("link", { name: "Support agent sign-in" })).toBeTruthy();
    expect(document.documentElement.lang).toBe("en-US");
  });
});
