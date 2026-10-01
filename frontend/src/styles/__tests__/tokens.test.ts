// Contraste AA de los tokens: los pares texto/fondo que usa la interfaz se calculan desde tokens.css (WCAG 2.1).
import { describe, expect, it } from "vitest";
import css from "../tokens.css?raw";

const root = css.slice(css.indexOf(":root"), css.indexOf("}"));
const tokens = Object.fromEntries([...root.matchAll(/(--[\w-]+):\s*(#[0-9a-f]{6})\s*;/g)].map((m) => [m[1], m[2]]));

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(tokens[a] ?? a), luminance(tokens[b] ?? b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// texto normal: 4.5:1
const TEXT_PAIRS: [string, string][] = [
  ["--text", "--paper"], ["--text", "--surface"], ["--text", "--surface-2"],
  ["--muted", "--paper"], ["--muted", "--surface"], ["--muted", "--surface-2"],
  ["--accent", "--surface"], ["--accent", "--paper"], ["--accent", "--accent-soft"],
  ["--surface", "--accent"], ["--surface", "--accent-hover"],            // texto blanco del botón primario
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
];

describe("design tokens", () => {
  it("defines every color used by the contrast pairs", () => {
    for (const name of new Set([...TEXT_PAIRS, ...UI_PAIRS].flat())) expect(tokens[name], name).toMatch(/^#[0-9a-f]{6}$/);
  });

  it.each(TEXT_PAIRS)("%s on %s meets AA for text (4.5:1)", (fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(UI_PAIRS)("%s on %s meets AA for UI components (3:1)", (fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(3);
  });
});
