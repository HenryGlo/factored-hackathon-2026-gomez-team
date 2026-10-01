"""Prompt 05, fase 2: límites de peticiones, presupuesto de LLM, tope del mensaje, cabeceras y CORS."""
from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.app.llm.fake import FakeLLMClient
from backend.app.llm.nodes import Nodes
from backend.app.main import create_app
from backend.app.protection.config import Limit
from backend.app.protection.ratelimit import MemoryStore
from backend.tests.conftest import PASSWORD, admin, make_settings


class StubAPI(FakeLLMClient):
    """Se registra como un proveedor real (cuenta para el presupuesto) pero responde como el fake: sin red."""
    provider = "stub_api"


def client(monkeypatch, env: dict | None = None, **settings) -> TestClient:
    monkeypatch.setenv("RATE_LIMITS_ENABLED", "true")
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    return TestClient(create_app(make_settings(**settings)))


def login(c: TestClient, username: str = "cliente_uno"):
    c.get("/api/auth/csrf")
    return c.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                  headers={"X-CSRF-Token": c.cookies.get("csrf_token", "")})


def turn(c: TestClient, cid: str, message: str):
    return c.post(f"/api/conversations/{cid}/turns", json={"message": message},
                  headers={"X-CSRF-Token": c.cookies.get("csrf_token", ""), "Idempotency-Key": str(uuid.uuid4())})


def new_conversation(c: TestClient) -> str:
    r = c.post("/api/conversations", json={}, headers={"X-CSRF-Token": c.cookies["csrf_token"], "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 201, r.text
    return r.json()["conversation_id"]


# ---------------------------------------------------------------- límites de peticiones
def test_window_counter_resets_after_the_window():
    now = [1000.0]
    store = MemoryStore(clock=lambda: now[0])
    lim = Limit(2, 60)
    assert [store.hit("r", "k", lim)[0] for _ in range(3)] == [True, True, False]
    ok, retry = store.hit("r", "k", lim)
    assert not ok and 1 <= retry <= 60
    now[0] += retry
    assert store.hit("r", "k", lim)[0] is True                    # ventana nueva
    assert store.hit("r", "otra-clave", lim)[0] is True            # cada clave cuenta aparte


def test_ip_limit_returns_429_with_retry_after_and_health_is_exempt(clean_auth, monkeypatch):
    with client(monkeypatch, {"RATE_IP_ALL": "3/60"}) as c:
        codes = [c.get("/api/auth/csrf").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        r = c.get("/api/auth/csrf")
        assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and r.json()["error"]["retryable"] is True
        assert 1 <= int(r.headers["Retry-After"]) <= 60 and r.headers["X-Content-Type-Options"] == "nosniff"
        assert all(c.get("/api/health").status_code == 200 for _ in range(5))   # chequeos de salud no cuentan


def test_login_is_stricter_per_ip(clean_auth, monkeypatch):
    with client(monkeypatch, {"RATE_LOGIN_IP": "2/60"}) as c:
        assert login(c).status_code == 200 and login(c).status_code == 200
        r = login(c)
        assert r.status_code == 429 and r.json()["error"]["details"]["rule"] == "login_ip"


def test_turns_are_limited_per_session(clean_auth, monkeypatch):
    with client(monkeypatch, {"RATE_TURNS_SESSION": "2/60"}) as c:
        login(c)
        cid = new_conversation(c)
        assert turn(c, cid, "hola").status_code == 200
        assert turn(c, cid, "¿cuáles fueron mis últimos movimientos?").status_code == 200
        r = turn(c, cid, "gracias")
        assert r.status_code == 429 and r.json()["error"]["details"]["rule"] == "turns_session"
        with TestClient(c.app) as other:          # otra sesión (otra cookie) no comparte el contador de sesión
            login(other, "cliente_dos")
            assert turn(other, new_conversation(other), "hola").status_code == 200


def test_session_limit_applies_to_all_routes(clean_auth, monkeypatch):
    with client(monkeypatch, {"RATE_SESSION_ALL": "3/60"}) as c:
        login(c)                                   # csrf y login: sin cookie de sesión todavía
        codes = [c.get("/api/auth/me").status_code for _ in range(4)]
        assert codes[:3] == [200, 200, 200] and codes[3] == 429


# ---------------------------------------------------------------- tope del mensaje
def test_message_length_cap_with_friendly_error(clean_auth, monkeypatch):
    with client(monkeypatch) as c:
        login(c)
        cid = new_conversation(c)
        r = turn(c, cid, "a" * 2001)
        assert r.status_code == 422 and r.json()["error"]["code"] == "message_too_long"
        assert r.json()["error"]["details"] == {"max_chars": 2000, "chars": 2001} and "menos de 2.000" in r.json()["error"]["message"]
        assert turn(c, cid, "hola " * 400).status_code == 200            # 2.000 justos


# ---------------------------------------------------------------- presupuesto de LLM
def test_llm_budget_degrades_to_templates_and_is_traced(clean_auth, monkeypatch):
    with client(monkeypatch, {"LLM_BUDGET_SESSION_CALLS": "1"}) as c:
        ctl = c.app.state.controller
        ctl.nodes = Nodes(StubAPI(), replace(ctl.nodes.config, provider="anthropic_api"))
        login(c)
        cid = new_conversation(c)
        first = turn(c, cid, "¿cuáles fueron mis últimos movimientos?").json()      # intent + extract: 1-2 llamadas
        second = turn(c, cid, "no reconozco un cargo de 120 dólares")
        assert second.status_code == 200 and second.json()["blocks"]             # sigue funcionando
        with admin() as a:
            steps = a.execute("SELECT turn_id, node, payload FROM app.traces WHERE node = 'presupuesto_llm'").fetchall()
            real_llm_in_second = a.execute("SELECT count(*) FROM app.traces WHERE turn_id = %s AND kind = 'llm' "
                                           "AND implementation <> 'fake'", (second.json()["turn_id"],)).fetchone()[0]
        assert first["turn_id"] not in [s[0] for s in steps]
        assert [s[0] for s in steps] == [second.json()["turn_id"]] and steps[0][2]["output"]["reason"] == "session_calls"
        assert steps[0][2]["output"]["modo"] == "degradado" and real_llm_in_second == 0     # el turno no llamó al LLM


def test_budget_is_skipped_with_the_fake_provider(clean_auth, monkeypatch):
    with client(monkeypatch, {"LLM_BUDGET_SESSION_CALLS": "1"}) as c:
        login(c)
        cid = new_conversation(c)
        for msg in ("hola", "¿cuáles fueron mis últimos movimientos?"):
            assert turn(c, cid, msg).status_code == 200
        with admin() as a:
            assert a.execute("SELECT count(*) FROM app.traces WHERE node = 'presupuesto_llm'").fetchone()[0] == 0


# ---------------------------------------------------------------- cabeceras y CORS
def test_security_headers_and_hsts_only_in_production(clean_auth, monkeypatch):
    with client(monkeypatch) as c:
        h = c.get("/api/health").headers
        assert h["X-Content-Type-Options"] == "nosniff" and h["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert h["X-Frame-Options"] == "DENY" and "default-src 'none'" in h["Content-Security-Policy"]
        assert h["Cache-Control"] == "no-store" and "Strict-Transport-Security" not in h
        assert c.get("/docs").status_code == 200                       # en desarrollo hay documentación
    with client(monkeypatch, app_env="production") as c:
        assert c.get("/api/health").headers["Strict-Transport-Security"].startswith("max-age=")
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


@pytest.mark.parametrize("origin,allowed", [("https://front.example.com", True), ("https://evil.example.com", False)])
def test_cors_is_closed_to_the_frontend_domain(clean_auth, monkeypatch, origin, allowed):
    with client(monkeypatch, cors_allow_origins="https://front.example.com") as c:
        r = c.options("/api/auth/login", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                   "Access-Control-Request-Headers": "content-type,x-csrf-token"})
        assert (r.headers.get("access-control-allow-origin") == origin) is allowed
        if allowed:
            assert r.headers["access-control-allow-credentials"] == "true"
