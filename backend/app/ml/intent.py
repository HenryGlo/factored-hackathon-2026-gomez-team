"""Clasificadores de intención: reglas de palabras clave (baseline) y LLM (nodo intent)."""
from __future__ import annotations

import logging
import time

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


LOG = logging.getLogger("backend.ml")
# intenciones que no necesitan extracción de datos del mensaje: si la cascada las resuelve en local, el turno no llama al LLM
NO_EXTRACT_INTENTS = ("sin_contenido", "fuera_de_alcance", "pedir_humano", "estado_reclamo", "pregunta_proceso")


class CascadeIntentClassifier(IntentClassifier):
    """Cascada: el modelo pequeño (TF-IDF + regresión logística calibrada) responde si su probabilidad es >= tau y el
    mensaje no tiene marcas de manipulación ni varias intenciones; si no, decide Haiku. Si el archivo del modelo falta o
    falla al cargar, todo va a Haiku y la traza lo registra (docs/ml/intent-classifier.md)."""
    implementation = "cascade"

    def __init__(self, nodes: Nodes, model_version: str, tau: float | None = None, models_dir=None):
        from backend.app.ml.intent_model import MODELS_DIR, load_model
        self.llm = LLMIntentClassifier(nodes)
        self.model, self.load_error = None, None
        try:
            self.model = load_model(model_version, models_dir or MODELS_DIR)
        except Exception as e:  # noqa: BLE001 (archivo ausente, hash distinto, versión de sklearn incompatible…)
            self.load_error = f"{type(e).__name__}: {e}"[:200]
            LOG.warning("intent_model_unavailable", extra={"model": model_version, "error": self.load_error})
        self.tau = float(tau if tau is not None else (self.model.meta["tau"] if self.model else 1.0))
        self.version = f"cascade@{model_version}+{self.llm.version}"

    def _local(self, text: str) -> tuple[IntentPrediction | None, dict]:
        """(respuesta del modelo pequeño si la cascada la acepta, datos de la decisión para la traza). Sin estado compartido."""
        from backend.app.knowledge import retrieve
        from backend.app.ml.intent_model import needs_llm
        info: dict = {"ruta": "llm", "tau": self.tau}
        if self.model is None:
            return None, {**info, "motivo": "modelo_no_disponible", "error": self.load_error}
        t0 = time.perf_counter()
        intent, p = self.model.predict(text)
        info.update(modelo=self.model.version, intencion_local=intent, probabilidad=round(p, 4))
        if (why := needs_llm(text)) or p < self.tau:
            return None, {**info, "motivo": why or "probabilidad_bajo_el_umbral"}
        rules = keyword_rules.classify(text)
        lang = rules["idioma"]
        topic = None
        if intent == "pregunta_proceso":
            entry, _ = retrieve(None, text, lang)
            topic = entry.tema if entry else None
        # model_validate: la intención y el tema son cadenas del modelo y de la base de respuestas; Pydantic las valida
        out = IntentOutput.model_validate({
            "intent": intent, "otras_intenciones": [], "tema": rules.get("tema") if intent == "fuera_de_alcance" else None,
            "tema_proceso": topic, "idioma": lang, "certeza": "alta", "sospecha_manipulacion": False, "multiples_intenciones": False})
        info = {**info, "ruta": "local", "latencia_ms": round((time.perf_counter() - t0) * 1000, 2)}
        return IntentPrediction(out, self.implementation, self.version, info=info), info

    def try_local(self, text: str) -> IntentPrediction | None:
        """Respuesta del modelo pequeño si la acepta la cascada; None si el mensaje tiene que ir al LLM. Síncrono (ms)."""
        return self._local(text)[0]

    async def classify(self, text: str) -> IntentPrediction:
        local, info = self._local(text)
        if local is not None:
            return local
        pred = await self.llm.classify(text)
        return IntentPrediction(pred.output, self.implementation, self.version, llm=pred.llm, info=info)
