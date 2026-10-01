"""API de conversaciones y turnos (cliente) y de consola (analyst). docs/api-contract.md.

Respuesta única por turno (sin SSE): el turno se procesa completo y devuelve bloques, estado,
data_as_of y trace_id. Con LLM real un turno tarda varios segundos; el frontend muestra un
indicador mientras espera.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text

from backend.app.auth.deps import current_session, databases, require_analyst, session_with_csrf
from backend.app.auth.service import SessionContext
from backend.app.controller.engine import TurnInput
from backend.app.errors import ApiError, not_found

router = APIRouter(prefix="/api", tags=["conversaciones"])
console = APIRouter(prefix="/api", tags=["consola"])


class NewConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Literal["es", "pt"] | None = None
    previous_conversation_id: str | None = Field(default=None, max_length=40,
                                                 description="Conversación anterior del mismo cliente: se hereda el cargo en foco.")
    dispute_transaction_id: str | None = Field(default=None, max_length=30,
                                               description='"No reconozco este cargo" desde Mis movimientos: la conversación queda lista '
                                                           'para la acción dispute_transaction con ese movimiento (debe ser del cliente).')


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["select_candidate", "select_candidates", "select_card", "dispute_transaction", "confirm", "reject",
                  "request_human", "new_request", "end_conversation"]
    transaction_id: str | None = Field(default=None, max_length=30)
    transaction_ids: list[str] | None = Field(default=None, max_length=10, description="select_candidates: varios cargos.")
    product_id: str | None = Field(default=None, max_length=20)
    confirmation_token: str | None = Field(default=None, max_length=100)


class TurnRequest(BaseModel):
    """Un mensaje O una acción. Nunca customer_id: sale de la sesión."""
    model_config = ConfigDict(extra="forbid")
    message: str | None = Field(default=None, max_length=20000)   # tope duro del cuerpo; el tope amable va en post_turn
    action: Action | None = None

    @model_validator(mode="after")
    def one_of(self):
        if (self.message is None) == (self.action is None):
            raise ValueError("envía un mensaje o una acción")
        return self


def controller(request: Request):
    return request.app.state.controller


def require_customer_csrf(ctx: SessionContext = Depends(session_with_csrf)) -> SessionContext:
    if ctx.role != "customer":
        raise ApiError(403, "forbidden", "No tienes permiso para esta operación.")
    return ctx


@router.post("/conversations", status_code=201)
async def create_conversation(request: Request, body: NewConversation | None = None,
                              ctx: SessionContext = Depends(require_customer_csrf)) -> dict:
    res = await controller(request).create_conversation(ctx, language=body.language if body else None,
                                                        previous_conversation_id=body.previous_conversation_id if body else None,
                                                        dispute_transaction_id=body.dispute_transaction_id if body else None)
    return {**res, "data_as_of": await controller(request).data_freshness()}


@router.post("/conversations/{conversation_id}/turns")
async def post_turn(conversation_id: str, body: TurnRequest, request: Request,
                    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=64),
                    ctx: SessionContext = Depends(require_customer_csrf)) -> dict:
    limit = request.app.state.security.max_message_chars
    if body.message is not None and len(body.message) > limit:
        raise ApiError(422, "message_too_long",
                       f"Tu mensaje es muy largo ({len(body.message)} caracteres). Resúmelo en menos de {limit:,} caracteres, por favor."
                       .replace(",", "."), details={"max_chars": limit, "chars": len(body.message)})
    inp = TurnInput(message=body.message, action=body.action.model_dump(exclude_none=True) if body.action else None)
    # app.state.faults: fallos inyectados SOLO por tests y el harness (en proceso); no hay forma de fijarlos por HTTP
    return await controller(request).handle_turn(ctx, conversation_id, inp, idempotency_key,
                                                 faults=set(getattr(request.app.state, "faults", set())))


async def _conversation(conn, conversation_id: str, customer_id: str | None) -> dict:
    q = "SELECT conversation_id, customer_id, state, language, clarification_round, session_date, created_at FROM app.conversations WHERE conversation_id = :id"
    p = {"id": conversation_id}
    if customer_id is not None:
        q += " AND customer_id = :c"
        p["c"] = customer_id
    row = (await conn.execute(text(q), p)).mappings().first()
    if row is None:
        raise not_found()
    turns = (await conn.execute(text("""SELECT turn_id, seq, role, message, action, blocks, state_after, created_at FROM app.turns
                                        WHERE conversation_id = :id ORDER BY seq"""), {"id": conversation_id})).mappings().all()
    return {**dict(row), "turns": [dict(t) for t in turns]}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request, ctx: SessionContext = Depends(current_session)) -> dict:
    """El cliente solo ve las suyas; el analyst ve cualquiera, con el usuario de solo lectura."""
    dbs = databases(request)
    if ctx.role == "analyst":
        async with dbs.ro.connect() as c:
            return await _conversation(c, conversation_id, None)
    async with dbs.rw.connect() as c:
        conv = await _conversation(c, conversation_id, ctx.customer_id)
    conv.pop("customer_id")
    return conv


# ---------------------------------------------------------------- consola (analyst, solo lectura)
@console.get("/cases/{case_id}")
async def get_case(case_id: str, request: Request, _: SessionContext = Depends(require_analyst)) -> dict:
    async with databases(request).ro.connect() as c:
        row = (await c.execute(text("""SELECT case_id, customer_id, transaction_id, status, reason_code, customer_statement,
                                           policy_rules_applied, idempotency_key IS NOT NULL AS idempotent, confirmed_at, created_at,
                                           conversation_id, turn_id FROM app.dispute_cases WHERE case_id = :id"""), {"id": case_id})).mappings().first()
    if row is None:
        raise not_found()
    return dict(row)


@console.get("/handoffs")
async def list_handoffs(request: Request, status: str | None = None, queue: str | None = None, limit: int = 50,
                        _: SessionContext = Depends(require_analyst)) -> list[dict]:
    q = "SELECT handoff_id, conversation_id, customer_id, reason_code, priority, queue, status, language, created_at FROM app.handoffs"
    where: list[str] = []
    p: dict[str, object] = {"lim": min(max(limit, 1), 200)}
    if status:
        where.append("status = :st"); p["st"] = status
    if queue:
        where.append("queue = :q"); p["q"] = queue
    q += (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC LIMIT :lim"
    async with databases(request).ro.connect() as c:
        return [dict(r) for r in (await c.execute(text(q), p)).mappings()]


@console.get("/handoffs/{handoff_id}")
async def get_handoff(handoff_id: str, request: Request, _: SessionContext = Depends(require_analyst)) -> dict:
    async with databases(request).ro.connect() as c:
        row = (await c.execute(text("SELECT payload, status, queue FROM app.handoffs WHERE handoff_id = :id"), {"id": handoff_id})).mappings().first()
    if row is None:
        raise not_found()
    return {**row["payload"], "status": row["status"], "queue": row["queue"]}


@console.get("/traces/{turn_id}")
async def get_trace(turn_id: str, request: Request, _: SessionContext = Depends(require_analyst)) -> dict:
    async with databases(request).ro.connect() as c:
        turn = (await c.execute(text("SELECT turn_id, conversation_id, state_before, state_after FROM app.turns WHERE turn_id = :t"),
                                {"t": turn_id})).mappings().first()
        if turn is None:
            raise not_found()
        steps = [dict(r) for r in (await c.execute(text("""SELECT step_seq, node, kind, implementation, tool, model, model_id, prompt_version,
                                                               latency_ms, cost_usd, payload, rules, error FROM app.traces
                                                               WHERE turn_id = :t ORDER BY step_seq"""), {"t": turn_id})).mappings()]
    return {**dict(turn), "steps": steps, "totals": {"latency_ms": sum(s["latency_ms"] or 0 for s in steps),
                                                      "cost_usd": str(sum((s["cost_usd"] or 0) for s in steps))}}
