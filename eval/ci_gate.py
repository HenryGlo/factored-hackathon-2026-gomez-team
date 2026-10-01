"""Puerta de calidad del harness en CI: 0 resultados inseguros y ninguna regresión en la tasa de aprobación.

    .venv/bin/python -m eval.ci_gate --split dev baseline "sistema+llm_provider-fake"      # compara y falla si hay regresión
    .venv/bin/python -m eval.ci_gate --split dev baseline "sistema+llm_provider-fake" --update   # reescribe la referencia

- Toma el último JSON crudo de cada variante en eval/results/raw/.
- Referencia: eval/ci_reference.json, versionada en main ("último resultado guardado en main"). Se actualiza a mano con
  --update cuando una mejora sube la tasa, y se commitea con el cambio que la produjo.
- Con GITHUB_STEP_SUMMARY, escribe la tabla en el resumen del workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "ci_reference.json"


def latest(variant: str, split: str) -> dict:
    files = sorted((ROOT / "results" / "raw").glob(f"*_{variant}_{split}.json"))
    if not files:
        raise SystemExit(f"no hay resultado de {variant} en eval/results/raw/")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.ci_gate")
    ap.add_argument("--split", default="dev")
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args(argv)
    ref = json.loads(REFERENCE.read_text(encoding="utf-8")) if REFERENCE.exists() else {"variants": {}}
    rows, failed, new_ref = [], False, {"split": a.split, "dataset": os.environ.get("EVAL_DATASET", "real"), "variants": {}}
    for v in a.variants:
        s = latest(v, a.split)["summary_all"]
        passed, total = s["casos_que_pasan_todo"]
        unsafe = s["resultados_inseguros"][0]
        rate = passed / total if total else 0.0
        r = ref.get("variants", {}).get(v)
        ref_rate = r["passed"] / r["total"] if r and r["total"] else None
        regression = ref_rate is not None and rate + 1e-9 < ref_rate
        status = "❌" if unsafe or regression else "✅"
        failed |= bool(unsafe or regression)
        rows.append(f"| `{v}` | {passed}/{total} ({rate:.1%}) | {f'{r['passed']}/{r['total']} ({ref_rate:.1%})' if r else '—'} | {unsafe} | {status} |")
        new_ref["variants"][v] = {"passed": passed, "total": total, "unsafe": unsafe}
    table = "\n".join(["### Puerta de calidad del harness", "",
                       f"Split `{a.split}`, dataset `{new_ref['dataset']}`. Falla con algún resultado inseguro o con una tasa menor a la referencia de main.",
                       "", "| Variante | Pasan todo | Referencia (main) | Inseguros | |", "|---|---|---|---|---|", *rows])
    print(table)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(table + "\n")
    if a.update:
        REFERENCE.write_text(json.dumps(new_ref, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"referencia actualizada: {REFERENCE}")
        return 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
