import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../lib/session";
import { preferredTheme } from "../../lib/theme";
import ThemeToggle from "../ThemeToggle";

function systemPrefersDark(dark: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: dark && query.includes("dark"), media: query }));
}

beforeEach(() => { localStorage.clear(); delete document.documentElement.dataset.theme; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("ThemeToggle", () => {
  it("switches to dark and back, sets data-theme on <html> and remembers the choice", () => {
    systemPrefersDark(false);
    render(<SessionProvider><ThemeToggle /></SessionProvider>);
    expect(document.documentElement.dataset.theme).toBe("light");
    fireEvent.click(screen.getByRole("button", { name: "Cambiar a modo oscuro" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Cambiar a modo claro" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("follows the system preference until the user chooses", () => {
    systemPrefersDark(true);
    expect(preferredTheme()).toBe("dark");
    render(<SessionProvider><ThemeToggle /></SessionProvider>);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBeNull();
    localStorage.setItem("theme", "light");
    expect(preferredTheme()).toBe("light");
  });
});
