"""Clasificadores de intención: reglas de palabras clave (baseline) y LLM (nodo intent)."""
from __future__ import annotations

from backend.app.llm.nodes import Nodes, load_prompt
from backend.app.llm.schemas import IntentOutput
from backend.app.ml import keyword_rules
from backend.app.ml.base import IntentClassifier, IntentPrediction


class KeywordIntentClassifier(IntentClassifier):
    implementation = "keyword"
    version = "keyword@v1"

    async def classify(self, text: str) -> IntentPrediction:
        return IntentPrediction(IntentOutput.model_validate(keyword_rules.classify(text)), self.implementation, self.version)


class LLMIntentClassifier(IntentClassifier):
    implementation = "llm"

    def __init__(self, nodes: Nodes):
        self.nodes = nodes
        self.version = load_prompt("intent")[1]

    async def classify(self, text: str) -> IntentPrediction:
        res = await self.nodes.intent(text)
        return IntentPrediction(res.data, self.implementation, res.prompt_version, llm=res)
