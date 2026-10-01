"""GET /api/ready (preparación) y GET /api/metrics (analyst). /api/health (vida) sigue en main.py."""
from __future__ import annotations

import asyncio
import os
import shutil

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.app.auth.deps import databases, require_analyst
from backend.app.auth.service import SessionContext

router = APIRouter(prefix="/api", tags=["salud"])


async def _db(engine) -> str:
    try:
        async with engine.connect() as c:
            await asyncio.wait_for(c.execute(text("SELECT 1")), timeout=3)
        return "ok"
    except Exception as e:      # noqa: BLE001
        return f"error: {type(e).__name__}"


def _llm(request: Request) -> tuple[str, str]:
    """No llama al LLM (costaría y no prueba la red de producción): revisa que la configuración esté completa."""
    cfg = request.app.state.controller.nodes.config
    if cfg.provider == "anthropic_api":
        return ("ok" if os.environ.get("ANTHROPIC_API_KEY") else "error: falta ANTHROPIC_API_KEY"), cfg.provider
    if cfg.provider == "claude_cli":
        return ("ok" if shutil.which("claude") else "error: no se encontró el binario claude"), cfg.provider
    return "ok", cfg.provider          # fake: sin red (tests, demos sin conexión)


@router.get("/ready")
async def ready(request: Request):
    """200 si la base (lectura/escritura y solo lectura) responde y la configuración del LLM está completa; si no, 503."""
    dbs = databases(request)
    rw, ro = await asyncio.gather(_db(dbs.rw), _db(dbs.ro))
    llm_status, provider = _llm(request)
    checks = {"database_rw": rw, "database_ro": ro, "llm": llm_status}
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ready" if ok else "not_ready", "checks": checks, "llm_provider": provider},
                        status_code=200 if ok else 503)


@router.get("/metrics", tags=["consola"])
async def metrics(request: Request, days: int = 7, _: SessionContext = Depends(require_analyst)) -> dict:
    """Para el panel de administración: latencia y errores por endpoint (en memoria, desde que arrancó el proceso) y,
    desde app.traces, llamadas, costo y latencia del LLM por día y de los turnos."""
    days = min(max(days, 1), 90)
    async with databases(request).ro.connect() as c:
        llm = [dict(r) for r in (await c.execute(text(
            "SELECT * FROM app.v_llm_daily WHERE day >= (now() AT TIME ZONE 'utc')::date - :d ORDER BY day DESC, cost_usd DESC"),
            {"d": days - 1})).mappings()]
        turns = [dict(r) for r in (await c.execute(text(
            "SELECT * FROM app.v_turn_daily WHERE day >= (now() AT TIME ZONE 'utc')::date - :d ORDER BY day DESC"),
            {"d": days - 1})).mappings()]
    return {"endpoints": request.app.state.metrics.snapshot(), "llm_daily": llm, "turns_daily": turns,
            "note": "endpoints: en memoria desde el arranque del proceso; llm_daily y turns_daily: app.traces (UTC)."}
