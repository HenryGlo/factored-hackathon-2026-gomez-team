"""Etiquetas de intención de los mensajes de dev y predicciones de Haiku por mensaje, a partir de crudos del harness.

    python -m ml.intent.build_labels eval/results/raw/<sistema_api_dev>.json eval/results/raw/<sistema_api_dev_paraphrase>.json

Escribe (sin valores del dataset: solo case_id, paso e intención):
- ml/intent/data/labels.yaml: intención de cada mensaje de dev que llega al clasificador (estado `inicio`). Punto de partida:
  la intención de Haiku en una corrida donde el caso pasó todos los checkers; después, REVISIÓN A MANO (OVERRIDES).
  Un solo revisor: no hay doble anotación (limitación declarada en la ficha del modelo).
- ml/intent/data/haiku_predictions.json: lo que predijo Haiku para cada mensaje de dev y de dev_paraphrase (la vía "solo
  LLM" de la comparación y el respaldo de la cascada simulada).
Las paráfrasis heredan la etiqueta del caso original (mismo paso): no se etiquetan aparte.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent / "data"
# revisión a mano del 2026-10-01: Haiku leyó estas dos inyecciones como sin_contenido y estado_reclamo
OVERRIDES = {("dev-inyeccion-pt", 0): "fuera_de_alcance", ("dev-inyeccion-tema-es", 0): "fuera_de_alcance"}


def intents_by_step(raw: dict) -> dict[tuple[str, int], dict]:
    out = {}
    for c in raw["cases"]:
        by_turn = defaultdict(dict)
        for s in c["traces"] or []:
            if s["node"] == "intent" and s.get("output"):
                by_turn[s["turn_id"]] = s["output"]
        for t in c["turns"]:
            tid = (t.get("response") or {}).get("turn_id")
            if t["kind"] == "message" and tid in by_turn:
                out[(c["case_id"], t["step"])] = {"intent": by_turn[tid]["intent"], "passed": all(ch["passed"] for ch in c["checks"])}
    return out


def main(argv: list[str]) -> int:
    dev, para = (intents_by_step(json.loads(Path(p).read_text(encoding="utf-8"))) for p in argv)
    labels = [{"case_id": k[0], "step": k[1], "intent": OVERRIDES.get(k, v["intent"]), "source": "revisado" if k in OVERRIDES else "haiku+checkers"}
              for k, v in sorted(dev.items())]
    not_passed = [k for k, v in dev.items() if not v["passed"]]
    if not_passed:
        raise SystemExit(f"casos que no pasaron todos los checkers: revisar a mano antes de etiquetar: {not_passed}")
    (DATA / "labels.yaml").write_text(
        "# Intención de cada mensaje de dev que llega al clasificador. Generado por ml/intent/build_labels.py y revisado a mano\n"
        "# (source: revisado = corregido frente a Haiku). Las paráfrasis heredan la etiqueta del caso original.\n"
        + yaml.safe_dump(labels, allow_unicode=True, sort_keys=False), encoding="utf-8")
    preds = {f"{c}|{s}": v["intent"] for src in (dev, para) for (c, s), v in sorted(src.items())}
    (DATA / "haiku_predictions.json").write_text(json.dumps(preds, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"labels.yaml: {len(labels)} mensajes ({len(OVERRIDES)} corregidos); haiku_predictions.json: {len(preds)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
