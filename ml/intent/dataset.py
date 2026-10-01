"""Conjunto de entrenamiento y validación del clasificador de intención.

Filas reales: mensajes de dev y dev_paraphrase que llegan al clasificador (ml/intent/data/labels.yaml; las paráfrasis
heredan la etiqueta del paso original). Los mensajes son PLANTILLAS con marcadores ({monto_es}, {comercio}…): se rellenan
con valores inventados y deterministas, así en el repo y en el modelo no entra ningún valor del dataset.
Filas sintéticas: ml/intent/data/synthetic.jsonl (solo para entrenar).

Grupos (para validación cruzada sin fuga): un grupo por caso original con sus paráfrasis; además, dos mensajes con el mismo
texto normalizado caen en el mismo grupo (muchos casos empiezan con la misma frase).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.app.ml.intent_model import preprocess
from eval.cases.schema import load_cases

DATA = Path(__file__).resolve().parent / "data"
MERCHANTS = ["Supermercado La Esquina", "Farmacia Central", "TiendaNet", "Gasolinera Ruta 9", "Café Aroma", "Mercado Bom Preço",
             "Loja Estrela", "Streaming Plus", "Librería Sol", "Padaria do Bairro"]
FILL = {
    "monto": lambda r: random.Random(r).choice(["120", "45,90", "1.250", "89,99", "300", "15.400", "72,35"]),
    "moneda_es": lambda r: random.Random(r).choice(["dólares", "pesos", "USD"]),
    "moneda_pt": lambda r: random.Random(r).choice(["reais", "dólares", "USD"]),
    "comercio": lambda r: random.Random(r).choice(MERCHANTS),
    "fecha_es": lambda r: random.Random(r).choice(["3 de junio", "12 de mayo", "28 de abril"]),
    "fecha_pt": lambda r: random.Random(r).choice(["3 de junho", "12 de maio", "28 de abril"]),
    "fecha": lambda r: random.Random(r).choice(["03/06", "12/05", "28/04"]),
    "mes_es": lambda r: random.Random(r).choice(["mayo", "junio"]),
    "mes_pt": lambda r: random.Random(r).choice(["maio", "junho"]),
    "categoria_es": lambda r: random.Random(r).choice(["en un restaurante", "en una tienda de ropa", "en una gasolinera"]),
    "categoria_pt": lambda r: random.Random(r).choice(["num restaurante", "numa loja de roupas", "num posto"]),
    "foreign_customer": lambda r: "de otra persona",
}


@dataclass(frozen=True)
class Row:
    text: str
    intent: str
    language: str
    source: str          # dev | dev_paraphrase | synthetic
    group: str           # grupo de validación cruzada
    key: str             # case_id|paso (reales) o syn-<n>


def fill_template(template: str, seed: str) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1).removeprefix("second_")
        for prefix, fn in FILL.items():
            if name == prefix or name.startswith(prefix):
                return fn(f"{seed}:{name}")
        return "algo"
    return re.sub(r"\{([a-z_]+)\}", sub, template)


def real_rows() -> list[Row]:
    labels = {(x["case_id"], x["step"]): x["intent"] for x in yaml.safe_load((DATA / "labels.yaml").read_text(encoding="utf-8"))}
    haiku = json.loads((DATA / "haiku_predictions.json").read_text(encoding="utf-8"))
    dev_ids = {c.case_id for c in load_cases("dev")}
    rows, parent = [], {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pending = []
    for split in ("dev", "dev_paraphrase"):
        for c in load_cases(split):
            base = c.case_id if c.case_id in dev_ids else re.sub(r"-p\d+$", "", c.case_id)
            for i, step in enumerate(c.steps):
                intent = labels.get((c.case_id, i)) or (labels.get((base, i)) if split == "dev_paraphrase" else None)
                if step.message is None or intent is None or f"{c.case_id}|{i}" not in haiku:
                    continue
                text = fill_template(step.message, f"{c.case_id}:{i}")
                same = "text:" + preprocess(re.sub(r"\{[a-z_]+\}", "X", step.message))     # misma plantilla → mismo grupo
                pending.append((text, intent, c.language, split, f"{c.case_id}|{i}", f"case:{base}", same))
                parent[find(same)] = find(f"case:{base}")
    for text, intent, lang, split, key, case_group, _ in pending:
        rows.append(Row(text, intent, lang, split, find(case_group), key))
    return rows


def synthetic_rows() -> list[Row]:
    out = []
    for n, line in enumerate((DATA / "synthetic.jsonl").read_text(encoding="utf-8").splitlines()):
        r = json.loads(line)
        out.append(Row(r["text"], r["intent"], r["language"], "synthetic", f"syn:{n}", f"syn-{n}"))
    return out


def data_hash(rows: list[Row]) -> str:
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: r.key):
        h.update(f"{r.key}\t{r.intent}\t{r.text}\n".encode())
    return h.hexdigest()
