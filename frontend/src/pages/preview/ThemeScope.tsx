// Aplica una dirección visual (a, b o c) a toda la página mientras la ruta de vista previa está abierta.
// Los temas solo reasignan tokens y ajustan unos pocos componentes: no cambian el marcado, los flujos ni la API.
import "@fontsource-variable/geist/wght.css";
import "@fontsource-variable/instrument-sans/wght.css";
import "@fontsource-variable/bricolage-grotesque/wght.css";
import "../../styles/previews.css";
import { useEffect, type ReactNode } from "react";
import { useParams } from "react-router-dom";

export type Theme = "a" | "b" | "c";
export const THEMES: { id: Theme; name: string }[] = [
  { id: "a", name: "Fintech oscuro" },
  { id: "b", name: "Claro premium" },
  { id: "c", name: "Cálido y cercano" },
];

export function useTheme(): Theme {
  const { theme } = useParams();
  return theme === "b" || theme === "c" ? theme : "a";
}

export default function ThemeScope({ children }: { children: ReactNode }) {
  const theme = useTheme();
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    return () => { delete document.documentElement.dataset.theme; };
  }, [theme]);
  return <>{children}</>;
}
