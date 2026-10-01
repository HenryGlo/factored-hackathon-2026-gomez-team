"""Presupuesto de LLM: tope diario global y por sesión, de llamadas y de costo.

Se calcula desde app.traces (pasos kind='llm' de hoy, en UTC), así sobrevive a reinicios y vale con varias instancias. Se
revisa al empezar cada turno. Si se superó, el turno corre en modo degradado (plantillas y baseline, sin llamar al LLM) y
queda registrado en la traza y en el log: nunca falla en silencio.

Las llamadas de un turno se guardan al final del turno, así que un turno puede pasar el tope por unas pocas llamadas (≤ 6).
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.app.protection.config import SecurityConfig

log = logging.getLogger("backend.protection")


@dataclass(frozen=True)
class BudgetStatus:
    ok: bool
    reason: str | None                 # daily_calls | daily_cost | session_calls | session_cost
    daily_calls: int
    daily_cost_usd: float
    session_calls: int
    session_cost_usd: float

    def as_dict(self) -> dict:
        return asdict(self)


class LLMBudget:
    def __init__(self, engine: AsyncEngine, config: SecurityConfig):
        self.engine, self.cfg = engine, config

    async def check(self, session_id: str) -> BudgetStatus:
        async with self.engine.connect() as c:
            row = (await c.execute(text("""
                SELECT count(*) AS daily_calls, coalesce(sum(t.cost_usd), 0) AS daily_cost,
                       count(*) FILTER (WHERE cv.session_id = :s) AS session_calls,
                       coalesce(sum(t.cost_usd) FILTER (WHERE cv.session_id = :s), 0) AS session_cost
                FROM app.traces t JOIN app.conversations cv ON cv.conversation_id = t.conversation_id
                WHERE t.kind = 'llm' AND coalesce(t.implementation, '') <> 'fake'     -- plantillas: no son llamadas al LLM
                  AND t.created_at >= date_trunc('day', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc'
                """), {"s": session_id})).mappings().one()
        cfg = self.cfg
        checks = [("daily_calls", row["daily_calls"] >= cfg.daily_calls), ("daily_cost", float(row["daily_cost"]) >= cfg.daily_cost_usd),
                  ("session_calls", row["session_calls"] >= cfg.session_calls),
                  ("session_cost", float(row["session_cost"]) >= cfg.session_cost_usd)]
        reason = next((name for name, over in checks if over), None)
        status = BudgetStatus(reason is None, reason, int(row["daily_calls"]), round(float(row["daily_cost"]), 6),
                              int(row["session_calls"]), round(float(row["session_cost"]), 6))
        if reason:
            log.warning("llm_budget_exceeded", extra={"reason": reason, **status.as_dict()})
        return status
