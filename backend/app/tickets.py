"""Bandeja de tickets para agentes humanos (prompt 08, A4): /api/tickets.

Un ticket es un handoff (caso escalado) con datos de trabajo: estado, asignado, SLA objetivo por prioridad y notas internas.
Rol: `analyst` (el agente de soporte). Cada cambio escribe una fila en app.ticket_events (quién, cuándo, de qué a qué): ese
es el registro de auditoría; la app solo puede insertar en él. Prioridades, plazos y orden son supuestos del equipo
(backend/config/tickets.toml).
"""
from __future__ import annotations

import logging
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from backend.app.auth.deps import csrf_error, csrf_ok, databases, require_analyst
from backend.app.auth.service import SessionContext
from backend.app.controller import blocks as B
from backend.app.errors import ApiError, not_found

router = APIRouter(prefix="/api/tickets", tags=["tickets"])
LOG = logging.getLogger("backend.tickets")
CONFIG = tomllib.loads((Path(__file__).resolve().parents[1] / "config" / "tickets.toml").read_text(encoding="utf-8"))
STATUSES = ("nuevo", "en_curso", "esperando_cliente", "resuelto")
Status = Literal["nuevo", "en_curso", "esperando_cliente", "resuelto"]
COLUMNS = """h.handoff_id, h.conversation_id, h.customer_id, h.language, h.reason_code, h.priority, h.queue, h.ticket_status,
             h.assigned_to, u.username AS assigned_username, h.created_at, h.updated_at, h.first_response_at, h.resolved_at, h.summary"""


def sla(priority: str, created_at: datetime, resolved_at: datetime | None, now: datetime | None = None) -> dict:
    """Plazo objetivo y estado: a_tiempo | por_vencer | vencido mientras está abierto; cumplido | incumplido al resolverse."""
    hours = CONFIG["sla_hours"].get(priority, CONFIG["sla_hours"]["media"])
    due = created_at + timedelta(hours=hours)
    now = now or datetime.now(timezone.utc)
    if resolved_at is not None:
        state = "cumplido" if resolved_at <= due else "incumplido"
    else:
        used = (now - created_at) / (due - created_at)
        state = "vencido" if used >= 1 else "por_vencer" if used >= CONFIG["sla"]["warning_fraction"] else "a_tiempo"
    return {"target_hours": hours, "due_at": due.isoformat(), "state": state}


def view(row: dict, now: datetime | None = None) -> dict:
    return {"ticket_id": row["handoff_id"], "reference_label": B.short_ref(row["handoff_id"]), "conversation_id": row["conversation_id"],
            "customer_id": row["customer_id"], "language": row["language"], "reason_code": row["reason_code"], "priority": row["priority"],
            "queue": row["queue"], "status": row["ticket_status"],
            "assignee": {"user_id": row["assigned_to"], "username": row["assigned_username"]} if row["assigned_to"] else None,
            "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat(),
            "first_response_at": row["first_response_at"].isoformat() if row["first_response_at"] else None,
            "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
            "age_minutes": int(((now or datetime.now(timezone.utc)) - row["created_at"]).total_seconds() // 60),
            "sla": sla(row["priority"], row["created_at"], row["resolved_at"], now), "summary": row["summary"]}


async def agent_with_csrf(request: Request, ctx: SessionContext = Depends(require_analyst)) -> SessionContext:
    if not csrf_ok(request, ctx.csrf_token_hash):
        raise csrf_error()
    return ctx


async def _load(conn, ticket_id: str, for_update: bool = False) -> dict:
    row = (await conn.execute(text(f"SELECT {COLUMNS} FROM app.handoffs h LEFT JOIN app.users u ON u.user_id = h.assigned_to "
                                   f"WHERE h.handoff_id = :id" + (" FOR UPDATE OF h" if for_update else "")), {"id": ticket_id})).mappings().first()
    if row is None:
        raise not_found()
    return dict(row)


async def _username(conn, user_id: str) -> str:
    return (await conn.execute(text("SELECT username FROM app.users WHERE user_id = :u"), {"u": user_id})).scalar_one()


async def _event(conn, ticket_id: str, ctx: SessionContext, kind: str, old: str | None, new: str | None, note: str | None = None) -> None:
    actor = await _username(conn, ctx.user_id)
    await conn.execute(text("""INSERT INTO app.ticket_events (handoff_id, actor_user_id, actor_username, kind, from_value, to_value, note)
                               VALUES (:h, :u, :n, :k, :o, :v, :note)"""),
                       {"h": ticket_id, "u": ctx.user_id, "n": actor, "k": kind, "o": old, "v": new, "note": note})
    LOG.info("ticket_event", extra={"ticket_id": ticket_id, "kind": kind, "from": old, "to": new, "actor": ctx.user_id,
                                    "has_note": note is not None})


@router.get("")
async def list_tickets(request: Request, status: Status | None = None, priority: Literal["urgente", "alta", "media"] | None = None,
                       assignee: str | None = Query(None, max_length=60, description="me | unassigned | nombre de usuario"),
                       sla_state: Literal["a_tiempo", "por_vencer", "vencido", "cumplido", "incumplido"] | None = Query(None, alias="sla"),
                       open_only: bool = Query(False, alias="open"), limit: int = Query(50, ge=1, le=200),
                       ctx: SessionContext = Depends(require_analyst)) -> dict:
    """Bandeja: primero por prioridad (riesgo) y, dentro de cada una, el más antiguo arriba."""
    where: list[str] = ["TRUE"]
    p: dict[str, str] = {}
    if status:
        where.append("h.ticket_status = :st")
        p["st"] = status
    if open_only:
        where.append("h.ticket_status <> 'resuelto'")
    if priority:
        where.append("h.priority = :pr")
        p["pr"] = priority
    if assignee == "me":
        where.append("h.assigned_to = :me")
        p["me"] = ctx.user_id
    elif assignee == "unassigned":
        where.append("h.assigned_to IS NULL")
    elif assignee:
        where.append("u.username = :an")
        p["an"] = assignee
    rank = CONFIG["priority_rank"]
    order = "CASE h.priority " + " ".join(f"WHEN '{k}' THEN {v}" for k, v in rank.items()) + " ELSE 9 END, h.created_at"
    now = datetime.now(timezone.utc)
    async with databases(request).ro.connect() as c:
        rows = (await c.execute(text(f"SELECT {COLUMNS} FROM app.handoffs h LEFT JOIN app.users u ON u.user_id = h.assigned_to "
                                     f"WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 500"), p)).mappings().all()
    items = [view(dict(r), now) for r in rows]
    if sla_state:
        items = [t for t in items if t["sla"]["state"] == sla_state]
    counts = {s: sum(t["status"] == s for t in items) for s in STATUSES}
    return {"tickets": items[:limit], "total": len(items), "by_status": counts, "sla_hours": CONFIG["sla_hours"],
            "assumption": "prioridades y plazos son supuestos del equipo (backend/config/tickets.toml)"}


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str, request: Request, _: SessionContext = Depends(require_analyst)) -> dict:
    """Detalle: el handoff estructurado, los datos del ticket y su historial (asignaciones, cambios de estado y notas internas)."""
    async with databases(request).ro.connect() as c:
        row = await _load(c, ticket_id)
        payload: dict = (await c.execute(text("SELECT payload FROM app.handoffs WHERE handoff_id = :id"), {"id": ticket_id})).scalar_one()
        events = (await c.execute(text("""SELECT event_id, actor_username, kind, from_value, to_value, note, created_at
                                          FROM app.ticket_events WHERE handoff_id = :id ORDER BY event_id"""), {"id": ticket_id})).mappings().all()
    return {**view(row), "handoff": payload,
            "events": [{**dict(e), "created_at": e["created_at"].isoformat()} for e in events]}


class Assign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignee: str | None = Field(max_length=60, description='"me", un nombre de usuario de agente, o null para dejarlo sin asignar')


class ChangeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1, max_length=2000)


@router.post("/{ticket_id}/assign")
async def assign(ticket_id: str, body: Assign, request: Request, ctx: SessionContext = Depends(agent_with_csrf)) -> dict:
    async with databases(request).rw.begin() as c:
        row = await _load(c, ticket_id, for_update=True)
        target = None
        if body.assignee == "me":
            target = ctx.user_id
        elif body.assignee:
            target = (await c.execute(text("SELECT user_id FROM app.users WHERE username = :n AND role IN ('analyst', 'admin') AND is_active"),
                                      {"n": body.assignee})).scalar()
            if target is None:
                raise ApiError(400, "validation_error", "Ese usuario no es un agente activo.")
        if target != row["assigned_to"]:
            new_name = await _username(c, target) if target else None
            await c.execute(text("UPDATE app.handoffs SET assigned_to = :a, updated_at = now() WHERE handoff_id = :id"), {"a": target, "id": ticket_id})
            await _event(c, ticket_id, ctx, "asignacion", row["assigned_username"], new_name)
        return view(await _load(c, ticket_id))


@router.post("/{ticket_id}/status")
async def change_status(ticket_id: str, body: ChangeStatus, request: Request, ctx: SessionContext = Depends(agent_with_csrf)) -> dict:
    async with databases(request).rw.begin() as c:
        row = await _load(c, ticket_id, for_update=True)
        if body.status != row["ticket_status"]:
            await c.execute(text("""UPDATE app.handoffs SET ticket_status = :s, updated_at = now(),
                                    first_response_at = CASE WHEN first_response_at IS NULL AND :responded THEN now() ELSE first_response_at END,
                                    resolved_at = CASE WHEN :resolved THEN now() ELSE NULL END
                                    WHERE handoff_id = :id"""),
                            {"s": body.status, "id": ticket_id, "responded": body.status != "nuevo", "resolved": body.status == "resuelto"})
            await _event(c, ticket_id, ctx, "estado", row["ticket_status"], body.status)
        return view(await _load(c, ticket_id))


@router.post("/{ticket_id}/notes", status_code=201)
async def add_note(ticket_id: str, body: Note, request: Request, ctx: SessionContext = Depends(agent_with_csrf)) -> dict:
    """Nota interna: solo la ven los agentes. Nunca se muestra al cliente ni entra a un prompt."""
    async with databases(request).rw.begin() as c:
        await _load(c, ticket_id, for_update=True)
        await _event(c, ticket_id, ctx, "nota", None, None, body.note.strip())
        await c.execute(text("UPDATE app.handoffs SET updated_at = now() WHERE handoff_id = :id"), {"id": ticket_id})
        return view(await _load(c, ticket_id))
