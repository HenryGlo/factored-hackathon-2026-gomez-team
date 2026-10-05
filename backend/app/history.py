"""Historial de conversaciones del cliente (prompt 08, A1): GET /api/me/conversations y /api/me/conversations/{id}.

Solo lectura y sin LLM. El resumen corto de cada conversación se arma con HECHOS que quedaron en la base (reclamos,
handoffs, bloqueos e intención registrada), con plantillas es/pt: no es texto libre de un LLM, así que no necesita guarda.
Solo las conversaciones del cliente de la sesión; pedir una ajena da 404 (no se revela que existe).
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from backend.app.auth.deps import databases
from backend.app.auth.service import SessionContext
from backend.app.controller import blocks as B
from backend.app.errors import ApiError, not_found
from backend.app.me import require_customer

router = APIRouter(prefix="/api/me", tags=["cliente"])

LIST = """
SELECT c.conversation_id, c.created_at, c.updated_at, c.closed_at, c.state, c.closed_reason, c.language, c.previous_conversation_id,
       c.context->>'intent' AS intent,
       (SELECT count(*) FROM app.turns t WHERE t.conversation_id = c.conversation_id AND t.role = 'customer') AS customer_turns,
       (SELECT coalesce(json_agg(json_build_object('case_id', d.case_id, 'reason_code', d.reason_code, 'status', d.status,
                                                   'transaction_id', d.transaction_id) ORDER BY d.created_at), '[]'::json)
          FROM app.dispute_cases d WHERE d.conversation_id = c.conversation_id) AS cases,
       (SELECT coalesce(json_agg(json_build_object('handoff_id', h.handoff_id, 'reason_code', h.reason_code) ORDER BY h.created_at), '[]'::json)
          FROM app.handoffs h WHERE h.conversation_id = c.conversation_id) AS handoffs,
       EXISTS (SELECT 1 FROM app.card_status_overrides o WHERE o.conversation_id = c.conversation_id) AS locked
FROM app.conversations c
WHERE c.customer_id = :cust AND {where}
  AND EXISTS (SELECT 1 FROM app.turns t WHERE t.conversation_id = c.conversation_id AND t.role = 'customer')
ORDER BY c.created_at DESC, c.conversation_id DESC LIMIT :n"""
TX = """SELECT transaction_id, merchant_name, transaction_type, transaction_category, amount, currency, transaction_date
        FROM ref.transactions WHERE customer_id = :cust AND transaction_id = ANY(:ids)"""

TEXT: dict[str, dict[str, Any]] = {
    "es": {"case": "Reclamo {ref} por {reason}: {tx}", "cases": "{n} reclamos: {refs}", "handoff": "Pasó a una persona ({ref}): {reason}",
           "lock": "Bloqueo de tarjeta", "reasons": {"unrecognized": "cargo no reconocido", "duplicate": "cobro duplicado", "amount_mismatch": "monto incorrecto"},
           "handoffs": {"pide_humano": "pediste hablar con una persona", "riesgo_alto": "revisión del equipo de fraude",
                        "riesgo_desconocido": "revisión del equipo de fraude", "cargo_pendiente_no_reconocido": "cargo pendiente que no reconoces",
                        "fuera_de_plazo": "cargo fuera del plazo de este canal", "aclaracion_agotada": "no se pudo identificar el cargo",
                        "reposicion_tarjeta": "reposición de tarjeta", "accion_no_verificada": "una acción no se pudo verificar"},
           "intents": {"consulta_movimientos": "Consulta de movimientos", "estado_reclamo": "Consulta del estado de un reclamo",
                       "pregunta_proceso": "Pregunta sobre el proceso", "fuera_de_alcance": "Consulta que este chat no atiende",
                       "cargo_no_reconocido": "Cargo no reconocido, sin reclamo registrado", "cobro_indebido": "Cobro indebido, sin reclamo registrado",
                       "bloquear_tarjeta": "Pedido de bloqueo, sin bloqueo registrado", "pedir_humano": "Pedido de hablar con una persona"},
           "none": "Sin acción", "other": "atención de una persona"},
    "pt": {"case": "Reclamação {ref} por {reason}: {tx}", "cases": "{n} reclamações: {refs}", "handoff": "Passou para uma pessoa ({ref}): {reason}",
           "lock": "Bloqueio de cartão", "reasons": {"unrecognized": "cobrança não reconhecida", "duplicate": "cobrança duplicada", "amount_mismatch": "valor incorreto"},
           "handoffs": {"pide_humano": "você pediu para falar com uma pessoa", "riesgo_alto": "análise da equipe de fraude",
                        "riesgo_desconocido": "análise da equipe de fraude", "cargo_pendiente_no_reconocido": "cobrança pendente que você não reconhece",
                        "fuera_de_plazo": "cobrança fora do prazo deste canal", "aclaracion_agotada": "não foi possível identificar a cobrança",
                        "reposicion_tarjeta": "reposição de cartão", "accion_no_verificada": "uma ação não pôde ser verificada"},
           "intents": {"consulta_movimientos": "Consulta de lançamentos", "estado_reclamo": "Consulta do status de uma reclamação",
                       "pregunta_proceso": "Pergunta sobre o processo", "fuera_de_alcance": "Consulta que este chat não atende",
                       "cargo_no_reconocido": "Cobrança não reconhecida, sem reclamação registrada", "cobro_indebido": "Cobrança indevida, sem reclamação registrada",
                       "bloquear_tarjeta": "Pedido de bloqueio, sem bloqueio registrado", "pedir_humano": "Pedido para falar com uma pessoa"},
           "none": "Sem ação", "other": "atendimento de uma pessoa"},
    "en": {"case": "Claim {ref} for {reason}: {tx}", "cases": "{n} claims: {refs}", "handoff": "Passed to a person ({ref}): {reason}",
           "lock": "Card block", "reasons": {"unrecognized": "unrecognized charge", "duplicate": "duplicate charge", "amount_mismatch": "wrong amount"},
           "handoffs": {"pide_humano": "you asked to talk to a person", "riesgo_alto": "review by the fraud team",
                        "riesgo_desconocido": "review by the fraud team", "cargo_pendiente_no_reconocido": "pending charge you don't recognize",
                        "fuera_de_plazo": "charge outside this channel's time limit", "aclaracion_agotada": "the charge could not be identified",
                        "reposicion_tarjeta": "card replacement", "accion_no_verificada": "an action could not be verified"},
           "intents": {"consulta_movimientos": "Transaction inquiry", "estado_reclamo": "Claim status inquiry",
                       "pregunta_proceso": "Question about the process", "fuera_de_alcance": "Request this chat doesn't handle",
                       "cargo_no_reconocido": "Unrecognized charge, no claim filed", "cobro_indebido": "Wrong charge, no claim filed",
                       "bloquear_tarjeta": "Block request, no block made", "pedir_humano": "Asked to talk to a person"},
           "none": "No action", "other": "attention by a person"},
}


def encode_cursor(created_at: datetime, conversation_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{conversation_id}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, cid = raw.split("|", 1)
        return datetime.fromisoformat(ts), cid
    except Exception as e:  # noqa: BLE001
        raise ApiError(400, "validation_error", "Cursor inválido.") from e


def summarize(row: dict, txs: dict[str, dict], lang: str) -> dict:
    """Resumen y resultado de una conversación a partir de hechos (nunca de texto libre)."""
    t = TEXT.get(lang, TEXT["es"])
    cases, handoffs = row["cases"] or [], row["handoffs"] or []
    refs = [B.short_ref(c["case_id"]) for c in cases] + [B.short_ref(h["handoff_id"]) for h in handoffs]
    parts, outcomes = [], []
    if len(cases) == 1:
        c = cases[0]
        tx = txs.get(c["transaction_id"])
        label = f"{B.tx_label(tx, lang)}, {B.fmt_money(tx['amount'], tx['currency'], lang)}" if tx else "—"
        parts.append(t["case"].format(ref=B.short_ref(c["case_id"]), reason=t["reasons"].get(c["reason_code"], c["reason_code"]), tx=label))
    elif cases:
        parts.append(t["cases"].format(n=len(cases), refs=", ".join(B.short_ref(c["case_id"]) for c in cases)))
    if cases:
        outcomes.append("reclamo")
    if row["locked"]:
        parts.append(t["lock"])
        outcomes.append("bloqueo")
    for h in handoffs:
        parts.append(t["handoff"].format(ref=B.short_ref(h["handoff_id"]), reason=t["handoffs"].get(h["reason_code"], t["other"])))
    if handoffs:
        outcomes.append("persona")
    if not parts:
        known = t["intents"].get(row["intent"] or "")
        parts.append(known or t["none"])
        outcomes.append("informacion" if row["intent"] in ("consulta_movimientos", "estado_reclamo", "pregunta_proceso") else "sin_accion")
    return {"conversation_id": row["conversation_id"], "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat(),
            "closed_at": row["closed_at"].isoformat() if row["closed_at"] else None, "state": row["state"],
            "closed_reason": row["closed_reason"], "language": row["language"], "intent": row["intent"], "outcomes": outcomes,
            "references": refs, "summary": ". ".join(parts) + ".", "customer_turns": row["customer_turns"],
            "previous_conversation_id": row["previous_conversation_id"]}


async def _rows(conn, customer_id: str, where: str, params: dict, limit: int) -> list[dict]:
    return [dict(r) for r in (await conn.execute(text(LIST.format(where=where)), {"cust": customer_id, "n": limit, **params})).mappings()]


async def _transactions(conn, customer_id: str, rows: list[dict]) -> dict[str, dict]:
    ids = sorted({c["transaction_id"] for r in rows for c in (r["cases"] or [])})
    if not ids:
        return {}
    return {r["transaction_id"]: dict(r) for r in (await conn.execute(text(TX), {"cust": customer_id, "ids": ids})).mappings()}


@router.get("/conversations")
async def my_conversations(request: Request, limit: int = Query(20, ge=1, le=50), cursor: str | None = Query(None, max_length=200),
                           lang: Literal["es", "pt", "en"] | None = None, ctx: SessionContext = Depends(require_customer)) -> dict:
    """Conversaciones del cliente, de la más reciente a la más antigua, paginadas con cursor. Las que no tienen ningún
    mensaje del cliente (solo el saludo) no aparecen."""
    assert ctx.customer_id
    where, params = "TRUE", {}
    if cursor:
        ts, cid = decode_cursor(cursor)
        where, params = "(c.created_at, c.conversation_id) < (:ts, :cid)", {"ts": ts, "cid": cid}
    language = lang or ctx.language or "es"
    async with databases(request).rw.connect() as conn:
        rows = await _rows(conn, ctx.customer_id, where, params, limit + 1)
        page = rows[:limit]
        txs = await _transactions(conn, ctx.customer_id, page)
    nxt = encode_cursor(page[-1]["created_at"], page[-1]["conversation_id"]) if len(rows) > limit else None
    return {"conversations": [summarize(r, txs, language) for r in page], "next_cursor": nxt}


@router.get("/conversations/{conversation_id}")
async def my_conversation(conversation_id: str, request: Request, lang: Literal["es", "pt", "en"] | None = None,
                          ctx: SessionContext = Depends(require_customer)) -> dict:
    """Una conversación propia en solo lectura: su resumen y los turnos con los mismos bloques que mostró el chat."""
    assert ctx.customer_id
    async with databases(request).rw.connect() as conn:
        rows = await _rows(conn, ctx.customer_id, "c.conversation_id = :id", {"id": conversation_id}, 1)
        if not rows:
            raise not_found()                       # ajena, inexistente o sin mensajes: misma respuesta
        txs = await _transactions(conn, ctx.customer_id, rows)
        turns = (await conn.execute(text("""SELECT turn_id, seq, role, message, action, blocks, state_after, created_at FROM app.turns
                                            WHERE conversation_id = :id ORDER BY seq"""), {"id": conversation_id})).mappings().all()
    return {**summarize(rows[0], txs, lang or ctx.language or "es"),
            "turns": [{**dict(t), "created_at": t["created_at"].isoformat()} for t in turns]}
