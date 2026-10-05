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
                  "tipo_problema": "¿No reconoces el cargo, te cobraron de más o te cobraron dos veces?",
                  "mas_datos": "No encontré cargos que coincidan en los últimos {dias} días. ¿Puedes darme el monto, la fecha o el comercio?",
                  "mas_datos_rechazo": "Entiendo. ¿Me das algún dato más del cargo (monto, fecha o comercio)?",
                  "reformular": "No me quedó claro cuál de estos cargos es. ¿Me dices el monto, la fecha o el comercio del que quieres reclamar?"},
           "pt": {"fecha": "Encontrei várias cobranças parecidas. Você lembra em que dia foi?",
                  "monto": "Encontrei várias cobranças. Você lembra o valor aproximado?",
                  "comercio": "Encontrei várias cobranças. Você lembra em qual estabelecimento foi?",
                  "tipo_problema": "Você não reconhece a cobrança, cobraram a mais ou cobraram duas vezes?",
                  "mas_datos": "Não encontrei cobranças que coincidam nos últimos {dias} dias. Pode me dizer o valor, a data ou o estabelecimento?",
                  "mas_datos_rechazo": "Entendi. Pode me dar mais algum dado da cobrança (valor, data ou estabelecimento)?",
                  "reformular": "Não ficou claro para mim qual destas cobranças é. Pode me dizer o valor, a data ou o estabelecimento da que quer contestar?"}}
EXPLAIN = {
    "es": {"reclamo_registrado": "Registré tu reclamo con el número {numero_reclamo}. El banco lo revisará; esto no es una devolución.",
           "cargo_pendiente": "El cargo todavía está pendiente y puede cambiar, por eso aún no se registra un reclamo.",
           "sin_cargo_vigente": "Ese movimiento fue rechazado o revertido, así que no hay un cargo vigente que reclamar.",
           "reclamo_existente": "Ya existe un reclamo abierto sobre este cargo ({numero_reclamo}); no hace falta abrir otro.",
           "default": "Revisé tu solicitud: {detalle}"},
    "pt": {"reclamo_registrado": "Registrei a sua reclamação com o número {numero_reclamo}. O banco vai analisar; isto não é uma devolução.",
           "cargo_pendiente": "A cobrança ainda está pendente e pode mudar, por isso ainda não é registrada uma reclamação.",
           "sin_cargo_vigente": "Essa movimentação foi recusada ou estornada, então não há cobrança vigente para contestar.",
           "reclamo_existente": "Já existe uma reclamação aberta sobre esta cobrança ({numero_reclamo}); não é preciso abrir outra.",
           "default": "Analisei a sua solicitação: {detalle}"},
}


FAQ_CONTEXT = {"es": {"reclamo": "Sobre tu reclamo {numero_reclamo} ({comercio}, {monto}):", "tarjeta": "Sobre tu tarjeta {tarjeta}:"},
               "pt": {"reclamo": "Sobre a sua reclamação {numero_reclamo} ({comercio}, {monto}):", "tarjeta": "Sobre o seu cartão {tarjeta}:"}}


class FakeLLMClient(LLMClient):
    provider = "fake"

    def _payload(self, node: str, user_content: str) -> dict:
        if node in ("intent", "extract"):
            text = re.sub(r"</?mensaje_cliente>", "", user_content).strip()
            return keyword_rules.classify(text) if node == "intent" else keyword_rules.extract(text)
        data = json.loads(user_content.split("\n\nAfirmaciones del cliente")[0])
        lang = data.get("idioma") or data.get("idioma_cliente") or "es"
        if node == "clarify":
            key = data["atributo_discriminante"]
            if key == "mas_datos" and "dias_buscados" not in data:
                key = "mas_datos_rechazo"      # el cliente descartó las opciones: no hace falta hablar de días
            return {"pregunta": CLARIFY[lang].get(key, CLARIFY[lang]["fecha"]).replace("{dias}", str(data.get("dias_buscados", "")))}
        if node == "confirm":
            text = CONFIRM[lang][data["accion"]]
            allowed = {p.strip("{}") for p in data["marcadores_disponibles"]}
            # deja solo los marcadores disponibles
            text = re.sub(r"\{([a-z_]+)\}", lambda m: m.group(0) if m.group(1) in allowed else "", text)
            return {"texto": re.sub(r"\s+([,.?])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()}
        if node == "explain":
            motivos = [r.get("motivo") for r in data.get("reglas_activadas", [])]
            key = data["resultado"] if data["resultado"] in EXPLAIN[lang] else next((m for m in motivos if m in EXPLAIN[lang]), "default")
            marks = {p.strip("{}") for p in data.get("marcadores_disponibles", [])}
            text = EXPLAIN[lang][key]
            if "{numero_reclamo}" in text and "numero_reclamo" not in marks:
                text = text.replace(" ({numero_reclamo})", "").replace(" con el número {numero_reclamo}", "").replace(" com o número {numero_reclamo}", "")
            return {"texto": text.replace("{detalle}", ", ".join(m for m in motivos if m) or data["resultado"])}
        if node == "faq_answer":
            hechos = data.get("hechos_del_caso") or {}
            if "referencia" in hechos:
                return {"contexto": FAQ_CONTEXT[lang]["reclamo"]}
            if "tarjeta" in hechos:
                return {"contexto": FAQ_CONTEXT[lang]["tarjeta"]}
            return {"contexto": ""}
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


# ---------------------------------------------------------------- inglés (2026-10-05)
CONFIRM["en"] = {"confirmar_movimiento": "Is this the transaction you mean? {comercio}, {monto}, on {fecha}.",
                 "confirmar_reclamo": "I'm going to file a claim for the charge from {comercio} of {monto} on {fecha}. "
                                      "This is not a refund: the bank will review the case. Do you confirm?",
                 "confirmar_bloqueo": "I'm going to block your card {tarjeta}. While it is blocked you won't be able to use it. Do you confirm?"}
CLARIFY["en"] = {"fecha": "I found several similar charges. Do you remember what day it was?",
                 "monto": "I found several charges. Do you remember the approximate amount?",
                 "comercio": "I found several charges. Do you remember at which merchant it was?",
                 "tipo_problema": "Don't you recognize the charge, were you charged too much, or were you charged twice?",
                 "mas_datos": "I didn't find matching charges in the last {dias} days. Can you give me the amount, the date or the merchant?",
                 "mas_datos_rechazo": "Got it. Can you give me another detail of the charge (amount, date or merchant)?",
                 "reformular": "It's not clear to me which of these charges it is. Can you tell me the amount, the date or the merchant of the one you want to dispute?"}
EXPLAIN["en"] = {"reclamo_registrado": "I filed your claim with number {numero_reclamo}. The bank will review it; this is not a refund.",
                 "cargo_pendiente": "The charge is still pending and may change, so a claim is not filed yet.",
                 "sin_cargo_vigente": "That transaction was declined or reversed, so there is no current charge to dispute.",
                 "reclamo_existente": "There is already an open claim for this charge ({numero_reclamo}); there's no need to open another one.",
                 "default": "I reviewed your request: {detalle}"}
FAQ_CONTEXT["en"] = {"reclamo": "About your claim {numero_reclamo} ({comercio}, {monto}):", "tarjeta": "About your card {tarjeta}:"}
