"""Split de estrés dev_paraphrase: 2 paráfrasis de los mensajes del cliente de cada caso de dev.

    .venv/bin/python -m eval.generator.paraphrase generate        # llama a claude -p --model sonnet
    .venv/bin/python -m eval.generator.paraphrase sample --n 10   # muestra N al azar (semilla fija) para revisar a mano
    .venv/bin/python -m eval.generator.paraphrase build           # escribe eval/cases/dev_paraphrase/cases.yaml

- El generador ve SOLO el escenario (título del caso), la conversación original (mensajes del cliente y qué botones
  toca) y un estilo. No ve las reglas de palabras clave, los selectores, los checkers ni el resultado esperado.
- Los marcadores ({monto_es}…) se conservan: cada caso parafraseado usa el mismo selector y el mismo resultado esperado.
- generated.json guarda todas las paráfrasis (sin IDs del dataset); review.json, la revisión a mano: las que cambian el
  significado se descartan en build.
- Las paráfrasis de un LLM pueden favorecer a otro LLM: este split es de desarrollo, no la medida final.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from backend.app.llm.claude_cli import ClaudeCLIClient
from backend.app.llm.client import LLMError
from eval.cases.schema import Case, load_cases

HERE = Path(__file__).resolve().parent
PROMPT = HERE / "paraphrase_prompt.md"
GENERATED = HERE / "paraphrase_generated.json"
REVIEW = HERE / "paraphrase_review.json"
OUT = HERE.parent / "cases" / "dev_paraphrase" / "cases.yaml"
MODEL = "sonnet"
N_VERSIONS = 2
MARK = re.compile(r"\{([a-z_]+)\}")

REGIONS = {"es": ["México", "Colombia", "Argentina"], "pt": ["Brasil (São Paulo)", "Brasil (Nordeste)", "Brasil (Rio de Janeiro)"]}
STYLES = ["muy coloquial, con 2 o 3 errores de tipeo y sin tildes", "informal, con otro orden de la información y alguna muletilla",
          "apurado, frases cortas, abreviaturas de chat", "detallista, con contexto personal irrelevante y otro orden"]


class Paraphrases(BaseModel):
    versiones: list[list[str]] = Field(description="Una lista por estilo; cada una con todos los mensajes del cliente, en orden.")


def styles_for(case: Case, idx: int) -> list[str]:
    regions = REGIONS[case.language]
    return [f"{STYLES[(idx + k) % len(STYLES)]}; regionalismos de {regions[(idx + k) % len(regions)]}" for k in range(N_VERSIONS)]


def conversation(case: Case) -> list[dict]:
    conv = []
    for s in case.steps:
        if s.message is not None:
            conv.append({"mensaje": s.message})
        elif s.action is not None:
            conv.append({"boton": s.action})
    return conv


def validate(original: list[str], versions: list[list[str]]) -> list[str]:
    errors = []
    if len(versions) != N_VERSIONS:
        errors.append(f"se pidieron {N_VERSIONS} versiones, llegaron {len(versions)}")
    for v, msgs in enumerate(versions, 1):
        if len(msgs) != len(original):
            errors.append(f"versión {v}: {len(msgs)} mensajes en vez de {len(original)}")
            continue
        for i, (a, b) in enumerate(zip(original, msgs), 1):
            if set(MARK.findall(a)) != set(MARK.findall(b)):
                errors.append(f"versión {v}, mensaje {i}: marcadores {sorted(set(MARK.findall(b)))} en vez de {sorted(set(MARK.findall(a)))}")
            if re.sub(MARK, "", b).count("{") or re.sub(MARK, "", b).count("}"):
                errors.append(f"versión {v}, mensaje {i}: llaves sueltas")
            if not b.strip():
                errors.append(f"versión {v}, mensaje {i}: vacío")
    return errors


async def generate_one(client: ClaudeCLIClient, sem: asyncio.Semaphore, case: Case, idx: int) -> dict:
    system = PROMPT.read_text(encoding="utf-8")
    version = re.search(r"version:\s*([\w.@-]+)", system).group(1)
    original = [s.message for s in case.steps if s.message is not None]
    payload = {"idioma": case.language, "escenario": case.title, "conversacion": conversation(case), "estilos": styles_for(case, idx)}
    last_err = None
    async with sem:
        for attempt in (1, 2):
            try:
                res = await client.complete_json("paraphrase", system, json.dumps(payload, ensure_ascii=False, indent=1),
                                                 Paraphrases, MODEL, version)
            except LLMError as e:
                last_err = str(e)
                continue
            errors = validate(original, res.data.versiones)
            if not errors:
                print(f"  {case.case_id}: ok ({res.latency_ms} ms, ${res.cost_usd or 0:.4f})", flush=True)
                return {"case_id": case.case_id, "styles": payload["estilos"], "original": original, "versions": res.data.versiones,
                        "model_id": res.model_id, "prompt_version": version, "cost_usd": res.cost_usd, "attempt": attempt}
            last_err = "; ".join(errors)
    print(f"  {case.case_id}: FALLÓ ({last_err})", flush=True)
    return {"case_id": case.case_id, "styles": payload["estilos"], "original": original, "versions": None, "error": last_err}


async def generate(concurrency: int, only: list[str] | None) -> None:
    cases = [c for c in load_cases("dev") if any(s.message for s in c.steps)]
    if only:
        cases = [c for c in cases if c.case_id in set(only)]
    prev = {g["case_id"]: g for g in json.loads(GENERATED.read_text(encoding="utf-8"))["cases"]} if GENERATED.exists() and only else {}
    client = ClaudeCLIClient(timeout_seconds=180, retries=1)
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*(generate_one(client, sem, c, i) for i, c in enumerate(cases)))
    prev.update({r["case_id"]: r for r in results})
    order = [c.case_id for c in load_cases("dev")]
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "model": MODEL,
           "cases": sorted(prev.values(), key=lambda r: order.index(r["case_id"]))}
    GENERATED.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ok = sum(r["versions"] is not None for r in out["cases"])
    print(f"{ok}/{len(out['cases'])} casos con paráfrasis válidas; costo ${sum(r.get('cost_usd') or 0 for r in out['cases']):.4f} → {GENERATED}")


def items() -> list[tuple[str, dict, int]]:
    data = json.loads(GENERATED.read_text(encoding="utf-8"))
    return [(f"{g['case_id']}-p{v + 1}", g, v) for g in data["cases"] if g["versions"] for v in range(len(g["versions"]))]


def sample(n: int, seed: int) -> None:
    chosen = random.Random(seed).sample(items(), n)
    for pid, g, v in chosen:
        print(f"\n=== {pid}  ({g['styles'][v]})")
        for a, b in zip(g["original"], g["versions"][v]):
            print(f"  original:  {a}\n  paráfrasis: {b}")
    print(f"\nsemilla {seed}; ids: {' '.join(pid for pid, _, _ in chosen)}")


def build() -> None:
    review = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {"discarded": []}
    discarded = {d["id"] for d in review.get("discarded", [])}
    by_id = {c.case_id: c for c in load_cases("dev")}
    out = []
    for pid, g, v in items():
        if pid in discarded:
            continue
        case = by_id[g["case_id"]].model_dump(exclude_none=True, exclude_defaults=True)
        msgs = iter(g["versions"][v])
        for step in case["steps"]:
            if step.get("message") is not None:
                step["message"] = next(msgs)
        case.update({"case_id": pid, "split": "dev_paraphrase", "title": f"{case['title']} (paráfrasis {v + 1}: {g['styles'][v]})"})
        out.append(case)
    header = (f"# Split de estrés dev_paraphrase: generado por eval/generator/paraphrase.py con claude -p --model {MODEL}\n"
              f"# ({json.loads(GENERATED.read_text(encoding='utf-8'))['generated_at']}). Mismo selector y resultado esperado que el caso\n"
              f"# de dev original. Descartadas por revisión a mano: {sorted(discarded) or 'ninguna'}.\n"
              "# Paráfrasis de un LLM pueden favorecer a otro LLM: split de desarrollo, no la medida final. No editar a mano.\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(header + yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=160), encoding="utf-8")
    n = len(load_cases("dev_paraphrase"))
    print(f"{n} casos → {OUT} ({len(discarded)} descartados)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.generator.paraphrase")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--concurrency", type=int, default=3)
    g.add_argument("--cases", nargs="*")
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=10)
    s.add_argument("--seed", type=int, default=20260930)
    sub.add_parser("build")
    a = ap.parse_args(argv)
    if a.cmd == "generate":
        asyncio.run(generate(a.concurrency, a.cases))
    elif a.cmd == "sample":
        sample(a.n, a.seed)
    else:
        build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
