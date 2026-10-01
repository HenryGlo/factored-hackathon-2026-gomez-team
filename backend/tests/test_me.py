"""GET /api/me/transactions y /api/me/cases (pantallas Mis movimientos y Mis reclamos) y disputa desde un movimiento."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.conftest import PASSWORD, make_settings
from backend.tests.test_conversations import REF, extra_rows  # noqa: F401  (fixture de movimientos sintéticos)


def login(c: TestClient, username: str = "cliente_uno"):
    c.get("/api/auth/csrf")
    assert c.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                  headers={"X-CSRF-Token": c.cookies.get("csrf_token", "")}).status_code == 200


def h(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies["csrf_token"], "Idempotency-Key": str(uuid.uuid4())}


def test_my_transactions_are_only_mine_with_filters_and_formatted(clean_auth, extra_rows):  # noqa: F811
    with TestClient(create_app(make_settings(reference_date=REF))) as c:
        assert c.get("/api/me/transactions").status_code == 401
        login(c)
        r = c.get("/api/me/transactions", params={"from": "2026-07-01", "to": "2026-07-05"}).json()
        ids = {t["transaction_id"] for t in r["transactions"]}
        assert ids and all(i.startswith("FXT-T") for i in ids) and r["period"] == {"from": "2026-07-01", "to": "2026-07-05"}
        t = next(x for x in r["transactions"] if x["transaction_id"] == "FXT-T9007")
        assert t["amount_label"] == "77,00 USD" and t["date_label"] == "1 jul 2026" and t["status_label"] == "Aprobado"
        assert "fraud_score" not in t and "customer_id" not in t
        pend = c.get("/api/me/transactions", params={"from": "2026-07-01", "to": "2026-07-05", "status": "Pending"}).json()
        assert "FXT-T9009" in {x["transaction_id"] for x in pend["transactions"]} and {x["status"] for x in pend["transactions"]} == {"Pending"}
        farm = c.get("/api/me/transactions", params={"from": "2026-07-01", "to": "2026-07-05", "merchant": "farmacia"}).json()
        assert {x["transaction_id"] for x in farm["transactions"]} == {"FXT-T9007", "FXT-T9008"}
        assert c.get("/api/me/transactions", params={"from": "2026-07-05", "to": "2026-07-01"}).status_code == 400
        pt = c.get("/api/me/transactions", params={"from": "2026-07-01", "to": "2026-07-05", "lang": "pt"}).json()
        assert next(x for x in pt["transactions"] if x["transaction_id"] == "FXT-T9007")["date_label"] == "1 jul. 2026"
        login(c, "analista_prueba")
        assert c.get("/api/me/transactions").status_code == 403                 # la consola no tiene "mis movimientos"


def test_dispute_from_my_transactions_and_my_cases(clean_auth, extra_rows):  # noqa: F811
    with TestClient(create_app(make_settings(reference_date=REF))) as c:
        login(c)
        assert c.get("/api/me/cases").json() == {"cases": []}
        conv = c.post("/api/conversations", json={"dispute_transaction_id": "FXT-T9007"}, headers=h(c)).json()
        r = c.post(f"/api/conversations/{conv['conversation_id']}/turns",
                   json={"action": {"type": "dispute_transaction", "transaction_id": "FXT-T9007"}}, headers=h(c)).json()
        assert r["state"] == "confirmando_movimiento"
        r = c.post(f"/api/conversations/{conv['conversation_id']}/turns", json={"message": "sí"}, headers=h(c)).json()
        ac = next(b for b in r["blocks"] if b["type"] == "action_confirmation")
        c.post(f"/api/conversations/{conv['conversation_id']}/turns",
               json={"action": {"type": "confirm", "confirmation_token": ac["confirmation_token"]}}, headers=h(c))
        cases = c.get("/api/me/cases").json()["cases"]
        assert len(cases) == 1 and cases[0]["transaction"]["transaction_id"] == "FXT-T9007" and cases[0]["status"] == "registrado"
        assert cases[0]["transaction"]["amount_label"] == "77,00 USD"
        # un movimiento de otro cliente no sirve para abrir la conversación (no se revela si existe)
        assert c.post("/api/conversations", json={"dispute_transaction_id": "FXT-T0102"}, headers=h(c)).status_code == 404
