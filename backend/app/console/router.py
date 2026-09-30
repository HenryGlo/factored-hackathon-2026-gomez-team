"""Consola del banco. Exige rol analyst y lee con el motor de solo lectura (usuario del grupo app_ro).

En la fase 1 solo existe la lista de reclamos; casos, handoffs y trazas se completan en la fase 5.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.auth.deps import databases, require_analyst
from backend.app.auth.service import SessionContext
from backend.persistence.models import app_dispute_cases as cases

router = APIRouter(prefix="/api", tags=["consola"])


class CaseSummary(BaseModel):
    case_id: str
    customer_id: str
    transaction_id: str
    status: str
    created_at: datetime


@router.get("/cases", response_model=list[CaseSummary])
async def list_cases(request: Request, status: str | None = Query(default=None, max_length=20),
                     limit: int = Query(default=50, ge=1, le=200),
                     _: SessionContext = Depends(require_analyst)) -> list[CaseSummary]:
    q = select(cases.c.case_id, cases.c.customer_id, cases.c.transaction_id, cases.c.status, cases.c.created_at) \
        .order_by(cases.c.created_at.desc()).limit(limit)
    if status:
        q = q.where(cases.c.status == status)
    async with databases(request).ro.connect() as conn:   # solo lectura
        return [CaseSummary(**r) for r in (await conn.execute(q)).mappings()]
