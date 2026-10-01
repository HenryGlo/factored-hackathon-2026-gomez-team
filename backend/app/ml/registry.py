"""Construye los componentes de ML según backend/config/ml.toml (+ overrides de entorno)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from backend.app.llm.nodes import Nodes
from backend.app.ml.base import ClarifyPolicy, IntentClassifier, Ranker, RiskModel
from backend.app.ml.clarify import ThresholdClarifyPolicy
from backend.app.ml.intent import KeywordIntentClassifier, LLMIntentClassifier
from backend.app.ml.ranker import RuleRanker
from backend.app.ml.risk import RawFraudScoreRisk

CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "ml.toml"


@dataclass
class MLComponents:
    intent: IntentClassifier
    ranker: Ranker
    risk: RiskModel
    clarify: ClarifyPolicy

    def versions(self) -> dict[str, str]:
        return {"intent": self.intent.version, "ranker": self.ranker.version, "risk": self.risk.version,
                "clarify": self.clarify.version}


def build_ml(nodes: Nodes | None, env: dict[str, str] | None = None, path: Path = CONFIG_FILE) -> MLComponents:
    env = dict(os.environ if env is None else env)
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    num = lambda key, section, name: float(env.get(key) or cfg[section][name])
    kind = env.get("INTENT_CLASSIFIER") or cfg["components"]["intent_classifier"]
    if kind == "keyword":
        intent: IntentClassifier = KeywordIntentClassifier()
    elif kind == "llm":
        if nodes is None:
            raise ValueError("INTENT_CLASSIFIER=llm requiere los nodos LLM")
        intent = LLMIntentClassifier(nodes)
    else:
        raise ValueError(f"INTENT_CLASSIFIER={kind!r}: usar keyword o llm")
    if (r := env.get("RANKER") or cfg["components"]["ranker"]) != "rule":
        raise ValueError(f"RANKER={r!r}: por ahora solo rule")
    if (m := env.get("RISK_MODEL") or cfg["components"]["risk_model"]) != "raw_fraud_score":
        raise ValueError(f"RISK_MODEL={m!r}: por ahora solo raw_fraud_score")
    return MLComponents(
        intent=intent,
        ranker=RuleRanker(temperature=num("RANKER_TEMPERATURE", "ranker", "temperature"), recency_days=cfg["ranker"]["recency_days"]),
        risk=RawFraudScoreRisk(threshold=num("RISK_THRESHOLD", "risk", "threshold"), medium_threshold=cfg["risk"]["medium_threshold"]),
        clarify=ThresholdClarifyPolicy(tau=num("CLARIFY_TAU", "clarify", "tau"), delta=num("CLARIFY_DELTA", "clarify", "delta"),
                                       amount_tolerance=num("AMOUNT_TOLERANCE", "clarify", "amount_tolerance")))
