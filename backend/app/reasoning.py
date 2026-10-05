"""Cómo decidió el asistente en cada turno, a partir de la traza (app.traces): qué entendió, qué datos usó, qué buscó,
qué riesgo y qué reglas de política aplicó, qué guardas actuaron y qué respondió.

No es una cadena de pensamiento del modelo (la traza no la guarda, ver controller/trace.py): son entradas, salidas y
decisiones registradas por el código. Dos usos, con el mismo vocabulario de pasos:

- `turn_reasoning`: el detalle de UN turno, para el agente que tiene asignado el ticket (GET /api/tickets/{id}/reasoning).
- `GUARDRAILS` y `step_group`: los mismos pasos agrupados para la analítica agregada del administrador
  (observability/analytics.py), que nunca devuelve mensajes ni turnos individuales.

Nunca se devuelven tokens de confirmación ni identificadores de otros clientes: las herramientas ya filtran por el cliente
de la sesión y aquí se omiten las entradas de las tools (solo queda cuántos resultados hubo).
"""
from __future__ import annotations

from typing import Any

# Pasos de la traza que son una guarda: código que impide, limita o verifica algo, con su explicación para el agente.
GUARDRAILS: dict[str, str] = {
    "sospecha_manipulacion": "Posible intento de manipulación: el mensaje se trata como dato, no como instrucción",
    "presupuesto_llm": "Presupuesto diario de LLM agotado: se respondió con reglas y plantillas",
    "token_emitido": "Confirmación explícita (R4): se emitió un token de un solo uso para el botón Confirmar",
    "token_invalido": "Confirmación rechazada (R4): el token no era válido, ya se usó o venció",
    "token_reemitido": "Confirmación (R4): se volvió a pedir con un token nuevo",
    "politica_revalidada": "La política se volvió a evaluar justo antes de ejecutar la acción",
    "verificacion": "Verificación: el resultado se comprobó en la base antes de decir que quedó hecho",
    "pedir_dato": "Sin monto, comercio ni fecha: se pidió un dato antes de buscar",
    "filtro_relevancia": "Solo se muestran movimientos que coinciden con lo que dijo el cliente",
    "sin_coincidencias": "Sin coincidencias: se dijo con honestidad, sin mostrar movimientos parecidos",
    "no_repetir": "No repetir: se evitó enviar dos veces el mismo mensaje",
    "pares_duplicados": "Reclamo duplicado (R3): ya había un reclamo abierto sobre ese cargo",
    "handoff_fallido": "El traspaso a una persona falló y se avisó al cliente",
    "intencion_corregida": "Las palabras clave corrigieron la intención que dio el LLM",
}
# Grupo de cada paso para la analítica agregada (lo que no está aquí cae en "otros").
GROUPS: dict[str, str] = {
    "entrada": "entrada", "fast_path": "comprension", "intent": "comprension", "enrutamiento": "comprension",
    "multiples_intenciones": "comprension", "tema_elegido": "comprension", "foco": "comprension",
    "extract": "datos", "fechas": "datos", "seleccion_por_texto": "datos", "eleccion_por_voz": "datos",
    "ranking": "busqueda", "aclaracion": "busqueda", "clarify": "busqueda", "varios_cargos": "busqueda",
    "fraud_risk": "riesgo", "politica": "politica",
    "confirm": "respuesta", "explain": "respuesta", "faq": "respuesta", "faq_answer": "respuesta", "handoff_summary": "respuesta",
    "ejecutando": "accion", "reconocido": "accion", "cancelado": "accion",
}
ACTION_LABEL = {"confirm": "Pulsó Confirmar", "reject": "Pulsó Cancelar", "request_human": "Pidió hablar con una persona",
                "select_candidate": "Eligió un movimiento de la lista", "dispute_transaction": "Pulsó «No reconozco este cargo»",
                "select_card": "Eligió una tarjeta", "end_conversation": "Terminó la conversación", "start_topic": "Eligió un tema"}


def step_group(node: str) -> str:
    if node in GUARDRAILS:
        return "guarda"
    if node.startswith("tool:"):
        return "busqueda"
    return GROUPS.get(node, "otros")


def _out(step: dict) -> dict:
    out = (step.get("payload") or {}).get("output")
    return out if isinstance(out, dict) else {}


def _source(step: dict) -> str:
    """Quién produjo el paso: el LLM, un modelo pequeño, o las reglas (con el motivo si fue un respaldo)."""
    fallback = (step.get("payload") or {}).get("fallback")
    if fallback:
        return f"respaldo ({fallback})" + (": el LLM no respondió" if step.get("error") else "")
    if step.get("kind") == "llm":
        return f"LLM ({step.get('model_id') or step.get('model') or step.get('implementation') or 'modelo'})"
    if step.get("kind") == "ml":
        return f"modelo ({step.get('implementation') or 'ml'})"
    return "reglas"


def _block_text(b: dict) -> str | None:
    t = b.get("type")
    if t in ("text", "notice"):
        return b.get("text")
    if t == "candidate_list":
        return f"[lista de {len(b.get('candidates') or [])} movimientos]"
    if t == "action_confirmation":
        return "[tarjeta de confirmación] " + str(b.get("summary") or b.get("text") or "")
    if t == "result":
        return f"[resultado: {b.get('status')}{', verificado' if b.get('verified') else ''}] " + str(b.get("text") or "")
    if t == "handoff":
        return "[traspaso a una persona] " + str(b.get("text") or "")
    if t == "quick_replies":
        return "[opciones rápidas]"
    return f"[{t}]"


def turn_reasoning(customer: dict | None, assistant: dict, steps: list[dict]) -> dict:
    """Un turno: el mensaje (o botón) del cliente, la respuesta y, entre ambos, lo que la traza dice que pasó."""
    by: dict[str, list[dict]] = {}
    for s in steps:
        by.setdefault(s["node"], []).append(s)
    last = lambda n: by[n][-1] if n in by else None      # noqa: E731

    action = (customer or {}).get("action") or {}
    said: dict[str, Any] = {"text": (customer or {}).get("message") or None,
                            "action": ACTION_LABEL.get(str(action.get("type")), str(action.get("type"))) if action else None}

    understanding: dict[str, Any] | None = None
    if (fp := last("fast_path")) is not None:
        understanding = {"intent": _out(fp).get("fast_path"), "source": "atajo de saludos (sin LLM)", "certainty": None,
                         "language": _out(fp).get("idioma"), "others": [], "corrected": False}
    elif (it := last("intent")) is not None:
        o = _out(it)
        route = _out(last("enrutamiento") or {})
        understanding = {"intent": route.get("intencion") or o.get("intent"), "source": _source(it), "certainty": o.get("certeza"),
                         "language": o.get("idioma"), "process_topic": o.get("tema_proceso"),
                         "others": o.get("otras_intenciones") or route.get("pendientes") or [],
                         "corrected": "intencion_corregida" in by, "manipulation_suspected": bool(o.get("sospecha_manipulacion"))}

    data: dict[str, Any] | None = None
    if (ex := last("extract")) is not None:
        fields = {k: v for k, v in _out(ex).items() if v not in (None, "", [], False)}
        data = {"source": _source(ex), "fields": fields}
    if (rk := last("ranking")) is not None and data is None:
        q = ((rk.get("payload") or {}).get("input") or {}).get("consulta") or {}
        data = {"source": "contexto de la conversación", "fields": {k: v for k, v in q.items() if v not in (None, "", False) and k != "session_date"}}

    search: list[dict] = []
    for s in steps:
        if s["node"].startswith("tool:"):
            out = (s.get("payload") or {}).get("output")
            n = out.get("n") if isinstance(out, dict) and "n" in out else (len(out) if isinstance(out, list) else None)
            search.append({"step": s["tool"] or s["node"][5:], "result": "error: " + s["error"] if s.get("error") else
                           (f"{n} resultado(s)" if n is not None else ("encontrado" if out else "sin resultado"))})
    if (fr := last("filtro_relevancia")) is not None:
        i = (fr.get("payload") or {}).get("input") or {}
        search.append({"step": "filtro de relevancia", "result": f"{_out(fr).get('coinciden')} de {i.get('movimientos')} coinciden con: {', '.join(i.get('criterios') or [])}"})
    if rk is not None:
        top = _out(rk).get("top") or []
        search.append({"step": "ranking", "result": f"{len(top)} candidata(s)" + (f"; la primera con probabilidad {top[0]['p']:.2f}" if top else "")})
    if (ac := last("aclaracion")) is not None:
        o = _out(ac)
        search.append({"step": "¿hace falta aclarar?", "result": ("sí" if o.get("preguntar") else "no") + (f" ({', '.join(o.get('motivos') or [])})" if o.get("motivos") else "")})

    risk = None
    if (r := last("fraud_risk")) is not None:
        o = _out(r)
        risk = {"band": o.get("banda"), "probability": o.get("probabilidad"), "missing_score": bool(o.get("score_faltante")), "source": _source(r)}

    policy = None
    pol = last("politica_revalidada") or last("politica")
    if pol is not None:
        policy = {"result": _out(pol).get("resultado"), "decides": _out(pol).get("decide"),
                  "rules": [{"id": x.get("id"), "result": x.get("resultado"), "reason": x.get("motivo")} for x in (pol.get("rules") or [])]}

    guardrails = [{"id": s["node"], "label": GUARDRAILS[s["node"]]} for s in steps if s["node"] in GUARDRAILS]
    if understanding and understanding.get("intent") == "fuera_de_alcance":
        guardrails.append({"id": "fuera_de_alcance", "label": "Fuera de alcance: se respondió con el texto aprobado, sin atender la consulta"})
    if any(x.get("id") == "R5" and x.get("resultado") != "permitir" for s in steps for x in (s.get("rules") or [])):
        guardrails.append({"id": "R5", "label": "No se aprueban devoluciones (R5): el pedido se respondió con el aviso aprobado"})
    for s in steps:
        if s.get("kind") == "llm" and (s.get("payload") or {}).get("fallback"):
            guardrails.append({"id": f"respaldo:{s['node']}", "label": f"Respaldo: el LLM no respondió en «{s['node']}» y se usó {(s['payload'] or {}).get('fallback')}"})
    guardrails = list({g["id"]: g for g in guardrails}.values())        # una vez cada una, en orden de aparición

    writer = next((s for s in reversed(steps) if s["node"] in ("explain", "confirm", "clarify", "faq", "faq_answer", "handoff_summary")), None)
    response = {"state_before": assistant.get("state_before"), "state_after": assistant.get("state_after"),
                "written_by": (f"{writer['node']}: " + ((writer.get('payload') or {}).get("modo") or _source(writer))) if writer else "plantilla",
                "blocks": [t for t in (_block_text(b) for b in (assistant.get("blocks") or [])) if t]}
    known = set(GUARDRAILS) | set(GROUPS)
    return {"turn_id": assistant["turn_id"], "at": assistant["created_at"].isoformat() if hasattr(assistant.get("created_at"), "isoformat") else assistant.get("created_at"),
            "customer": said, "understanding": understanding, "data": data, "search": search, "risk": risk, "policy": policy,
            "guardrails": guardrails, "response": response,
            "other_steps": sorted({s["node"] for s in steps if s["node"] not in known and not s["node"].startswith("tool:")}),
            "totals": {"steps": len(steps), "llm_calls": sum(s.get("kind") == "llm" for s in steps),
                       "latency_ms": sum(s.get("latency_ms") or 0 for s in steps),
                       "cost_usd": round(sum(float(s.get("cost_usd") or 0) for s in steps), 6),
                       "errors": [f"{s['node']}: {s['error']}" for s in steps if s.get("error")]}}
