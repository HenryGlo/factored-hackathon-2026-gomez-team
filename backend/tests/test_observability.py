"""Prompt 05, fase 3: logs JSON con contexto, request_id, /api/ready y /api/metrics, sin datos sensibles en los logs."""
from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.observability.logs import redact
from backend.tests.conftest import PASSWORD, make_settings

SECRET_TEXT = "mi-texto-privado-7781"


def login(c: TestClient, username: str = "cliente_uno"):
    c.get("/api/auth/csrf")
    return c.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                  headers={"X-CSRF-Token": c.cookies.get("csrf_token", "")})


def json_lines(out: str) -> list[dict]:
    rows = []
    for line in out.splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def test_redact_hides_sensitive_fields():
    assert redact({"password": "x", "nested": {"Cookie": "y", "ok": 1}, "items": [{"message": "hola"}]}) == \
        {"password": "[oculto]", "nested": {"Cookie": "[oculto]", "ok": 1}, "items": [{"message": "[oculto]"}]}


def test_request_id_header_is_returned_and_only_safe_ids_are_accepted(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        rid = c.get("/api/health").headers["X-Request-ID"]
        assert len(rid) == 32
        assert c.get("/api/health", headers={"X-Request-ID": "front-abc12345"}).headers["X-Request-ID"] == "front-abc12345"
        bad = c.get("/api/health", headers={"X-Request-ID": "<script>"}).headers["X-Request-ID"]
        assert bad != "<script>" and len(bad) == 32


def test_json_logs_carry_context_and_never_secrets(clean_auth, capsys, monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "INFO")              # no depender del entorno (CI usa WARNING)
    with TestClient(create_app(make_settings())) as c:
        login(c)
        csrf, cookie = c.cookies["csrf_token"], c.cookies["session"]
        conv = c.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}).json()
        r = c.post(f"/api/conversations/{conv['conversation_id']}/turns", json={"message": f"No reconozco un cargo de 120 dólares {SECRET_TEXT}"},
                   headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4()), "X-Request-ID": "req-test-0001"})
        assert r.status_code == 200
    out = capsys.readouterr().out
    for secret in (PASSWORD, cookie, csrf, SECRET_TEXT):
        assert secret not in out                                           # ni contraseña, ni cookie, ni CSRF, ni texto
    rows = json_lines(out)
    access = [x for x in rows if x["event"] == "http_request"]
    assert {x["route"] for x in access} >= {"/api/auth/login", "/api/conversations", "/api/conversations/{conversation_id}/turns"}
    turn_req = next(x for x in access if x.get("request_id") == "req-test-0001")
    assert turn_req["status"] == 200 and turn_req["latency_ms"] > 0 and turn_req["conversation_id"] == conv["conversation_id"]
    assert len(turn_req["session"]) == 16                                  # hash de la cookie, no la cookie
    turn = next(x for x in rows if x["event"] == "turn")
    assert turn["request_id"] == "req-test-0001" and turn["turn_id"] == r.json()["turn_id"] == turn["trace_id"]
    assert turn["conversation_id"] == conv["conversation_id"] and turn["state_after"] == "confirmando_movimiento"
    assert turn["llm_calls"] >= 1 and turn["chars"] > 0 and "transaction_card" in turn["blocks"]
    llm = [x for x in rows if x["event"] == "llm_call"]
    assert llm and all(x["turn_id"] == turn["turn_id"] and "latency_ms" in x and x["provider"] == "fake" for x in llm)


def test_ready_checks_database_and_llm_config(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        r = c.get("/api/ready")
        assert r.status_code == 200 and r.json() == {"status": "ready", "llm_provider": "fake",
                                                      "checks": {"database_rw": "ok", "database_ro": "ok", "llm": "ok"}}
    broken = make_settings().model_copy(update={"console_database_url": "postgresql+psycopg://nadie:nada@127.0.0.1:1/bank_no_existe_test"})
    with TestClient(create_app(broken)) as c:
        r = c.get("/api/ready")
        assert r.status_code == 503 and r.json()["status"] == "not_ready" and r.json()["checks"]["database_ro"].startswith("error")
        assert c.get("/api/health").status_code == 200                     # vida ≠ preparación


def test_metrics_for_the_admin_panel(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        login(c)
        csrf = c.cookies["csrf_token"]
        conv = c.post("/api/conversations", json={}, headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}).json()
        c.post(f"/api/conversations/{conv['conversation_id']}/turns", json={"message": "¿cuáles fueron mis últimos movimientos?"},
               headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())})
        assert c.get("/api/metrics").status_code == 403                    # cliente
        login(c, "analista_prueba")
        m = c.get("/api/metrics").json()
    turns = next(e for e in m["endpoints"] if e["route"] == "/api/conversations/{conversation_id}/turns")
    assert turns["requests"] == 1 and turns["latency_ms_p50"] > 0 and turns["errors_5xx"] == 0
    assert any(e["route"] == "/api/metrics" and e["errors_4xx"] == 1 for e in m["endpoints"])
    assert m["llm_daily"] and {"day", "node", "model", "calls", "cost_usd", "latency_ms_p95"} <= set(m["llm_daily"][0])
    assert m["turns_daily"][0]["turns"] >= 1


def test_rate_limited_responses_also_carry_request_id(clean_auth, monkeypatch):
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("RATE_IP_ALL", "1/60")
    with TestClient(create_app(make_settings())) as c:
        c.get("/api/auth/csrf")
        r = c.get("/api/auth/csrf", headers={"X-Request-ID": "req-limited-01"})
        assert r.status_code == 429 and r.headers["X-Request-ID"] == "req-limited-01" and r.headers["Retry-After"]
        assert r.headers["X-Content-Type-Options"] == "nosniff"
