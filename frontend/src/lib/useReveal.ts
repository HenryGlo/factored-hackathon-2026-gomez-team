// Revela un bloque cuando entra en pantalla (una sola vez): agrega data-shown al elemento. La animación vive en el CSS
// y se apaga con prefers-reduced-motion. Sin IntersectionObserver (tests, navegadores viejos) el contenido se muestra ya.
import { useEffect, useRef } from "react";

export function useReveal<E extends HTMLElement>() {
  const ref = useRef<E>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") { el.dataset.shown = "true"; return; }
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { el.dataset.shown = "true"; io.disconnect(); }
    }, { rootMargin: "0px 0px -12% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return ref;
}
