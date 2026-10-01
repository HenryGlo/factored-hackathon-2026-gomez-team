"""Modelo pequeño de intención (TF-IDF + regresión logística calibrada) y su carga segura.

El entrenamiento vive en ml/intent/train.py; aquí solo está lo que el backend necesita en ejecución: el preprocesado
(que el modelo serializado referencia por nombre) y la carga del artefacto con sus metadatos.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.dates import normalize

MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "intent"


def preprocess(text: str) -> str:
    """Minúsculas sin tildes; los números se vuelven '0' (el monto no decide la intención) y los espacios se compactan."""
    return re.sub(r"\s+", " ", re.sub(r"\d+([.,]\d+)*", "0", normalize(text))).strip()


def needs_llm(text: str) -> str | None:
    """Motivo por el que un mensaje va SIEMPRE al LLM aunque el modelo pequeño esté seguro; None si puede decidir solo.
    El modelo pequeño da una sola intención y no detecta manipulación: esos casos no son suyos."""
    from backend.app.ml import keyword_rules
    t = normalize(text)
    if re.search(keyword_rules.MANIPULATION, t):
        return "manipulacion"
    rules = keyword_rules.classify(text)
    if rules["multiples_intenciones"] or rules["otras_intenciones"]:
        return "varias_intenciones"
    if len(text) > 400:
        return "mensaje_largo"
    return None


@dataclass
class LoadedIntentModel:
    pipeline: Any
    meta: dict

    @property
    def version(self) -> str:
        return str(self.meta["version"])

    @property
    def classes(self) -> list[str]:
        return list(self.pipeline.classes_)

    def predict(self, text: str) -> tuple[str, float]:
        """(intención, probabilidad calibrada de esa intención)."""
        proba = self.pipeline.predict_proba([text])[0]
        i = int(proba.argmax())
        return self.classes[i], float(proba[i])


def load_model(version: str, models_dir: Path = MODELS_DIR) -> LoadedIntentModel:
    """Carga models/intent/<version>.joblib verificando el hash de <version>.json. Lanza si falta o no coincide."""
    import joblib

    meta = json.loads((models_dir / f"{version}.json").read_text(encoding="utf-8"))
    blob = (models_dir / f"{version}.joblib").read_bytes()
    if hashlib.sha256(blob).hexdigest() != meta["artifact_sha256"]:
        raise ValueError(f"el artefacto de {version} no coincide con su hash")
    return LoadedIntentModel(joblib.load(models_dir / f"{version}.joblib"), meta)
