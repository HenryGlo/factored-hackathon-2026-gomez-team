"""Analítica agregada de los pasos de decisión del asistente: GET /api/admin/analytics (rol admin).

El administrador ve cuántas veces ocurrió cada cosa (intenciones, datos que dio el cliente, guardas, reglas de política,
riesgo, aclaraciones, cómo terminó), nunca un mensaje, un turno ni una conversación en particular:

- solo conteos y proporciones; no se devuelve ningún texto del cliente ni identificador;
- supresión de grupos pequeños: un grupo con menos de MIN_GROUP casos se devuelve sin su número (`n: null, suppressed: true`),
  para que un conteo no señale a una persona;
- `origin` separa las conversaciones reales de las sintéticas (scripts/seed_synthetic_history.py), que siempre van marcadas.

El detalle turno a turno es del agente que tiene el ticket asignado (GET /api/tickets/{id}/reasoning).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from backend.app.auth.deps import databases, require_admin
from backend.app.auth.service import SessionContext
from backend.app.reasoning import GUARDRAILS

router = APIRouter(prefix="/api/admin", tags=["admin"])
MIN_GROUP = 5

SCOPE = """FROM app.traces t JOIN app.conversations c USING (conversation_id)
           WHERE t.created_at >= now() - make_interval(days => :days) AND (:origin = 'all' OR c.origin = :origin)"""
CONV = "FROM app.conversations c WHERE c.created_at >= now() - make_interval(days => :days) AND (:origin = 'all' OR c.origin = :origin)"

Q = {
    "totals": f"""SELECT count(*) AS conversations, count(*) FILTER (WHERE c.origin = 'synthetic') AS synthetic,
                         (SELECT count(DISTINCT t.turn_id) {SCOPE}) AS turns,
                         (SELECT count(*) {SCOPE} AND t.kind = 'llm') AS llm_calls {CONV}""",
    # qué entendió: intención final del turno (la del enrutamiento) y el atajo de saludos
    "intents": f"""SELECT coalesce(t.payload->'output'->>'intencion', '—') AS key, count(*) AS n {SCOPE} AND t.node = 'enrutamiento' GROUP BY 1
                   UNION ALL SELECT 'saludo o cortesía (atajo)', count(*) {SCOPE} AND t.node = 'fast_path' HAVING count(*) > 0""",
    "intent_source": f"""SELECT CASE WHEN t.payload->>'fallback' IS NOT NULL THEN 'respaldo por reglas (el LLM no respondió)'
                                     WHEN t.kind = 'llm' THEN 'LLM' WHEN t.kind = 'ml' THEN 'modelo pequeño o palabras clave' ELSE 'reglas' END AS key,
                                count(*) AS n {SCOPE} AND t.node = 'intent' GROUP BY 1""",
    "certainty": f"SELECT coalesce(t.payload->'output'->>'certeza', '—') AS key, count(*) AS n {SCOPE} AND t.node = 'intent' GROUP BY 1",
    # qué datos dio el cliente: nombres de campo con valor en la extracción, nunca los valores
    "data_fields": f"""SELECT e.key, count(*) AS n {SCOPE.replace('FROM app.traces t', "FROM app.traces t CROSS JOIN LATERAL jsonb_each(CASE WHEN jsonb_typeof(t.payload->'output') = 'object' THEN t.payload->'output' ELSE '{}'::jsonb END) e")}
                       AND t.node = 'extract' AND jsonb_typeof(e.value) <> 'null' AND e.value NOT IN ('false'::jsonb, '[]'::jsonb, '""'::jsonb)
                       GROUP BY 1""",
    "extractions": f"SELECT count(*) AS n {SCOPE} AND t.node = 'extract' AND jsonb_typeof(t.payload->'output') = 'object'",
    "guardrails": f"SELECT t.node AS key, count(DISTINCT t.turn_id) AS n {SCOPE} AND t.node = ANY(:guards) GROUP BY 1",
    "fallbacks": f"""SELECT t.node AS key, count(*) AS n {SCOPE} AND t.kind IN ('llm', 'ml') AND t.payload->>'fallback' IS NOT NULL GROUP BY 1""",
    "llm_by_node": f"SELECT t.node AS key, count(*) AS n {SCOPE} AND t.kind = 'llm' GROUP BY 1",
    "out_of_scope": f"SELECT count(*) AS n {SCOPE} AND t.node = 'enrutamiento' AND t.payload->'output'->>'intencion' = 'fuera_de_alcance'",
    "policy_results": f"SELECT coalesce(t.payload->'output'->>'resultado', '—') AS key, count(*) AS n {SCOPE} AND t.node = 'politica' GROUP BY 1",
    "policy_rules": f"""SELECT r->>'id' AS rule, r->>'resultado' AS result, count(*) AS n
                        {SCOPE.replace('FROM app.traces t', "FROM app.traces t CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(t.rules) = 'array' THEN t.rules ELSE '[]'::jsonb END) r")}
                        AND t.node = 'politica' GROUP BY 1, 2""",
    "risk": f"SELECT coalesce(t.payload->'output'->>'banda', '—') AS key, count(*) AS n {SCOPE} AND t.node = 'fraud_risk' GROUP BY 1",
    "clarify": f"""SELECT CASE WHEN (t.payload->'output'->>'preguntar')::boolean THEN 'tuvo que preguntar' ELSE 'candidata clara, sin preguntar' END AS key,
                          count(*) AS n {SCOPE} AND t.node = 'aclaracion' GROUP BY 1""",
    "clarify_rounds": f"SELECT c.clarification_round::text AS key, count(*) AS n {CONV} GROUP BY 1",
    "states": """SELECT s.state AS key, count(DISTINCT s.conversation_id) AS n
                  FROM (SELECT tu.conversation_id, tu.state_after AS state FROM app.turns tu) s JOIN app.conversations c USING (conversation_id)
                  WHERE c.created_at >= now() - make_interval(days => :days) AND (:origin = 'all' OR c.origin = :origin) GROUP BY 1""",
    "outcomes": f"""SELECT c.language, CASE WHEN EXISTS (SELECT 1 FROM app.handoffs h WHERE h.conversation_id = c.conversation_id AND h.reason_code <> 'reposicion_tarjeta') THEN 'pasó a una persona'
                                            WHEN EXISTS (SELECT 1 FROM app.dispute_cases d WHERE d.conversation_id = c.conversation_id) THEN 'reclamo registrado'
                                            WHEN EXISTS (SELECT 1 FROM app.card_status_overrides o WHERE o.conversation_id = c.conversation_id) THEN 'tarjeta bloqueada'
                                            ELSE 'información o sin acción' END AS key, count(*) AS n {CONV} GROUP BY 1, 2""",
    "handoff_reasons": """SELECT h.reason_code AS key, count(*) AS n FROM app.handoffs h JOIN app.conversations c USING (conversation_id)
                           WHERE c.created_at >= now() - make_interval(days => :days) AND (:origin = 'all' OR c.origin = :origin) GROUP BY 1""",
    "feedback": """SELECT f.rating AS key, count(*) AS n FROM app.feedback f JOIN app.conversations c USING (conversation_id)
                    WHERE c.created_at >= now() - make_interval(days => :days) AND (:origin = 'all' OR c.origin = :origin) GROUP BY 1""",
}
STATE_ORDER = ["inicio", "aclarando", "confirmando_movimiento", "confirmando_accion", "escalado", "cerrado"]


def cell(n: int, total: int | None = None) -> dict:
    """Un conteo publicable: los grupos de menos de MIN_GROUP casos van sin número."""
    if 0 < n < MIN_GROUP:
        return {"n": None, "share": None, "suppressed": True}
    return {"n": n, "share": round(n / total, 4) if total else None, "suppressed": False}


def table(rows: list[dict], total: int | None = None, order: list[str] | None = None, labels: dict[str, str] | None = None) -> list[dict]:
    total = total if total is not None else sum(r["n"] for r in rows)
    key = (lambda r: order.index(r["key"]) if r["key"] in order else len(order)) if order else (lambda r: -r["n"])
    return [{"key": r["key"], "label": (labels or {}).get(r["key"], r["key"]), **cell(r["n"], total)} for r in sorted(rows, key=key)]


@router.get("/analytics")
async def analytics(request: Request, days: int = Query(30, ge=1, le=365), origin: Literal["all", "real", "synthetic"] = "all",
                    _: SessionContext = Depends(require_admin)) -> dict:
    p = {"days": days, "origin": origin, "guards": list(GUARDRAILS)}
    async with databases(request).ro.connect() as c:
        r = {name: [dict(x) for x in (await c.execute(text(sql), p)).mappings()] for name, sql in Q.items()}
    tot = r["totals"][0]
    turns, convs = int(tot["turns"]), int(tot["conversations"])
    extractions = int(r["extractions"][0]["n"])
    guard_rows = r["guardrails"] + [{"key": f"respaldo:{x['key']}", "n": x["n"]} for x in r["fallbacks"]]
    if r["out_of_scope"][0]["n"]:
        guard_rows.append({"key": "fuera_de_alcance", "n": r["out_of_scope"][0]["n"]})
    r5 = sum(x["n"] for x in r["policy_rules"] if x["rule"] == "R5" and x["result"] != "permitir")
    if r5:
        guard_rows.append({"key": "R5", "n": r5})
    labels = {**GUARDRAILS, "fuera_de_alcance": "Fuera de alcance: texto aprobado, sin atender la consulta",
              "R5": "No se aprueban devoluciones (R5)", **{f"respaldo:{x['key']}": f"Respaldo: el LLM no respondió en «{x['key']}»" for x in r["fallbacks"]}}
    llm_calls = {x["key"]: x["n"] for x in r["llm_by_node"]}
    rules: dict[str, dict] = {}
    for x in r["policy_rules"]:
        rules.setdefault(x["rule"], {})[x["result"]] = x["n"]
    langs = sorted({x["language"] for x in r["outcomes"]})
    return {
        "days": days, "origin": origin, "min_group": MIN_GROUP,
        "totals": {"conversations": convs, "synthetic_conversations": int(tot["synthetic"]), "assistant_turns": turns,
                   "llm_calls": int(tot["llm_calls"])},
        "understanding": {"intents": table(r["intents"]), "source": table(r["intent_source"]), "certainty": table(r["certainty"])},
        "data": {"extractions": extractions, "fields": table(r["data_fields"], extractions)},
        "guardrails": table(guard_rows, turns, labels=labels),
        "fallback_rate": [{"key": k, **cell(next((x["n"] for x in r["fallbacks"] if x["key"] == k), 0), n)} for k, n in sorted(llm_calls.items())],
        "risk": table(r["risk"]),
        "policy": {"results": table(r["policy_results"]),
                   "rules": [{"rule": rule, "total": sum(v.values()), "results": table([{"key": k, "n": n} for k, n in v.items()])}
                             for rule, v in sorted(rules.items())]},
        "clarification": {"decisions": table(r["clarify"]), "rounds": table(r["clarify_rounds"], convs, order=["0", "1", "2", "3"])},
        "funnel": table(r["states"], convs, order=STATE_ORDER),
        "outcomes": {"languages": langs,
                     "by_language": {lang: table([{"key": x["key"], "n": x["n"]} for x in r["outcomes"] if x["language"] == lang]) for lang in langs}},
        "handoff_reasons": table(r["handoff_reasons"]),
        "feedback": table(r["feedback"]),
        "note": (f"Solo conteos agregados; los grupos con menos de {MIN_GROUP} casos van sin número. «guardrails» cuenta turnos sobre "
                 "el total de turnos del asistente; «funnel», conversaciones que pasaron por cada estado."),
    }
