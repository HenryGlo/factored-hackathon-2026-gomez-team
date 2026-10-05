"""Herramientas de análisis para el administrador, todas de solo lectura y sin mensajes de clientes:

- GET /api/admin/simulate: qué habría decidido la política con otros umbrales, sobre las decisiones ya tomadas
  (backend/app/policy/simulate.py). No cambia ninguna configuración.
- GET /api/admin/topics: temas de los mensajes que el asistente no supo atender (backend/app/ml/topics.py): tamaño del grupo
  y términos frecuentes, nunca un mensaje.
- GET /api/admin/merchants: comercios con más reclamos y cuánto se alejan de su peso normal en los movimientos.

Como en analytics.py, los grupos de menos de MIN_GROUP casos van sin número.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from backend.app.auth.deps import databases, require_admin
from backend.app.auth.service import SessionContext
from backend.app.ml.topics import topic_clusters
from backend.app.observability.analytics import MIN_GROUP, cell
from backend.app.policy.simulate import Thresholds, reevaluate, simulate

router = APIRouter(prefix="/api/admin", tags=["admin"])
Origin = Literal["all", "real", "synthetic"]
WHERE = "t.created_at >= now() - make_interval(days => :days) AND (:origin = 'all' OR c.origin = :origin)"
NOT_UNDERSTOOD = ("fuera_de_alcance", "sin_contenido")
BASELINE_TTL = 3600


def current_thresholds(request: Request) -> Thresholds:
    ctl = request.app.state.controller
    return Thresholds(dispute_window_days=int(ctl.policy.dispute_window_days), risk_threshold=float(ctl.ml.risk.threshold),
                      self_service_max_usd=Decimal(str(ctl.policy.self_service_max_usd)))


@router.get("/simulate")
async def simulate_thresholds(request: Request, days: int = Query(30, ge=1, le=365), origin: Origin = "all",
                              dispute_window_days: int | None = Query(None, ge=1, le=365),
                              risk_threshold: float | None = Query(None, gt=0, lt=1),
                              self_service_max_usd: float | None = Query(None, ge=0, le=1_000_000),
                              _: SessionContext = Depends(require_admin)) -> dict:
    """Decisiones de política del periodo con los umbrales actuales y con los propuestos. Solo lectura."""
    now = current_thresholds(request)
    proposed = Thresholds(dispute_window_days=dispute_window_days if dispute_window_days is not None else now.dispute_window_days,
                          risk_threshold=risk_threshold if risk_threshold is not None else now.risk_threshold,
                          self_service_max_usd=Decimal(str(self_service_max_usd)) if self_service_max_usd is not None else now.self_service_max_usd)
    async with databases(request).ro.connect() as c:
        rows = (await c.execute(text(f"""SELECT t.rules, t.payload->'output'->>'resultado' AS stored FROM app.traces t
                                         JOIN app.conversations c USING (conversation_id)
                                         WHERE t.node = 'politica' AND jsonb_typeof(t.rules) = 'array' AND {WHERE}"""),
                                {"days": days, "origin": origin})).mappings().all()
    evaluations = [r["rules"] for r in rows]
    out = simulate(evaluations, now, proposed)
    total = out["evaluated"]
    # decisiones que no se reproducen con los umbrales de hoy (se tomaron con otra configuración u otro modelo de riesgo)
    stale = sum(reevaluate(r["rules"], now)[0] != r["stored"] for r in rows if r["stored"])
    return {"days": days, "origin": origin, "min_group": MIN_GROUP, "current": now.as_dict(), "proposed": proposed.as_dict(),
            "evaluated": total,
            "before": {k: cell(v, total) for k, v in out["before"].items()}, "after": {k: cell(v, total) for k, v in out["after"].items()},
            "changes": [{"from": x["from"], "to": x["to"], "rule": x["rule"], **cell(x["n"], total)} for x in out["changes"]],
            "changed": cell(sum(x["n"] for x in out["changes"]), total), "not_reproducible": cell(stale, total),
            "note": ("Simula la decisión de política sobre evaluaciones ya registradas: no sabe si el cliente habría confirmado ni incluye "
                     "conversaciones que no llegaron a la política. No cambia la configuración: un valor nuevo se aplica en "
                     "backend/config, medido con el harness y revisado por una persona.")}


@router.get("/topics")
async def not_understood_topics(request: Request, days: int = Query(30, ge=1, le=365), origin: Origin = "all",
                                _: SessionContext = Depends(require_admin)) -> dict:
    """Temas de los mensajes que terminaron fuera de alcance o sin contenido. Los mensajes se leen aquí y no salen: solo grupos."""
    async with databases(request).ro.connect() as c:
        rows = (await c.execute(text(f"""SELECT cu.message, t.payload->'output'->>'intencion' AS intent FROM app.traces t
                                         JOIN app.turns a ON a.turn_id = t.turn_id
                                         JOIN app.turns cu ON cu.conversation_id = a.conversation_id AND cu.seq = a.seq - 1 AND cu.role = 'customer'
                                         JOIN app.conversations c ON c.conversation_id = t.conversation_id
                                         WHERE t.node = 'enrutamiento' AND t.payload->'output'->>'intencion' = ANY(:intents)
                                           AND coalesce(cu.message, '') <> '' AND {WHERE}"""),
                                {"days": days, "origin": origin, "intents": list(NOT_UNDERSTOOD)})).mappings().all()
        turns: int = (await c.execute(text(f"""SELECT count(*) FROM app.traces t JOIN app.conversations c USING (conversation_id)
                                               WHERE t.node = 'enrutamiento' AND {WHERE}"""), {"days": days, "origin": origin})).scalar_one()
    out = topic_clusters([r["message"] for r in rows], min_group=MIN_GROUP)
    by_intent = {k: sum(r["intent"] == k for r in rows) for k in NOT_UNDERSTOOD}
    return {"days": days, "origin": origin, "min_group": MIN_GROUP, "classified_turns": int(turns),
            "not_understood": cell(len(rows), int(turns)), "by_intent": [{"key": k, "label": k, **cell(v, len(rows))} for k, v in by_intent.items()],
            "clusters": [{"terms": x["terms"], **cell(x["size"], out["messages"])} for x in out["clusters"]],
            "unclustered": cell(out["unclustered"], out["messages"]),
            "note": (f"Términos que aparecen en al menos {MIN_GROUP} mensajes del grupo; sin números ni mensajes. Agrupación automática "
                     "(TF-IDF y k-means): es exploratoria, para ver qué piden los clientes fuera de lo que el chat atiende.")}


async def _baseline(request: Request, conn, merchants: list[str], ref_days: int) -> dict:
    """Peso de cada comercio en los movimientos recientes (compras). Se guarda una hora: la tabla es grande."""
    cache = getattr(request.app.state, "merchant_baseline", None) or {}
    key = (tuple(sorted(merchants)), ref_days)
    if cache.get("key") == key and time.time() - cache.get("at", 0) < BASELINE_TTL:
        return cache["data"]
    rows = (await conn.execute(text("""WITH w AS (SELECT merchant_name FROM ref.transactions
                                                  WHERE transaction_type = 'Purchase' AND merchant_name IS NOT NULL
                                                    AND transaction_date >= (SELECT max(transaction_date) FROM ref.transactions) - make_interval(days => :d))
                                       SELECT (SELECT count(*) FROM w) AS total, merchant_name, count(*) AS n FROM w
                                       WHERE merchant_name = ANY(:m) GROUP BY merchant_name"""), {"d": ref_days, "m": merchants})).mappings().all()
    data = {"total": int(rows[0]["total"]) if rows else 0, "by": {r["merchant_name"]: int(r["n"]) for r in rows}}
    request.app.state.merchant_baseline = {"key": key, "at": time.time(), "data": data}
    return data


@router.get("/merchants")
async def merchants_with_disputes(request: Request, days: int = Query(30, ge=1, le=365), origin: Origin = "all",
                                  _: SessionContext = Depends(require_admin)) -> dict:
    """Comercios por número de reclamos del periodo y su «lift»: cuántas veces más reclamos de los que tocarían por su peso en
    las compras. Un lift alto con varios reclamos puede señalar un incidente o un fraude sobre ese comercio."""
    async with databases(request).ro.connect() as c:
        rows = (await c.execute(text("""SELECT tx.merchant_name AS merchant, count(*) AS n FROM app.dispute_cases d
                                        JOIN app.conversations c USING (conversation_id)
                                        JOIN ref.transactions tx ON tx.transaction_id = d.transaction_id
                                        WHERE d.created_at >= now() - make_interval(days => :days) AND (:origin = 'all' OR c.origin = :origin)
                                          AND tx.merchant_name IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""),
                                {"days": days, "origin": origin})).mappings().all()
        total = sum(r["n"] for r in rows)
        shown = [r for r in rows if r["n"] >= MIN_GROUP]
        base = await _baseline(request, c, [r["merchant"] for r in shown], 120) if shown else {"total": 0, "by": {}}
    items = []
    for r in shown:
        expected = base["by"].get(r["merchant"], 0) / base["total"] if base["total"] else None
        share = r["n"] / total
        lift = round(share / expected, 2) if expected else None
        items.append({"merchant": r["merchant"], "n": int(r["n"]), "share": round(share, 4), "purchase_share": round(expected, 4) if expected else None,
                      "lift": lift, "flag": bool(lift and lift >= 2)})
    return {"days": days, "origin": origin, "min_group": MIN_GROUP, "disputes": int(total), "merchants": items,
            "other_merchants": cell(sum(r["n"] for r in rows if r["n"] < MIN_GROUP), int(total)),
            "note": ("lift = proporción de los reclamos ÷ proporción de las compras de los últimos 120 días del dataset. Marcado cuando es 2 o más. "
                     f"Solo comercios con al menos {MIN_GROUP} reclamos. Es una señal para revisar, no una conclusión.")}
