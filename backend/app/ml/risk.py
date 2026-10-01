"""Riesgo de fraude. Baseline: fraud_score/100 sin calibrar, con umbral configurable.

Medido en el dataset completo (2026-09-30): fraud_score >= 70 marca 999 transacciones y las 999
tienen is_fraud (precisión 100 %, recall 999/4.316 = 23 %). 885.157 transacciones no tienen
fraud_score: banda 'desconocido', que R6 no escala por sí sola (docs/policies.md).
La calibración real llega en el prompt 04 (E2).
"""
from __future__ import annotations

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
