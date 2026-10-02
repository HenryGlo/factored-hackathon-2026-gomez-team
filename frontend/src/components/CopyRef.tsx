// Referencia corta (RCL-…, ATN-…) con botón para copiarla. El aviso "Copiado" se anuncia a lectores de pantalla.
import { useState } from "react";
import type { Lang } from "../api/types";
import { T } from "../lib/i18n";

export default function CopyRef({ value, lang }: { value: string; lang: Lang }) {
  const t = T[lang].chat;
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* sin permiso de portapapeles: la referencia sigue visible y seleccionable */
    }
  }
  return (
    <span className="copy-ref">
      <code>{value}</code>
      <button type="button" className="btn ghost small" onClick={() => void copy()} aria-label={t.copyRef(value)}>{copied ? t.copied : t.copy}</button>
      <span className="sr-only" role="status">{copied ? t.copied : ""}</span>
    </span>
  );
}
