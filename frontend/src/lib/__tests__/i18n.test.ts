// Los tres idiomas de la interfaz (es, pt, en) tienen exactamente las mismas claves, y el inglés no hereda textos en español.
import { describe, expect, it } from "vitest";
import { T } from "../i18n";

type Flat = Record<string, unknown>;
function flatten(o: unknown, prefix = ""): Flat {
  if (o === null || typeof o !== "object") return { [prefix]: o };
  const out: Flat = {};
  for (const [k, v] of Object.entries(o)) Object.assign(out, flatten(v, prefix ? `${prefix}.${k}` : k));
  return out;
}
const sample = (v: unknown) => (typeof v === "function" ? (v as (...a: unknown[]) => unknown)(2, 3, 4) : v);

describe("i18n", () => {
  const es = flatten(T.es);
  it.each(["pt", "en"] as const)("%s has exactly the same keys as es", (lang) => {
    expect(Object.keys(flatten(T[lang])).sort()).toEqual(Object.keys(es).sort());
  });

  it.each(["pt", "en"] as const)("%s has the same kind of value (text, list or function) for every key", (lang) => {
    const other = flatten(T[lang]);
    for (const k of Object.keys(es)) expect(typeof other[k], k).toBe(typeof es[k]);
  });

  it("English is actually translated: no Spanish text left (only names and words that are the same)", () => {
    const en = flatten(T.en);
    const SAME = /^(BankyFicticious|Banky|Total|LLM|SLA|Tickets?|Ticket|Web|No|PR|Inbox|Status|Error|Online)$/;
    const untranslated = Object.keys(es).filter((k) => {
      const a = sample(es[k]), b = sample(en[k]);
      return typeof a === "string" && a === b && !SAME.test(a) && !/^\d|^[A-Z0-9_ ./#-]+$/.test(a) && !k.startsWith("history.caseSteps");
    });
    expect(untranslated).toEqual([]);
    expect(Object.values(en).filter((v) => typeof v === "string" && /[ñ¿¡]|ción\b|ção\b/.test(v as string))).toEqual([]);
  });
});

describe("textos fijos del backend", () => {
  it("cada grupo tiene las mismas claves en es, pt y en", () => {
    for (const g of ["intents", "states", "fields", "guardrails", "policy", "risk", "clarify", "sources", "outcomes", "slo"] as const) {
      const keys = Object.keys(T.es.backend[g]).sort();
      expect(Object.keys(T.pt.backend[g]).sort()).toEqual(keys);
      expect(Object.keys(T.en.backend[g]).sort()).toEqual(keys);
    }
    expect(T.en.backend.fallbackIn("extract")).toContain("extract");
  });
});
