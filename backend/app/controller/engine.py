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
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.app.auth.service import SessionContext
from backend.app.config import get_chat_settings
from backend.app.controller import blocks as B
from backend.app.controller import phases
from backend.app.controller.replies import classify_reply
from backend.app.controller.small_talk import small_talk
from backend.app.controller.trace import TraceRecorder
from backend.app.dates import normalize, resolve_date_hint
from backend.app.errors import ApiError, not_found
from backend.app.knowledge import OUT_OF_SCOPE_ID, load_faq, retrieve
from backend.app.llm.client import LLMError
from backend.app.llm.fake import FakeLLMClient
from backend.app.llm.nodes import Nodes, candidate_views, fill, status_values
from backend.app.ml.base import RankQuery
from backend.app.ml.intent import KeywordIntentClassifier
from backend.app.ml.ranker import alias_merchants, duplicate_pairs
from backend.app.ml.registry import MLComponents
from backend.app.ml import keyword_rules
from backend.app.observability import logs
from backend.app.policy import rules as P
from backend.app.security import new_id, sha256
from backend.app.tools import ToolContext, ToolError, Tools

LOG = logging.getLogger("backend.turns")
WRITING_NODES = ("clarify", "confirm", "explain", "faq_answer", "handoff_summary")
TERMINAL = ("cerrado", "escalado")
DISPUTE_INTENTS = ("cargo_no_reconocido", "cobro_indebido")
REASON_BY_PROBLEM = {"monto_incorrecto": "amount_mismatch", "duplicado": "duplicate", "no_reconoce": "unrecognized"}
CANCEL = r"\b(cancela\w*|olvidalo|olvídalo|deja(lo)? asi|no quiero|desisto|esquece|deixa pra la|nao quero)\b"
RECOGNIZED = r"\b(lo reconozco|ya lo reconoc\w*|ya me acorde|ya me acordé|era mio|era mío|si lo hice|sí lo hice|fui yo|agora reconheço|agora reconheco|reconheço sim|reconheco sim|lembrei|era meu|fui eu)\b"
OTHER = r"\b(era otr[oa]|es otr[oa]|no es ese|no es esa|otro cargo|otro movimiento|era outr[oa]|é outr[oa]|e outr[oa]|nao e ess[ea]|não é ess[ea]|outra cobrança|outra cobranca)\b"
REFUND = r"\b(devuelv\w*|devolucion|devolución|reembols\w*|reintegr\w*|estorn\w*|devolucao|devolução|me regresen)\b"
# fin de la conversación (sobre el texto normalizado, sin tildes)
GOODBYE = (r"^(no,? )?(muchas )?gracias[.! ]*$|^(nao,? )?(muito )?obrigad[oa][.! ]*$|\b(eso es todo|eso seria todo|es todo|nada mas|"
           r"no necesito nada mas|chau|chao|adios|hasta luego|nos vemos|e so isso|so isso|nada mais|tchau|ate logo|ate mais)\b")
# referencias al cargo en foco
ANAPHORA = (r"\b(ese|esa|eso|este|esta|esto|lo|la|ese cargo|el cargo|ese cobro|esse|essa|isso|este cargo|essa cobranca|a cobranca|"
            r"o cargo)\b")
OTHER_FOCUS = r"\b(el otro|la otra|ese otro|esa otra|otro cargo|o outro|a outra|esse outro|essa outra|outra cobranca)\b"
ALL_OF_THEM = r"\b(todos|todas|ambos|ambas|los dos|las dos|los tres|las tres|os dois|as duas|os tres|as tres|esos|esas)\b"


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
    nodes: Any = None                     # nodos LLM del turno (los de plantilla si el presupuesto se agotó)
    degraded: bool = False                # presupuesto de LLM agotado: plantillas y baseline (fase 2 del prompt 05)
    message: str = ""                     # texto del cliente en este turno (para recuperar la respuesta aprobada)
    flow_done: str | None = None          # el turno terminó un flujo (resuelto, informado, escalado…): se ofrece "¿algo más?"
    offered_more: bool = False            # el turno anterior preguntó "¿algo más?"
    asserted: bool = False                # el mensaje afirma que el cliente no hizo el cargo (R2b)

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
                 reference_date: date | None = None, budget=None):
        self.engine, self.tools, self.nodes, self.ml, self.policy = engine, tools, nodes, ml, policy
        self.budget = budget                                       # LLMBudget o None (sin tope)
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
                                  language: str | None = None, previous_conversation_id: str | None = None,
                                  dispute_transaction_id: str | None = None) -> dict:
        """previous_conversation_id: conversación anterior del MISMO cliente (cerrada o no). Se hereda el cargo en foco
        y las últimas afirmaciones del cliente, para que "pero yo no lo hice" se entienda sin volver a buscar."""
        if session.role != "customer" or not session.customer_id:
            raise ApiError(403, "forbidden", "Solo un cliente puede iniciar una conversación.")
        context: dict = {}
        if previous_conversation_id:
            prev = await self._load(previous_conversation_id, session.customer_id)      # 404 si no es suya
            pc = prev["context"]
            context = {k: v for k, v in {"focus": pc.get("focus"), "claims": (pc.get("claims") or [])[-5:] if pc.get("focus") else None,
                                         "last_case_id": pc.get("last_case_id"), "last_card": pc.get("last_card")}.items() if v}
            language = language or prev.get("language")
            session_date = session_date or prev.get("session_date")
        if dispute_transaction_id:     # "No reconozco este cargo" desde Mis movimientos: el movimiento tiene que ser suyo
            async with self.engine.connect() as c:
                owned = (await c.execute(text("SELECT 1 FROM ref.transactions WHERE transaction_id = :t AND customer_id = :c"),
                                         {"t": dispute_transaction_id, "c": session.customer_id})).first()
            if owned is None:
                raise not_found()
            context["listed"] = [dispute_transaction_id]
        conv_id, sd, lang = new_id("conv"), session_date or await self.session_date(), language or session.language or "es"
        greeting = [B.text_block(B.t(lang, "greeting"))]
        async with self.engine.begin() as c:
            await c.execute(text("""INSERT INTO app.conversations (conversation_id, session_id, customer_id, state, language, session_date,
                                    context, previous_conversation_id) VALUES (:id, :s, :c, 'inicio', :l, :d, CAST(:ctx AS jsonb), :prev)"""),
                            {"id": conv_id, "s": session.session_id, "c": session.customer_id, "l": lang, "d": sd,
                             "ctx": json.dumps(context, ensure_ascii=False, default=str), "prev": previous_conversation_id})
            await c.execute(text("""INSERT INTO app.turns (turn_id, conversation_id, seq, role, blocks, state_before, state_after)
                                    VALUES (:t, :conv, 1, 'assistant', CAST(:b AS jsonb), NULL, 'inicio')"""),
                            {"t": new_id("turn"), "conv": conv_id, "b": json.dumps(greeting, ensure_ascii=False)})
        return {"conversation_id": conv_id, "state": "inicio", "language": lang, "session_date": sd.isoformat(), "blocks": greeting,
                "previous_conversation_id": previous_conversation_id, "focus": bool(context.get("focus"))}

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
                                   {"s": session.session_id, "k": key})).mappings().one()     # existe: el INSERT chocó con ella
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
        phases.safe(phases.set_phase, conversation_id, session.customer_id, "understanding")
        try:
            response = await self._run_turn(session, conversation_id, inp, idempotency_key, faults or set())
        except BaseException:
            if idempotency_key:
                await self._idem_release(session, idempotency_key)
            raise
        finally:
            phases.safe(phases.clear, conversation_id)
        if idempotency_key:
            async with self.engine.begin() as c:
                await c.execute(text("UPDATE app.idempotency_keys SET response = CAST(:r AS jsonb), status_code = 200 "
                                     "WHERE session_id = :s AND idempotency_key = :k"),
                                {"r": json.dumps(response, ensure_ascii=False, default=str), "s": session.session_id, "k": idempotency_key})
        return response

    async def _run_turn(self, session, conversation_id, inp, idempotency_key, faults) -> dict:
        conv = await self._load(conversation_id, session.customer_id)
        lang = conv.get("language") or "es"
        if conv["state"] in TERMINAL:
            reason = conv.get("closed_reason") or "cliente"
            raise ApiError(409, "conversation_closed", B.t(lang, "closed_idle" if reason == "inactividad" else "closed"),
                           details={"reason": reason, "conversation_id": conversation_id})
        if datetime.now(timezone.utc) - conv["updated_at"] > timedelta(minutes=self.policy.conversation_idle_minutes):
            await self._close(conversation_id, "inactividad")
            raise ApiError(409, "conversation_closed", B.t(lang, "closed_idle"),
                           details={"reason": "inactividad", "conversation_id": conversation_id})
        state_before = conv["state"]
        ctx = ToolContext(customer_id=session.customer_id, session_id=session.session_id, conversation_id=conversation_id,
                          session_date=conv["session_date"], faults=faults)
        turn = Turn(conv, ctx, session, TraceRecorder(), new_id("turn"), idempotency_key, nodes=self.nodes)
        turn.trace.add("entrada", "code", input=inp.as_dict(), extra={"state": state_before, "session_date": str(ctx.session_date)})
        if self.budget is not None and self.nodes.config.provider != "fake":
            status = await self.budget.check(session.session_id)
            if not status.ok:     # modo degradado: el turno no llama al LLM; queda en la traza y en el log
                turn.nodes, turn.degraded = self.fallback, True
                turn.trace.add("presupuesto_llm", "code", output={"modo": "degradado", **status.as_dict()})
        turn.offered_more = bool(turn.c.pop("offered_more", False))
        if inp.message is not None:
            turn.c.setdefault("claims", []).append({"claim": inp.message[:500], "turn_id": turn.turn_id})
            turn.asserted = bool(re.search(keyword_rules.ASSERTS_NOT_DONE, normalize(inp.message)))
            turn.message = inp.message
            await self._on_message(turn, inp.message)
        else:
            await self._on_action(turn, inp.action or {})
        if turn.flow_done and conv["state"] == "inicio" and not turn.c.get("resume_intent"):
            # ningún resultado cierra la conversación: se ofrece seguir (respuestas rápidas)
            turn.say("anything_else")
            turn.blocks.append(B.quick_replies(turn.lang))
            turn.c["offered_more"] = True
            turn.trace.add("algo_mas", "code", output={"resultado_del_flujo": turn.flow_done})
        await self._persist(turn, inp, state_before)
        self._log_turn(turn, inp, state_before)
        return {"turn_id": turn.turn_id, "conversation_id": conversation_id, "state": conv["state"], "language": turn.lang,
                "blocks": turn.blocks, "input": inp.as_dict(), "data_as_of": await self.data_freshness(), "trace_id": turn.turn_id,
                "clarification_round": conv["clarification_round"]}

    async def _persist(self, turn: Turn, inp: TurnInput, state_before: str) -> None:
        conv = turn.conv
        async with self.engine.begin() as c:
            seq: int = (await c.execute(text("SELECT coalesce(max(seq), 0) FROM app.turns WHERE conversation_id = :c"),
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
                                    context = CAST(:ctx AS jsonb), updated_at = now(), closed_reason = :cr,
                                    closed_at = CASE WHEN CAST(:st AS varchar) IN ('cerrado', 'escalado') THEN now() ELSE closed_at END
                                    WHERE conversation_id = :id"""),
                            {"st": conv["state"], "l": turn.lang, "r": conv["clarification_round"], "cr": conv.get("closed_reason"),
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

    @staticmethod
    def _log_turn(turn: Turn, inp: TurnInput, state_before: str) -> None:
        """Una línea por llamada al LLM y una por turno. Sin el texto del cliente (queda en app.turns, con control de acceso)."""
        logs.conversation_id.set(turn.ctx.conversation_id)
        logs.turn_id.set(turn.turn_id)
        llm = [s for s in turn.trace.steps if s.kind == "llm"]
        for s in llm:
            LOG.info("llm_call", extra={"node": s.node, "provider": s.implementation, "model": s.model, "model_id": s.model_id,
                                        "prompt_version": s.prompt_version, "latency_ms": s.latency_ms, "cost_usd": s.cost_usd,
                                        "error": (s.error or "")[:120] or None, "fallback": (s.payload or {}).get("fallback")})
        LOG.info("turn", extra={"input_kind": "message" if inp.message is not None else "action",
                                "action": (inp.action or {}).get("type"), "chars": len(inp.message or ""),
                                "state_before": state_before, "state_after": turn.conv["state"], "steps": len(turn.trace.steps),
                                "llm_calls": len(llm), "llm_latency_ms": sum(s.latency_ms or 0 for s in llm),
                                "llm_cost_usd": round(sum(s.cost_usd or 0 for s in llm), 6),
                                "models": sorted({str(s.model_id or s.model) for s in llm if s.model_id or s.model}),
                                "fallbacks": sum(1 for s in turn.trace.steps if (s.payload or {}).get("fallback")),
                                "tool_errors": sum(1 for s in turn.trace.steps if s.tool and s.error),
                                "blocks": [b["type"] for b in turn.blocks]})

    async def _close(self, conversation_id: str, reason: str) -> None:
        async with self.engine.begin() as c:
            await c.execute(text("UPDATE app.conversations SET state = 'cerrado', closed_reason = :r, closed_at = now() "
                                 "WHERE conversation_id = :id"), {"r": reason, "id": conversation_id})

    # ================================================================ utilidades de pasos
    async def _tool(self, turn: Turn, name: str, fn, *args, retry: bool = True, **kwargs):
        """Llama un tool con un reintento acotado (solo errores de infraestructura) y lo deja en la traza."""
        if name == "search_transactions":
            self._phase(turn, "searching_transactions")
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
            safe_kwargs = {k: ("[oculto]" if k == "token" else v) for k, v in kwargs.items()}     # el token nunca va a la traza
            turn.trace.add(f"tool:{name}", "code", tool=name, input={"args": [a for a in args], **safe_kwargs} if name not in (
                "create_handoff",) else {"reason_code": args[0].get("reason_code") if args else None},
                output=summary, latency_ms=t["ms"], error=f"{err.code}: {err.message}" if err else None,
                extra={"attempt": attempt})
            if err is None:
                return out
            if err.code != "db_unavailable" or attempt == attempts:
                raise err
        raise AssertionError("inalcanzable")

    async def _llm(self, turn: Turn, node: str, *args, _mode: str = "llm", _why: str | None = None, **kwargs):
        """Llama un nodo LLM; si falla tras su reintento, usa la plantilla del cliente falso y lo registra.

        _mode="template" no llama al LLM: usa directamente la plantilla (CONFIRM_MODE / CLARIFY_MODE). En la traza
        de confirm y clarify queda {"modo": "llm"|"plantilla", "motivo": _why}."""
        args_in = {"args": [str(a)[:300] for a in args]}
        if node in WRITING_NODES:
            self._phase(turn, "writing")
        mode = {"modo": "plantilla" if _mode == "template" else "llm", "motivo": _why} if node in ("confirm", "clarify") else None
        if _mode == "template":
            res = await getattr(self.fallback, node)(*args, **kwargs)
            turn.trace.add(node, "code", implementation="plantilla", input=args_in, output=res.data.model_dump(), extra=mode)
            return res.data
        t0 = time.perf_counter()
        try:
            res = await getattr(turn.nodes, node)(*args, **kwargs)
            turn.trace.add_llm(node, res, input=args_in, extra=mode)
            return res.data
        except LLMError as e:
            waited = round((time.perf_counter() - t0) * 1000)
            res = await getattr(self.fallback, node)(*args, **kwargs)
            turn.trace.add_llm(node, None, error=str(e), fallback="plantilla", model=self.nodes.config.model_for(node),
                               input=args_in, extra=mode).latency_ms = waited
            return res.data

    async def _confirm_text(self, turn: Turn, action: str, reason_code: str | None, placeholders: list[str]):
        """confirm: por defecto plantilla (CONFIRM_MODE=template). Confirmar es mostrar datos del registro y una
        pregunta fija; el LLM no aporta nada ahí."""
        return await self._llm(turn, "confirm", turn.lang, action, reason_code, placeholders,
                               _mode=self.nodes.config.confirm_mode, _why=action)

    async def _clarify_text(self, turn: Turn, kind: str, shown: list[dict], discriminant: str, **kw) -> str:
        """Texto de una aclaración. kind: elegir_candidatas | tipo_problema | mas_datos | reformular.

        CLARIFY_MODE=auto: plantilla cuando la aclaración es elegir entre 2–3 candidatas (lista con comercio, monto
        y fecha + "¿cuál de ellos?"); LLM en los demás casos. template/llm fuerzan uno u otro."""
        mode = self.nodes.config.clarify_mode
        if mode == "auto":
            mode = "template" if kind == "elegir_candidatas" else "llm"
        if mode == "template" and kind == "elegir_candidatas":
            text = B.pick_text(shown, turn.lang)
            turn.trace.add("clarify", "code", implementation="plantilla", input={"n_candidatas": len(shown)},
                           output={"pregunta": text}, extra={"modo": "plantilla", "motivo": kind})
            return text
        views, _ = candidate_views(shown, turn.lang)
        out = await self._llm(turn, "clarify", turn.lang, views, discriminant, max(turn.conv["clarification_round"], 1),
                              self.policy.max_clarify_rounds, _mode=mode, _why=kind, **kw)
        return fill(out.pregunta, status_values(shown, turn.lang), set(status_values(shown, turn.lang)))   # P-31

    @staticmethod
    def _phase(turn: Turn, phase: str) -> None:
        """Fase real del turno para el indicador de espera (controller/phases.py). Nunca falla el turno."""
        phases.safe(phases.set_phase, turn.ctx.conversation_id, turn.ctx.customer_id, phase)

    def _fact(self, turn: Turn, fact: str, value: Any, source_tool: str) -> None:
        turn.c.setdefault("facts", []).append({"fact": fact, "value": value, "source_tool": source_tool,
                                               "tool_call_id": f"{turn.turn_id}#{len(turn.trace.steps)}"})

    # ================================================================ mensajes
    async def _on_message(self, turn: Turn, message: str) -> None:
        st = turn.conv["state"]
        norm = normalize(message)
        if st == "inicio" and get_chat_settings().fast_path_enabled and (talk := small_talk(message)):
            await self._small_talk(turn, *talk)
            return
        if re.search(REFUND, norm):
            turn.c["refund_requested"] = True
            turn.blocks.append(B.notice("no_refund_approval", B.t(turn.lang, "no_refund")))
        reply = classify_reply(message)            # sí / no con tipeos y variantes es/pt; None si no se reconoce
        if st == "inicio" and (re.search(GOODBYE, norm) or (turn.offered_more and reply == "no")):
            await self._goodbye(turn)
            return
        if st == "inicio":
            if (resume := turn.c.get("resume_intent")) and reply == "yes":
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
            if pending.get("action") == "create_dispute_case" and not pending.get("multi") and re.search(OTHER, norm):
                # cambio de movimiento después de ver la confirmación: se anula el token y se busca de nuevo
                await self.tools.invalidate_tokens(turn.ctx)
                turn.c.setdefault("excluded", []).append(pending["params"]["transaction_id"])
                turn.c.update({"pending": None, "selected": None})
                turn.trace.add("cambio_de_movimiento", "code", output={"excluida": pending["params"]["transaction_id"]})
                ex = await self._llm(turn, "extract", message)
                self._merge_hints(turn, ex.model_dump())
                await self._dispute_step(turn, count_round=True)
                return
            if re.search(RECOGNIZED, norm) and pending.get("action") == "create_dispute_case" and not pending.get("multi"):
                await self.tools.invalidate_tokens(turn.ctx)
                turn.c["pending"] = None
                turn.say("recognized")
                await self._after_flow(turn)
                return
            if re.search(CANCEL, norm) or reply == "no":
                await self._cancel_pending(turn)
            else:   # R4: el texto nunca ejecuta (ni siquiera "sí"); se vuelve a mostrar la confirmación con los botones
                turn.trace.add("r4_texto_no_confirma", "code", output={"mensaje_ignorado_como_confirmacion": True, "respuesta": reply},
                               rules=[P.r4_constant().as_dict()])
                turn.say("use_buttons")
                await self._reissue_pending(turn)
            return
        if re.search(CANCEL, norm):
            await self.tools.invalidate_tokens(turn.ctx)
            turn.trace.add("cancelado", "code", output={"por_texto": True})
            turn.say("cancelled")
            await self._finish(turn, "cancelado")
            return
        if st == "confirmando_movimiento":
            turn.trace.add("respuesta_confirmacion", "code", input={"texto": message[:100]}, output={"respuesta": reply})
            if reply == "yes":
                await self._confirm_movement(turn)
                return
            if reply == "no":
                turn.c.setdefault("excluded", []).append(turn.c.get("selected"))
                turn.c["selected"] = None
                await self._dispute_step(turn, count_round=True)
                return
            # ni sí ni no: si trae datos para identificar otro cargo, se busca de nuevo; si no, NO se confirma
            ex = await self._llm(turn, "extract", message)
            if not any(ex.model_dump().get(k) for k in ("merchant_hint", "amount_hint", "date_hint")):
                await self._repeat_movement_question(turn)
                return
            self._merge_hints(turn, ex.model_dump())
            await self._dispute_step(turn, count_round=True)
            return
        if st == "aclarando" and turn.c.get("multi"):
            shown = turn.c.get("shown") or []
            nums = [int(x) for x in re.findall(r"\b([1-9])\b", norm) if int(x) <= len(shown)]
            ids = [shown[i - 1] for i in dict.fromkeys(nums)] if nums else (
                (turn.c.get("suggested") or shown) if re.search(r"\b(los dos|las dos|os dois|as duas|los tres|las tres)\b", norm)
                else shown if re.search(ALL_OF_THEM, norm) else [])
            if ids:
                turn.trace.add("seleccion_por_texto", "code", output={"elegidos": ids})
                await self._on_action(turn, {"type": "select_candidates", "transaction_ids": ids})
                return
        # aclarando (o confirmando_movimiento con más datos): nuevas pistas → buscar de nuevo
        if turn.c.get("mode") == "card_pick":
            await self._card_step(turn, hint=message)
            return
        prev_shown = turn.c.get("shown") if st == "aclarando" else None
        ex = await self._llm(turn, "extract", message)
        self._merge_hints(turn, ex.model_dump())
        await self._dispute_step(turn, count_round=True, prev_shown=prev_shown)

    async def _understand(self, turn: Turn, message: str) -> None:
        """inicio: intención y extracción en paralelo; luego enrutar."""
        t0 = time.perf_counter()
        elapsed = lambda: round((time.perf_counter() - t0) * 1000)      # en fallos, el tiempo esperado al LLM
        intent_clf = KeywordIntentClassifier() if turn.degraded else self.ml.intent
        intent_task = asyncio.create_task(intent_clf.classify(message))
        extract_task = asyncio.create_task(turn.nodes.extract(message))
        try:
            pred = await intent_task
            turn.trace.add_llm("intent", pred.llm, input={"texto": message[:300]}) if pred.llm else turn.trace.add(
                "intent", "ml", implementation=pred.version, input={"texto": message[:300]}, output=pred.output.model_dump())
            out = pred.output
        except LLMError as e:
            pred = await KeywordIntentClassifier().classify(message)
            turn.trace.add("intent", "ml", implementation=pred.version, error=str(e), output=pred.output.model_dump(),
                           extra={"fallback": "keyword"}, latency_ms=elapsed())
            out = pred.output
        try:
            exres = await extract_task
            turn.trace.add_llm("extract", exres, input={"texto": message[:300]})
            extracted = exres.data.model_dump()
        except LLMError as e:
            extracted = keyword_rules.extract(message)
            turn.trace.add_llm("extract", None, error=str(e), fallback="reglas",
                               model=self.nodes.config.model_for("extract")).latency_ms = elapsed()
        turn.conv["language"] = out.idioma
        if out.sospecha_manipulacion:
            turn.c["manipulation_attempts"] = turn.c.get("manipulation_attempts", 0) + 1
            turn.trace.add("sospecha_manipulacion", "code", output={"intentos": turn.c["manipulation_attempts"]})
            turn.blocks.append(B.notice("scope_own_account", B.t(turn.lang, "manipulation"), level="warning"))
        if out.intent in ("sin_contenido", "fuera_de_alcance"):
            # red de seguridad: una pregunta corta sobre el proceso ("¿y ahora qué pasa?") sin contexto puede parecer vacía
            quick = keyword_rules.classify(message)
            if quick["intent"] == "pregunta_proceso":
                turn.trace.add("intencion_corregida", "code", input={"llm": out.intent},
                               output={"intencion": "pregunta_proceso", "tema_proceso": quick.get("tema_proceso")})
                out = out.model_copy(update={"intent": "pregunta_proceso", "tema_proceso": quick.get("tema_proceso")})
            elif out.intent == "sin_contenido" and quick["intent"] == "fuera_de_alcance" and quick.get("tema"):
                # "cuéntame un chiste" no es un mensaje vacío: es un pedido que este chat no atiende y se redirige
                turn.trace.add("intencion_corregida", "code", input={"llm": out.intent},
                               output={"intencion": "fuera_de_alcance", "tema": quick["tema"]})
                out = out.model_copy(update={"intent": "fuera_de_alcance", "tema": quick["tema"]})
        intents = [out.intent, *[i for i in out.otras_intenciones if i != out.intent]]
        if "fuera_de_alcance" in intents and any(i not in ("fuera_de_alcance", "sin_contenido") for i in intents):
            # mensaje mixto: se redirige la parte que no es de este chat y se atiende la otra en el mismo turno
            intents = [i for i in intents if i not in ("fuera_de_alcance", "sin_contenido")]
            turn.trace.add("multiples_intenciones", "code", output={"redirigida": "fuera_de_alcance", "atendida": intents[0]})
            self._redirect_out_of_scope(turn, follow=False)
        if "bloquear_tarjeta" in intents:        # contener el riesgo primero
            intents.remove("bloquear_tarjeta")
            intents.insert(0, "bloquear_tarjeta")
        main, rest = intents[0], [i for i in intents[1:] if i in DISPUTE_INTENTS + ("consulta_movimientos", "estado_reclamo", "pregunta_proceso")]
        turn.c.update({"intent": main, "pending_intents": rest, "tema": out.tema, "certeza": out.certeza, "saved_hints": extracted,
                       "tema_proceso": out.tema_proceso})
        if turn.c.get("focus") and await self._focus_turn(turn, message, main, extracted):
            return
        turn.trace.add("enrutamiento", "code", output={"intencion": main, "pendientes": rest})
        await self._route(turn, main, extracted)

    async def _repeat_movement_question(self, turn: Turn) -> None:
        """La respuesta no fue un sí ni un no reconocible: no se confirma; se repite la pregunta con el movimiento y los botones."""
        try:
            tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, turn.c["selected"])
        except ToolError:
            await self._tool_failed(turn)
            return
        turn.say("confirm_repeat")
        turn.blocks.append({"type": "transaction_card", "transaction": B.tx_view(tx, lang=turn.lang), "source": "get_transaction"})

    async def _process_question(self, turn: Turn) -> None:
        """pregunta_proceso: respuesta APROBADA (backend/knowledge/faq.yaml) + una frase de contexto del LLM con los hechos del
        caso en foco. El texto aprobado lo copia el código tal cual; el LLM no lo reescribe. Traza: qué entrada se usó."""
        topic = turn.c.get("tema_proceso")
        entry, method = retrieve(topic, turn.message, turn.lang)
        version, _ = load_faq()
        turn.trace.add("faq", "code", implementation=version, input={"tema": topic},
                       output={"faq_id": entry.id if entry else None, "metodo": method})
        if entry is None:          # sin respuesta aprobada: se dice y se ofrece una persona
            turn.say("faq_none")
            turn.blocks.append({"type": "quick_replies", "options": [
                {"label": B.t(turn.lang, "qr_human"), "action": {"type": "request_human"}}, *B.quick_replies(turn.lang)["options"]]})
            turn.c["offered_more"] = True
            turn.conv["state"] = "inicio"
            return
        facts, values = await self._focus_facts(turn, entry.tema)
        context = ""
        if facts:
            out = await self._llm(turn, "faq_answer", turn.lang, entry.tema, entry.texto[turn.lang], facts, list(values))
            context = self._fill(turn, out.contexto, **values).strip()
        turn.blocks.append(B.text_block(f"{context}\n{entry.texto[turn.lang]}" if context else entry.texto[turn.lang]))
        await self._finish(turn, "informado")

    async def _focus_facts(self, turn: Turn, topic: str) -> tuple[dict, dict]:
        """Hechos del reclamo o la tarjeta en foco. Al LLM solo le llegan marcadores; el código los rellena después."""
        c, facts, values = turn.c, {}, {}
        if topic in ("tarjeta_bloqueada", "reposicion_tarjeta"):
            if card := c.get("last_card"):
                facts, values = {"tarjeta": "{tarjeta}"}, {"tarjeta": card.get("label", "")}
            return facts, values
        if topic in ("seguridad", "hablar_persona"):
            return facts, values
        focus = c.get("focus") or {}
        case_id = focus.get("case_id") or c.get("last_case_id")
        if focus.get("transaction_id"):
            try:
                tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, focus["transaction_id"])
            except ToolError:
                tx = None
            if tx:
                facts = {"comercio": "{comercio}", "monto": "{monto}", "fecha": "{fecha}", "estado": "{estado}"}
                values = {"comercio": B.tx_label(tx, turn.lang), "monto": B.fmt_money(tx["amount"], tx["currency"], turn.lang),
                          "fecha": B.fmt_date(tx["transaction_date"], turn.lang), "estado": B.status_label(tx["transaction_status"], turn.lang)}
        if case_id:
            facts["referencia"] = "{numero_reclamo}"
            values["numero_reclamo"] = B.short_ref(case_id)
        return facts, values

    async def _focus_turn(self, turn: Turn, message: str, intent: str, extracted: dict) -> bool:
        """El mensaje se refiere al cargo del que se acaba de hablar ("pero yo no lo hice", "y ese otro?")?
        Solo si no trae datos nuevos para identificar otro cargo. Devuelve True si lo atendió."""
        focus, norm = turn.c["focus"], normalize(message)
        if any(extracted.get(k) for k in ("merchant_hint", "amount_hint", "date_hint")) or (extracted.get("n_charges") or 0) > 1:
            return False
        if intent in ("consulta_movimientos", "estado_reclamo", "bloquear_tarjeta", "pedir_humano"):
            return False
        asserted = turn.asserted or bool(extracted.get("afirma_no_haberlo_hecho"))
        other = bool(re.search(OTHER_FOCUS, norm))
        if not (other or asserted or intent in DISPUTE_INTENTS or re.search(ANAPHORA, norm)):
            return False
        turn.trace.add("foco", "code", input={"cargo_en_foco": focus["transaction_id"]},
                       output={"otro_cargo": other, "afirma_no_haberlo_hecho": asserted, "intencion": intent})
        dispute_intent = intent if intent in DISPUTE_INTENTS else focus.get("intent") if focus.get("intent") in DISPUTE_INTENTS \
            else "cargo_no_reconocido"
        hints = {**(focus.get("hints") or {}), **{k: v for k, v in extracted.items() if v}}
        if other:          # "y ese otro?": la otra candidata que se mostró, o la misma búsqueda sin el cargo en foco
            alternatives = focus.get("alternatives") or []
            self._start_dispute(turn, dispute_intent, hints)
            turn.c["excluded"] = [focus["transaction_id"]]
            if alternatives:       # en orden de ranking: se propone la siguiente y el cliente confirma o la rechaza
                try:
                    await self._propose(turn, await self._tool(turn, "get_transaction", self.tools.get_transaction, alternatives[0]))
                except ToolError:
                    await self._tool_failed(turn)
                return True
            await self._dispute_step(turn, count_round=False)
            return True
        self._start_dispute(turn, dispute_intent, hints, preselected=focus["transaction_id"])
        if turn.c.get("reason_code") is None:
            turn.c["reason_code"] = focus.get("reason_code") or "unrecognized"
        await self._confirm_movement(turn)        # el cliente ya vio este cargo: no se vuelve a preguntar si es ese
        return True

    def _set_focus(self, turn: Turn, tx: dict) -> None:
        c = turn.c
        c["focus"] = {"transaction_id": tx["transaction_id"], "status": tx.get("transaction_status"), "intent": c.get("intent"),
                      "reason_code": c.get("reason_code"), "hints": c.get("hints") or {},
                      "alternatives": [i for i in c.get("last_candidates") or [] if i != tx["transaction_id"]]}

    async def _route(self, turn: Turn, intent: str, extracted: dict) -> None:
        c = turn.c
        if intent == "sin_contenido":
            turn.say("sin_contenido")
        elif intent == "fuera_de_alcance":
            self._redirect_out_of_scope(turn, follow=True)
            await self._finish(turn, "abstencion")
            turn.flow_done = None          # la pregunta de seguimiento es la de la redirección, no el "¿algo más?" genérico
            c["offered_more"] = True
        elif intent == "pedir_humano":
            await self._escalate(turn, "pide_humano")
        elif intent == "pregunta_proceso":
            await self._process_question(turn)
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
                       "selected": preselected, "multi": False, "suggested": [],
                       "asserted_unauthorized": turn.asserted or bool(hints.get("afirma_no_haberlo_hecho"))})
        turn.conv["clarification_round"] = 0
        self._merge_hints(turn, hints)

    def _merge_hints(self, turn: Turn, new: dict) -> None:
        h = turn.c.setdefault("hints", {})
        for k, v in new.items():
            if v not in (None, "", [], {}):
                h[k] = v
        if new.get("afirma_no_haberlo_hecho") or turn.asserted:
            turn.c["asserted_unauthorized"] = True
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

    async def _dispute_step(self, turn: Turn, count_round: bool, prev_shown: list[str] | None = None) -> None:
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
            turn.blocks.append(B.text_block(await self._clarify_text(turn, "mas_datos", [], "mas_datos",
                                                                     search_days=self.policy.search_window_days)))
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
                turn.trace.add("clarify", "code", implementation="plantilla", output={"pregunta": B.t(turn.lang, "duplicate_pick")},
                               extra={"modo": "plantilla", "motivo": "elegir_candidatas"})
                await self._show_candidates(turn, [a, b], B.t(turn.lang, "duplicate_pick"), counts=False)
                return
            turn.say("no_duplicate")
        ranked = self.ml.ranker.rank(q, txs)
        n_charges = int(c["hints"].get("n_charges") or 0)
        if c.get("reason_code") != "duplicate" and (n_charges >= 2 or c["hints"].get("seleccion") == "todos"):
            await self._show_multi(turn, q, txs, ranked, n_charges)
            return
        decision = self.ml.clarify.decide(q, ranked, problem_known=c.get("reason_code") is not None)
        top = [{"transaction_id": s.transaction["transaction_id"], "score": s.score, "p": round(s.probability, 4)}
               for s in ranked.candidates[:5]]
        turn.trace.add("ranking", "ml", implementation=ranked.version, input={"n_candidatas": len(txs), "consulta": vars(q)},
                       output={"top": top})
        turn.trace.add("aclaracion", "ml", implementation=decision.version,
                       output={"preguntar": decision.ask, "motivos": decision.reasons, "atributo": decision.discriminant})
        if decision.ask:
            shown = [ranked.candidates[i].transaction for i in decision.show]
            if decision.discriminant == "tipo_problema":
                kind, disc = "tipo_problema", "tipo_problema"
            elif prev_shown and {t["transaction_id"] for t in shown} == set(prev_shown):
                kind, disc = "reformular", "reformular"     # la respuesta no correspondía a ninguna opción
            else:
                kind, disc = "elegir_candidatas", decision.discriminant or "fecha"
            await self._show_candidates(turn, shown, await self._clarify_text(turn, kind, shown, disc), counts=True)
            return
        await self._propose(turn, ranked.candidates[0].transaction)

    async def _show_multi(self, turn: Turn, q: RankQuery, txs: list[dict], ranked, n: int) -> None:
        """Varios cargos ("los dos más recientes", "los tres de ayer"): lista con selección múltiple y sugeridos."""
        c, sel = turn.c, turn.c["hints"].get("seleccion")
        in_range = (lambda t: q.date_range is None or q.date_range.start <= t["transaction_date"].date() <= q.date_range.end)
        if sel in ("mas_recientes", "mas_antiguos"):
            pool = sorted([t for t in txs if in_range(t)] or txs, key=lambda t: t["transaction_date"], reverse=sel == "mas_recientes")
        else:
            ordered = [s.transaction for s in ranked.candidates]
            pool = [t for t in ordered if in_range(t)] + [t for t in ordered if not in_range(t)]
        k = self.policy.max_multi_charges
        shown = pool[:min(k, max(n, 3))] if sel != "todos" else ([t for t in pool if in_range(t)] or pool)[:k]
        suggested = [t["transaction_id"] for t in (shown[:n] if n else shown)]
        c.update(multi=True, suggested=suggested)
        turn.trace.add("varios_cargos", "code", input={"n_cargos": n, "seleccion": sel},
                       output={"mostrados": len(shown), "sugeridos": suggested})
        prompt = B.t(turn.lang, "multi_pick")                 # la lista va solo en el bloque
        turn.trace.add("clarify", "code", implementation="plantilla", output={"pregunta": prompt},
                       extra={"modo": "plantilla", "motivo": "elegir_varios"})
        await self._show_candidates(turn, shown, prompt, counts=True)
        turn.blocks[-1].update(multi_select=True, suggested=suggested, select_all_label=B.t(turn.lang, "multi_all"))

    async def _multi_evaluate(self, turn: Turn, ids: list[str]) -> None:
        """Cada cargo elegido sigue su regla. Los que se pueden reclamar van en UNA confirmación; los demás se
        explican por separado (aviso) o se escalan. Si alguno pide bloqueo, se ofrece al final."""
        c = turn.c
        c.update(multi=False, reason_code=c.get("reason_code") or "unrecognized")
        permitted, rules_by_tx, lock_products = [], {}, []
        for tid in ids:
            try:
                tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, tid)
                existing = await self._tool(turn, "get_existing_case", self.tools.get_existing_case, tid)
            except ToolError:
                await self._tool_failed(turn)
                return
            risk = self.ml.risk.assess(tx)
            self._phase(turn, "checking_policy")
            decision = P.evaluate_dispute(tx, turn.ctx.session_date, existing, risk, c["reason_code"], self.policy,
                                          refund_requested=bool(c.get("refund_requested")),
                                          asserted_unauthorized=bool(c.get("asserted_unauthorized")))
            turn.trace.add("politica", "code", implementation="policy@v1", input={"transaction_id": tid},
                           output={"resultado": decision.outcome, "decide": decision.decisive.as_dict() if decision.decisive else None},
                           rules=decision.rules_dicts())
            self._fact(turn, "transaccion_confirmada_por_cliente", tid, "get_transaction")
            c["last_rules"] = decision.rules_dicts()
            if decision.offer_lock or decision.recommend_lock:
                lock_products.append(tx["product_id"])
            line = B.tx_line(tx, turn.lang)
            if decision.outcome == P.PERMITIR:
                permitted.append(tx)
                rules_by_tx[tid] = decision.rules_dicts()
            elif decision.outcome == P.INFORMAR:
                assert decision.notice_code                     # informar siempre trae su aviso
                turn.blocks.append(B.notice(decision.notice_code, f"{line}: {self._notice_text(turn, decision, existing)}"))
            else:
                assert decision.handoff_reason                  # escalar siempre trae su motivo
                await self._escalate(turn, decision.handoff_reason, queue=decision.handoff_queue, tx=tx)
                if decision.handoff_reason == "cargo_pendiente_no_reconocido" and c.get("handoff_id"):
                    turn.blocks.append(B.notice("pending_unrecognized",
                                                f"{line}: {B.t(turn.lang, 'pending_unrecognized', handoff_id=B.short_ref(c['handoff_id']))}"))
        c["lock_after"] = list(dict.fromkeys(lock_products))
        if len(permitted) == 1:
            c["selected"] = permitted[0]["transaction_id"]
            await self._ask_dispute_confirmation(turn, permitted[0], bool(c["lock_after"]))
        elif permitted:
            params = {"transaction_ids": sorted(t["transaction_id"] for t in permitted), "reason_code": c["reason_code"]}
            token, exp = await self.tools.issue_token(turn.ctx, "create_dispute_case", params, self.policy.confirmation_token_ttl_seconds)
            summary = B.multi_confirm_text(permitted, turn.lang)
            turn.trace.add("confirm", "code", implementation="plantilla", output={"texto": summary},
                           extra={"modo": "plantilla", "motivo": "confirmar_reclamos"})
            c["pending"] = {"action": "create_dispute_case", "params": params, "multi": True, "rules": rules_by_tx,
                            "offer_lock_after": bool(c["lock_after"])}
            turn.blocks.append({"type": "action_confirmation", "action": "create_dispute_case", "summary": summary, "params": params,
                                "confirmation_token": token, "expires_at": exp.isoformat(), "disclaimer": B.DISCLAIMER[turn.lang]})
            turn.trace.add("token_emitido", "code", output={"accion": "create_dispute_case", "cargos": len(permitted), "vence": exp})
            turn.conv["state"] = "confirmando_accion"
        elif c["lock_after"]:
            await self._offer_lock(turn, c["lock_after"][0], recommend=False, escalate_after=True)
        else:
            await self._finish(turn, "informado")

    async def _execute_multi(self, turn: Turn, token: str) -> None:
        """Un reclamo por transacción con una sola confirmación: revalida cada uno, crea todos o ninguno y verifica cada uno."""
        c, pending = turn.c, turn.c["pending"]
        ids = pending["params"]["transaction_ids"]
        txs = {}
        for tid in ids:
            tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, tid)
            existing = await self._tool(turn, "get_existing_case", self.tools.get_existing_case, tid)
            self._phase(turn, "checking_policy")
            decision = P.evaluate_dispute(tx, turn.ctx.session_date, existing, self.ml.risk.assess(tx), pending["params"]["reason_code"],
                                          self.policy, refund_requested=bool(c.get("refund_requested")),
                                          asserted_unauthorized=bool(c.get("asserted_unauthorized")))
            turn.trace.add("politica_revalidada", "code", implementation="policy@v1", input={"transaction_id": tid},
                           output={"resultado": decision.outcome}, rules=decision.rules_dicts())
            if decision.outcome != P.PERMITIR:            # algo cambió desde la confirmación: se vuelve a evaluar todo
                await self.tools.invalidate_tokens(turn.ctx)
                c["pending"] = None
                await self._multi_evaluate(turn, ids)
                return
            txs[tid] = tx
        created = await self._tool(turn, "create_dispute_cases", self.tools.create_dispute_cases, retry=False, transaction_ids=ids,
                                   reason_code=pending["params"]["reason_code"],
                                   customer_statement=" ".join(x["claim"] for x in c.get("claims", []))[:1000], token=token,
                                   idempotency_key=turn.idempotency_key, policy_rules=pending.get("rules") or {}, turn_id=None)
        items = []
        for row in created:
            try:
                case = await self._tool(turn, "get_case", self.tools.get_case, row["case_id"])
                ok = case["transaction_id"] == row["transaction_id"] and case["status"] == "registrado"
            except ToolError:
                ok = False
            items.append({"transaction_id": row["transaction_id"], "reference_id": row["case_id"], "reference_label": B.short_ref(row["case_id"]),
                          "verified": ok,
                          "status": "success" if ok else "failed", "label": B.tx_line(txs[row["transaction_id"]], turn.lang)})
            if ok:
                c.setdefault("actions", []).append({"action": "create_dispute_case", "status": "success", "verified": True,
                                                    "reference_id": row["case_id"]})
        all_ok = all(i["verified"] for i in items)
        turn.trace.add("verificacion", "code", output={"accion": "create_dispute_case", "verificados": sum(i["verified"] for i in items),
                                                        "total": len(items)})
        turn.blocks.append({"type": "result", "action": "create_dispute_case",
                            "status": "success" if all_ok else "partial" if any(i["verified"] for i in items) else "failed",
                            "verified": all_ok, "reference_id": None,
                            "details": {"reason_code": pending["params"]["reason_code"], "count": len(items)}, "items": items})
        c["pending"] = None
        if not all_ok:
            turn.say("multi_partial")
            await self._escalate(turn, "accion_no_verificada")
            return
        turn.blocks.append(B.text_block("\n".join([B.t(turn.lang, "multi_done", n=len(items)),
                                                    *[f"• {i['reference_label']}: {i['label']}" for i in items],
                                                    B.t(turn.lang, "multi_done_tail")])))
        if pending.get("offer_lock_after") and c.get("lock_after"):
            await self._offer_lock(turn, c["lock_after"][0], recommend=False, escalate_after=False)
            return
        await self._after_flow(turn)

    async def _show_candidates(self, turn: Turn, txs: list[dict], prompt: str, counts: bool) -> None:
        conv = turn.conv
        if counts and conv["clarification_round"] == 0:
            conv["clarification_round"] = 1
        turn.c["shown"] = turn.c["last_candidates"] = [t["transaction_id"] for t in txs]
        turn.blocks.append(B.text_block(prompt))
        turn.blocks.append({"type": "candidate_list", "prompt": prompt, "candidates": [B.tx_view(t, i + 1, turn.lang) for i, t in enumerate(txs)],
                            "allow_none": True, "round": conv["clarification_round"], "max_rounds": self.policy.max_clarify_rounds})
        conv["state"] = "aclarando"

    async def _propose(self, turn: Turn, tx: dict) -> None:
        """Candidata clara (o elegida): transaction_card para confirmar el movimiento."""
        turn.c["selected"] = tx["transaction_id"]
        turn.c["shown"] = [tx["transaction_id"]]
        self._set_focus(turn, tx)
        self._fact(turn, "transaccion_propuesta", tx["transaction_id"], "search_transactions")
        out = await self._confirm_text(turn, "confirmar_movimiento", turn.c.get("reason_code"), ["comercio", "monto", "fecha"])
        turn.blocks.append(B.text_block(self._fill(turn, out.texto, tx)))
        turn.blocks.append({"type": "transaction_card", "transaction": B.tx_view(tx, lang=turn.lang), "source": "get_transaction"})
        turn.conv["state"] = "confirmando_movimiento"

    def _fill(self, turn: Turn, template: str, tx: dict | None = None, **extra) -> str:
        values = dict(extra)
        if tx:
            values.update({"estado": B.status_label(tx["transaction_status"], turn.lang),     # P-31: después de la guarda R5
                           "comercio": B.tx_label(tx, turn.lang),
                           "monto": B.fmt_money(tx["amount"], tx["currency"], turn.lang),
                           "fecha": B.fmt_date(tx["transaction_date"], turn.lang)})
        try:
            return fill(template, values, set(values) | {"comercio", "monto", "fecha", "tarjeta", "numero_reclamo", "numero_atencion",
                                                          "estado"})
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
        self._set_focus(turn, tx)
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
        self._phase(turn, "checking_policy")
        decision = P.evaluate_dispute(tx, turn.ctx.session_date, existing, risk, c["reason_code"], self.policy,
                                      refund_requested=bool(c.get("refund_requested")),
                                      asserted_unauthorized=bool(c.get("asserted_unauthorized")))
        if c.get("asserted_unauthorized"):
            self._fact(turn, "cliente_afirma_no_haberlo_hecho", True, "mensaje_del_cliente")
        c["last_rules"] = decision.rules_dicts()
        turn.trace.add("politica", "code", implementation="policy@v1", output={"resultado": decision.outcome,
                       "decide": decision.decisive.as_dict() if decision.decisive else None,
                       "ofrecer_bloqueo": decision.offer_lock, "recomendar_bloqueo": decision.recommend_lock},
                       rules=decision.rules_dicts())
        c["offer_lock_product"] = tx["product_id"] if (decision.offer_lock or decision.recommend_lock) else None
        if decision.outcome == P.INFORMAR:
            case_num = existing["case_id"] if existing else None
            assert decision.notice_code                         # informar siempre trae su aviso
            turn.blocks.append(B.notice(decision.notice_code, self._notice_text(turn, decision, existing)))
            out = await self._llm(turn, "explain", turn.lang, "informar", self._rules_for_llm(decision),
                                  self._facts_for_llm(turn, tx), ["numero_reclamo"] if case_num else [])
            turn.blocks.append(B.text_block(self._fill(turn, out.texto, tx, numero_reclamo=B.short_ref(case_num))))
            await self._finish(turn, "cerrado")
            return
        if decision.outcome == P.ESCALAR:
            assert decision.handoff_reason                      # escalar siempre trae su motivo
            await self._escalate(turn, decision.handoff_reason, queue=decision.handoff_queue, tx=tx)
            if decision.handoff_reason == "cargo_pendiente_no_reconocido" and c.get("handoff_id"):     # R2b
                turn.blocks.append(B.notice("pending_unrecognized", B.t(turn.lang, "pending_unrecognized", handoff_id=B.short_ref(c["handoff_id"]))))
            if decision.recommend_lock or decision.offer_lock:
                await self._offer_lock(turn, tx["product_id"], recommend=decision.recommend_lock, escalate_after=True)
            return
        await self._ask_dispute_confirmation(turn, tx, decision.offer_lock)

    async def _ask_dispute_confirmation(self, turn: Turn, tx: dict, offer_lock: bool) -> None:
        """permitir → confirmación explícita de la acción (R4)."""
        c = turn.c
        params = {"transaction_id": tx["transaction_id"], "reason_code": c["reason_code"]}
        token, exp = await self.tools.issue_token(turn.ctx, "create_dispute_case", params, self.policy.confirmation_token_ttl_seconds)
        out = await self._confirm_text(turn, "confirmar_reclamo", c["reason_code"], ["comercio", "monto", "fecha"])
        c["pending"] = {"action": "create_dispute_case", "params": params, "offer_lock_after": offer_lock}
        turn.blocks.append({"type": "action_confirmation", "action": "create_dispute_case", "summary": self._fill(turn, out.texto, tx),
                            "params": params, "confirmation_token": token, "expires_at": exp.isoformat(),
                            "disclaimer": B.DISCLAIMER[turn.lang]})
        turn.trace.add("token_emitido", "code", output={"accion": "create_dispute_case", "vence": exp})
        turn.conv["state"] = "confirmando_accion"

    def _notice_text(self, turn: Turn, decision: P.PolicyDecision, existing: dict | None) -> str:
        es = turn.lang == "es"
        if decision.notice_code == "existing_case":
            assert existing is not None                         # R3 solo informa si hay un reclamo existente
            ref = B.short_ref(existing["case_id"])
            return (f"Ya tienes un reclamo abierto sobre este cargo: {ref} ({existing['status']})." if es else
                    f"Você já tem uma reclamação aberta sobre esta cobrança: {ref} ({existing['status']}).")
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
        return {"comercio": v[0].comercio, "monto": v[0].monto, "fecha": v[0].fecha, "estado": "{estado}"}   # P-31

    # ================================================================ acciones
    async def _on_action(self, turn: Turn, action: dict) -> None:
        kind = action.get("type")
        st, c = turn.conv["state"], turn.c
        if kind == "end_conversation":
            await self._goodbye(turn)
        elif kind == "new_request":
            if st != "inicio":
                raise ApiError(409, "invalid_state", "Primero termina o cancela el paso actual.")
            turn.say("new_request")
        elif kind == "request_human":
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
        elif kind == "select_candidates":          # varios cargos a la vez (lista con selección múltiple)
            ids = list(dict.fromkeys(action.get("transaction_ids") or []))
            if st != "aclarando" or not ids or not set(ids) <= set(c.get("shown") or []):
                raise ApiError(409, "invalid_state", "Esos movimientos no están entre las opciones de este paso.")
            if len(ids) == 1:
                c["selected"] = ids[0]
                await self._confirm_movement(turn)
            else:
                await self._multi_evaluate(turn, ids)
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
                    turn.blocks.append(B.text_block(await self._clarify_text(turn, "mas_datos", [], "mas_datos")))
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
            if action == "create_dispute_case" and pending.get("multi"):
                await self._execute_multi(turn, token)
            elif action == "create_dispute_case":
                tx = await self._tool(turn, "get_transaction", self.tools.get_transaction, pending["params"]["transaction_id"])
                existing = await self._tool(turn, "get_existing_case", self.tools.get_existing_case, tx["transaction_id"])
                risk = self.ml.risk.assess(tx)
                self._phase(turn, "checking_policy")
                decision = P.evaluate_dispute(tx, turn.ctx.session_date, existing, risk, pending["params"]["reason_code"],
                                              self.policy, refund_requested=bool(c.get("refund_requested")),
                                              asserted_unauthorized=bool(c.get("asserted_unauthorized")))
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
                turn.blocks.append(B.notice("existing_case", B.short_ref(e.data.get("case_id"))))
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
                            "reference_id": case_id, "reference_label": B.short_ref(case_id),
                            "details": {"reason_code": pending["params"]["reason_code"]}})
        turn.c["last_case_id"] = case_id
        if turn.c.get("focus"):
            turn.c["focus"]["case_id"] = case_id
        out = await self._llm(turn, "explain", turn.lang, "reclamo_registrado", [], self._facts_for_llm(turn, tx), ["numero_reclamo"])
        turn.blocks.append(B.text_block(self._fill(turn, out.texto, tx, numero_reclamo=B.short_ref(case_id))))
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
        turn.c["last_card"] = {"product_id": product_id, "label": pending.get("card_label", "")}
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
                                "reference_label": B.short_ref(handoff_id),
                                "message": B.t(turn.lang, "handoff", handoff_id=B.short_ref(handoff_id)), "next_step": "contacto_del_banco"})

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

    async def _finish(self, turn: Turn, outcome: str) -> None:
        """Fin de un flujo (resuelto, informado, escalado, cancelado…). La conversación queda abierta en `inicio`
        y al final del turno se pregunta "¿algo más?". Solo la despedida o la inactividad la cierran."""
        turn.flow_done = outcome
        turn.conv["state"] = "inicio"
        turn.conv["clarification_round"] = 0
        turn.c.update(mode=None, multi=False)

    def _redirect_out_of_scope(self, turn: Turn, follow: bool) -> None:
        """Consulta que no es de este chat: texto APROBADO (faq.yaml, fuera_de_alcance) + enlace a la página inicial del banco
        (BANK_HOME_URL, ficticia). Nunca se responde la consulta, ni en parte: aquí no se llama a ningún LLM."""
        version, entries = load_faq()
        entry = entries[OUT_OF_SCOPE_ID]
        turn.trace.add("faq", "code", implementation=version, input={"tema": OUT_OF_SCOPE_ID, "tema_cliente": turn.c.get("tema")},
                       output={"faq_id": entry.id, "metodo": "intencion"})
        turn.blocks.append(B.notice("out_of_scope", entry.texto[turn.lang]))
        turn.blocks.append({"type": "link", "label": B.t(turn.lang, "bank_home"), "url": get_chat_settings().bank_home_url})
        if follow:
            turn.say("oos_follow")

    async def _small_talk(self, turn: Turn, kind: str, lang: str | None) -> None:
        """Mensaje que es SOLO saludo, gracias o despedida: plantilla, sin LLM ni herramientas. Saludo y gracias dejan la
        conversación abierta; la despedida la cierra, como siempre (docs/conversation-flow.md, ciclo de vida)."""
        if lang:
            turn.conv["language"] = lang
        turn.trace.add("fast_path", "code", input={"texto": (turn.message or "")[:100]}, output={"fast_path": kind, "idioma": lang})
        if kind == "farewell":
            await self._goodbye(turn)
        elif kind == "thanks":
            turn.say("thanks")
            turn.blocks.append(B.quick_replies(turn.lang))
            turn.c["offered_more"] = True
        else:
            turn.say("greeting")

    async def _goodbye(self, turn: Turn) -> None:
        if turn.c.get("pending"):
            await self.tools.invalidate_tokens(turn.ctx)
            turn.c["pending"] = None
        turn.say("goodbye")
        turn.trace.add("despedida", "code", output={"cierra": True})
        turn.conv.update(state="cerrado", closed_reason="cliente")

    async def _cancel_pending(self, turn: Turn) -> None:
        pending = turn.c.get("pending") or {}
        await self.tools.invalidate_tokens(turn.ctx)
        turn.c["pending"] = None
        turn.trace.add("cancelado", "code", output={"accion": pending.get("action")})
        turn.say("lock_declined_escalated" if pending.get("escalate_after") else "cancelled")
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
        if pending["action"] == "create_dispute_case" and pending.get("multi"):
            try:
                txs = [await self.tools.get_transaction(turn.ctx, t) for t in pending["params"]["transaction_ids"]]
                summary = B.multi_confirm_text(txs, turn.lang)
            except ToolError:
                summary = B.DISCLAIMER[turn.lang]
        elif pending["action"] == "create_dispute_case":
            try:
                tx = await self.tools.get_transaction(turn.ctx, pending["params"]["transaction_id"])
                out = await self._confirm_text(turn, "confirmar_reclamo", pending["params"]["reason_code"],
                                               ["comercio", "monto", "fecha"])
                summary = self._fill(turn, out.texto, tx)
            except ToolError:
                summary = B.DISCLAIMER[turn.lang]
        elif pending["action"] == "lock_card":
            out = await self._confirm_text(turn, "confirmar_bloqueo", None, ["tarjeta"])
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
        out = await self._confirm_text(turn, "confirmar_bloqueo", None, ["tarjeta"])
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
                            "totals": [{"currency": x["currency"], "count": x["n"], "total": B.money(x["total"]),
                                        "total_label": B.fmt_money(x["total"], x["currency"], turn.lang)} for x in res["spend_by_currency"]],
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
            turn.blocks.append({"type": "case_list", "cases": [{"case_id": x["case_id"], "reference_label": B.short_ref(x["case_id"]),
                                "status": x["status"], "reason_code": x["reason_code"],
                                "created_at": x["created_at"].isoformat(),
                                "transaction": {"label": B.tx_label(x, turn.lang),
                                                "amount": B.money(x["amount"]) if x["amount"] is not None else None, "currency": x["currency"],
                                                "date": x["transaction_date"].isoformat() if x["transaction_date"] else None,
                                                "amount_label": B.fmt_money(x["amount"], x["currency"], turn.lang) if x["amount"] is not None else None,
                                                "date_label": B.fmt_date(x["transaction_date"], turn.lang) if x["transaction_date"] else None}}
                                               for x in cases]})
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
                  "pide_humano": ["¿Qué necesita el cliente?"],
                  "cargo_pendiente_no_reconocido": ["Cargo pendiente que el cliente afirma no haber hecho: ¿es fraude? "
                                                    "Abrir el reclamo formal cuando el cargo se confirme."]}.get(reason, ["Revisar el caso."])
        summary_model = {"model": self.nodes.config.model_for("handoff_summary"), "prompt_version": "handoff_summary@v3"}
        try:
            res = await turn.nodes.handoff_summary(turn.lang, reason, [x["claim"] for x in c.get("claims", [])][-5:], minimal,
                                                   [{"id": r["id"], "resultado": r["resultado"], "motivo": r["motivo"]} for r in rules],
                                                   [{"accion": a["action"], "verificada": a["verified"]} for a in c.get("actions", [])])
            turn.trace.add_llm("handoff_summary", res)
            status = {"estado": B.status_label(tx["transaction_status"], "es") if tx else ""}     # P-31: después de la guarda
            summary = fill(res.data.resumen, status, {"estado"})
            questions = list(dict.fromkeys(open_q + [fill(q, status, {"estado"}) for q in res.data.preguntas_abiertas]))[:5]
            summary_model.update(model_id=res.model_id)
        except LLMError as e:
            res = await self.fallback.handoff_summary(turn.lang, reason, [], minimal, [], [])
            turn.trace.add_llm("handoff_summary", None, error=str(e), fallback="plantilla", model=summary_model["model"])
            summary = fill(res.data.resumen, {"estado": B.status_label(tx["transaction_status"], "es") if tx else ""}, {"estado"})
            questions = open_q
        return {"handoff_id": new_id("hof"), "created_at": datetime.now(timezone.utc).isoformat(),
                "conversation_id": turn.ctx.conversation_id, "trace_turn_ids": [turn.turn_id],
                "customer_ref": dict(cust) if cust else {"customer_id": turn.ctx.customer_id},
                "language": turn.lang, "reason_code": reason, "priority": P.handoff_priority(reason),
                "queue": queue or P.handoff_queue(reason), "request": {
                    "cargo_no_reconocido": "Disputa de un cargo no reconocido", "cobro_indebido": "Disputa de un cobro indebido",
                    "bloquear_tarjeta": "Bloqueo de tarjeta"}.get(str(c.get("intent")), "Atención de una persona"),
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
            await self._finish(turn, "escalado")
            return
        await self._verify_handoff(turn, res["handoff_id"], handoff)
        if reason in ("riesgo_alto", "riesgo_desconocido"):
            turn.blocks[-1]["message"] = B.t(turn.lang, "handoff_fraud", handoff_id=B.short_ref(res["handoff_id"]))
        elif reason == "cargo_pendiente_no_reconocido":
            turn.blocks[-1]["message"] = B.t(turn.lang, "handoff_pending_fraud", handoff_id=B.short_ref(res["handoff_id"]))
        turn.c["handoff_id"] = res["handoff_id"]
        await self._finish(turn, "escalado")

    async def _tool_failed(self, turn: Turn) -> None:
        turn.blocks.append(B.error("tool_failed", B.t(turn.lang, "tool_failed"), retryable=True))
        await self._escalate(turn, "fallo_tool")
