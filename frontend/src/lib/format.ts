// Formato de fechas en la interfaz (los montos y las fechas de los movimientos ya vienen formateados del backend).
import type { Lang } from "../api/types";

/** Locale de formato para cada idioma de la interfaz (fechas y números en en-US cuando el idioma es inglés). */
export const localeOf = (lang: Lang): string => (lang === "pt" ? "pt-BR" : lang === "en" ? "en-US" : "es");
const locale = localeOf;

/** "2026-06-08" o ISO completo → "8 jun 2026". Una fecha sin hora se toma como día de calendario (sin corrimiento por zona). */
export function formatDate(value: string | null | undefined, lang: Lang): string {
  if (!value) return "—";
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(locale(lang), { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined, lang: Lang): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(locale(lang), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
