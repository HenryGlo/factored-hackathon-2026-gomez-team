"""Métricas para el panel de administración (prompt 07, bloque 4): /api/admin/metrics/*.

Solo lectura, con el usuario de solo lectura de la base (app_ro) y rol analyst. Todo sale de lo que la app registró
(conversaciones, reclamos, handoffs y trazas): son números de operación, no del dataset ni de la evaluación.
- operations: cómo terminaron las conversaciones del periodo, con n/N.
- latency: latencia p50/p95, llamadas, errores y costo por nodo.
- roi: estimación con los supuestos de backend/config/roi.toml (editables) y los conteos reales del periodo.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from backend.app.auth.deps import databases, require_analyst
from backend.app.auth.service import SessionContext

router = APIRouter(prefix="/api/admin/metrics", tags=["admin"])
ROI_FILE = Path(__file__).resolve().parents[2] / "config" / "roi.toml"

OPERATIONS = """
WITH conv AS (
  SELECT c.conversation_id,
         EXISTS (SELECT 1 FROM app.dispute_cases d WHERE d.conversation_id = c.conversation_id) AS has_case,
         EXISTS (SELECT 1 FROM app.card_status_overrides o WHERE o.conversation_id = c.conversation_id) AS has_lock,
         EXISTS (SELECT 1 FROM app.handoffs h WHERE h.conversation_id = c.conversation_id AND h.reason_code <> 'reposicion_tarjeta') AS has_handoff,
         EXISTS (SELECT 1 FROM app.traces t WHERE t.conversation_id = c.conversation_id AND t.node = 'clarify') AS clarified
  FROM app.conversations c WHERE c.created_at >= now() - make_interval(days => :days))
SELECT count(*) AS conversations,
       count(*) FILTER (WHERE has_handoff) AS escalated,
       count(*) FILTER (WHERE NOT has_handoff AND (has_case OR has_lock) AND NOT clarified) AS resolved_automatically,
       count(*) FILTER (WHERE NOT has_handoff AND (has_case OR has_lock) AND clarified) AS resolved_after_clarification,
       count(*) FILTER (WHERE NOT has_handoff AND NOT has_case AND NOT has_lock) AS no_action
FROM conv"""
HANDOFFS = """SELECT reason_code, priority, count(*) AS n FROM app.handoffs
              WHERE created_at >= now() - make_interval(days => :days) GROUP BY 1, 2 ORDER BY 3 DESC"""
LATENCY = """
SELECT node, kind, count(*) AS calls, count(*) FILTER (WHERE error IS NOT NULL) AS errors,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms,
       coalesce(sum(cost_usd), 0) AS cost_usd
FROM app.traces WHERE created_at >= now() - make_interval(days => :days) AND (kind = 'llm' OR tool IS NOT NULL)
GROUP BY node, kind ORDER BY p50_ms DESC NULLS LAST"""
COSTS = """SELECT count(DISTINCT conversation_id) AS conversations, coalesce(sum(cost_usd), 0) AS llm_cost_usd
           FROM app.traces WHERE created_at >= now() - make_interval(days => :days)"""


def frac(n: int, d: int) -> dict:
    return {"n": n, "of": d, "share": round(n / d, 4) if d else None}


def roi_numbers(a: dict) -> dict:
    """Mismos cálculos que analytics/report.py (docs/analytics.md, sección 4)."""
    human = a["agent_cost_per_minute_usd"] * a["minutes_per_case_human"]
    saved = a["automatable_share"] * (human - a["llm_cost_per_case_usd"]) - (1 - a["automatable_share"]) * a["llm_cost_per_case_usd"]
    return {"human_cost_per_case_usd": round(human, 4), "saving_per_case_usd": round(saved, 4),
            "monthly_saving_usd": round(a["cases_per_month"] * saved - a["fixed_monthly_cost_usd"], 2),
            "break_even_cases_per_month": round(a["fixed_monthly_cost_usd"] / saved) if saved > 0 else None}


async def _operations(request: Request, days: int) -> dict:
    async with databases(request).ro.connect() as c:
        row = (await c.execute(text(OPERATIONS), {"days": days})).mappings().one()
        handoffs = [dict(r) for r in (await c.execute(text(HANDOFFS), {"days": days})).mappings()]
    total = row["conversations"]
    return {"days": days, "conversations": total,
            "resolved_automatically": frac(row["resolved_automatically"], total),
            "resolved_after_clarification": frac(row["resolved_after_clarification"], total),
            "escalated": frac(row["escalated"], total), "no_action": frac(row["no_action"], total),
            "handoffs": handoffs}


@router.get("/operations")
async def operations(request: Request, days: int = Query(30, ge=1, le=365), _: SessionContext = Depends(require_analyst)) -> dict:
    """Cómo terminaron las conversaciones del periodo: sola, con aclaración, con una persona o sin acción (n/N)."""
    return await _operations(request, days)


@router.get("/latency")
async def latency(request: Request, days: int = Query(7, ge=1, le=365), _: SessionContext = Depends(require_analyst)) -> dict:
    """Latencia p50/p95, llamadas, errores y costo por nodo (LLM y tools), desde app.traces."""
    async with databases(request).ro.connect() as c:
        rows = [dict(r) for r in (await c.execute(text(LATENCY), {"days": days})).mappings()]
    for r in rows:
        r.update(p50_ms=round(float(r["p50_ms"] or 0), 1), p95_ms=round(float(r["p95_ms"] or 0), 1), cost_usd=round(float(r["cost_usd"]), 6))
    return {"days": days, "nodes": rows}


@router.get("/roi")
async def roi(request: Request, days: int = Query(30, ge=1, le=365), _: SessionContext = Depends(require_analyst)) -> dict:
    """ROI estimado: supuestos editables + lo medido en el periodo. Es una ESTIMACIÓN, no un resultado."""
    assumptions = tomllib.loads(ROI_FILE.read_text(encoding="utf-8"))["assumptions"]
    ops = await _operations(request, days)
    async with databases(request).ro.connect() as c:
        cost = (await c.execute(text(COSTS), {"days": days})).mappings().one()
    conversations = cost["conversations"]
    measured = {"days": days, "conversations": ops["conversations"],
                "not_escalated_share": round(1 - ops["escalated"]["n"] / ops["conversations"], 4) if ops["conversations"] else None,
                "llm_cost_per_conversation_usd": round(float(cost["llm_cost_usd"]) / conversations, 6) if conversations else None}
    return {"label": "estimación con supuestos del equipo; no es un resultado medido", "assumptions": assumptions,
            "estimate": roi_numbers(assumptions), "measured": measured}
