// Vista previa de tres propuestas visuales en blanco, negro y azul (/preview/1, /2, /3 y …/chat). Mismo concepto, mismo
// marcado y mismos flujos: cada propuesta solo reasigna los tokens y ajusta unos pocos componentes (styles/looks.css).
// Mientras la vista previa está abierta se usa el modo claro; al salir se restaura el modo que tenía el usuario.
import "@fontsource-variable/public-sans/wght.css";
import "@fontsource-variable/manrope/wght.css";
import "@fontsource-variable/plus-jakarta-sans/wght.css";
import "../../styles/looks.css";
import { useEffect, type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

export const LOOKS = [
  { id: "1", name: "Banca clara" },
  { id: "2", name: "Contraste" },
  { id: "3", name: "Azul profundo" },
];

export function useLook(): string {
  const { look } = useParams();
  return LOOKS.some((l) => l.id === look) ? look! : "1";
}

/** Selector flotante para comparar las propuestas sin perder la pantalla (landing o chat). */
function LookSwitch({ look }: { look: string }) {
  const { pathname } = useLocation();
  const chat = pathname.endsWith("/chat");
  return (
    <nav className="look-switch" aria-label="Propuestas visuales">
      <span>Propuesta</span>
      {LOOKS.map((l) => (
        <Link key={l.id} to={`/preview/${l.id}${chat ? "/chat" : ""}`} aria-current={l.id === look ? "page" : undefined} title={l.name}>
          {l.id}<span className="sr-only"> {l.name}</span>
        </Link>
      ))}
      <Link to={chat ? `/preview/${look}` : `/preview/${look}/chat`}>{chat ? "Landing" : "Chat"}</Link>
    </nav>
  );
}

export default function LookScope({ children }: { children: ReactNode }) {
  const look = useLook();
  useEffect(() => {
    const root = document.documentElement;
    const theme = root.dataset.theme;
    root.dataset.look = look;
    delete root.dataset.theme;                       // las propuestas se evalúan en modo claro
    return () => {
      delete root.dataset.look;
      if (theme) root.dataset.theme = theme;
    };
  }, [look]);
  return <>{children}<LookSwitch look={look} /></>;
}
