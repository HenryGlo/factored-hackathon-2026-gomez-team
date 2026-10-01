"""Tabla comparativa de variantes a partir de los JSON crudos del harness.

    .venv/bin/python -m eval.compare --split dev baseline claude_cli sistema
    .venv/bin/python -m eval.compare --split dev eval/results/raw/<a>.json eval/results/raw/<b>.json

Cada argumento es un JSON crudo o el nombre de una variante (se toma su último crudo del split). Escribe
eval/results/<fecha>_comparacion_<split>.md (sin IDs del dataset) y lo imprime. No ejecuta casos.

Re-evaluación: `sin_exito_sin_verificar` se recalcula desde las respuestas crudas con el checker actual, así todas las
variantes se juzgan igual aunque se hayan corrido con una versión anterior del checker. "Pasan todo", "inseguros" y
"resolución segura" se recalculan a partir de eso; el reporte indica cuántos resultados cambiaron.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from eval.cases.schema import load_cases
from eval.harness.checkers import AUTO, unverified_success_problems
from eval.harness.metrics import classify_failure, frac, latency_split, latency_summary, root_cause

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
SAFETY = {"sin_acciones_prohibidas", "sin_datos_de_otro_cliente", "sin_exito_sin_verificar", "sin_reclamos_duplicados"}


def resolve(arg: str, split: str) -> Path:
    p = Path(arg)
    if p.suffix == ".json" and p.exists():
        return p
    found = sorted((RESULTS / "raw").glob(f"*_{arg}_{split}.json"))
    if not found:
        raise SystemExit(f"no hay crudo de la variante {arg!r} para el split {split}")
    return found[-1]


def clarify_modes(traces: list[dict]) -> Counter:
    return Counter(f"{t.get('modo') or ('llm' if t['kind'] == 'llm' else 'plantilla')}:{t.get('motivo') or '—'}"
                   for t in traces if t["node"] == "clarify")


def rescore(cases: list[dict], expected: dict[str, list[str]]) -> tuple[dict, int]:
    """Recalcula sin_exito_sin_verificar y las métricas que dependen de él. Devuelve (métricas, n cambiados)."""
    changed = 0
    for c in cases:
        responses = [t["response"] for t in c["turns"] if t["kind"] in ("message", "action") and t["status"] == 200 and t["response"]]
        problems = unverified_success_problems(responses)
        for ch in c["checks"]:
            if ch["name"] == "sin_exito_sin_verificar" and ch["passed"] != (not problems):
                changed += 1
                ch["passed"], ch["detail"] = not problems, "; ".join(sorted(set(problems)))
    ok = lambda c, name: next(ch["passed"] for ch in c["checks"] if ch["name"] == name)
    unsafe = lambda c: any(ch["safety"] and not ch["passed"] for ch in c["checks"])
    auto = [c for c in cases if any(o in AUTO for o in expected.get(c["case_id"], []))]
    return {"casos_que_pasan_todo": (sum(all(ch["passed"] for ch in c["checks"]) for c in cases), len(cases)),
            "resultados_inseguros": (sum(unsafe(c) for c in cases), len(cases)),
            "resolucion_automatica_segura": (sum(ok(c, "resultado_final") and ok(c, "transaccion_correcta") and not unsafe(c)
                                                 for c in auto), len(auto))}, changed


def analyze(raw: dict, expected: dict[str, list[str]]) -> dict:
    cases = raw["cases"]
    re_metrics, changed = rescore(cases, expected)
    agg = {**raw["summary_all"], **re_metrics}
    n = len(cases)
    split = [x for c in cases for x in latency_split(c["turns"], c["traces"] or [])]
    cost = sum(c["cost_usd"] or 0 for c in cases)
    fails: Counter = Counter()
    examples = defaultdict(list)
    modes: Counter = Counter()
    roots: Counter = Counter()
    root_cases = defaultdict(list)
    for c in cases:
        modes += clarify_modes(c["traces"] or [])
        if rc := root_cause(c["checks"], c["outcome"], expected.get(c["case_id"], []), c["traces"] or []):
            roots[rc] += 1
            root_cases[rc].append(c["case_id"])
        for ch in c["checks"]:
            if not ch["passed"]:
                key = (classify_failure(ch["name"], c["outcome"], expected.get(c["case_id"], []), c["traces"] or []), ch["name"],
                       ch["detail"].split(";")[0][:90])
                fails[key] += 1
                if c["case_id"] not in examples[key]:
                    examples[key].append(c["case_id"])
    return {"variant": raw["variant"], "repeats": raw["config"]["repeats"], "n": n, "agg": agg, "lat": latency_summary(split),
            "cost": cost, "cost_case": cost / n if n else None, "fails": fails, "examples": examples, "modes": modes,
            "by_class": _by_class(fails), "rescored": changed, "roots": roots, "root_cases": root_cases,
            "commit": raw["config"].get("git_commit", "")[:7], "dirty": raw["config"].get("git_dirty")}


def _by_class(fails: Counter) -> Counter:
    out: Counter = Counter()
    for (cl, _, _), k in fails.items():
        out[cl] += k
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.compare")
    ap.add_argument("--split", default="dev")
    ap.add_argument("runs", nargs="+", help="variantes o rutas de JSON crudo")
    args = ap.parse_args(argv)
    try:
        expected = {c.case_id: c.outcomes for c in load_cases(args.split)}
    except Exception:
        expected = {}
    files = [resolve(r, args.split) for r in args.runs]
    rows = [analyze(json.loads(f.read_text(encoding="utf-8")), expected) for f in files]

    ms = lambda d: f"{d['p50'] / 1000:.1f} s / {d['p95'] / 1000:.1f} s" if d["p50"] >= 1000 else f"{d['p50']:.0f} ms / {d['p95']:.0f} ms"
    L = [f"# Comparación de variantes · split {args.split} · {datetime.now():%Y-%m-%d %H:%M}", "",
         "Generado con `python -m eval.compare` a partir de: " + ", ".join(f"`{f.name}`" for f in files) + " (crudos fuera de git).", "",
         "Todas las repeticiones juntas: cada fracción cuenta casos × repeticiones. `sin_exito_sin_verificar` re-evaluado con el "
         "checker actual sobre las respuestas crudas (cambios por variante: " + ", ".join(f"`{r['variant']}` {r['rescored']}" for r in rows) + ").", "",
         "| Variante | Rep. | Resolución segura | Pasan todo | Inseguros | Escalamientos correctos | Contención | Latencia/turno p50 / p95 | Costo por caso | Commit |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        a = r["agg"]
        L.append(f"| `{r['variant']}` | {r['repeats']} | {frac(*a['resolucion_automatica_segura'])} | {frac(*a['casos_que_pasan_todo'])} | "
                 f"{frac(*a['resultados_inseguros'])} | {frac(*a['escalamientos_correctos'])} | {frac(*a['contencion'])} | "
                 f"{ms(r['lat']['total'])} | ${r['cost_case']:.4f} | {r['commit']}{' (con cambios sin commit)' if r['dirty'] else ''} |")
    L += ["", "## Latencia por turno: LLM vs resto (entorno de desarrollo)", "",
          "Portátil de desarrollo con `claude -p` local; cada llamada incluye el arranque del proceso del CLI. No es una medida de "
          "producción. LLM = llamadas LLM del turno según la traza (intent y extract en paralelo cuentan una vez, los fallos cuentan "
          "el tiempo esperado); resto = total − LLM (código, tools, base y harness).", "",
          "| Variante | Turnos | Con LLM | Total p50 / p95 | LLM p50 / p95 | Resto p50 / p95 |", "|---|---|---|---|---|---|"]
    for r in rows:
        la = r["lat"]
        L.append(f"| `{r['variant']}` | {la['n']} | {la['turnos_con_llm']} | {ms(la['total'])} | {ms(la['llm'])} | {ms(la['resto'])} |")
    L += ["", "## Casos fallidos por causa raíz", "",
          "Una clase por caso: la del resultado final si falló, si no la de la transacción, si no la del primer checker. "
          "Extracción incluye la comprensión del mensaje (intención mal clasificada o datos mal extraídos).", "",
          "| Variante | " + " | ".join(("extracción", "aclaración", "política", "escalamiento", "idioma", "tool")) + " | casos fallidos |", "|---|" + "---|" * 7]
    for r in rows:
        L.append(f"| `{r['variant']}` | " + " | ".join(str(r["roots"].get(c, 0)) for c in ("extracción", "aclaración", "política", "escalamiento", "idioma", "tool")) + f" | {sum(r['roots'].values())}/{r['n']} |")
    for r in rows:
        if r["roots"]:
            L += ["", f"`{r['variant']}`: " + "; ".join(f"{k}: {', '.join(sorted(set(v)))}" for k, v in sorted(r["root_cases"].items()))]
    L += ["", "## Checkers fallidos por clase", "", "Cuenta checkers, no casos: un mismo caso puede sumar varios.", "",
          "| Variante | " + " | ".join(c for c in ("extracción", "aclaración", "política", "escalamiento", "idioma", "tool")) + " | total |",
          "|---|" + "---|" * 7]
    for r in rows:
        bc = r["by_class"]
        L.append(f"| `{r['variant']}` | " + " | ".join(str(bc.get(c, 0)) for c in ("extracción", "aclaración", "política", "escalamiento", "idioma", "tool"))
                 + f" | {sum(bc.values())} |")
    for r in rows:
        if not r["fails"]:
            continue
        L += ["", f"### `{r['variant']}`: fallos", "", "| Clase | Checker | Detalle | n | Casos |", "|---|---|---|---|---|"]
        for (cl, ch, d), k in r["fails"].most_common():
            L.append(f"| {cl} | {ch} | {d} | {k} | {', '.join(r['examples'][(cl, ch, d)][:6])} |")
    L += ["", "## Aclaraciones por modo", "", "Paso `clarify` de la traza: modo (llm / plantilla) y motivo. Las corridas anteriores a "
          "CONFIRM_MODE / CLARIFY_MODE no registran motivo (—).", "", "| Variante | Modo:motivo → n |", "|---|---|"]
    for r in rows:
        L.append(f"| `{r['variant']}` | " + (", ".join(f"{k} → {v}" for k, v in sorted(r["modes"].items())) or "—") + " |")
    out = RESULTS / f"{datetime.now():%Y%m%d-%H%M}_comparacion_{args.split}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nescrito: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
