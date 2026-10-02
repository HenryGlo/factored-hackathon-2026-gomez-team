// Estados compartidos de las pantallas de lectura: carga (esqueleto) y vacío (con Banky y, si aplica, una acción).
import type { ReactNode } from "react";
import Banky, { type BankyState } from "./Banky";

export function Loading({ label, rows = 3 }: { label: string; rows?: number }) {
  return (
    <div className="skeleton" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => <span key={i} className="skeleton-row" aria-hidden="true" />)}
    </div>
  );
}

export function Empty({ title, children, banky = "idle" }: { title: string; children?: ReactNode; banky?: BankyState }) {
  return (
    <div className="empty-state">
      <Banky state={banky} size={72} />
      <p className="empty-title">{title}</p>
      {children}
    </div>
  );
}
