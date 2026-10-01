"""Lecturas del propio cliente para las pantallas "Mis movimientos" y "Mis reclamos" (docs/api-contract.md).

Solo lectura y sin LLM: reusan los tools list_transactions y list_cases. El customer_id sale de la sesión. Los movimientos
vienen con la misma vista que el chat (tx_view: montos, fechas y estados ya formateados por idioma).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from backend.app.auth.deps import current_session
from backend.app.auth.service import SessionContext
from backend.app.controller import blocks as B
from backend.app.errors import ApiError
from backend.app.tools import ToolContext, ToolError

router = APIRouter(prefix="/api/me", tags=["cliente"])
STATUSES = {"Approved", "Pending", "Declined", "Reversed"}


def require_customer(ctx: SessionContext = Depends(current_session)) -> SessionContext:
    if ctx.role != "customer" or not ctx.customer_id:
        raise ApiError(403, "forbidden", "No tienes permiso para esta operación.")
    return ctx


async def _tool_ctx(request: Request, ctx: SessionContext) -> ToolContext:
    controller = request.app.state.controller
    assert ctx.customer_id                                     # require_customer lo garantiza
    return ToolContext(customer_id=ctx.customer_id, session_id=ctx.session_id, conversation_id=None,
                       session_date=await controller.session_date())


@router.get("/transactions")
async def my_transactions(request: Request, date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
                          merchant: str | None = Query(None, max_length=60),
                          status: Literal["Approved", "Pending", "Declined", "Reversed"] | None = None,
                          limit: int = Query(50, ge=1, le=200), lang: Literal["es", "pt"] | None = None,
                          ctx: SessionContext = Depends(require_customer)) -> dict:
    tctx = await _tool_ctx(request, ctx)
    policy = request.app.state.controller.policy
    end = date_to or tctx.session_date
    start = date_from or end - timedelta(days=policy.list_default_days)
    if start > end:
        raise ApiError(400, "validation_error", "La fecha inicial es posterior a la final.")
    if (end - start).days > 366:
        raise ApiError(400, "validation_error", "El período máximo es de un año.")
    language = lang or ctx.language or "es"
    try:
        res = await request.app.state.controller.tools.list_transactions(
            tctx, date_from=start, date_to=end, merchant_like=merchant.strip() if merchant else None, status=status,
            limit=min(limit, policy.list_max_results))
    except ToolError as e:
        raise ApiError(503, "dependency_unavailable", "No pude leer tus movimientos. Intenta de nuevo.", retryable=True) from e
    return {"period": {"from": start.isoformat(), "to": end.isoformat()}, "session_date": tctx.session_date.isoformat(),
            "filters": {"merchant": merchant, "status": status}, "count": res["count"],
            "totals": [{"currency": x["currency"], "count": x["n"], "total": B.money(x["total"]),
                        "total_label": B.fmt_money(x["total"], x["currency"], language)} for x in res["spend_by_currency"]],
            "transactions": [B.tx_view(x, lang=language) for x in res["transactions"]],
            "data_as_of": await request.app.state.controller.data_freshness()}


@router.get("/cases")
async def my_cases(request: Request, lang: Literal["es", "pt"] | None = None, ctx: SessionContext = Depends(require_customer)) -> dict:
    tctx = await _tool_ctx(request, ctx)
    language = lang or ctx.language or "es"
    try:
        cases = await request.app.state.controller.tools.list_cases(tctx, limit=50)
    except ToolError as e:
        raise ApiError(503, "dependency_unavailable", "No pude leer tus reclamos. Intenta de nuevo.", retryable=True) from e
    return {"cases": [{"case_id": x["case_id"], "status": x["status"], "reason_code": x["reason_code"], "created_at": x["created_at"].isoformat(),
                       "transaction": {"transaction_id": x["transaction_id"], "label": B.tx_label(x, language),
                                       "amount": B.money(x["amount"]) if x["amount"] is not None else None, "currency": x["currency"],
                                       "date": x["transaction_date"].isoformat() if x["transaction_date"] else None,
                                       "amount_label": B.fmt_money(x["amount"], x["currency"], language) if x["amount"] is not None else None,
                                       "date_label": B.fmt_date(x["transaction_date"], language) if x["transaction_date"] else None}}
                      for x in cases]}
