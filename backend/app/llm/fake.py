"""Cliente LLM falso: respuestas deterministas por nodo, sin red. Para tests, el baseline del
harness y demos sin conexión (LLM_PROVIDER=fake).

intent y extract usan las reglas de palabras clave; clarify, confirm, explain y handoff_summary
usan plantillas fijas por idioma. Pasa por la misma validación de esquema que el cliente real.
"""
from __future__ import annotations

import json
import re
import time

from backend.app.llm.client import LLMClient, LLMResult
from backend.app.ml import keyword_rules

CONFIRM = {
    "es": {"confirmar_movimiento": "¿Es este el movimiento al que te refieres? {comercio} por {monto} el {fecha}.",
           "confirmar_reclamo": "Voy a registrar un reclamo por el cargo de {comercio} por {monto} del {fecha}. "
                                "No es una devolución: el banco revisará el caso. ¿Confirmas?",
           "confirmar_bloqueo": "Voy a bloquear tu tarjeta {tarjeta}. Mientras esté bloqueada no podrás usarla. ¿Confirmas?"},
    "pt": {"confirmar_movimiento": "É esta a movimentação a que você se refere? {comercio}, {monto}, em {fecha}.",
           "confirmar_reclamo": "Vou registrar uma reclamação pela cobrança de {comercio} de {monto} em {fecha}. "
                                "Não é uma devolução: o banco vai analisar o caso. Você confirma?",
           "confirmar_bloqueo": "Vou bloquear o seu cartão {tarjeta}. Enquanto estiver bloqueado, não poderá usá-lo. Você confirma?"},
}
CLARIFY = {"es": {"fecha": "Encontré varios cargos parecidos. ¿Recuerdas qué día fue?",
                  "monto": "Encontré varios cargos. ¿Recuerdas el monto aproximado?",
                  "comercio": "Encontré varios cargos. ¿Recuerdas en qué comercio fue?",
                  "tipo_problema": "¿No reconoces el cargo, te cobraron de más o te cobraron dos veces?"},
           "pt": {"fecha": "Encontrei várias cobranças parecidas. Você lembra em que dia foi?",
                  "monto": "Encontrei várias cobranças. Você lembra o valor aproximado?",
                  "comercio": "Encontrei várias cobranças. Você lembra em qual estabelecimento foi?",
                  "tipo_problema": "Você não reconhece a cobrança, cobraram a mais ou cobraram duas vezes?"}}
EXPLAIN = {"es": "Listo con tu solicitud: {detalle} Si necesitas algo más, escríbeme.",
           "pt": "Pronto: {detalle} Se precisar de algo mais, é só escrever."}


class FakeLLMClient(LLMClient):
    provider = "fake"

    def _payload(self, node: str, user_content: str) -> dict:
        if node in ("intent", "extract"):
            text = re.sub(r"</?mensaje_cliente>", "", user_content).strip()
            return keyword_rules.classify(text) if node == "intent" else keyword_rules.extract(text)
        data = json.loads(user_content.split("\n\nAfirmaciones del cliente")[0])
        lang = data.get("idioma") or data.get("idioma_cliente") or "es"
        if node == "clarify":
            return {"pregunta": CLARIFY[lang].get(data["atributo_discriminante"], CLARIFY[lang]["fecha"])}
        if node == "confirm":
            text = CONFIRM[lang][data["accion"]]
            allowed = {p.strip("{}") for p in data["marcadores_disponibles"]}
            # deja solo los marcadores disponibles
            text = re.sub(r"\{([a-z_]+)\}", lambda m: m.group(0) if m.group(1) in allowed else "", text)
            return {"texto": re.sub(r"\s+([,.?])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()}
        if node == "explain":
            rules = ", ".join(f"{r.get('id')}: {r.get('motivo') or r.get('resultado')}" for r in data.get("reglas_activadas", []))
            marks = " ".join(data.get("marcadores_disponibles", []))
            detalle = f"resultado {data['resultado']}" + (f" ({rules})." if rules else ".") + (f" Referencia: {marks}." if marks else "")
            return {"texto": EXPLAIN[lang].format(detalle=detalle)}
        if node == "handoff_summary":
            return {"resumen": f"Caso escalado por {data['motivo_escalamiento']}. Idioma del cliente: {data['idioma_cliente']}. "
                               f"Hechos verificados: {json.dumps(data['hechos_verificados'], ensure_ascii=False)}.",
                    "preguntas_abiertas": [f"Revisar el motivo de escalamiento: {data['motivo_escalamiento']}."]}
        raise ValueError(node)

    async def complete_json(self, node, system_prompt, user_content, schema, model, prompt_version) -> LLMResult:
        t0 = time.perf_counter()
        data = schema.model_validate(self._payload(node, user_content))
        return LLMResult(data=data, node=node, model=model, model_id="fake", prompt_version=prompt_version,
                         latency_ms=round((time.perf_counter() - t0) * 1000), cost_usd=0.0, provider=self.provider)
