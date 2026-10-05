// Recorrido guiado de una pantalla: resalta cada sección y explica para qué sirve. Se muestra solo la primera vez que el
// usuario entra (se recuerda en este navegador) y se puede repetir con el botón "Ver recorrido".
// - Sin dependencias: un recorte sobre la sección (sombra enorme alrededor) y una tarjeta junto a ella; en celular, abajo.
// - Accesible: diálogo con nombre, foco en la tarjeta, Esc cierra, flechas avanzan y retroceden.
// - Si una sección no está en pantalla (sin datos, otra pestaña sin cargar), ese paso se salta.
// - `localStorage["tour:off"] = "1"` lo desactiva (pruebas automáticas, grabación del video).
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import type { Lang } from "../api/types";
import { T } from "../lib/i18n";

export interface TourStep {
  /** selector CSS de la sección a resaltar */
  target: string;
  title: string;
  body: string;
  /** antes de mostrar el paso (p. ej. cambiar de pestaña) */
  before?: () => void;
}

const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento: se vuelve a mostrar */ } },
};
const HEADER = 72;      // barra superior fija
const seenKey = (id: string, user: string) => `tour:${id}:${user}:v1`;

/** Abre el recorrido la primera vez que la pantalla está lista; `start` lo repite. */
export function useTour(id: string, user: string | null | undefined, ready: boolean) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!ready || !user || store.get("tour:off") === "1" || store.get(seenKey(id, user))) return;
    const timer = setTimeout(() => setOpen(true), 700);
    return () => clearTimeout(timer);
  }, [id, user, ready]);
  const close = useCallback(() => { if (user) store.set(seenKey(id, user), "1"); setOpen(false); }, [id, user]);
  return { open, start: useCallback(() => setOpen(true), []), close };
}

async function findTarget(selector: string, timeoutMs = 2500): Promise<HTMLElement | null> {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const el = document.querySelector<HTMLElement>(selector);
    if (el && el.getBoundingClientRect().height > 0) return el;
    if (Date.now() > end) return null;
    await new Promise((r) => setTimeout(r, 120));
  }
}

export default function Tour({ steps, lang, onClose }: { steps: TourStep[]; lang: Lang; onClose: () => void }) {
  const t = T[lang].tour;
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const targetRef = useRef<HTMLElement | null>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const dirRef = useRef(1);
  const step = steps[index];

  // prepara el paso: ejecuta `before`, espera la sección y la trae a la vista; si no aparece, salta al siguiente
  useEffect(() => {
    let alive = true;
    step?.before?.();
    (async () => {
      const el = await findTarget(step.target);
      if (!alive) return;
      if (!el) {
        const next = index + dirRef.current;
        if (next >= 0 && next < steps.length) setIndex(next);
        else onClose();
        return;
      }
      targetRef.current = el;
      // secciones altas: arriba, bajo la barra; las demás, centradas
      const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      const r = el.getBoundingClientRect();
      if (r.height > window.innerHeight - 200) window.scrollTo?.({ top: r.top + window.scrollY - HEADER - 16, behavior: still ? "auto" : "smooth" });
      else el.scrollIntoView?.({ block: "center", behavior: still ? "auto" : "smooth" });
      setRect(el.getBoundingClientRect());
      popRef.current?.focus();
    })();
    return () => { alive = false; };
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  // sigue a la sección si la página se desplaza o cambia de tamaño
  useLayoutEffect(() => {
    const update = () => { if (targetRef.current) setRect(targetRef.current.getBoundingClientRect()); };
    const id = window.setInterval(update, 250);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { window.clearInterval(id); window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, []);

  const go = useCallback((d: number) => {
    const next = index + d;
    if (next < 0) return;
    if (next >= steps.length) { onClose(); return; }
    dirRef.current = d;
    setRect(null);
    setIndex(next);
  }, [index, steps.length, onClose]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClose]);

  if (!step) return null;
  const pad = 8;
  const vh = window.innerHeight, vw = window.innerWidth;
  const popH = popRef.current?.offsetHeight ?? 240;
  // la tarjeta va debajo de la sección, o encima; si la sección ocupa la pantalla, en la esquina inferior, siempre visible
  let popStyle: CSSProperties = { top: "40%", left: "50%", transform: "translateX(-50%)" };
  if (rect) {
    const left = Math.max(16, Math.min(rect.left, vw - 380 - 16));
    if (vh - rect.bottom - 14 - 16 >= popH) popStyle = { top: rect.bottom + 14, left };
    else if (rect.top - 14 - HEADER >= popH) popStyle = { top: rect.top - 14 - popH, left };
    else popStyle = { bottom: 16, right: 16 };
  }

  return createPortal(
    <div className="tour" role="presentation">
      {rect
        ? <div className="tour-spot" aria-hidden="true" style={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }} />
        : <div className="tour-dim" aria-hidden="true" />}
      <div ref={popRef} className="tour-pop" role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-body" tabIndex={-1} style={popStyle}>
        <p className="tour-count">{t.step(index + 1, steps.length)}</p>
        <h2 id="tour-title">{step.title}</h2>
        <p id="tour-body">{step.body}</p>
        <div className="tour-actions">
          <button type="button" className="btn ghost small" onClick={onClose}>{t.skip}</button>
          <span className="tour-nav">
            {index > 0 && <button type="button" className="btn secondary small" onClick={() => go(-1)}>{t.back}</button>}
            <button type="button" className="btn primary small" onClick={() => go(1)}>{index === steps.length - 1 ? t.done : t.next}</button>
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Botón para repetir el recorrido. */
export function TourButton({ lang, onClick }: { lang: Lang; onClick: () => void }) {
  return (
    <button type="button" className="btn ghost small tour-replay" onClick={onClick} data-tour="replay">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.8-.9 1.4V13M12 16.5h.01" /></svg>
      {T[lang].tour.start}
    </button>
  );
}
