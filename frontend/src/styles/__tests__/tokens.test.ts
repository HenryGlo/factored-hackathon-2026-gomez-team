// Contraste AA de los tokens: los pares texto/fondo que usa la interfaz se calculan desde tokens.css (WCAG 2.1),
// en el tema claro (:root) y en el oscuro (:root[data-theme="dark"], que solo redefine los colores que cambian).
import { describe, expect, it } from "vitest";
import css from "../tokens.css?raw";

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*(#[0-9a-f]{6})\s*;/g)].map((m) => [m[1], m[2]]));
}

const light = block(":root");
const dark = { ...light, ...block(':root[data-theme="dark"]') };
const THEMES: [string, Record<string, string>][] = [["light", light], ["dark", dark]];

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(tokens: Record<string, string>, a: string, b: string): number {
  const [hi, lo] = [luminance(tokens[a]), luminance(tokens[b])].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// texto normal: 4.5:1
const TEXT_PAIRS: [string, string][] = [
  ["--text", "--paper"], ["--text", "--surface"], ["--text", "--surface-2"],
  ["--muted", "--paper"], ["--muted", "--surface"], ["--muted", "--surface-2"],
  ["--accent", "--surface"], ["--accent", "--paper"], ["--accent", "--accent-soft"],
  ["--surface", "--accent"], ["--surface", "--accent-hover"],            // texto blanco del botón primario
  ["--on-accent", "--accent"], ["--on-accent", "--accent-hover"],        // botón primario, chips y control segmentado activos
  ["--on-accent", "--ok"], ["--on-accent", "--err"], ["--on-accent", "--info"], ["--on-accent", "--warn"],   // insignias llenas e iconos de aviso
  ["--on-accent", "--text"],                                             // idioma activo
  ["--on-bubble-me", "--bubble-me"], ["--on-sun", "--sun"], ["--violet", "--violet-bg"],
  ["--text", "--surface-hi"], ["--muted", "--surface-hi"], ["--text", "--accent-soft"], ["--muted", "--accent-soft"],
  ["--text", "--info-bg"], ["--muted", "--warn-bg"],
  ["--on-dark", "--ink-900"], ["--on-dark", "--ink-800"], ["--on-dark", "--ink-700"],
  ["--on-dark-muted", "--ink-900"], ["--on-dark-muted", "--ink-800"], ["--on-dark-muted", "--ink-700"],
  ["--accent-bright", "--ink-900"], ["--accent-bright", "--ink-700"],
  ["--ink-900", "--accent-bright"],                                      // botón primario sobre oscuro
  ["--ok", "--ok-bg"], ["--ok", "--surface"], ["--warn", "--warn-bg"], ["--err", "--err-bg"], ["--err", "--surface"],
  ["--info", "--info-bg"], ["--text", "--warn-bg"], ["--text", "--err-bg"],
];
// bordes de controles y anillo de foco: 3:1
const UI_PAIRS: [string, string][] = [
  ["--line-strong", "--surface"], ["--line-strong", "--paper"], ["--accent", "--paper"], ["--accent-bright", "--ink-800"],
  ["--edge", "--paper"], ["--edge", "--surface"],                        // contornos de tinta: chat, campo de mensaje, opciones
];

describe.each(THEMES)("design tokens (%s theme)", (_name, tokens) => {
  it("defines every color used by the contrast pairs", () => {
    for (const name of new Set([...TEXT_PAIRS, ...UI_PAIRS].flat())) expect(tokens[name], name).toMatch(/^#[0-9a-f]{6}$/);
  });

  it.each(TEXT_PAIRS)("%s on %s meets AA for text (4.5:1)", (fg, bg) => {
    expect(contrast(tokens, fg, bg)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(UI_PAIRS)("%s on %s meets AA for UI components (3:1)", (fg, bg) => {
    expect(contrast(tokens, fg, bg)).toBeGreaterThanOrEqual(3);
  });
});

describe("dark theme", () => {
  it("redefines the surface, text and accent colors", () => {
    const own = block(':root[data-theme="dark"]');
    for (const name of ["--paper", "--surface", "--text", "--muted", "--accent", "--on-accent", "--edge"]) expect(own[name], name).not.toBe(light[name]);
  });
});
