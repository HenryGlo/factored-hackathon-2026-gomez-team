"""Tools de lectura y escritura (docs/tools-contract.md).

Reglas comunes:
- El customer_id sale de `ToolContext` (la sesión); ningún tool lo recibe como argumento.
- Un recurso ajeno o inexistente → ToolError('not_found') sin distinguir los casos.
- Las escrituras (create_dispute_case, lock_card, create_handoff) consumen un confirmation_token
  en la MISMA transacción en que escriben; el controlador verifica después con una lectura.
- `faults` permite inyectar fallos por nombre de tool (solo harness y tests; la API no lo expone).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from backend.app.security import new_id, new_token, sha256

DISPUTABLE_TYPES = ("Purchase", "Payment", "Withdrawal")
CARD_TYPES = ("Tarjeta Crédito", "Tarjeta Débito")
TX_COLS = """t.transaction_id, t.transaction_date, t.process_date, t.amount, t.currency, t.amount_usd_filled,
             t.merchant_name, t.merchant_category, t.transaction_category, t.transaction_type, t.transaction_status,
             t.channel, t.product_id, t.fraud_score"""


class ToolError(Exception):
    def __init__(self, code: str, message: str = "", data: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.data = code, message, data or {}


@dataclass
class ToolContext:
    customer_id: str
    session_id: str
    conversation_id: str
    session_date: date
    faults: set[str] = field(default_factory=set)

    def check_fault(self, tool: str) -> None:
        if tool in self.faults:
            raise ToolError("db_unavailable", f"fallo inyectado en {tool}")


def params_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()


class Tools:
    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    # ------------------------------------------------------------------ lecturas
    async def search_transactions(self, ctx: ToolContext, window_days: int) -> list[dict]:
        """Universo de búsqueda del reclamo: cargos disputables del cliente (incluye Pending, Declined y
        Reversed) en [hoy − window_days, hoy], según transaction_date."""
        ctx.check_fault("search_transactions")
        q = text(f"""SELECT {TX_COLS} FROM ref.transactions t
                     WHERE t.customer_id = :cid AND t.transaction_type = ANY(:types)
                       AND t.transaction_date >= :start AND t.transaction_date < :end
                     ORDER BY t.transaction_date DESC LIMIT 500""")
        async with self.engine.connect() as c:
            rows = await c.execute(q, {"cid": ctx.customer_id, "types": list(DISPUTABLE_TYPES),
                                       "start": ctx.session_date - timedelta(days=window_days),
                                       "end": ctx.session_date + timedelta(days=1)})
            return [dict(r) for r in rows.mappings()]

    async def get_transaction(self, ctx: ToolContext, transaction_id: str) -> dict:
        ctx.check_fault("get_transaction")
        async with self.engine.connect() as c:
            row = (await c.execute(text(f"SELECT {TX_COLS} FROM ref.transactions t WHERE t.transaction_id = :tid "
                                        "AND t.customer_id = :cid"), {"tid": transaction_id, "cid": ctx.customer_id})).mappings().first()
        if row is None:
            raise ToolError("not_found")
        return dict(row)

    async def list_transactions(self, ctx: ToolContext, *, date_from: date, date_to: date, merchants: list[str] | None = None,
                                merchant_like: str | None = None, min_amount: Decimal | None = None,
                                max_amount: Decimal | None = None, status: str | None = None, limit: int = 10) -> dict:
        """Consulta de movimientos (solo lectura). Totales y conteos los calcula el código, sobre TODO lo que
        cumple los filtros (no solo lo devuelto)."""
        ctx.check_fault("list_transactions")
        where = ["t.customer_id = :cid", "t.transaction_date >= :start", "t.transaction_date < :end"]
        p: dict[str, Any] = {"cid": ctx.customer_id, "start": date_from, "end": date_to + timedelta(days=1)}
        if merchants:
            where.append("t.merchant_name = ANY(:merchants)"); p["merchants"] = merchants
        elif merchant_like:
            where.append("t.merchant_name ILIKE :mlike"); p["mlike"] = f"%{merchant_like}%"
        if min_amount is not None:
            where.append("t.amount >= :minamt"); p["minamt"] = min_amount
        if max_amount is not None:
            where.append("t.amount <= :maxamt"); p["maxamt"] = max_amount
        if status:
            where.append("t.transaction_status = :status"); p["status"] = status
        w = " AND ".join(where)
        async with self.engine.connect() as c:
            rows = [dict(r) for r in (await c.execute(text(f"SELECT {TX_COLS} FROM ref.transactions t WHERE {w} "
                                                            "ORDER BY t.transaction_date DESC LIMIT :lim"),
                                                       {**p, "lim": limit})).mappings()]
            totals = [dict(r) for r in (await c.execute(text(
                f"SELECT t.currency, count(*) AS n, sum(t.amount) AS total FROM ref.transactions t WHERE {w} "
                "AND t.transaction_status IN ('Approved', 'Pending') AND t.transaction_type IN ('Purchase', 'Payment', 'Withdrawal') "
                "GROUP BY 1 ORDER BY 1"), p)).mappings()]
            n_all = (await c.execute(text(f"SELECT count(*) FROM ref.transactions t WHERE {w}"), p)).scalar_one()
        return {"transactions": rows, "count": n_all, "spend_by_currency": totals}

    async def get_existing_case(self, ctx: ToolContext, transaction_id: str) -> dict | None:
        """Reclamo ABIERTO del cliente sobre esa transacción (R3)."""
        ctx.check_fault("get_existing_case")
        async with self.engine.connect() as c:
            row = (await c.execute(text("""SELECT case_id, status, created_at, reason_code FROM app.dispute_cases
                                           WHERE customer_id = :cid AND transaction_id = :tid AND status IN ('registrado', 'en_revision')"""),
                                   {"cid": ctx.customer_id, "tid": transaction_id})).mappings().first()
        return dict(row) if row else None

    async def get_case(self, ctx: ToolContext, case_id: str) -> dict:
        ctx.check_fault("get_case")
        async with self.engine.connect() as c:
            row = (await c.execute(text("""SELECT case_id, transaction_id, status, reason_code, created_at, confirmed_at,
                                                  policy_rules_applied FROM app.dispute_cases
                                           WHERE case_id = :id AND customer_id = :cid"""),
                                   {"id": case_id, "cid": ctx.customer_id})).mappings().first()
        if row is None:
            raise ToolError("not_found")
        return dict(row)

    async def list_cases(self, ctx: ToolContext, limit: int = 10) -> list[dict]:
        ctx.check_fault("list_cases")
        async with self.engine.connect() as c:
            rows = await c.execute(text("""SELECT d.case_id, d.transaction_id, d.status, d.reason_code, d.created_at,
                                                  t.merchant_name, t.transaction_category, t.transaction_type, t.amount, t.currency, t.transaction_date
                                           FROM app.dispute_cases d LEFT JOIN ref.transactions t
                                             ON t.transaction_id = d.transaction_id AND t.customer_id = d.customer_id
                                           WHERE d.customer_id = :cid ORDER BY d.created_at DESC LIMIT :lim"""),
                                   {"cid": ctx.customer_id, "lim": limit})
            return [dict(r) for r in rows.mappings()]

    async def list_cards(self, ctx: ToolContext) -> list[dict]:
        """Tarjetas del cliente con su estado efectivo (override de la app o ref.products) y últimos 4 dígitos."""
        ctx.check_fault("list_cards")
        async with self.engine.connect() as c:
            rows = await c.execute(text("""SELECT e.product_id, e.product_type, e.status, right(p.product_number, 4) AS last4, p.currency
                                           FROM app.card_status_effective e JOIN ref.products p USING (product_id)
                                           WHERE e.customer_id = :cid AND e.product_type = ANY(:types)
                                           ORDER BY e.product_type, e.product_id"""),
                                   {"cid": ctx.customer_id, "types": list(CARD_TYPES)})
            return [dict(r) for r in rows.mappings()]

    async def get_card_status(self, ctx: ToolContext, product_id: str) -> dict:
        ctx.check_fault("get_card_status")
        async with self.engine.connect() as c:
            row = (await c.execute(text("""SELECT product_id, product_type, status, ref_status, overridden_at
                                           FROM app.card_status_effective WHERE product_id = :pid AND customer_id = :cid"""),
                                   {"pid": product_id, "cid": ctx.customer_id})).mappings().first()
        if row is None:
            raise ToolError("not_found")
        if row["product_type"] not in CARD_TYPES:
            raise ToolError("not_a_card")
        return dict(row)

    # ------------------------------------------------------------------ tokens de confirmación
    async def issue_token(self, ctx: ToolContext, action: str, params: dict, ttl_seconds: int) -> tuple[str, datetime]:
        """Emite un token de un solo uso ligado a (sesión, conversación, acción, params) e invalida los anteriores
        de la conversación que sigan pendientes."""
        token, exp = new_token(), datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        async with self.engine.begin() as c:
            await c.execute(text("""UPDATE app.confirmation_tokens SET invalidated_at = now()
                                    WHERE conversation_id = :conv AND consumed_at IS NULL AND invalidated_at IS NULL"""),
                            {"conv": ctx.conversation_id})
            await c.execute(text("""INSERT INTO app.confirmation_tokens (token_id, token_hash, session_id, conversation_id, action,
                                    params, params_hash, expires_at) VALUES (:id, :h, :ses, :conv, :action, CAST(:params AS jsonb), :ph, :exp)"""),
                            {"id": new_id("ct"), "h": sha256(token), "ses": ctx.session_id, "conv": ctx.conversation_id,
                             "action": action, "params": json.dumps(params, default=str), "ph": params_hash(params), "exp": exp})
        return token, exp

    async def invalidate_tokens(self, ctx: ToolContext) -> None:
        async with self.engine.begin() as c:
            await c.execute(text("""UPDATE app.confirmation_tokens SET invalidated_at = now()
                                    WHERE conversation_id = :conv AND consumed_at IS NULL AND invalidated_at IS NULL"""),
                            {"conv": ctx.conversation_id})

    @staticmethod
    async def _consume(c: AsyncConnection, ctx: ToolContext, token: str, action: str, params: dict) -> str:
        """Valida y consume el token en la transacción `c`. Cualquier desajuste → invalid_confirmation."""
        row = (await c.execute(text("""SELECT token_id, session_id, conversation_id, action, params_hash, expires_at,
                                              consumed_at, invalidated_at FROM app.confirmation_tokens
                                       WHERE token_hash = :h FOR UPDATE"""), {"h": sha256(token or "")})).mappings().first()
        why = None
        if row is None:
            why = "desconocido"
        elif row["consumed_at"] is not None:
            why = "ya_usado"
        elif row["invalidated_at"] is not None:
            why = "anulado"
        elif row["expires_at"] <= datetime.now(timezone.utc):
            why = "vencido"
        elif row["session_id"] != ctx.session_id:
            why = "otra_sesion"
        elif row["conversation_id"] != ctx.conversation_id or row["action"] != action or row["params_hash"] != params_hash(params):
            why = "no_coincide"
        if why:
            raise ToolError("invalid_confirmation", why)
        await c.execute(text("UPDATE app.confirmation_tokens SET consumed_at = now() WHERE token_id = :id"), {"id": row["token_id"]})
        return row["token_id"]

    # ------------------------------------------------------------------ escrituras
    async def create_dispute_case(self, ctx: ToolContext, *, transaction_id: str, reason_code: str, customer_statement: str,
                                  token: str, idempotency_key: str | None, policy_rules: list[dict], turn_id: str | None) -> dict:
        ctx.check_fault("create_dispute_case")
        params = {"transaction_id": transaction_id, "reason_code": reason_code}
        case_id = new_id("case")
        try:
            async with self.engine.begin() as c:
                token_id = await self._consume(c, ctx, token, "create_dispute_case", params)
                owned = (await c.execute(text("SELECT 1 FROM ref.transactions WHERE transaction_id = :t AND customer_id = :c"),
                                         {"t": transaction_id, "c": ctx.customer_id})).first()
                if owned is None:
                    raise ToolError("not_found")
                await c.execute(text("""INSERT INTO app.dispute_cases (case_id, customer_id, transaction_id, conversation_id, turn_id,
                                        confirmation_token_id, idempotency_key, reason_code, customer_statement, policy_rules_applied,
                                        confirmed_at) VALUES (:id, :cid, :tid, :conv, :turn, :tok, :idem, :reason, :stmt,
                                        CAST(:rules AS jsonb), now())"""),
                                {"id": case_id, "cid": ctx.customer_id, "tid": transaction_id, "conv": ctx.conversation_id,
                                 "turn": turn_id, "tok": token_id, "idem": idempotency_key, "reason": reason_code,
                                 "stmt": (customer_statement or "")[:1000], "rules": json.dumps(policy_rules, default=str)})
        except IntegrityError as e:
            existing = await self.get_existing_case(ctx, transaction_id)
            if existing:
                raise ToolError("duplicate_case", "ya hay un reclamo abierto", {"case_id": existing["case_id"]}) from e
            raise
        return {"case_id": case_id, "status": "registrado"}

    async def lock_card(self, ctx: ToolContext, *, product_id: str, token: str, reason: str, turn_id: str | None) -> dict:
        ctx.check_fault("lock_card")
        async with self.engine.begin() as c:
            token_id = await self._consume(c, ctx, token, "lock_card", {"product_id": product_id})
            card = (await c.execute(text("""SELECT product_type, status FROM app.card_status_effective
                                            WHERE product_id = :p AND customer_id = :c"""), {"p": product_id, "c": ctx.customer_id})).mappings().first()
            if card is None:
                raise ToolError("not_found")
            if card["product_type"] not in CARD_TYPES:
                raise ToolError("not_a_card")
            if card["status"] == "Blocked":
                raise ToolError("already_blocked")
            await c.execute(text("""INSERT INTO app.card_status_overrides (customer_id, product_id, status, reason, conversation_id,
                                    confirmation_token_id) VALUES (:c, :p, 'Blocked', :r, :conv, :tok)"""),
                            {"c": ctx.customer_id, "p": product_id, "r": reason, "conv": ctx.conversation_id, "tok": token_id})
        return {"product_id": product_id, "status": "Blocked"}

    async def create_handoff(self, ctx: ToolContext, handoff: dict, token: str | None = None) -> dict:
        """Lo invoca el controlador. Con `token` (reposición pedida por el cliente) se consume en la misma transacción."""
        ctx.check_fault("create_handoff")
        async with self.engine.begin() as c:
            if token is not None:
                await self._consume(c, ctx, token, "create_handoff", {"reason_code": handoff["reason_code"]})
            await c.execute(text("""INSERT INTO app.handoffs (handoff_id, conversation_id, customer_id, language, reason_code, priority,
                                    queue, summary, payload) VALUES (:id, :conv, :cid, :lang, :reason, :prio, :queue, :summary,
                                    CAST(:payload AS jsonb))"""),
                            {"id": handoff["handoff_id"], "conv": ctx.conversation_id, "cid": ctx.customer_id,
                             "lang": handoff["language"], "reason": handoff["reason_code"], "prio": handoff["priority"],
                             "queue": handoff["queue"], "summary": handoff.get("summary"),
                             "payload": json.dumps(handoff, default=str, ensure_ascii=False)})
        return {"handoff_id": handoff["handoff_id"], "queue": handoff["queue"], "status": "pendiente"}

    async def get_handoff(self, ctx: ToolContext, handoff_id: str) -> dict:
        async with self.engine.connect() as c:
            row = (await c.execute(text("SELECT handoff_id, status, reason_code, queue FROM app.handoffs WHERE handoff_id = :h AND customer_id = :c"),
                                   {"h": handoff_id, "c": ctx.customer_id})).mappings().first()
        if row is None:
            raise ToolError("not_found")
        return dict(row)
