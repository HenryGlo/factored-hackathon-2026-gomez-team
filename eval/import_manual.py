"""Convierte el CSV de los redactores (eval/manual/template.csv) en casos del split test. NO ejecuta nada.

    .venv/bin/python -m eval.import_manual --csv eval/manual/template.csv
    .venv/bin/python -m eval.import_manual --csv respuestas.csv --out eval/cases/test/manual.yaml --force

- Cada ficha se enlaza con su escenario, selector, pick y fecha de sesión (eval/manual/assignments.json).
- Columnas: ficha_id, momento (inicio | si_pregunta | si_muestra_cargo | al_confirmar), orden, mensaje, notas.
  Las filas con ficha_id EJEMPLO o vacías se ignoran.
- Los pasos se arman por fases (eval/manual/scenarios.py): los mensajes que dependen de lo que haga el asistente
  llevan `when` y el runner los salta si la conversación no está en ese estado.
- Valida cada caso con el esquema (eval/cases/schema.py) y lo informa. Se niega a sobrescribir un split test existente
  sin --force (el test está congelado: se importa una vez).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml
from pydantic import ValidationError

from eval.cases.schema import Case
from eval.manual.scenarios import BY_KEY, MOMENTS, WHEN, YES

ROOT = Path(__file__).resolve().parent
ASSIGN = ROOT / "manual" / "assignments.json"
OUT = ROOT / "cases" / "test" / "manual.yaml"
COLUMNS = ("ficha_id", "momento", "orden", "mensaje", "notas")


def read_rows(path: Path) -> tuple[dict[str, list[dict]], list[str]]:
    errors, by_ficha = [], defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS[:4] if c not in (reader.fieldnames or [])]
        if missing:
            return {}, [f"faltan columnas: {missing} (esperadas: {', '.join(COLUMNS)})"]
        for n, row in enumerate(reader, start=2):
            fid = (row.get("ficha_id") or "").strip().upper()
            if not fid or fid == "EJEMPLO":
                continue
            moment = (row.get("momento") or "").strip().lower()
            msg = (row.get("mensaje") or "").strip()
            if moment not in MOMENTS:
                errors.append(f"línea {n}: momento {moment!r} no válido; usar uno de {', '.join(MOMENTS)}")
            if not msg:
                errors.append(f"línea {n}: mensaje vacío")
            try:
                order = int((row.get("orden") or "1").strip())
            except ValueError:
                errors.append(f"línea {n}: orden {row.get('orden')!r} no es un número")
                order = 1
            by_ficha[fid].append({"momento": moment, "orden": order, "mensaje": msg, "notas": (row.get("notas") or "").strip(), "linea": n})
    return by_ficha, errors


def build_case(a: dict, rows: list[dict]) -> dict:
    s = BY_KEY[a["scenario"]]
    lang = a["language"]
    by_moment = {m: [r["mensaje"].replace("{", "{{").replace("}", "}}")     # el runner usa str.format
                     for r in sorted((r for r in rows if r["momento"] == m), key=lambda r: (r["orden"], r["linea"]))]
                 for m in MOMENTS}
    steps = [{"message": m} for m in by_moment["inicio"]]
    steps += [{"message": m, "when": WHEN["si_pregunta"]} for m in by_moment["si_pregunta"]]
    if s.pick_target:
        steps.append({"action": "select_target", "when": ["aclarando"]})
    answers = by_moment["si_muestra_cargo"] or ([YES[lang]] if s.default_yes else [])
    steps += [{"message": m, "when": WHEN["si_muestra_cargo"]} for m in answers]
    steps += [{"message": m, "when": WHEN["al_confirmar"]} for m in by_moment["al_confirmar"]]
    steps += [{"action": b, "when": ["confirmando_accion"]} for b in s.buttons]
    notes = "; ".join(r["notas"] for r in rows if r["notas"])
    return {"case_id": f"test-manual-{a['ficha_id'].lower()}", "split": "test", "language": lang, "category": s.category,
            "title": f"{s.sentence} (ficha {a['ficha_id']}, escrita a mano{': ' + notes if notes else ''})",
            "selector": a["selector"], "pick": a["pick"], "session_date": a["session_date"], "steps": steps,
            "expected": s.expected}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.import_manual")
    ap.add_argument("--csv", type=Path, default=ROOT / "manual" / "template.csv")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--force", action="store_true", help="sobrescribir un split test ya importado")
    ap.add_argument("--check", action="store_true", help="solo validar; no escribir")
    args = ap.parse_args(argv)
    assignments = {x["ficha_id"]: x for x in json.loads(ASSIGN.read_text(encoding="utf-8"))["fichas"]}
    by_ficha, errors = read_rows(args.csv)
    for fid in sorted(set(by_ficha) - set(assignments)):
        errors.append(f"ficha {fid}: no existe en {ASSIGN.name}")
    cases = []
    for fid in sorted(set(by_ficha) & set(assignments)):
        rows = by_ficha[fid]
        if not any(r["momento"] == "inicio" for r in rows):
            errors.append(f"ficha {fid}: falta al menos un mensaje con momento inicio")
            continue
        raw = build_case(assignments[fid], rows)
        try:
            Case.model_validate(raw)
        except ValidationError as e:
            errors.append(f"ficha {fid}: {e.errors()[0]['msg']}")
            continue
        cases.append(raw)
    missing = sorted(set(assignments) - set(by_ficha))
    print(f"{len(cases)} casos válidos de {len(assignments)} fichas; sin respuestas: {', '.join(missing) or 'ninguna'}")
    if errors:
        print("errores:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    if args.check or not cases:
        return 0
    if args.out.exists() and not args.force:
        print(f"{args.out} ya existe: el split test está congelado. Usa --force solo si nunca se corrió.", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    header = ("# Split test escrito a mano: generado por `python -m eval.import_manual` desde el CSV de los redactores.\n"
              "# Congelado: se corre una vez, al final (`python -m eval.run --split test ... --i-know-this-is-final`). No editar a mano.\n")
    args.out.write_text(header + yaml.safe_dump(cases, allow_unicode=True, sort_keys=False, width=160), encoding="utf-8")
    print(f"escrito {args.out} (no se ejecutó nada)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
