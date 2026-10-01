"""Panel de administración (prompt 08, A5): /api/admin/overview, /api/admin/slo y /api/admin/logs. Rol `admin`.

- overview: tiempos de respuesta por endpoint y por nodo, conversaciones recientes, tasas de resolución / aclaración /
  escalamiento, costo de LLM (y de voz) por día y presupuesto consumido.
- slo: objetivos de backend/config/slo.toml con el valor actual, el presupuesto de error y las violaciones (cuántas y cuándo).
- logs: los últimos eventos del proceso, ya redactados, con filtros. Sin textos del cliente ni secretos (logs.py los oculta).
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from backend.app.auth.deps import databases, require_admin
from backend.app.auth.service import SessionContext
from backend.app.observability import logs
from backend.app.observability.admin_metrics import LATENCY, _operations

router = APIRouter(prefix="/api/admin", tags=["admin"])
SLO_FILE = Path(__file__).resolve().parents[2] / "config" / "slo.toml"

RECENT = """
SELECT c.conversation_id, c.created_at, c.updated_at, c.state, c.language, c.context->>'intent' AS intent,
       (SELECT count(*) FROM app.turns t WHERE t.conversation_id = c.conversation_id AND t.role = 'customer') AS customer_turns,
       EXISTS (SELECT 1 FROM app.dispute_cases d WHERE d.conversation_id = c.conversation_id) AS has_case,
       EXISTS (SELECT 1 FROM app.handoffs h WHERE h.conversation_id = c.conversation_id) AS has_handoff,
       (SELECT f.rating FROM app.feedback f WHERE f.conversation_id = c.conversation_id) AS feedback
FROM app.conversations c ORDER BY c.created_at DESC LIMIT :n"""
LLM_DAILY = """SELECT day, sum(calls) AS calls, sum(errors) AS errors, round(sum(cost_usd)::numeric, 6) AS cost_usd
               FROM app.v_llm_daily WHERE day >= (now() AT TIME ZONE 'utc')::date - :d AND provider <> 'fake' GROUP BY day ORDER BY day DESC"""
TODAY = """SELECT count(*) AS calls, coalesce(sum(cost_usd), 0) AS cost_usd FROM app.traces
           WHERE kind = 'llm' AND coalesce(implementation, '') <> 'fake'
             AND created_at >= date_trunc('day', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc'"""
VOICE_DAILY = """SELECT (created_at AT TIME ZONE 'utc')::date AS day, sum(seconds) AS stt_seconds, sum(characters) AS tts_characters,
                        round(sum(cost_usd)::numeric, 6) AS cost_usd
                 FROM app.voice_usage WHERE created_at >= ((now() AT TIME ZONE 'utc')::date - :d) GROUP BY 1 ORDER BY 1 DESC"""
TURNS = """
WITH per_turn AS (SELECT turn_id, min(created_at) AS at, sum(latency_ms) AS ms FROM app.traces
                  WHERE created_at >= now() - make_interval(days => :days) GROUP BY turn_id)
SELECT turn_id, at, ms FROM per_turn ORDER BY at DESC"""
TICKETS = """SELECT handoff_id, created_at, first_response_at FROM app.handoffs
             WHERE created_at >= now() - make_interval(days => :days) ORDER BY created_at DESC"""


def budget_report(objective: float, total: int, bad: int) -> dict:
    """Presupuesto de error: cuántos eventos pueden incumplir sin romper el objetivo, y cuánto se consumió."""
    allowed = (1 - objective) * total
    return {"events": total, "bad_events": bad, "allowed_bad_events": round(allowed, 2),
            "consumed": round(bad / allowed, 3) if allowed > 0 else (None if bad == 0 else float(bad)),
            "remaining_bad_events": round(allowed - bad, 2)}


@router.get("/overview")
async def overview(request: Request, days: int = Query(7, ge=1, le=90), _: SessionContext = Depends(require_admin)) -> dict:
    async with databases(request).ro.connect() as c:
        nodes = [dict(r) for r in (await c.execute(text(LATENCY), {"days": days})).mappings()]
        recent = [dict(r) for r in (await c.execute(text(RECENT), {"n": 20})).mappings()]
        llm = [dict(r) for r in (await c.execute(text(LLM_DAILY), {"d": days - 1})).mappings()]
        today = (await c.execute(text(TODAY))).mappings().one()
        voice = [{"day": str(r["day"]), "stt_seconds": float(r["stt_seconds"]), "tts_characters": int(r["tts_characters"]),
                  "cost_usd": float(r["cost_usd"])} for r in (await c.execute(text(VOICE_DAILY), {"d": days - 1})).mappings()]
    for r in nodes:
        r.update(p50_ms=round(float(r["p50_ms"] or 0), 1), p95_ms=round(float(r["p95_ms"] or 0), 1), cost_usd=round(float(r["cost_usd"]), 6))
    for r in recent:
        r.update(created_at=r["created_at"].isoformat(), updated_at=r["updated_at"].isoformat())
    cfg = request.app.state.security                              # límites del presupuesto de LLM (docs/security.md)
    limit_cost, limit_calls = float(cfg.daily_cost_usd), int(cfg.daily_calls)
    return {"days": days,
            "endpoints": request.app.state.metrics.snapshot(),          # en memoria, desde que arrancó el proceso
            "nodes": nodes, "recent_conversations": recent, "outcomes": await _operations(request, days),
            "llm_cost_daily": [{"day": str(r["day"]), "calls": int(r["calls"]), "errors": int(r["errors"]), "cost_usd": float(r["cost_usd"])} for r in llm],
            "voice_cost_daily": voice,
            "budget": {"today_calls": int(today["calls"]), "today_cost_usd": round(float(today["cost_usd"]), 6),
                       "daily_calls_limit": limit_calls or None, "daily_cost_limit_usd": limit_cost or None,
                       "cost_consumed": round(float(today["cost_usd"]) / limit_cost, 4) if limit_cost else None,
                       "calls_consumed": round(int(today["calls"]) / limit_calls, 4) if limit_calls else None},
            "note": "endpoints: en memoria desde el arranque; lo demás, de la base (UTC)."}


@router.get("/slo")
async def slo(request: Request, _: SessionContext = Depends(require_admin)) -> dict:
    cfg = tomllib.loads(SLO_FILE.read_text(encoding="utf-8"))
    out = []
    async with databases(request).ro.connect() as c:
        lat, tick = cfg["turn_latency"], cfg["ticket_first_response"]
        turns = (await c.execute(text(TURNS), {"days": lat["window_days"]})).mappings().all()
        slow = [t for t in turns if (t["ms"] or 0) > lat["target_ms"]]
        ordered = sorted((t["ms"] or 0) for t in turns)
        p95 = ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1) + 0.5))] if ordered else None
        out.append({"id": "turn_latency", "description": lat["description"], "objective": lat["objective"], "window_days": lat["window_days"],
                    "target": {"p95_ms": lat["target_ms"]}, "current": {"p95_ms": p95},
                    "met": p95 is None or p95 <= lat["target_ms"], "error_budget": budget_report(lat["objective"], len(turns), len(slow)),
                    "violations": [{"at": t["at"].isoformat(), "turn_id": t["turn_id"], "ms": int(t["ms"])} for t in slow[:20]],
                    "note": "latencia del turno = suma de sus pasos en la traza (intent y extract en paralelo cuentan dos veces: cota superior)"})
        tickets = (await c.execute(text(TICKETS), {"days": tick["window_days"]})).mappings().all()
        late = (await c.execute(text("""SELECT handoff_id, created_at FROM app.handoffs
                                        WHERE created_at >= now() - make_interval(days => :days)
                                          AND coalesce(first_response_at, now()) - created_at > make_interval(hours => :h)
                                        ORDER BY created_at DESC"""), {"days": tick["window_days"], "h": tick["target_hours"]})).mappings().all()
    ok = len(tickets) - len(late)
    out.append({"id": "ticket_first_response", "description": tick["description"], "objective": tick["objective"], "window_days": tick["window_days"],
                "target": {"hours": tick["target_hours"]}, "current": {"on_time_share": round(ok / len(tickets), 4) if tickets else None},
                "met": not tickets or ok / len(tickets) >= tick["objective"], "error_budget": budget_report(tick["objective"], len(tickets), len(late)),
                "violations": [{"at": t["created_at"].isoformat(), "ticket_id": t["handoff_id"]} for t in late[:20]]})
    av = cfg["availability"]
    snap = request.app.state.metrics.snapshot()
    total, bad = sum(e["requests"] for e in snap), sum(e["errors_5xx"] for e in snap)
    out.append({"id": "availability", "description": av["description"], "objective": av["objective"], "window": "desde el arranque del proceso",
                "target": {"success_share": av["objective"]}, "current": {"success_share": round(1 - bad / total, 5) if total else None},
                "met": not total or 1 - bad / total >= av["objective"], "error_budget": budget_report(av["objective"], total, bad),
                "violations": [{"at": at, "method": m, "route": r, "status": s} for at, m, r, s in list(request.app.state.metrics.server_errors)[-20:]]})
    return {"slos": out, "assumption": "objetivos y ventanas son supuestos del equipo (backend/config/slo.toml)"}


@router.get("/logs")
async def search_logs(request_id: str | None = Query(None, max_length=64), conversation_id: str | None = Query(None, max_length=40),
                      level: Literal["debug", "info", "warning", "error"] | None = None, route: str | None = Query(None, max_length=80),
                      limit: int = Query(100, ge=1, le=500), _: SessionContext = Depends(require_admin)) -> dict:
    """Eventos recientes del proceso (más nuevos primero), ya redactados: sin contraseñas, tokens, cookies ni textos del cliente."""
    events = logs.MEMORY.search(request_id=request_id, conversation_id=conversation_id, level=level, route=route, limit=limit)
    return {"events": events, "kept": len(logs.MEMORY.records),
            "note": "búfer en memoria del proceso (últimos 5.000 eventos); se pierde al reiniciar"}
