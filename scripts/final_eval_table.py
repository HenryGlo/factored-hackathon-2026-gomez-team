"""Tabla de la evaluación final en formato para las diapositivas, a partir de los JSON crudos del harness.

    python scripts/final_eval_table.py eval/results/raw/<a>.json eval/results/raw/<b>.json [--out tabla.md] [--note "…"]

Una fila por corrida: casos que pasan todo (n/N), resultados inseguros (n/N), resolución segura, escalamientos correctos,
latencia por turno p50 / p95, costo por caso y llamadas LLM fallidas. No ejecuta casos ni muestra IDs del dataset.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LABELS = {"baseline": "Baseline (reglas, sin LLM)", "claude_cli": "Todo LLM", "sistema": "Sistema", "sistema_api": "Sistema (API)",
          "sistema_cascade": "Sistema + cascada de intención"}
MAX_LLM_ERRORS = 0.05


def frac(x: list[int]) -> str:
    n, total = x
    return f"{n}/{total} ({n / total:.1%})".replace(".", ",") if total else "—"


def ms(v: float) -> str:
    return f"{v:.0f} ms" if v < 1000 else f"{v / 1000:.1f} s".replace(".", ",")


def row(raw: dict) -> tuple[str, list[str], bool]:
    s, env = raw["summary_all"], raw.get("config", {}).get("env", {})
    name = LABELS.get(raw["variant"].split("+")[0], raw["variant"])
    provider = env.get("LLM_PROVIDER", "")
    lat = s["latencia_turno_ms"]
    failed, calls = s["llamadas_llm_fallidas"]
    too_many = bool(calls) and failed / calls > MAX_LLM_ERRORS
    cells = [f"{name} · `{provider}`" if provider else name, frac(s["casos_que_pasan_todo"]), frac(s["resultados_inseguros"]),
             frac(s["resolucion_automatica_segura"]), frac(s["escalamientos_correctos"]), f"{ms(lat['p50'])} / {ms(lat['p95'])}",
             f"${s['costo_por_caso_usd']:.4f}", frac(s["llamadas_llm_fallidas"]) + (" ⚠" if too_many else "")]
    return raw["split"], cells, too_many


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("raws", nargs="+", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--note", action="append", default=[])
    a = ap.parse_args(argv)
    by_split: dict[str, list[list[str]]] = {}
    invalid = False
    for path in a.raws:
        split, cells, too_many = row(json.loads(path.read_text(encoding="utf-8")))
        by_split.setdefault(split, []).append(cells)
        invalid |= too_many
    out = []
    for split, rows in by_split.items():
        out += [f"### Split `{split}`", "",
                "| Variante | Pasan todo | Inseguros | Resolución segura | Escalamientos correctos | Latencia por turno p50 / p95 | Costo por caso | Llamadas LLM fallidas |",
                "|---|---|---|---|---|---|---|---|", *("| " + " | ".join(r) + " |" for r in rows), ""]
    if invalid:
        out += [f"**⚠ Corrida no válida:** alguna variante supera {MAX_LLM_ERRORS:.0%} de llamadas LLM fallidas; sus números no miden el sistema.", ""]
    out += [f"- {n}" for n in a.note]
    text = "\n".join(out).rstrip() + "\n"
    print(text)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    return 3 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
