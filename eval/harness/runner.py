"""Ejecuta un caso contra el sistema real (API FastAPI en proceso, sin mocks de tools) y junta lo que dejó.

Cada caso: app vacía → usuario de prueba para el cliente elegido por el selector → login → guion fijo
de mensajes y clics → lectura de lo que quedó en la base (reclamos, handoffs, bloqueos, trazas).
El customer_id sale SIEMPRE de la sesión del usuario de prueba.
"""
from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.controller.blocks import CATEGORY_LABEL, tx_label
from backend.app.security import hash_password
from eval.cases.schema import Case, Step
from eval.cases.selectors import resolve
from eval.harness.env import plain, reset_app

MONTHS = {"es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
          "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]}
CURRENCY_WORD = {"USD": "dólares", "COP": "pesos", "ARS": "pesos", "MXN": "pesos", "BRL": "reais"}
CATEGORY_PHRASE = {"es": {"Food": "en el súper", "Health": "en la farmacia", "Transport": "en un taxi"},
                   "pt": {"Food": "no mercado", "Health": "na farmácia", "Transport": "num táxi"}}


def _latin(amount) -> str:
    return f"{Decimal(str(amount)).quantize(Decimal('0.01')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _round2(amount) -> str:
    """Monto 'como lo diría el cliente': 2 cifras significativas, sin decimales (467,70 → 470)."""
    x = float(amount)
    if x < 10:
        return str(round(x))
    mag = 10 ** (len(str(int(x))) - 2)
    return f"{int(round(x / mag) * mag):,}".replace(",", ".")


def _as_date(v) -> date:
    return v.date() if isinstance(v, datetime) else v if isinstance(v, date) else datetime.fromisoformat(str(v)).date()


def tx_vars(tx: dict | None, session_date: date, prefix: str = "") -> dict[str, str]:
    if not tx:
        return {}
    d = tx["transaction_date"].date() if isinstance(tx["transaction_date"], datetime) else tx["transaction_date"]
    wrong = min(d + timedelta(days=2), session_date)
    cat = tx.get("merchant_category") or tx.get("transaction_category")
    v = {"monto_es": _latin(tx["amount"]), "monto_pt": _latin(tx["amount"]), "monto_aprox": _round2(tx["amount"]),
         "moneda_es": CURRENCY_WORD.get(tx["currency"], tx["currency"]), "moneda_pt": CURRENCY_WORD.get(tx["currency"], tx["currency"]),
         "comercio": tx_label(tx, "es"), "comercio_pt": tx_label(tx, "pt"), "fecha_ddmm": d.strftime("%d/%m"),
         "fecha_es": f"{d.day} de {MONTHS['es'][d.month - 1]}", "fecha_pt": f"{d.day} de {MONTHS['pt'][d.month - 1]}",
         "fecha_mal_ddmm": wrong.strftime("%d/%m"), "mes_es": MONTHS["es"][d.month - 1], "mes_pt": MONTHS["pt"][d.month - 1],
         "categoria_es": CATEGORY_PHRASE["es"].get(cat, CATEGORY_LABEL["es"].get(cat, "")),
         "categoria_pt": CATEGORY_PHRASE["pt"].get(cat, CATEGORY_LABEL["pt"].get(cat, ""))}
    return {f"{prefix}{k}": val for k, val in v.items()}


@dataclass
class TurnRecord:
    step: int
    kind: str
    request: dict
    status: int
    latency_ms: float
    response: dict


@dataclass
class CaseRun:
    case: Case
    repeat: int
    variant: str
    resolved: dict                     # IDs resueltos por el selector (solo raw, fuera de git)
    turns: list[TurnRecord] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def responses(self) -> list[dict]:
        return [t.response for t in self.turns if t.kind in ("message", "action") and t.status == 200]


class CaseRunner:
    def __init__(self, app, urls: dict[str, str], session_date: date):
        self.app, self.urls, self.session_date = app, urls, session_date

    def _admin(self):
        return psycopg.connect(plain(self.urls["admin"]), autocommit=True, row_factory=dict_row)

    async def _resolve(self, case: Case, sd: date) -> dict:
        eng = create_async_engine(self.urls["admin"])
        try:
            async with eng.connect() as c:
                return await resolve(c, case.selector, case.pick, sd)
        finally:
            await eng.dispose()

    def run(self, client: TestClient, case: Case, repeat: int, variant: str) -> CaseRun:
        sd = case.session_date or self.session_date
        with self._admin() as c:
            reset_app(c)
        resolved = asyncio.run(self._resolve(case, sd))
        if case.today_after and isinstance(resolved.get(case.today_after), dict):
            sd = _as_date(resolved[case.today_after]["transaction_date"]) + timedelta(days=1)
        run = CaseRun(case, repeat, variant, resolved={k: (v["transaction_id"] if isinstance(v, dict) else v) for k, v in resolved.items()})
        password = secrets.token_urlsafe(16)
        username = f"eval_{case.case_id}".replace("-", "_")[:60]
        with self._admin() as c:
            c.execute("INSERT INTO app.users (user_id, username, password_hash, role, customer_id) VALUES (%s, %s, %s, 'customer', %s)",
                      (f"usr_{uuid.uuid4().hex[:20]}", username, hash_password(password), resolved["customer_id"]))
            c.execute("INSERT INTO app.users (user_id, username, password_hash, role, display_name) VALUES (%s, 'eval_analista', %s, 'analyst', 'Analista eval')",
                      (f"usr_{uuid.uuid4().hex[:20]}", hash_password(password)))
            seg = c.execute("SELECT segment, country FROM ref.customers WHERE customer_id = %s", (resolved["customer_id"],)).fetchone()
        run.artifacts["segment"], run.artifacts["country"] = (seg or {}).get("segment"), (seg or {}).get("country")
        vars_ = {**tx_vars(resolved.get("target"), sd), **tx_vars(resolved.get("second"), sd, "second_"),
                 "foreign_customer": "CLI-ZZZZ9999ZZZZ"}
        self.app.state.controller.reference_date = sd
        self.app.state.faults = set()
        client.cookies.clear()
        state = {"conv": None, "old_token": None, "last": None, "password": password}

        def login():
            client.get("/api/auth/csrf")
            r = client.post("/api/auth/login", json={"username": username, "password": password},
                            headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")})
            assert r.status_code == 200, r.text

        def new_conv(link: bool = False):
            body = {"language": case.language}
            if link and state.get("conv"):
                body["previous_conversation_id"] = state["conv"]
            r = client.post("/api/conversations", json=body,
                            headers={"X-CSRF-Token": client.cookies.get("csrf_token", ""), "Idempotency-Key": str(uuid.uuid4())})
            assert r.status_code == 201, r.text
            state["conv"] = r.json()["conversation_id"]

        try:
            login()
            new_conv()
            for i, step in enumerate(case.steps):
                rec = self._step(client, case, step, i, vars_, resolved, state, login, new_conv, username)
                if rec:
                    run.turns.append(rec)
                    if step.expect_status is None and rec.kind in ("message", "action") and rec.status != 200:
                        break                       # un error inesperado corta el guion (queda registrado)
        except Exception as e:                      # noqa: BLE001 — el caso falla, la corrida sigue
            run.error = f"{type(e).__name__}: {e}"
        finally:
            self.app.state.faults = set()
        run.artifacts.update(self._collect(resolved["customer_id"]))
        return run

    def _step(self, client, case, step: Step, i, vars_, resolved, state, login, new_conv, username) -> TurnRecord | None:
        headers = lambda: {"X-CSRF-Token": client.cookies.get("csrf_token", ""), "Idempotency-Key": str(uuid.uuid4())}
        last = state["last"] or {}
        blocks = {b["type"]: b for b in last.get("blocks", [])}
        if step.when is not None and (last.get("state") or "inicio") not in step.when:
            return None
        if step.expire_session:
            with self._admin() as c:
                c.execute("UPDATE app.sessions SET expires_at = now() - interval '1 minute' WHERE revoked_at IS NULL")
            return TurnRecord(i, "expire_session", {}, 0, 0, {})
        if step.relogin:
            login()
            return TurnRecord(i, "relogin", {}, 200, 0, {})
        if step.fault is not None:
            self.app.state.faults = set(step.fault)
            return TurnRecord(i, "fault", {"fault": step.fault}, 0, 0, {})
        if step.new_conversation:
            new_conv(step.link_previous)
            state["last"] = None
            return TurnRecord(i, "new_conversation", {}, 201, 0, {})
        if step.http is not None:
            who = step.http.get("as", "customer")
            c2 = TestClient(self.app) if who != "customer" else client
            if who == "analyst":
                c2.get("/api/auth/csrf")
                c2.post("/api/auth/login", json={"username": "eval_analista", "password": state["password"]},
                        headers={"X-CSRF-Token": c2.cookies.get("csrf_token", "")})
            path = step.http["path"].format(conversation_id=state["conv"])
            t0 = time.perf_counter()
            r = c2.request(step.http.get("method", "GET"), path)
            return TurnRecord(i, "http", {"http": step.http}, r.status_code, (time.perf_counter() - t0) * 1000,
                              r.json() if r.headers.get("content-type", "").startswith("application/json") else {})
        if step.message is not None:
            body = {"message": step.message.format(**vars_)}
        else:
            a = step.action
            if a in ("confirm", "confirm_old"):
                ac = blocks.get("action_confirmation")
                token = state["old_token"] if a == "confirm_old" else (ac or {}).get("confirmation_token")
                if token is None and step.optional:
                    return None
                body = {"action": {"type": "confirm", "confirmation_token": token or "sin-token"}}
            elif a in ("select_target", "select_second"):
                body = {"action": {"type": "select_candidate", "transaction_id": resolved["target" if a == "select_target" else "second"]["transaction_id"]}}
            elif a == "select_index":
                cands = (blocks.get("candidate_list") or {}).get("candidates") or []
                body = {"action": {"type": "select_candidate", "transaction_id": cands[step.index or 0]["transaction_id"] if cands else "sin-candidatas"}}
            elif a == "select_foreign":
                body = {"action": {"type": "select_candidate", "transaction_id": resolved["foreign"]["transaction_id"]}}
            elif a == "dispute_target":
                body = {"action": {"type": "dispute_transaction", "transaction_id": resolved["target"]["transaction_id"]}}
            elif a == "select_card":
                cards = (blocks.get("card_list") or {}).get("cards") or []
                if not cards and step.optional:
                    return None
                want = {"credito": "Tarjeta Crédito", "debito": "Tarjeta Débito"}.get(step.card or "")
                pick = next((x for x in cards if x["product_type"] == want), cards[0] if cards else None)
                body = {"action": {"type": "select_card", "product_id": pick["product_id"] if pick else "sin-tarjetas"}}
            else:
                body = {"action": {"type": a}}
        t0 = time.perf_counter()
        r = client.post(f"/api/conversations/{state['conv']}/turns", json=body, headers=headers())
        lat = (time.perf_counter() - t0) * 1000
        resp = r.json()
        if r.status_code == 200:
            state["last"] = resp
            ac = next((b for b in resp.get("blocks", []) if b["type"] == "action_confirmation"), None)
            if ac and state["old_token"] is None:
                state["old_token"] = ac["confirmation_token"]
        kind = "message" if step.message is not None else "action"
        return TurnRecord(i, kind, body, r.status_code, lat, resp)

    def _collect(self, customer_id: str) -> dict:
        with self._admin() as c:
            q = lambda sql, *p: [dict(r) for r in c.execute(sql, p).fetchall()]
            return {
                "cases": q("SELECT case_id, customer_id, transaction_id, reason_code, status FROM app.dispute_cases"),
                "handoffs": q("SELECT handoff_id, customer_id, reason_code, queue, priority, payload FROM app.handoffs"),
                "overrides": q("SELECT customer_id, product_id, status FROM app.card_status_overrides"),
                "conversations": q("SELECT conversation_id, state, language, clarification_round FROM app.conversations"),
                "traces": q("""SELECT turn_id, step_seq, node, kind, implementation, tool, model, model_id, prompt_version, latency_ms,
                               cost_usd, error, payload->>'fallback' AS fallback, payload->>'modo' AS modo, payload->>'motivo' AS motivo,
                               payload->'output' AS output FROM app.traces
                               ORDER BY created_at, turn_id, step_seq"""),
                "owned_tx": {r["transaction_id"] for r in c.execute("SELECT transaction_id FROM ref.transactions WHERE customer_id = %s",
                                                                    (customer_id,)).fetchall()},
                "owned_products": {r["product_id"] for r in c.execute("SELECT product_id FROM ref.products WHERE customer_id = %s",
                                                                      (customer_id,)).fetchall()},
            }
