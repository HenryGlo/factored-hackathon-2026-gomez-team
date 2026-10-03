"""Flujos generados a escala: generar, guardar en el esquema eval de la base local, correr una muestra y ver métricas.

    .venv/bin/python -m eval.generated generate --n 5000                  # lote combinatorio (gratis, sin LLM)
    .venv/bin/python -m eval.generated generate --n 5000 --claude 20      # + paráfrasis nuevas de 20 semillas con claude -p
    .venv/bin/python -m eval.generated run --variant sistema --set LLM_PROVIDER=fake --sample 500   # gratis
    .venv/bin/python -m eval.generated run --variant sistema_api --sample 1000                       # API: ≈ $7
    .venv/bin/python -m eval.generated report                             # última corrida (o --run N)
    .venv/bin/python -m eval.generated status                             # lotes y corridas

Para ensayar el proyecto basta `scripts/eval_generated.sh` (ver su encabezado). Diseño y tamaños: eval/generated/README.md.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path

from eval.generated import generator as gen
from eval.generated import store

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COST = {"anthropic_api": 0.0075, "claude_cli": 0.015}     # por caso, de eval/results (2026-10-01); fake = 0
API_CONFIRM_USD = 2.0                                             # sobre esto, la API pide --yes
CLI_CONFIRM_CASES = 300                                           # sobre esto, claude -p pide --yes (consume el cupo)


def cmd_generate(a) -> int:
    if a.if_missing:
        with store.connect() as conn:
            batch = store.latest_batch(conn)
        if batch is not None:
            print(f"   ya hay un lote ({batch}); se usa ese (--new-batch para generar otro)")
            return 0
    items = gen.generate(a.n, a.seed)
    if a.claude:
        items += claude_paraphrases(a.claude, a.seed, a.concurrency)
    with store.connect() as conn:
        batch = store.save_batch(conn, items, a.seed, {"n": a.n, "claude": a.claude, "seed_splits": list(gen.SEED_SPLITS)}, a.note)
    by = Counter((g.case.language, g.case.category) for g in items)
    print(f"lote {batch}: {len(items)} flujos de {len({g.seed_case_id for g in items})} semillas → eval.generated_cases")
    print("  " + ", ".join(f"{lang}·{cat} {n}" for (lang, cat), n in sorted(by.items())))
    return 0


def claude_paraphrases(k: int, seed: int, concurrency: int) -> list[gen.Generated]:
    """Paráfrasis nuevas (2 por semilla) de k semillas de dev con el generador del split dev_paraphrase (claude -p, Sonnet).
    Cuestan tokens una vez y NO están revisadas a mano: quedan con origin = parafrasis_claude para filtrarlas."""
    from backend.app.llm.claude_cli import ClaudeCLIClient
    from eval.cases.schema import Case, load_cases
    from eval.generator.paraphrase import generate_one

    seeds = [c for c in load_cases("dev") if any(s.message for s in c.steps) and c.expected.fast_path is not True]
    chosen = gen.stratified_sample(seeds, k, seed, key=lambda c: (c.language, c.category))

    async def go():
        client, sem = ClaudeCLIClient(timeout_seconds=180, retries=1), asyncio.Semaphore(concurrency)
        return await asyncio.gather(*(generate_one(client, sem, c, i + seed) for i, c in enumerate(chosen)))

    out = []
    results = asyncio.run(go())
    for case, res in zip(chosen, results):
        for v, msgs in enumerate(res.get("versions") or []):
            raw = case.model_dump(exclude_none=True)
            it = iter(msgs)
            for step in raw["steps"]:
                if step.get("message") is not None:
                    step["message"] = next(it)
            raw.update({"case_id": f"g-{case.case_id}-c{seed % 10000}-{v + 1}", "split": "generated",
                        "title": f"{case.title} · paráfrasis Claude sin revisar ({res['styles'][v]})"})
            out.append(gen.Generated(Case.model_validate(raw), case.case_id, "dev", "parafrasis_claude", case.pick, "", "ninguno"))
    print(f"paráfrasis con Claude: {len(out)} flujos de {sum(bool(r.get('versions')) for r in results)}/{k} semillas, "
          f"${sum(r.get('cost_usd') or 0 for r in results):.4f}")
    return out


def provider_of(variant: str, overrides: dict[str, str]) -> str:
    env = tomllib.loads((ROOT / "variants" / f"{variant}.toml").read_text(encoding="utf-8")).get("env", {})
    return overrides.get("LLM_PROVIDER") or env.get("LLM_PROVIDER") or "claude_cli"


def cmd_run(a) -> int:
    overrides = dict(x.split("=", 1) for x in a.set)
    if not (ROOT / "variants" / f"{a.variant}.toml").exists():
        print(f"no existe eval/variants/{a.variant}.toml", file=sys.stderr)
        return 2
    provider = provider_of(a.variant, overrides)
    with store.connect() as conn:
        batch = a.batch or store.latest_batch(conn)
        if batch is None:
            print("no hay lotes: correr primero `python -m eval.generated generate`", file=sys.stderr)
            return 1
        items = store.load_batch(conn, batch)
        label = a.variant + ("+" + ",".join(f"{k}={v}" for k, v in overrides.items()) if overrides else "")
        hist = store.cost_per_case(conn, label)
    if a.origin:
        items = [g for g in items if g.origin == a.origin]
    sample = gen.stratified_sample(items, a.sample, a.sample_seed)
    n = len(sample) * a.repeats
    if provider == "anthropic_api":
        per_case = hist or DEFAULT_COST["anthropic_api"]
        print(f"estimado: {n} casos × ${per_case:.4f} ≈ ${n * per_case:.2f} de API ({'histórico de esta variante' if hist else 'costo de referencia'})")
        if n * per_case > API_CONFIRM_USD and not a.yes:
            print(f"más de ${API_CONFIRM_USD:.0f}: repetir con --yes para confirmar", file=sys.stderr)
            return 3
    elif provider == "claude_cli":
        print(f"estimado: {n} casos con claude -p ≈ {n * 10 / 60:.0f} min y consumo de tu cupo de Claude Code")
        if n > CLI_CONFIRM_CASES and not a.yes:
            print(f"más de {CLI_CONFIRM_CASES} casos con claude -p: repetir con --yes para confirmar", file=sys.stderr)
            return 3
    else:
        print(f"{n} casos con LLM {provider}: sin costo")

    from eval.run import load_variant, run_cases

    variant = load_variant(a.variant, overrides)
    problem = preflight()
    if problem:
        print(f"el LLM ({provider}) no responde: {problem}\nNo se corre: los casos medirían las reglas de respaldo, no el modelo. "
              "Con claude -p, iniciar sesión en la CLI (`claude` y luego /login) desde la terminal donde se corre esto.", file=sys.stderr)
        return 4
    started = datetime.now().astimezone()
    command = "python -m eval.generated " + " ".join(sys.argv[1:])
    runs, config, md, raw = run_cases([g.case for g in sample], a.variant, variant, a.repeats, "generated", command,
                                      prepare=store.clamp_picks)
    with store.connect() as conn:
        run_id = store.save_run(conn, batch, started, config, runs, len(sample), a.sample_seed, str(md.relative_to(ROOT.parent)))
        text = store.report(conn, run_id)
    print("\n" + text)
    print(f"corrida {run_id} en eval.runs / eval.case_results (vista eval.v_results)\nreporte del harness: {md}\ncrudo:   {raw}")
    return 0


def preflight() -> str | None:
    """Una llamada mínima al LLM de la variante antes de correr cientos de casos. None si responde (o si es el falso)."""
    from pydantic import BaseModel

    from backend.app.llm.client import LLMError
    from backend.app.llm.config import load_llm_config
    from backend.app.llm.factory import make_client

    class Ok(BaseModel):
        ok: bool

    cfg = load_llm_config()
    if cfg.provider == "fake":
        return None
    try:
        asyncio.run(make_client(cfg).complete_json("preflight", 'Responde exactamente {"ok": true}.', "ok", Ok,
                                                   cfg.model_for("intent"), "preflight@v1"))
    except LLMError as e:
        return e.message
    return None


def cmd_report(a) -> int:
    with store.connect() as conn:
        run_id = a.run or conn.execute("SELECT max(run_id) AS r FROM eval.runs").fetchone()["r"]
        if run_id is None:
            print("todavía no hay corridas", file=sys.stderr)
            return 1
        print(store.report(conn, run_id))
    return 0


def cmd_status(_a) -> int:
    with store.connect() as conn:
        print(store.status(conn))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.generated", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="genera un lote y lo guarda en eval.generated_cases")
    g.add_argument("--n", type=int, default=5000, help="flujos combinatorios (por defecto 5000)")
    g.add_argument("--seed", type=int, default=20261002)
    g.add_argument("--claude", type=int, default=0, metavar="K", help="además, 2 paráfrasis nuevas de K semillas con claude -p (cuesta tokens)")
    g.add_argument("--concurrency", type=int, default=3)
    g.add_argument("--note")
    g.add_argument("--if-missing", action="store_true", help="no genera si ya hay un lote")
    r = sub.add_parser("run", help="corre una muestra estratificada de un lote y guarda los resultados")
    r.add_argument("--variant", required=True, help="eval/variants/<nombre>.toml")
    r.add_argument("--set", action="append", default=[], metavar="CLAVE=VALOR", help="p. ej. --set LLM_PROVIDER=fake (gratis)")
    r.add_argument("--sample", type=int, default=200, help="flujos de la muestra (por defecto 200)")
    r.add_argument("--sample-seed", type=int, default=1)
    r.add_argument("--batch", type=int, help="lote (por defecto el último)")
    r.add_argument("--origin", choices=["combinatorio", "parafrasis_claude"], help="solo flujos de ese origen")
    r.add_argument("--repeats", type=int, default=1)
    r.add_argument("--yes", action="store_true", help="confirma una corrida cara (API sobre $2 o más de 300 casos con claude -p)")
    p = sub.add_parser("report", help="métricas de una corrida desde la base")
    p.add_argument("--run", type=int)
    sub.add_parser("status", help="lotes y corridas")
    a = ap.parse_args(argv)
    return {"generate": cmd_generate, "run": cmd_run, "report": cmd_report, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
