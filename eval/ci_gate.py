"""Puerta de calidad del harness en CI: 0 resultados inseguros, ninguna regresión en la tasa de aprobación y resultados
del MISMO commit que se está evaluando.

    .venv/bin/python -m eval.ci_gate --split dev baseline "sistema+llm_provider-fake"      # compara y falla si hay regresión
    .venv/bin/python -m eval.ci_gate --split dev baseline "sistema+llm_provider-fake" --update   # reescribe la referencia

- Toma el último JSON crudo de cada variante en eval/results/raw/.
- Referencia: eval/ci_reference.json, versionada en main ("último resultado guardado en main"). Se actualiza a mano con
  --update cuando una mejora sube la tasa, y se commitea con el cambio que la produjo.
- Cada resultado debe ser de este commit (el SHA que guardó eval.run en `config.git_commit` = `git rev-parse HEAD`) y cubrir
  todos los casos del split. Si el harness no corrió o falló, el último crudo es de otro commit y la puerta falla en vez de
  aprobar con resultados viejos (pasó el 2026-10-02 en local).
- Con GITHUB_STEP_SUMMARY, escribe la tabla en el resumen del workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "ci_reference.json"


def latest(variant: str, split: str) -> dict:
    files = sorted((ROOT / "results" / "raw").glob(f"*_{variant}_{split}.json"))
    if not files:
        raise SystemExit(f"no hay resultado de {variant} en eval/results/raw/")
    return json.loads(files[-1].read_text(encoding="utf-8"))


def head_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()


def freshness_problem(raw: dict, head: str, n_cases: int) -> str | None:
    """Por qué este crudo no sirve para juzgar el commit actual; None si sirve."""
    sha = (raw.get("config") or {}).get("git_commit") or ""
    if not head or sha != head:
        return f"resultado de otro commit ({sha[:7] or 'sin SHA'}; se evalúa {head[:7] or '?'})"
    total = raw["summary_all"]["casos_que_pasan_todo"][1]
    if n_cases and (total < n_cases or total % n_cases):
        return f"corrida incompleta ({total} resultados para {n_cases} casos)"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.ci_gate")
    ap.add_argument("--split", default="dev")
    ap.add_argument("variants", nargs="+")
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args(argv)
    ref = json.loads(REFERENCE.read_text(encoding="utf-8")) if REFERENCE.exists() else {"variants": {}}
    rows, failed, new_ref = [], False, {"split": a.split, "dataset": os.environ.get("EVAL_DATASET", "real"), "variants": {}}
    from eval.cases.schema import load_cases
    head, n_cases = head_sha(), len(load_cases(a.split))
    for v in a.variants:
        raw = latest(v, a.split)
        s = raw["summary_all"]
        stale = freshness_problem(raw, head, n_cases)
        passed, total = s["casos_que_pasan_todo"]
        unsafe = s["resultados_inseguros"][0]
        rate = passed / total if total else 0.0
        r = ref.get("variants", {}).get(v)
        ref_rate = r["passed"] / r["total"] if r and r["total"] else None
        regression = ref_rate is not None and rate + 1e-9 < ref_rate
        status = "❌" if unsafe or regression or stale else "✅"
        failed |= bool(unsafe or regression or stale)
        rows.append(f"| `{v}` | {passed}/{total} ({rate:.1%}) | {f'{r['passed']}/{r['total']} ({ref_rate:.1%})' if r else '—'} | {unsafe} | {status}{f' {stale}' if stale else ''} |")
        new_ref["variants"][v] = {"passed": passed, "total": total, "unsafe": unsafe}
    table = "\n".join(["### Puerta de calidad del harness", "",
                       f"Split `{a.split}`, dataset `{new_ref['dataset']}`. Commit `{head[:7]}`. Falla con algún resultado inseguro, con una tasa menor a la referencia de main, o si el resultado no es de este commit o está incompleto.",
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
