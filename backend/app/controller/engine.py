"""Controlador de la conversación: máquina de estados con aclaración acotada (ADR-0005).

Estados: inicio, aclarando, confirmando_movimiento, confirmando_accion, ejecutando (transitorio dentro
del turno), cerrado, escalado. El estado y el contexto se guardan por conversación. El controlador:

- toma el customer_id SIEMPRE de la sesión (ToolContext);
- decide con código: el LLM solo interpreta (intent, extract) y redacta (clarify, confirm, explain,
  handoff_summary); si un nodo LLM falla tras su reintento, usa una plantilla y lo deja en la traza;
- aplica la política R1–R6 al confirmar el movimiento y la revalida al ejecutar;
- solo ejecuta acciones con efecto con un confirmation_token válido (R4) y las verifica leyendo lo
  escrito antes de emitir un bloque result con verified: true;
- registra cada paso en app.traces.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.app.auth.service import SessionContext
from backend.app.controller import blocks as B
from backend.app.controller.trace import TraceRecorder
from backend.app.dates import normalize, resolve_date_hint
from backend.app.errors import ApiError, not_found
from backend.app.llm.client import LLMError
from backend.app.llm.fake import FakeLLMClient
from backend.app.llm.nodes import Nodes, candidate_views, fill
from backend.app.ml.base import RankQuery
from backend.app.ml.intent import KeywordIntentClassifier
from backend.app.ml.ranker import alias_merchants, duplicate_pairs
from backend.app.ml.registry import MLComponents
from backend.app.ml import keyword_rules
from backend.app.policy import rules as P
from backend.app.security import new_id, sha256
from backend.app.tools import ToolContext, ToolError, Tools

TERMINAL = ("cerrado", "escalado")
DISPUTE_INTENTS = ("cargo_no_reconocido", "cobro_indebido")
REASON_BY_PROBLEM = {"monto_incorrecto": "amount_mismatch", "duplicado": "duplicate", "no_reconoce": "unrecognized"}
YES = r"^(si|sí|sim|claro|correcto|exacto|ese|esa|es ese|es esa|ese mismo|isso|isso mesmo|é esse|e esse|é essa|confirmo|dale|ok|okay|de acuerdo)\b"
NO = r"^(no|nao|não|ninguno|nenhum|nenhuma|ninguna|no es|não é|nao e|otro|outra|outro)\b"
CANCEL = r"\b(cancela\w*|olvidalo|olvídalo|deja(lo)? asi|no quiero|desisto|esquece|deixa pra la|nao quero)\b"
RECOGNIZED = r"\b(lo reconozco|ya lo reconoc\w*|ya me acorde|ya me acordé|era mio|era mío|si lo hice|sí lo hice|fui yo|agora reconheço|agora reconheco|reconheço sim|reconheco sim|lembrei|era meu|fui eu)\b"
OTHER = r"\b(era otr[oa]|es otr[oa]|no es ese|no es esa|otro cargo|otro movimiento|era outr[oa]|é outr[oa]|e outr[oa]|nao e ess[ea]|não é ess[ea]|outra cobrança|outra cobranca)\b"
REFUND = r"\b(devuelv\w*|devolucion|devolución|reembols\w*|reintegr\w*|estorn\w*|devolucao|devolução|me regresen)\b"


@dataclass
class TurnInput:
    message: str | None = None
    action: dict | None = None

    def as_dict(self) -> dict:
        return {"message": self.message} if self.message is not None else {"action": self.action}


@dataclass
class Turn:
    """Estado de trabajo de un turno."""
    conv: dict
    ctx: ToolContext
    session: SessionContext
    trace: TraceRecorder
    turn_id: str
    idempotency_key: str | None
    blocks: list[dict] = field(default_factory=list)

    @property
    def c(self) -> dict:
        return self.conv["context"]

    @property
    def lang(self) -> str:
        return self.conv.get("language") or "es"

    def say(self, key: str, **kw) -> None:
        self.blocks.append(B.text_block(B.t(self.lang, key, **kw)))


class Controller:
    def __init__(self, engine: AsyncEngine, tools: Tools, nodes: Nodes, ml: MLComponents, policy: P.PolicyConfig,
                 reference_date: date | None = None):
        self.engine, self.tools, self.nodes, self.ml, self.policy = engine, tools, nodes, ml, policy
        self.fallback = Nodes(FakeLLMClient(), nodes.config)       # plantillas si el LLM falla
        self.reference_date = reference_date

    # ================================================================ conversaciones
    async def session_date(self) -> date:
        """'Hoy' de la demo (P-08): REFERENCE_DATE o el último día con transacciones cargadas."""
        if self.reference_date:
            return self.reference_date
        async with self.engine.connect() as c:
            d = (await c.execute(text("SELECT max_transaction_date FROM ops.etl_runs WHERE status IN ('success', 'warning', 'noop') "
                                      "AND max_transaction_date IS NOT NULL ORDER BY run_id DESC LIMIT 1"))).scalar_one_or_none()
        return d.date() if d else date.today()

    async def data_freshness(self) -> dict:
        async with self.engine.connect() as c:
            row = (await c.execute(text("SELECT data_as_of, max_transaction_date FROM ops.etl_runs WHERE status IN "
                                        "('success', 'warning', 'noop') ORDER BY run_id DESC LIMIT 1"))).mappings().first()
        return {"data_as_of": row["data_as_of"].isoformat() if row and row["data_as_of"] else None,
                "max_transaction_date": row["max_transaction_date"].isoformat() if row and row["max_transaction_date"] else None}

    async def create_conversation(self, session: SessionContext, session_date: date | None = None,
                                  language: str | None = None) -> dict:
        if session.role != "customer" or not session.customer_id:
            raise ApiError(403, "forbidden", "Solo un cliente puede iniciar una conversación.")
        conv_id, sd, lang = new_id("conv"), session_date or await self.session_date(), language or session.language or "es"
        greeting = [B.text_block(B.t(lang, "greeting"))]
        async with self.engine.begin() as c:
            await c.execute(text("""INSERT INTO app.conversations (conversation_id, session_id, customer_id, state, language, session_date,
                                    context) VALUES (:id, :s, :c, 'inicio', :l, :d, '{}'::jsonb)"""),
                            {"id": conv_id, "s": session.session_id, "c": session.customer_id, "l": lang, "d": sd})
            await c.execute(text("""INSERT INTO app.turns (turn_id, conversation_id, seq, role, blocks, state_before, state_after)
                                    VALUES (:t, :conv, 1, 'assistant', CAST(:b AS jsonb), NULL, 'inicio')"""),
                            {"t": new_id("turn"), "conv": conv_id, "b": json.dumps(greeting, ensure_ascii=False)})
        return {"conversation_id": conv_id, "state": "inicio", "language": lang, "session_date": sd.isoformat(), "blocks": greeting}

    async def _load(self, conversation_id: str, customer_id: str) -> dict:
        async with self.engine.connect() as c:
            row = (await c.execute(text("SELECT * FROM app.conversations WHERE conversation_id = :id AND customer_id = :c"),
                                   {"id": conversation_id, "c": customer_id})).mappings().first()
        if row is None:
            raise not_found()
        conv = dict(row)
        conv["context"] = dict(conv["context"] or {})
        return conv

    # ================================================================ idempotencia
    async def _idem_begin(self, session: SessionContext, key: str, body_hash: str) -> dict | None:
        """Reserva la clave. Devuelve la respuesta guardada si es un reintento del mismo cuerpo."""
        async with self.engine.begin() as c:
            ins = await c.execute(text("""INSERT INTO app.idempotency_keys (session_id, idempotency_key, request_hash, expires_at)
                                          VALUES (:s, :k, :h, now() + interval '24 hours') ON CONFLICT DO NOTHING RETURNING 1"""),
                                  {"s": session.session_id, "k": key, "h": body_hash})
            if ins.first():
                return None
            row = (await c.execute(text("SELECT request_hash, response FROM app.idempotency_keys WHERE session_id = :s AND idempotency_key = :k"),
                                   {"s": session.session_id, "k": key})).mappings().first()
        if row["request_hash"] != body_hash:
            raise ApiError(409, "idempotency_conflict", "Esa Idempotency-Key ya se usó con otro contenido.")
        if row["response"] is None:
            raise ApiError(409, "idempotency_in_progress", "Esa petición todavía se está procesando.", retryable=True)
        return row["response"]

    async def _idem_release(self, session: SessionContext, key: str) -> None:
        async with self.engine.begin() as c:
            await c.execute(text("DELETE FROM app.idempotency_keys WHERE session_id = :s AND idempotency_key = :k AND response IS NULL"),
                            {"s": session.session_id, "k": key})

    # ================================================================ turno
    async def handle_turn(self, session: SessionContext, conversation_id: str, inp: TurnInput, idempotency_key: str | None,
                          faults: set[str] | None = None) -> dict:
        if session.role != "customer" or not session.customer_id:
            raise ApiError(403, "forbidden", "Solo el cliente dueño de la conversación puede escribir en ella.")
        if (inp.message is None) == (inp.action is None):
            raise ApiError(400, "validation_error", "Envía un mensaje o una acción, no ambos.")
        body_hash = sha256(json.dumps({"conversation_id": conversation_id, **inp.as_dict()}, sort_keys=True, ensure_ascii=False))
        if idempotency_key:
            if (saved := await self._idem_begin(session, idempotency_key, body_hash)) is not None:
                return {**saved, "replayed": True}
        try:
            response = await self._run_turn(session, conversation_id, inp, idempotency_key, faults or set())
        except BaseException:
            if idempotency_key:
                await self._idem_release(session, idempotency_key)
            raise
        if idempotency_key:
            async with self.engine.begin() as c:
                await c.execute(text("UPDATE app.idempotency_keys SET response = CAST(:r AS jsonb), status_code = 200 "
                                     "WHERE session_id = :s AND idempotency_key = :k"),
                                {"r": json.dumps(response, ensure_ascii=False, default=str), "s": session.session_id, "k": idempotency_key})
        return response

    async def _run_turn(self, session, conversation_id, inp, idempotency_key, faults) -> dict:
        conv = await self._load(conversation_id, session.customer_id)
        if conv["state"] in TERMINAL:
            raise ApiError(409, "conversation_closed", B.t(conv.get("language") or "es", "closed"))
        state_before = conv["state"]
        ctx = ToolContext(customer_id=session.customer_id, session_id=session.session_id, conversation_id=conversation_id,
                          session_date=conv["session_date"], faults=faults)
        turn = Turn(conv, ctx, session, TraceRecorder(), new_id("turn"), idempotency_key)
        turn.trace.add("entrada", "code", input=inp.as_dict(), extra={"state": state_before, "session_date": str(ctx.session_date)})
        if inp.message is not None:
            turn.c.setdefault("claims", []).append({"claim": inp.message[:500], "turn_id": turn.turn_id})
            await self._on_message(turn, inp.message)
        else:
            await self._on_action(turn, inp.action or {})
        await self._persist(turn, inp, state_before)
        return {"turn_id": turn.turn_id, "conversation_id": conversation_id, "state": conv["state"], "language": turn.lang,
                "blocks": turn.blocks, "input": inp.as_dict(), "data_as_of": await self.data_freshness(), "trace_id": turn.turn_id,
                "clarification_round": conv["clarification_round"]}

    async def _persist(self, turn: Turn, inp: TurnInput, state_before: str) -> None:
        conv = turn.conv
        async with self.engine.begin() as c:
            seq = (await c.execute(text("SELECT coalesce(max(seq), 0) FROM app.turns WHERE conversation_id = :c"),
                                   {"c": conv["conversation_id"]})).scalar_one()
            await c.execute(text("""INSERT INTO app.turns (turn_id, conversation_id, seq, role, message, action, blocks, state_before, state_after)
                                    VALUES (:t, :c, :s, 'customer', :m, CAST(:a AS jsonb), '[]'::jsonb, :sb, :sb)"""),
                            {"t": new_id("turn"), "c": conv["conversation_id"], "s": seq + 1, "m": inp.message,
                             "a": json.dumps(inp.action) if inp.action else None, "sb": state_before})
            await c.execute(text("""INSERT INTO app.turns (turn_id, conversation_id, seq, role, blocks, state_before, state_after)
                                    VALUES (:t, :c, :s, 'assistant', CAST(:b AS jsonb), :sb, :sa)"""),
                            {"t": turn.turn_id, "c": conv["conversation_id"], "s": seq + 2, "sb": state_before, "sa": conv["state"],
                             "b": json.dumps(turn.blocks, ensure_ascii=False, default=str)})
            await c.execute(text("""UPDATE app.conversations SET state = :st, language = :l, clarification_round = :r,
                                    context = CAST(:ctx AS jsonb), updated_at = now(),
                                    closed_at = CASE WHEN CAST(:st AS varchar) IN ('cerrado', 'escalado') THEN now() ELSE closed_at END
                                    WHERE conversation_id = :id"""),
                            {"st": conv["state"], "l": turn.lang, "r": conv["clarification_round"],
                             "ctx": json.dumps(conv["context"], ensure_ascii=False, default=str), "id": conv["conversation_id"]})
            for s in turn.trace.steps:
                await c.execute(text("""INSERT INTO app.traces (turn_id, conversation_id, step_seq, node, kind, implementation, tool, model,
                                        model_id, prompt_version, latency_ms, cost_usd, payload, rules, error)
                                        VALUES (:t, :c, :seq, :node, :kind, :impl, :tool, :model, :mid, :pv, :lat, :cost,
                                        CAST(:payload AS jsonb), CAST(:rules AS jsonb), :err)"""),
                                {"t": turn.turn_id, "c": conv["conversation_id"], "seq": s.seq, "node": s.node, "kind": s.kind,
                                 "impl": s.implementation, "tool": s.tool, "model": s.model, "mid": s.model_id, "pv": s.prompt_version,
                                 "lat": s.latency_ms, "cost": s.cost_usd, "payload": json.dumps(s.payload, ensure_ascii=False),
                                 "rules": json.dumps(s.rules, ensure_ascii=False) if s.rules else None, "err": s.error})

    # ================================================================ utilidades de pasos
    async def _tool(self, turn: Turn, name: str, fn, *args, retry: bool = True, **kwargs):
        """Llama un tool con un reintento acotado (solo errores de infraestructura) y lo deja en la traza."""
        attempts = 2 if retry else 1
        for attempt in range(1, attempts + 1):
            with turn.trace.timed() as t:
                try:
                    out = await fn(turn.ctx, *args, **kwargs)
                    err = None
                except ToolError as e:
                    out, err = None, e
                except Exception as e:     # noqa: BLE001 (base caída, etc.)
                    out, err = None, ToolError("db_unavailable", type(e).__name__)
            summary = out if not isinstance(out, list) else {"n": len(out)}
            turn.trace.add(f"tool:{name}", "code", tool=name, input={"args": [a for a in args], **kwargs} if name not in (
                "create_handoff",) else {"reason_code": args[0].get("reason_code") if args else None},
                output=summary, latency_ms=t["ms"], error=f"{err.code}: {err.message}" if err else None,
                extra={"attempt": attempt})
            if err is None:
                return out
            if err.code != "db_unavailable" or attempt == attempts:
                raise err
        raise AssertionError("inalcanzable")

    async def _llm(self, turn: Turn, node: str, *args, **kwargs):
        """Llama un nodo LLM; si falla tras su reintento, usa la plantilla del cliente falso y lo registra."""
        try:
            res = await getattr(self.nodes, node)(*args, **kwargs)
            turn.trace.add_llm(node, res, input={"args": [str(a)[:300] for a in args]})
            return res.data
        except LLMError as e:
            res = await getattr(self.fallback, node)(*args, **kwargs)
            turn.trace.add_llm(node, None, error=str(e), fallback="plantilla", model=self.nodes.config.model_for(node),
                               input={"args": [str(a)[:300] for a in args]})
            return res.data

    def _fact(self, turn: Turn, fact: str, value: Any, source_tool: str) -> None:
        turn.c.setdefault("facts", []).append({"fact": fact, "value": value, "source_tool": source_tool,
                                               "tool_call_id": f"{turn.turn_id}#{len(turn.trace.steps)}"})

    # ================================================================ mensajes
    async def _on_message(self, turn: Turn, message: str) -> None:
        st = turn.conv["state"]
        norm = normalize(message)
        if re.search(REFUND, norm):
            turn.c["refund_requested"] = True
            turn.blocks.append(B.notice("no_refund_approval", B.t(turn.lang, "no_refund")))
        if st == "inicio":
            if (resume := turn.c.get("resume_intent")) and re.match(YES, norm):
                turn.c["resume_intent"] = None
                turn.trace.add("reanudar", "code", output={"intencion": resume})
                await self._route(turn, resume, turn.c.get("saved_hints") or {})
                return
            turn.c["resume_intent"] = None
            await self._understand(turn, message)
            return
        quick = keyword_rules.classify(message)
        if quick["intent"] == "pedir_humano":
            await self._escalate(turn, "pide_humano")
            return
        if st in ("aclarando", "confirmando_movimiento") and turn.c.get("mode") == "dispute" and re.search(RECOGNIZED, norm):
            await self.tools.invalidate_tokens(turn.ctx)
            turn.trace.add("reconocido", "code", output={"reconoce_el_cargo": True})
            turn.say("recognized")
            await self._after_flow(turn)
            return
        if st == "confirmando_accion":
            pending = turn.c.get("pending") or {}
            if pending.get("action") == "create_dispute_case" and re.search(OTHER, norm):
                # cambio de movimiento después de ver la confirmación: se anula el token y se busca de nuevo
                await self.tools.invalidate_tokens(turn.ctx)
                turn.c.setdefault("excluded", []).append(pending["params"]["transaction_id"])
                turn.c.update({"pending": None, "selected": None})
                turn.trace.add("cambio_de_movimiento", "code", output={"excluida": pending["params"]["transaction_id"]})
                ex = await self._llm(turn, "extract", message)
                self._merge_hints(turn, ex.model_dump())
                await self._dispute_step(turn, count_round=True)
                return
            if re.search(RECOGNIZED, norm) and pending.get("action") == "create_dispute_case":
                await self.tools.invalidate_tokens(turn.ctx)
                turn.c["pending"] = None
                turn.say("recognized")
                await self._after_flow(turn)
                return
            if re.search(CANCEL, norm) or re.match(NO, norm):
                await self._cancel_pending(turn)
            else:   # R4: el texto nunca ejecuta; se vuelve a mostrar la confirmación
                turn.trace.add("r4_texto_no_confirma", "code", output={"mensaje_ignorado_como_confirmacion": True},
                               rules=[P.r4_constant().as_dict()])
                await self._reissue_pending(turn)
            return
        if re.search(CANCEL, norm):
            turn.say("cancelled")
            turn.conv["state"] = "cerrado"
            return
        if st == "confirmando_movimiento":
            if re.match(YES, norm):
                await self._confirm_movement(turn)
                return
            if re.match(NO, norm):
                turn.c.setdefault("excluded", []).append(turn.c.get("selected"))
                turn.c["selected"] = None
                await self._dispute_step(turn, count_round=True)
                return
        # aclarando (o confirmando_movimiento con más datos): nuevas pistas → buscar de nuevo
        if turn.c.get("mode") == "card_pick":
            await self._card_step(turn, hint=message)
            return
        ex = await self._llm(turn, "extract", message)
        self._merge_hints(turn, ex.model_dump())
        await self._dispute_step(turn, count_round=True)

    async def _understand(self, turn: Turn, message: str) -> None:
        """inicio: intención y extracción en paralelo; luego enrutar."""
        intent_task = asyncio.create_task(self.ml.intent.classify(message))
        extract_task = asyncio.create_task(self.nodes.extract(message))
        try:
            pred = await intent_task
            turn.trace.add_llm("intent", pred.llm, input={"texto": message[:300]}) if pred.llm else turn.trace.add(
                "intent", "ml", implementation=pred.version, input={"texto": message[:300]}, output=pred.output.model_dump())
            out = pred.output
        except LLMError as e:
            pred = await KeywordIntentClassifier().classify(message)
            turn.trace.add("intent", "ml", implementation=pred.version, error=str(e), output=pred.output.model_dump(),
                           extra={"fallback": "keyword"})
            out = pred.output
        try:
            exres = await extract_task
            turn.trace.add_llm("extract", exres, input={"texto": message[:300]})
            extracted = exres.data.model_dump()
        except LLMError as e:
            extracted = keyword_rules.extract(message)
            turn.trace.add_llm("extract", None, error=str(e), fallback="reglas", model=self.nodes.config.model_for("extract"))
        turn.conv["language"] = out.idioma
        if out.sospecha_manipulacion:
            turn.c["manipulation_attempts"] = turn.c.get("manipulation_attempts", 0) + 1
            turn.trace.add("sospecha_manipulacion", "code", output={"intentos": turn.c["manipulation_attempts"]})
            turn.blocks.append(B.notice("scope_own_account", B.t(turn.lang, "manipulation"), level="warning"))
        intents = [out.intent, *[i for i in out.otras_intenciones if i != out.intent]]
        if "bloquear_tarjeta" in intents:        # contener el riesgo primero
            intents.remove("bloquear_tarjeta")
            intents.insert(0, "bloquear_tarjeta")
        main, rest = intents[0], [i for i in intents[1:] if i in DISPUTE_INTENTS + ("consulta_movimientos", "estado_reclamo")]
        turn.c.update({"intent": main, "pending_intents": rest, "tema": out.tema, "certeza": out.certeza, "saved_hints": extracted})
        turn.trace.add("enrutamiento", "code", output={"intencion": main, "pendientes": rest})
        await self._route(turn, main, extracted)

    async def _route(self, turn: Turn, intent: str, extracted: dict) -> None:
        c = turn.c
        if intent == "sin_contenido":
            turn.say("sin_contenido")
        elif intent == "fuera_de_alcance":
            tema = c.get("tema")
            turn.blocks.append(B.notice("out_of_scope", B.t(turn.lang, "out_of_scope", tema=tema) if tema else B.t(turn.lang, "out_of_scope_generic")))
        elif intent == "pedir_humano":
            await self._escalate(turn, "pide_humano")
        elif intent == "estado_reclamo":
            await self._cases(turn)
        elif intent == "consulta_movimientos":
            await self._movements(turn, extracted)
        elif intent == "bloquear_tarjeta":
            c.update({"mode": "card_pick", "card_hint": extracted.get("card_hint")})
            c["saved_hints"] = extracted          # por si luego sigue con otra intención
            await self._card_step(turn, hint=extracted.get("card_hint"))
        else:
            self._start_dispute(turn, intent, extracted)
            await self._dispute_step(turn, count_round=False)

    # ================================================================ disputa
    def _start_dispute(self, turn: Turn, intent: str, hints: dict, preselected: str | None = None) -> None:
        problema = hints.get("problema")
        reason = "unrecognized" if intent == "cargo_no_reconocido" else REASON_BY_PROBLEM.get(problema) if problema in (
            "monto_incorrecto", "duplicado") else None
        turn.c.update({"intent": intent, "mode": "dispute", "reason_code": reason, "hints": {}, "excluded": [], "shown": [],
                       "selected": preselected})
        turn.conv["clarification_round"] = 0
        self._merge_hints(turn, hints)

    def _merge_hints(self, turn: Turn, new: dict) -> None:
        h = turn.c.setdefault("hints", {})
        for k, v in new.items():
            if v not in (None, "", [], {}):
                h[k] = v
        if turn.c.get("intent") == "cobro_indebido" and turn.c.get("reason_code") is None and h.get("problema") in (
                "monto_incorrecto", "duplicado"):
            turn.c["reason_code"] = REASON_BY_PROBLEM[h["problema"]]

    def _query(self, turn: Turn) -> RankQuery:
        h = turn.c.get("hints", {})
        amount = currency = None
        approx = False
        if a := h.get("amount_hint"):
            try:
                amount = Decimal(str(a.get("value"))) if a.get("value") else None
            except InvalidOperation:
                amount = None
            currency, approx = a.get("currency"), bool(a.get("approx"))
        return RankQuery(amount=amount, currency=currency, amount_approx=approx,
                         date_range=resolve_date_hint(h.get("date_hint"), turn.ctx.session_date),
                         merchant_hint=h.get("merchant_hint"), session_date=turn.ctx.session_date)

    async def _dispute_step(self, turn: Turn, count_round: bool) -> None:
        c, conv = turn.c, turn.conv
        max_rounds = self.policy.max_clarify_rounds
        try:
            txs = await self._tool(turn, "search_transactions", self.tools.search_transactions, self.policy.search_window_days)
        except ToolError:
            await self._tool_failed(turn)
            return
        txs = [t for t in txs if t["transaction_id"] not in set(c.get("excluded") or [])]
        q = self._query(turn)
        if q.date_range:
            turn.trace.add("fechas", "code", implementation="dates.py", input={"date_hint": c["hints"].get("date_hint")},
                           output={"desde": q.date_range.start, "hasta": q.date_range.end, "regla": q.date_range.rule})
        if count_round:
            if conv["clarification_round"] >= max_rounds:      # ya se hicieron las 3 vueltas
                turn.say("exhausted")
                await self._escalate(turn, "aclaracion_agotada")
                return
            conv["clarification_round"] += 1
        if not txs:
            turn.say("no_candidates", dias=self.policy.search_window_days)
            conv["state"] = "aclarando"
            return
        # cobro duplicado: proponer el par de cargos iguales
        if c.get("reason_code") == "duplicate" and not c.get("dup_offered"):
            ranked_all = self.ml.ranker.rank(q, txs)
            order = {s.transaction["transaction_id"]: s.rank for s in ranked_all.candidates}
            pairs = sorted(duplicate_pairs(txs), key=lambda p: order[p[0]["transaction_id"]] + order[p[1]["transaction_id"]])
            turn.trace.add("pares_duplicados", "code", implementation="duplicate_pairs", output={"n_pares": len(pairs)})
            c["dup_offered"] = True
            if pairs:
                a, b = pairs[0]
                await self._show_candidates(turn, [a, b], B.t(turn.lang, "duplicate_pick"), counts=False)
                return
            turn.say("no_duplicate")
        ranked = self.ml.ranker.rank(q, txs)
        decision = self.ml.clarify.decide(q, ranked, problem_known=c.get("reason_code") is not None)
        top = [{"transaction_id": s.transaction["transaction_id"], "score": s.score, "p": round(s.probability, 4)}
               for s in ranked.candidates[:5]]
        turn.trace.add("ranking", "ml", implementation=ranked.version, input={"n_candidatas": len(txs), "consulta": vars(q)},
                       output={"top": top})
        turn.trace.add("aclaracion", "ml", implementation=decision.version,
                       output={"preguntar": decision.ask, "motivos": decision.reasons, "atributo": decision.discriminant})
        if decision.ask:
            shown = [ranked.candidates[i].transaction for i in decision.show]
            views, _ = candidate_views(shown, turn.lang)
            q_out = await self._llm(turn, "clarify", turn.lang, views, decision.discriminant, max(conv["clarification_round"], 1),
                                    max_rounds)
            await self._show_candidates(turn, shown, q_out.pregunta, counts=True)
            return
        await self._propose(turn, ranked.candidates[0].transaction)

    async def _show_candidates(self, turn: Turn, txs: list[dict], prompt: str, counts: bool) -> None:
        conv = turn.conv
        if counts and conv["clarification_round"] == 0:
            conv["clarification_round"] = 1
        turn.c["shown"] = [t["transaction_id"] for t in txs]
        turn.blocks.append(B.text_block(prompt))
        turn.blocks.append({"type": "candidate_list", "prompt": prompt, "candidates": [B.tx_view(t, i + 1, turn.lang) for i, t in enumerate(txs)],
                            "allow_none": True, "round": conv["clarification_round"], "max_rounds": self.policy.max_clarify_rounds})
        conv["state"] = "aclarando"

    async def _propose(self, turn: Turn, tx: dict) -> None:
        """Candidata clara (o elegida): transaction_card para confirmar el movimiento."""
        turn.c["selected"] = tx["transaction_id"]
        turn.c["shown"] = [tx["transaction_id"]]
        self._fact(turn, "transaccion_propuesta", tx["transaction_id"], "search_transactions")
        out = await self._llm(turn, "confirm", turn.lang, "confirmar_movimiento", turn.c.get("reason_code"), ["comercio", "monto", "fecha"])
        turn.blocks.append(B.text_block(self._fill(turn, out.texto, tx)))
        turn.blocks.append({"type": "transaction_card", "transaction": B.tx_view(tx, lang=turn.lang), "source": "get_transaction"})
        turn.conv["state"] = "confirmando_movimiento"

    def _fill(self, turn: Turn, template: str, tx: dict | None = None, **extra) -> str:
        values = dict(extra)
        if tx:
            values.update({"comercio": B.tx_label(tx, turn.lang),
                           "monto": B.fmt_money(tx["amount"], tx["currency"], turn.lang),
                           "fecha": B.fmt_date(tx["transaction_date"], turn.lang)})
        try:
            return fill(template, values, set(values) | {"comercio", "monto", "fecha", "tarjeta", "numero_reclamo", "numero_atencion"})
        except LLMError:
            return template

    async def _confirm_movement(self, turn: Turn) -> None:
        """El cliente confirmó el movimiento: política R1–R6 y, si permite, confirmación de la acción."""
        c = turn.c
        if c.get("reason_code") is None:        # cobro_indebido sin tipo: se pregunta antes de seguir
            await self._dispute_step(turn, count_round=True)
            return
        try:
            tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, c["selected"])
            existing = await self._tool(turn, "get_existing_case", self.tools.get_existing_case, c["selected"])
        except ToolError as e:
            if e.code == "not_found":
                turn.blocks.append(B.error("not_found", "No encontré ese movimiento en tu cuenta."))
                return
            await self._tool_failed(turn)
            return
        self._fact(turn, "transaccion_confirmada_por_cliente", tx["transaction_id"], "get_transaction")
        self._fact(turn, "monto", f"{B.money(tx['amount'])} {tx['currency']}", "get_transaction")
        self._fact(turn, "fecha", tx["transaction_date"].isoformat(), "get_transaction")
        self._fact(turn, "estado", tx["transaction_status"], "get_transaction")
        self._fact(turn, "dias_desde_el_cargo", (turn.ctx.session_date - tx["transaction_date"].date()).days, "get_transaction")
        self._fact(turn, "reclamo_existente", existing["case_id"] if existing else None, "get_existing_case")
        risk = self.ml.risk.assess(tx)
        turn.trace.add("fraud_risk", "ml", implementation=risk.version, input={"fraud_score": risk.inputs_used.get("fraud_score")},
                       output={"banda": risk.band, "probabilidad": risk.probability, "score_faltante": risk.probability is None})
        self._fact(turn, "banda_riesgo", risk.band, "fraud_risk")
        decision = P.evaluate_dispute(tx, turn.ctx.session_date, existing, risk, c["reason_code"], self.policy,
                                      refund_requested=bool(c.get("refund_requested")))
        c["last_rules"] = decision.rules_dicts()
        turn.trace.add("politica", "code", implementation="policy@v1", output={"resultado": decision.outcome,
                       "decide": decision.decisive.as_dict() if decision.decisive else None,
                       "ofrecer_bloqueo": decision.offer_lock, "recomendar_bloqueo": decision.recommend_lock},
                       rules=decision.rules_dicts())
        c["offer_lock_product"] = tx["product_id"] if (decision.offer_lock or decision.recommend_lock) else None
        if decision.outcome == P.INFORMAR:
            case_num = existing["case_id"] if existing else None
            turn.blocks.append(B.notice(decision.notice_code, self._notice_text(turn, decision, existing)))
            out = await self._llm(turn, "explain", turn.lang, "informar", self._rules_for_llm(decision),
                                  self._facts_for_llm(turn, tx), ["numero_reclamo"] if case_num else [])
            turn.blocks.append(B.text_block(self._fill(turn, out.texto, numero_reclamo=case_num or "")))
            await self._finish(turn, "cerrado")
            return
        if decision.outcome == P.ESCALAR:
            await self._escalate(turn, decision.handoff_reason, queue=decision.handoff_queue, tx=tx)
            if decision.recommend_lock or decision.offer_lock:
                await self._offer_lock(turn, tx["product_id"], recommend=decision.recommend_lock, escalate_after=True)
            return
        # permitir → confirmación explícita de la acción (R4)
        params = {"transaction_id": tx["transaction_id"], "reason_code": c["reason_code"]}
        token, exp = await self.tools.issue_token(turn.ctx, "create_dispute_case", params, self.policy.confirmation_token_ttl_seconds)
        out = await self._llm(turn, "confirm", turn.lang, "confirmar_reclamo", c["reason_code"], ["comercio", "monto", "fecha"])
        c["pending"] = {"action": "create_dispute_case", "params": params, "offer_lock_after": decision.offer_lock}
        turn.blocks.append({"type": "action_confirmation", "action": "create_dispute_case", "summary": self._fill(turn, out.texto, tx),
                            "params": params, "confirmation_token": token, "expires_at": exp.isoformat(),
                            "disclaimer": B.DISCLAIMER[turn.lang]})
        turn.trace.add("token_emitido", "code", output={"accion": "create_dispute_case", "vence": exp})
        turn.conv["state"] = "confirmando_accion"

    def _notice_text(self, turn: Turn, decision: P.PolicyDecision, existing: dict | None) -> str:
        es = turn.lang == "es"
        if decision.notice_code == "existing_case":
            return (f"Ya tienes un reclamo abierto sobre este cargo: {existing['case_id']} ({existing['status']})." if es else
                    f"Você já tem uma reclamação aberta sobre esta cobrança: {existing['case_id']} ({existing['status']}).")
        if decision.notice_code == "pending_transaction":
            return ("Este cargo todavía está pendiente y puede cambiar; por ahora no se registra un reclamo." if es else
                    "Esta cobrança ainda está pendente e pode mudar; por enquanto não é registrada uma reclamação.")
        return ("Este movimiento no tiene un cargo vigente (fue rechazado o revertido), así que no hace falta un reclamo." if es else
                "Esta movimentação não tem cobrança vigente (foi recusada ou estornada), então não é preciso reclamar.")

    @staticmethod
    def _rules_for_llm(decision: P.PolicyDecision) -> list[dict]:
        return [{"id": r.id, "resultado": r.resultado, "motivo": r.motivo} for r in decision.rules if r.resultado != P.PERMITIR]

    @staticmethod
    def _facts_for_llm(turn: Turn, tx: dict) -> dict:
        """Solo los campos imprescindibles (P-05): comercio, monto, moneda, fecha y estado."""
        v, _ = candidate_views([tx], turn.lang)
        return {"comercio": v[0].comercio, "monto": v[0].monto, "moneda": v[0].moneda, "fecha": v[0].fecha, "estado": v[0].estado}

    # ================================================================ acciones
    async def _on_action(self, turn: Turn, action: dict) -> None:
        kind = action.get("type")
        st, c = turn.conv["state"], turn.c
        if kind == "request_human":
            await self._escalate(turn, "pide_humano")
        elif kind == "select_candidate":
            tid = action.get("transaction_id")
            if st not in ("aclarando", "confirmando_movimiento") or tid not in (c.get("shown") or []):
                raise ApiError(409, "invalid_state", "Ese movimiento no está entre las opciones de este paso.")
            if st == "confirmando_movimiento" and tid == c.get("selected"):
                await self._confirm_movement(turn)
            else:
                try:
                    tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, tid)
                except ToolError as e:
                    if e.code == "not_found":
                        raise not_found() from e
                    await self._tool_failed(turn)
                    return
                if c.get("intent") == "cobro_indebido" and c.get("reason_code") == "duplicate":
                    c["selected"] = tid       # en duplicado, elegir cuál de los dos ya identifica el movimiento
                    await self._confirm_movement(turn)
                else:
                    await self._propose(turn, tx)
        elif kind == "dispute_transaction":        # "No reconozco este cargo" desde la lista de movimientos
            tid = action.get("transaction_id")
            if tid not in (c.get("listed") or []):
                raise ApiError(409, "invalid_state", "Ese movimiento no está en la lista mostrada.")
            try:
                tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, tid)
            except ToolError as e:
                raise not_found() from e
            self._start_dispute(turn, "cargo_no_reconocido", {}, preselected=tid)
            await self._propose(turn, tx)
        elif kind == "select_card":
            if c.get("mode") != "card_pick" or action.get("product_id") not in (c.get("cards_shown") or []):
                raise ApiError(409, "invalid_state", "Esa tarjeta no está entre las opciones de este paso.")
            await self._offer_lock(turn, action["product_id"], recommend=False, escalate_after=False)
        elif kind == "reject":
            if st == "confirmando_accion":
                await self._cancel_pending(turn)
            elif st == "confirmando_movimiento":
                c.setdefault("excluded", []).append(c.get("selected"))
                c["selected"] = None
                await self._dispute_step(turn, count_round=True)
            elif st == "aclarando":
                c.setdefault("excluded", []).extend(c.get("shown") or [])
                if turn.conv["clarification_round"] >= self.policy.max_clarify_rounds:
                    turn.say("exhausted")
                    await self._escalate(turn, "aclaracion_agotada")
                else:
                    turn.conv["clarification_round"] += 1
                    turn.say("ask_more")
            else:
                raise ApiError(409, "invalid_state", "No hay nada que rechazar en este paso.")
        elif kind == "confirm":
            if st != "confirmando_accion" or not c.get("pending"):
                raise ApiError(409, "invalid_state", "No hay ninguna acción pendiente de confirmar.")
            await self._execute(turn, action.get("confirmation_token") or "")
        else:
            raise ApiError(400, "validation_error", f"Acción desconocida: {kind!r}")

    async def _execute(self, turn: Turn, token: str) -> None:
        """confirmando_accion → ejecutando → verificado (o escalado). Revalida permisos y reglas antes de actuar."""
        c = turn.c
        pending = c["pending"]
        action = pending["action"]
        turn.trace.add("ejecutando", "code", input={"accion": action}, rules=[P.r4_constant().as_dict()])
        try:
            if action == "create_dispute_case":
                tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, pending["params"]["transaction_id"])
                existing = await self._tool(turn, "get_existing_case", self.tools.get_existing_case, tx["transaction_id"])
                risk = self.ml.risk.assess(tx)
                decision = P.evaluate_dispute(tx, turn.ctx.session_date, existing, risk, pending["params"]["reason_code"],
                                              self.policy, refund_requested=bool(c.get("refund_requested")))
                turn.trace.add("politica_revalidada", "code", implementation="policy@v1", output={"resultado": decision.outcome},
                               rules=decision.rules_dicts())
                if decision.outcome != P.PERMITIR:
                    await self.tools.invalidate_tokens(turn.ctx)
                    c["pending"] = None
                    c["selected"] = tx["transaction_id"]
                    await self._confirm_movement(turn)       # el camino que corresponda ahora (informar / escalar)
                    return
                res = await self._tool(turn, "create_dispute_case", self.tools.create_dispute_case, retry=False,
                                       transaction_id=tx["transaction_id"], reason_code=pending["params"]["reason_code"],
                                       customer_statement=" ".join(x["claim"] for x in c.get("claims", []))[:1000], token=token,
                                       idempotency_key=turn.idempotency_key, policy_rules=decision.rules_dicts(), turn_id=None)
                await self._verify_case(turn, res["case_id"], tx, pending)
            elif action == "lock_card":
                res = await self._tool(turn, "lock_card", self.tools.lock_card, retry=False, product_id=pending["params"]["product_id"],
                                       token=token, reason=c.get("intent") or "riesgo", turn_id=None)
                await self._verify_lock(turn, pending["params"]["product_id"], pending)
            elif action == "create_handoff":
                handoff = await self._build_handoff(turn, "reposicion_tarjeta")
                res = await self._tool(turn, "create_handoff", self.tools.create_handoff, handoff, token=token, retry=False)
                await self._verify_handoff(turn, res["handoff_id"], handoff)
                c["pending"] = None
                await self._after_flow(turn, default_state="escalado")
        except ToolError as e:
            if e.code == "invalid_confirmation":
                turn.blocks.append(B.error("invalid_confirmation", B.t(turn.lang, "invalid_confirmation")))
                turn.trace.add("token_invalido", "code", output={"motivo": e.message})
                await self._reissue_pending(turn)            # la conversación se retoma sin ejecutar nada
            elif e.code == "duplicate_case":
                c["pending"] = None
                turn.blocks.append(B.notice("existing_case", f"{e.data.get('case_id')}"))
                await self._finish(turn, "cerrado")
            elif e.code == "already_blocked":
                c["pending"] = None
                turn.say("card_already_blocked")
                await self._after_flow(turn)
            elif e.code == "not_found":
                c["pending"] = None
                turn.blocks.append(B.error("not_found", "No encontré ese recurso en tu cuenta."))
                await self._finish(turn, "cerrado")
            else:
                await self._tool_failed(turn)

    async def _verify_case(self, turn: Turn, case_id: str, tx: dict, pending: dict) -> None:
        try:
            case = await self._tool(turn, "get_case", self.tools.get_case, case_id)
            ok = case["transaction_id"] == tx["transaction_id"] and case["status"] == "registrado"
        except ToolError:
            ok = False
        turn.trace.add("verificacion", "code", output={"accion": "create_dispute_case", "verificado": ok, "case_id": case_id})
        if not ok:
            turn.blocks.append({"type": "result", "action": "create_dispute_case", "status": "failed", "verified": False,
                                "reference_id": None, "details": B.t(turn.lang, "not_verified")})
            await self._escalate(turn, "accion_no_verificada", tx=tx)
            return
        turn.c.setdefault("actions", []).append({"action": "create_dispute_case", "status": "success", "verified": True,
                                                  "reference_id": case_id})
        turn.blocks.append({"type": "result", "action": "create_dispute_case", "status": "success", "verified": True,
                            "reference_id": case_id, "details": {"reason_code": pending["params"]["reason_code"]}})
        out = await self._llm(turn, "explain", turn.lang, "reclamo_registrado", [], self._facts_for_llm(turn, tx), ["numero_reclamo"])
        turn.blocks.append(B.text_block(self._fill(turn, out.texto, numero_reclamo=case_id)))
        turn.c["pending"] = None
        if pending.get("offer_lock_after") and turn.c.get("offer_lock_product"):
            await self._offer_lock(turn, turn.c["offer_lock_product"], recommend=False, escalate_after=False)
            return
        await self._after_flow(turn)

    async def _verify_lock(self, turn: Turn, product_id: str, pending: dict) -> None:
        try:
            st = await self._tool(turn, "get_card_status", self.tools.get_card_status, product_id)
            ok = st["status"] == "Blocked"
        except ToolError:
            ok = False
        turn.trace.add("verificacion", "code", output={"accion": "lock_card", "verificado": ok})
        turn.c["pending"] = None
        if not ok:
            turn.blocks.append({"type": "result", "action": "lock_card", "status": "failed", "verified": False, "reference_id": None,
                                "details": B.t(turn.lang, "not_verified")})
            await self._escalate(turn, "accion_no_verificada")
            return
        turn.c.setdefault("actions", []).append({"action": "lock_card", "status": "success", "verified": True, "reference_id": product_id})
        turn.blocks.append({"type": "result", "action": "lock_card", "status": "success", "verified": True, "reference_id": product_id,
                            "details": {"status": "Blocked"}})
        if pending.get("escalate_after"):
            await self._finish(turn, "escalado")
            return
        if turn.c.get("intent") == "bloquear_tarjeta":     # autoservicio: ofrecer reposición con una persona
            token, exp = await self.tools.issue_token(turn.ctx, "create_handoff", {"reason_code": "reposicion_tarjeta"},
                                                      self.policy.confirmation_token_ttl_seconds)
            turn.c["pending"] = {"action": "create_handoff", "params": {"reason_code": "reposicion_tarjeta"}}
            turn.blocks.append({"type": "action_confirmation", "action": "create_handoff", "summary": B.t(turn.lang, "offer_replacement"),
                                "params": {"reason_code": "reposicion_tarjeta"}, "confirmation_token": token, "expires_at": exp.isoformat(),
                                "disclaimer": ""})
            turn.conv["state"] = "confirmando_accion"
            return
        await self._after_flow(turn)

    async def _verify_handoff(self, turn: Turn, handoff_id: str, handoff: dict) -> None:
        try:
            h = await self._tool(turn, "get_handoff", self.tools.get_handoff, handoff_id)
            ok = h["status"] == "pendiente"
        except ToolError:
            ok = False
        turn.trace.add("verificacion", "code", output={"accion": "create_handoff", "verificado": ok})
        if ok:
            turn.blocks.append({"type": "handoff_notice", "handoff_id": handoff_id, "reason_code": handoff["reason_code"],
                                "message": B.t(turn.lang, "handoff", handoff_id=handoff_id), "next_step": "contacto_del_banco"})

    async def _after_flow(self, turn: Turn, default_state: str = "cerrado") -> None:
        """Fin de un flujo: si quedó otra intención pendiente (p. ej. cargo tras bloquear), se ofrece seguir."""
        rest = turn.c.get("pending_intents") or []
        if rest:
            turn.say("continue_other")
            turn.c["resume_intent"] = rest[0]
            turn.c["pending_intents"] = rest[1:]
            turn.conv["state"] = "inicio"
            turn.c["mode"] = None
            return
        await self._finish(turn, default_state)

    async def _finish(self, turn: Turn, state: str) -> None:
        turn.conv["state"] = state

    async def _cancel_pending(self, turn: Turn) -> None:
        pending = turn.c.get("pending") or {}
        await self.tools.invalidate_tokens(turn.ctx)
        turn.c["pending"] = None
        turn.trace.add("cancelado", "code", output={"accion": pending.get("action")})
        turn.say("cancelled")
        if pending.get("escalate_after"):
            await self._finish(turn, "escalado")
        elif pending.get("action") in ("lock_card", "create_handoff") and turn.c.get("actions"):
            await self._after_flow(turn)            # ya hubo una acción verificada antes
        else:
            await self._after_flow(turn)

    async def _reissue_pending(self, turn: Turn) -> None:
        """Vuelve a mostrar la confirmación pendiente con un token nuevo (sesión nueva, texto libre, token viejo)."""
        pending = turn.c.get("pending")
        if not pending:
            return
        token, exp = await self.tools.issue_token(turn.ctx, pending["action"], pending["params"], self.policy.confirmation_token_ttl_seconds)
        summary = B.t(turn.lang, "offer_replacement") if pending["action"] == "create_handoff" else None
        if pending["action"] == "create_dispute_case":
            try:
                tx = await self.tools.get_transaction(turn.ctx, pending["params"]["transaction_id"])
                out = await self._llm(turn, "confirm", turn.lang, "confirmar_reclamo", pending["params"]["reason_code"],
                                      ["comercio", "monto", "fecha"])
                summary = self._fill(turn, out.texto, tx)
            except ToolError:
                summary = B.DISCLAIMER[turn.lang]
        elif pending["action"] == "lock_card":
            out = await self._llm(turn, "confirm", turn.lang, "confirmar_bloqueo", None, ["tarjeta"])
            summary = self._fill(turn, out.texto, tarjeta=pending.get("card_label", ""))
        turn.blocks.append({"type": "action_confirmation", "action": pending["action"], "summary": summary, "params": pending["params"],
                            "confirmation_token": token, "expires_at": exp.isoformat(),
                            "disclaimer": B.DISCLAIMER[turn.lang] if pending["action"] == "create_dispute_case" else ""})
        turn.trace.add("token_reemitido", "code", output={"accion": pending["action"]})
        turn.conv["state"] = "confirmando_accion"

    # ================================================================ tarjeta
    async def _card_step(self, turn: Turn, hint: str | None) -> None:
        try:
            cards = await self._tool(turn, "list_cards", self.tools.list_cards)
        except ToolError:
            await self._tool_failed(turn)
            return
        active = [x for x in cards if x["status"] not in ("Blocked", "Closed")]
        if not active:
            turn.say("card_already_blocked" if cards else "no_cards")
            await self._after_flow(turn)
            return
        chosen = active if len(active) == 1 else self._match_cards(active, hint)
        if len(chosen) == 1:
            await self._offer_lock(turn, chosen[0]["product_id"], recommend=False, escalate_after=False, card=chosen[0])
            return
        turn.c.update({"mode": "card_pick", "cards_shown": [x["product_id"] for x in active]})
        turn.say("pick_card")
        turn.blocks.append({"type": "card_list", "cards": [{"product_id": x["product_id"],
                                                            "label": f"{B.CARD_LABEL[turn.lang].get(x['product_type'], x['product_type'])} ···{x['last4']}",
                                                            "product_type": x["product_type"], "status": x["status"]} for x in active]})
        turn.conv["state"] = "aclarando"

    @staticmethod
    def _match_cards(cards: list[dict], hint: str | None) -> list[dict]:
        h = normalize(hint or "")
        if m := re.search(r"(\d{4})", h):
            return [x for x in cards if x["last4"] == m.group(1)]
        if "credito" in h:
            return [x for x in cards if x["product_type"] == "Tarjeta Crédito"]
        if "debito" in h:
            return [x for x in cards if x["product_type"] == "Tarjeta Débito"]
        return cards

    async def _offer_lock(self, turn: Turn, product_id: str, recommend: bool, escalate_after: bool, card: dict | None = None) -> None:
        if card is None:
            try:
                card = await self._tool(turn, "get_card_status", self.tools.get_card_status, product_id)
                card["last4"] = next((x["last4"] for x in await self.tools.list_cards(turn.ctx) if x["product_id"] == product_id), "")
            except ToolError:                      # el producto del cargo no es una tarjeta: no hay qué bloquear
                if escalate_after:
                    await self._finish(turn, "escalado")
                else:
                    await self._after_flow(turn)
                return
            if card["status"] == "Blocked":
                if escalate_after:
                    await self._finish(turn, "escalado")
                else:
                    await self._after_flow(turn)
                return
        label = f"{B.CARD_LABEL[turn.lang].get(card['product_type'], card['product_type'])} ···{card.get('last4', '')}"
        params = {"product_id": product_id}
        token, exp = await self.tools.issue_token(turn.ctx, "lock_card", params, self.policy.confirmation_token_ttl_seconds)
        out = await self._llm(turn, "confirm", turn.lang, "confirmar_bloqueo", None, ["tarjeta"])
        if recommend:
            turn.say("recommend_lock")
        elif escalate_after or turn.c.get("intent") != "bloquear_tarjeta":
            turn.say("offer_lock")
        turn.blocks.append({"type": "action_confirmation", "action": "lock_card", "summary": self._fill(turn, out.texto, tarjeta=label),
                            "params": params, "confirmation_token": token, "expires_at": exp.isoformat(), "disclaimer": ""})
        turn.c["pending"] = {"action": "lock_card", "params": params, "escalate_after": escalate_after, "card_label": label}
        turn.c["mode"] = None
        turn.conv["state"] = "confirmando_accion"

    # ================================================================ lecturas informativas
    async def _movements(self, turn: Turn, hints: dict) -> None:
        sd = turn.ctx.session_date
        rng = resolve_date_hint(hints.get("date_hint"), sd)
        start, end = (rng.start, rng.end) if rng else (sd - timedelta(days=self.policy.list_default_days), sd)
        merchants = sorted(alias_merchants(hints.get("merchant_hint")))
        like = None
        if hints.get("merchant_hint") and not merchants:
            words = [w for w in re.split(r"\W+", normalize(hints["merchant_hint"])) if len(w) > 2 and w not in ("una", "uno", "los", "las")]
            like = max(words, key=len) if words else None
        try:
            res = await self._tool(turn, "list_transactions", self.tools.list_transactions, date_from=start, date_to=end,
                                   merchants=merchants or None, merchant_like=like, limit=10)
        except ToolError:
            await self._tool_failed(turn)
            return
        turn.c["listed"] = [x["transaction_id"] for x in res["transactions"]]
        desde, hasta = B.fmt_date(start, turn.lang), B.fmt_date(end, turn.lang)
        turn.say("movements" if res["count"] else "movements_none", n=res["count"], desde=desde, hasta=hasta)
        turn.blocks.append({"type": "transaction_list", "period": {"from": start.isoformat(), "to": end.isoformat()},
                            "filters": {"merchants": merchants, "merchant_text": like}, "count": res["count"],
                            "totals": [{"currency": x["currency"], "count": x["n"], "total": B.money(x["total"])} for x in res["spend_by_currency"]],
                            "transactions": [B.tx_view(x, lang=turn.lang) for x in res["transactions"]], "can_dispute": True})
        await self._after_flow(turn, default_state="inicio")

    async def _cases(self, turn: Turn) -> None:
        try:
            cases = await self._tool(turn, "list_cases", self.tools.list_cases)
        except ToolError:
            await self._tool_failed(turn)
            return
        turn.say("cases_list" if cases else "cases_none")
        if cases:
            turn.blocks.append({"type": "case_list", "cases": [{"case_id": x["case_id"], "status": x["status"], "reason_code": x["reason_code"],
                                "created_at": x["created_at"].isoformat(),
                                "transaction": {"label": B.tx_label(x, turn.lang),
                                                "amount": B.money(x["amount"]) if x["amount"] is not None else None, "currency": x["currency"],
                                                "date": x["transaction_date"].isoformat() if x["transaction_date"] else None}} for x in cases]})
        await self._after_flow(turn, default_state="inicio")

    # ================================================================ escalamiento
    async def _build_handoff(self, turn: Turn, reason: str, tx: dict | None = None, queue: str | None = None) -> dict:
        c = turn.c
        async with self.engine.connect() as conn:
            cust = (await conn.execute(text("SELECT customer_id, display_name, country, segment FROM ref.customers WHERE customer_id = :c"),
                                       {"c": turn.ctx.customer_id})).mappings().first()
        facts = c.get("facts", [])
        minimal = self._facts_for_llm(turn, tx) if tx else {}
        risk_fact = next((f["value"] for f in reversed(facts) if f["fact"] == "banda_riesgo"), None)
        if risk_fact:
            minimal["banda_riesgo"] = risk_fact
        rules = c.get("last_rules") or []
        open_q = {"fuera_de_plazo": ["¿Aplica una excepción al plazo de 60 días?"],
                  "riesgo_alto": ["¿El cargo es fraude? Revisar con el equipo de fraude y confirmar el bloqueo de la tarjeta."],
                  "riesgo_desconocido": ["El cargo no tiene fraud_score y supera el monto de autoservicio: ¿es fraude?"],
                  "aclaracion_agotada": ["¿Cuál es la transacción que el cliente reclama?"],
                  "reposicion_tarjeta": ["Gestionar la reposición de la tarjeta bloqueada."],
                  "pide_humano": ["¿Qué necesita el cliente?"]}.get(reason, ["Revisar el caso."])
        summary_model = {"model": self.nodes.config.model_for("handoff_summary"), "prompt_version": "handoff_summary@v1"}
        try:
            res = await self.nodes.handoff_summary(turn.lang, reason, [x["claim"] for x in c.get("claims", [])][-5:], minimal,
                                                   [{"id": r["id"], "resultado": r["resultado"], "motivo": r["motivo"]} for r in rules],
                                                   [{"accion": a["action"], "verificada": a["verified"]} for a in c.get("actions", [])])
            turn.trace.add_llm("handoff_summary", res)
            summary, questions = res.data.resumen, list(dict.fromkeys(open_q + res.data.preguntas_abiertas))[:5]
            summary_model.update(model_id=res.model_id)
        except LLMError as e:
            res = await self.fallback.handoff_summary(turn.lang, reason, [], minimal, [], [])
            turn.trace.add_llm("handoff_summary", None, error=str(e), fallback="plantilla", model=summary_model["model"])
            summary, questions = res.data.resumen, open_q
        return {"handoff_id": new_id("hof"), "created_at": datetime.now(timezone.utc).isoformat(),
                "conversation_id": turn.ctx.conversation_id, "trace_turn_ids": [turn.turn_id],
                "customer_ref": dict(cust) if cust else {"customer_id": turn.ctx.customer_id},
                "language": turn.lang, "reason_code": reason, "priority": P.handoff_priority(reason),
                "queue": queue or P.handoff_queue(reason), "request": {
                    "cargo_no_reconocido": "Disputa de un cargo no reconocido", "cobro_indebido": "Disputa de un cobro indebido",
                    "bloquear_tarjeta": "Bloqueo de tarjeta"}.get(c.get("intent"), "Atención de una persona"),
                "customer_claims": c.get("claims", [])[-10:], "verified_facts": facts,
                "candidate_transactions": c.get("shown") or [], "policy_evaluations": rules, "actions_taken": c.get("actions", []),
                "open_questions": questions, "summary": summary, "summary_model": summary_model, "status": "pendiente"}

    async def _escalate(self, turn: Turn, reason: str, queue: str | None = None, tx: dict | None = None) -> None:
        try:
            handoff = await self._build_handoff(turn, reason, tx=tx, queue=queue)
            res = await self._tool(turn, "create_handoff", self.tools.create_handoff, handoff)
        except ToolError:
            # nunca se dice que se transfirió si no se pudo (tools-contract)
            turn.blocks.append(B.error("handoff_failed", B.t(turn.lang, "tool_failed"), retryable=True))
            turn.trace.add("handoff_fallido", "code", error="create_handoff")
            turn.conv["state"] = "escalado"
            return
        await self._verify_handoff(turn, res["handoff_id"], handoff)
        if reason in ("riesgo_alto", "riesgo_desconocido"):
            turn.blocks[-1]["message"] = B.t(turn.lang, "handoff_fraud", handoff_id=res["handoff_id"])
        turn.c["handoff_id"] = res["handoff_id"]
        turn.conv["state"] = "escalado"

    async def _tool_failed(self, turn: Turn) -> None:
        turn.blocks.append(B.error("tool_failed", B.t(turn.lang, "tool_failed"), retryable=True))
        await self._escalate(turn, "fallo_tool")
