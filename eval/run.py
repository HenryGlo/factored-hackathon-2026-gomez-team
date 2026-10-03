"""Runner del harness.

    .venv/bin/python -m eval.run --split dev --variant baseline --repeats 1
    .venv/bin/python -m eval.run --split dev --variant claude_cli --repeats 3
    .venv/bin/python -m eval.run --split dev --variant sistema_api --repeats 1      # API de Claude (ANTHROPIC_API_KEY)
    .venv/bin/python -m eval.run --split test --variant claude_cli --i-know-this-is-final

- Corre contra el sistema real (API FastAPI en proceso, tools y base reales) en una base cuyo nombre contiene
  "_test" (EVAL_DATABASE_URL o <servidor de TEST_DATABASE_URL>/bank_eval_test), con el esquema app vacío en cada caso.
- --variant elige eval/variants/<nombre>.toml (variables de entorno: proveedor LLM, clasificador de intención…).
- El split test está congelado: sin --i-know-this-is-final se niega, y cada ejecución queda en eval/results/test_runs.log.
"""
from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Callable

import psycopg

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.run")
    ap.add_argument("--split", choices=["dev", "dev_paraphrase", "dev_noisy", "test"], required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--cases", nargs="*", help="solo estos case_id")
    ap.add_argument("--i-know-this-is-final", action="store_true", dest="final")
    ap.add_argument("--set", action="append", default=[], metavar="CLAVE=VALOR",
                    help="sobrescribe una variable de la variante (p. ej. --set LLM_PROVIDER=fake); queda en el reporte")
    args = ap.parse_args(argv)

    if args.split == "test":
        if not args.final:
            print("El split test está congelado: se corre una vez, al final, con --i-know-this-is-final.", file=sys.stderr)
            return 2
        RESULTS.mkdir(exist_ok=True)
        with open(RESULTS / "test_runs.log", "a", encoding="utf-8") as f:
            commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{getpass.getuser()}\t{args.variant}\trepeats={args.repeats}\t{commit}\n")

    variant = load_variant(args.variant, dict(x.split("=", 1) for x in args.set))
    if variant is None:
        return 2

    from eval.cases.schema import load_cases

    cases = load_cases(args.split)
    if args.cases:
        cases = [c for c in cases if c.case_id in set(args.cases)]
    if not cases:
        print(f"no hay casos en eval/cases/{args.split}/", file=sys.stderr)
        return 1
    command = "python -m eval.run " + " ".join(sys.argv[1:] if argv is None else argv)
    _, _, md, raw = run_cases(cases, args.variant, variant, args.repeats, args.split, command)
    print(f"reporte: {md}\ncrudo:   {raw}")
    return 0


def load_variant(name: str, overrides: dict[str, str]) -> dict | None:
    """Lee eval/variants/<name>.toml, aplica los --set y deja sus variables en el entorno ANTES de crear la app."""
    vfile = ROOT / "variants" / f"{name}.toml"
    if not vfile.exists():
        print(f"no existe {vfile}", file=sys.stderr)
        return None
    variant = tomllib.loads(vfile.read_text(encoding="utf-8"))
    from dotenv import load_dotenv
    load_dotenv(ROOT.parent / ".env", override=False)          # p. ej. ANTHROPIC_API_KEY; el entorno manda
    os.environ.setdefault("RATE_LIMITS_ENABLED", "false")      # el harness mide comportamiento, no los límites de peticiones
    variant.setdefault("env", {}).update(overrides)
    variant["overrides"] = overrides
    os.environ.update({k: str(v) for k, v in variant.get("env", {}).items()})   # antes de crear la app
    return variant


def run_cases(cases: list, variant_name: str, variant: dict, repeats: int, split: str, command: str,
              prepare: Callable | None = None) -> tuple[list, dict, Path, Path]:
    """Corre los casos contra el sistema en proceso y escribe el reporte. `prepare(urls, ref_date, cases)` puede ajustar
    los casos ya con la base lista (p. ej. eval/generated ajusta el pick a las filas que tiene cada selector)."""
    from fastapi.testclient import TestClient

    from backend.app.config import Settings
    from backend.app.main import create_app
    from eval.harness.checkers import run_checks
    from eval.harness.env import ensure_eval_db, eval_urls, plain
    from eval.harness.metrics import Scored, write_report
    from eval.harness.runner import CaseRunner

    overrides = variant.get("overrides", {})
    urls = eval_urls()
    ensure_eval_db(urls)
    with psycopg.connect(plain(urls["admin"])) as c:
        ref_date = c.execute("SELECT max(transaction_date)::date FROM ref.transactions").fetchone()[0]
    if prepare:
        cases = prepare(urls, ref_date, cases)
    settings = Settings(database_url=urls["app"], console_database_url=urls["console"], reference_date=ref_date, _env_file=None)
    app = create_app(settings)
    config = {"variant": variant_name + ("+" + ",".join(f"{k}={v}" for k, v in overrides.items()) if overrides else ""),
              "env": variant.get("env", {}), "command": command, "description": variant.get("description"),
              "split": split, "n_cases": len(cases), "repeats": repeats, "reference_date": str(ref_date),
              "database": urls["name"], "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "git_dirty": bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip())}
    runs_by_repeat = []
    t0 = time.time()
    with TestClient(app) as client:
        ctl = app.state.controller
        config["versions"] = {"ml": ctl.ml.versions(), "llm_provider": ctl.nodes.config.provider, "llm_models": ctl.nodes.config.models, "llm_model_ids": ctl.nodes.config.model_ids,
                              "prompts": {n: __import__("backend.app.llm.nodes", fromlist=["load_prompt"]).load_prompt(n)[1]
                                          for n in ctl.nodes.config.models}}
        runner = CaseRunner(app, urls, ref_date)
        for rep in range(1, repeats + 1):
            scored = []
            for i, case in enumerate(cases, 1):
                run = runner.run(client, case, rep, variant_name)
                s = Scored(run, run_checks(run))
                scored.append(s)
                mark = "ok" if s.all_pass else "FALLA " + ",".join(c.name for c in s.checks if not c.passed)
                print(f"[rep {rep} {i:02d}/{len(cases)} {time.time() - t0:6.0f}s] {case.case_id:32s} {s.outcome:24s} {mark}", flush=True)
            runs_by_repeat.append(scored)
    name = variant_name + "".join(f"+{k.lower()}-{v}" for k, v in overrides.items())   # p. ej. sistema+llm_provider-fake
    out_dir = RESULTS / "generated" if split == "generated" else RESULTS      # los generados viven en la base; sus .md no se versionan
    md, raw = write_report(runs_by_repeat, name, config, out_dir, split)
    return runs_by_repeat, config, md, raw

if __name__ == "__main__":
    sys.exit(main())
