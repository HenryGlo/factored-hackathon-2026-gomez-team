// Tema claro u oscuro. La elección se guarda en este navegador; sin elección, manda la preferencia del sistema.
// El tema vive en <html data-theme="…"> y los colores salen de styles/tokens.css. public/theme-init.js aplica la misma
// regla antes del primer pintado.
import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "theme";
const THEME_COLOR: Record<Theme, string> = { light: "#f6eedf", dark: "#0a211a" };   // --paper de cada tema

export function preferredTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark") return v;
  } catch {
    /* sin almacenamiento: se usa la preferencia del sistema */
  }
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLOR[theme]);
}

function currentTheme(): Theme {
  const v = document.documentElement.dataset.theme;
  return v === "light" || v === "dark" ? v : preferredTheme();
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => {
      const next: Theme = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* sin almacenamiento: solo esta pestaña */
      }
      return next;
    });
  }, []);

  return { theme, toggle };
}
