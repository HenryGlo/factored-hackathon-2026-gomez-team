"""Riesgo de fraude. Baseline: fraud_score/100 sin calibrar, con umbral configurable.

Medido en el dataset completo (2026-09-30): fraud_score >= 70 marca 999 transacciones y las 999
tienen is_fraud (precisión 100 %, recall 999/4.316 = 23 %). 885.157 transacciones no tienen
fraud_score: banda 'desconocido', que R6 no escala por sí sola (docs/policies.md).
La calibración real llega en el prompt 04 (E2).
"""
from __future__ import annotations

import bisect
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from backend.app.ml.base import RiskAssessment, RiskModel


class RawFraudScoreRisk(RiskModel):
    implementation = "raw_fraud_score"
    version = "raw_fraud_score@v1"

    def __init__(self, threshold: float = 0.70, medium_threshold: float = 0.35):
        if not 0 < medium_threshold < threshold <= 1:
            raise ValueError("se requiere 0 < medium_threshold < threshold <= 1")
        self.threshold, self.medium = threshold, medium_threshold

    def assess(self, transaction: dict[str, Any]) -> RiskAssessment:
        score = transaction.get("fraud_score")
        if score is None:
            return RiskAssessment(None, "desconocido", self.threshold, self.implementation, self.version, {"fraud_score": None})
        p = float(score) / 100
        band = "alto" if p >= self.threshold else "medio" if p >= self.medium else "bajo"
        return RiskAssessment(round(p, 4), band, self.threshold, self.implementation, self.version, {"fraud_score": float(score)})


LOG = logging.getLogger("backend.ml")
RISK_MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "risk"


class CalibratedFraudScoreRisk(RiskModel):
    """fraud_score calibrado con isotónica: probabilidad de `is_fraud` y bandas con umbral elegido por costo esperado
    (ml/fraud_risk/experiment.py, docs/ml/fraud-risk.md). El calibrador es una lista de puntos (score/100, probabilidad) en
    models/risk/<version>.json; entre puntos se interpola. Sin score sigue siendo `desconocido`: el experimento mostró que
    las variables del movimiento no separan el fraude. Si el archivo falta o no coincide con su hash, se usa el score crudo
    y la evaluación lo dice (`inputs_used.fallback`).

    La banda es una señal de MOVIMIENTO ANÓMALO para decidir ruta y prioridad; no declara un fraude."""
    implementation = "calibrated_fraud_score"

    def __init__(self, model_version: str, fallback: RawFraudScoreRisk, models_dir: Path = RISK_MODELS_DIR):
        self.fallback, self.load_error = fallback, None
        self.version = f"calibrated@{model_version}"
        try:
            meta = json.loads((models_dir / f"{model_version}.json").read_text(encoding="utf-8"))
            if hashlib.sha256(json.dumps(meta["points"]).encode()).hexdigest() != meta["points_sha256"]:
                raise ValueError("los puntos del calibrador no coinciden con su hash")
            self.xs, self.ys = [p[0] for p in meta["points"]], [p[1] for p in meta["points"]]
            self.threshold, self.medium = float(meta["threshold_high"]), float(meta["threshold_medium"])
        except Exception as e:  # noqa: BLE001
            self.load_error = f"{type(e).__name__}: {e}"[:200]
            LOG.warning("risk_model_unavailable", extra={"model": model_version, "error": self.load_error})

    def probability(self, score: float) -> float:
        x = min(max(score / 100, self.xs[0]), self.xs[-1])
        i = bisect.bisect_right(self.xs, x)
        if i >= len(self.xs):
            return self.ys[-1]
        x0, x1, y0, y1 = self.xs[i - 1], self.xs[i], self.ys[i - 1], self.ys[i]
        return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)

    def assess(self, transaction: dict[str, Any]) -> RiskAssessment:
        if self.load_error:
            raw = self.fallback.assess(transaction)
            return RiskAssessment(raw.probability, raw.band, raw.threshold, raw.implementation, raw.version,
                                  {**raw.inputs_used, "fallback": "raw_fraud_score", "error": self.load_error})
        score = transaction.get("fraud_score")
        if score is None:
            return RiskAssessment(None, "desconocido", self.threshold, self.implementation, self.version, {"fraud_score": None})
        p = self.probability(float(score))
        band = "alto" if p >= self.threshold else "medio" if p >= self.medium else "bajo"
        return RiskAssessment(round(p, 6), band, self.threshold, self.implementation, self.version, {"fraud_score": float(score)})
