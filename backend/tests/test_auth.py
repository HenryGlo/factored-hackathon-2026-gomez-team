"""Fase 1: autenticación, sesión, roles, CSRF y límite de intentos."""
from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.conftest import PASSWORD, admin, csrf_headers, login, make_settings


def error_code(r) -> str:
    return r.json()["error"]["code"]


# ---------------------------------------------------------------- sin sesión
@pytest.mark.parametrize("method, path", [("GET", "/api/auth/me"), ("GET", "/api/cases"), ("POST", "/api/auth/logout")])
def test_without_session_is_401(client, method, path):
    r = client.request(method, path)
    assert r.status_code == 401 and error_code(r) == "unauthorized"


def test_forged_cookie_is_401(client):
    client.cookies.set("session", "token-inventado")
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and error_code(r) == "unauthorized"


# ---------------------------------------------------------------- login
def test_login_sets_httponly_cookie_and_identity_comes_from_session(client):
    r = login(client, "Cliente_Uno")                      # sin distinguir mayúsculas
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "customer" and body["display_name"] == "Fixture U." and body["idle_timeout_minutes"] == 30
    set_cookie = r.headers.get_list("set-cookie")
    session_cookie = next(h for h in set_cookie if h.startswith("session="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie and "Secure" not in session_cookie
    assert "HttpOnly" not in next(h for h in set_cookie if h.startswith("csrf_token="))
    me = client.get("/api/auth/me").json()
    assert me["role"] == "customer" and me["display_name"] == "Fixture U."
    with admin() as c:   # la base guarda el hash del token, nunca el token
        token_hash, cid = c.execute("SELECT token_hash, customer_id FROM app.sessions").fetchone()
    assert token_hash != client.cookies.get("session") and len(token_hash) == 64 and cid == "FXT-C001"


def test_login_rejects_customer_id_in_body(client):
    r = login(client, "cliente_uno", customer_id="FXT-C002")
    assert r.status_code == 422


def test_secure_cookie_in_production(clean_auth):
    with TestClient(create_app(make_settings(app_env="production")), base_url="https://testserver") as c:
        r = login(c, "cliente_uno")
        assert all("Secure" in h for h in r.headers.get_list("set-cookie"))


@pytest.mark.parametrize("username, password", [("cliente_uno", "otra-clave"), ("no_existe", PASSWORD),
                                                ("cliente_inactivo", PASSWORD)])
def test_bad_credentials_are_generic(client, username, password):
    r = login(client, username, password)
    assert r.status_code == 401 and error_code(r) == "invalid_credentials"
    assert r.json()["error"]["message"] == "Usuario o contraseña incorrectos."
    with admin() as c:
        ev = c.execute("SELECT username, success, reason FROM app.login_events").fetchall()
    assert ev == [(username, False, "inactive" if username == "cliente_inactivo" else "bad_credentials")]


# ---------------------------------------------------------------- CSRF
def test_login_without_csrf_header_is_rejected(client):
    client.get("/api/auth/csrf")
    r = client.post("/api/auth/login", json={"username": "cliente_uno", "password": PASSWORD})
    assert r.status_code == 403 and error_code(r) == "csrf_failed"


def test_state_change_needs_csrf_bound_to_session(client):
    login(client, "cliente_uno")
    assert client.post("/api/auth/logout").status_code == 403                       # sin cabecera
    client.cookies.set("csrf_token", "otro")
    r = client.post("/api/auth/logout", headers={"X-CSRF-Token": "otro"})           # cookie = cabecera, pero no es el de la sesión
    assert r.status_code == 403 and error_code(r) == "csrf_failed"


# ---------------------------------------------------------------- roles
def test_customer_cannot_use_console(client):
    login(client, "cliente_uno")
    r = client.get("/api/cases")
    assert r.status_code == 403 and error_code(r) == "forbidden"


def test_analyst_uses_console_with_read_only_user(client):
    r = login(client, "analista_prueba")
    assert r.json()["role"] == "analyst" and r.json()["display_name"] == "Analista de prueba"
    assert client.get("/api/cases").status_code == 200
    ro = client.app.state.dbs.ro.url
    assert ro.username == make_settings().console_database_url.split("://")[1].split(":")[0]


def test_console_user_cannot_read_password_hashes():
    s = make_settings()
    with psycopg.connect(s.console_database_url.replace("postgresql+psycopg://", "postgresql://")) as c:
        c.execute("SELECT username, role FROM app.users").fetchall()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT password_hash FROM app.users")


# ---------------------------------------------------------------- vencimiento y revocación
def test_idle_expired_session(client):
    login(client, "cliente_uno")
    with admin() as c:
        c.execute("UPDATE app.sessions SET expires_at = now() - interval '1 minute'")
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and error_code(r) == "session_expired"


def test_activity_slides_expiration(client):
    login(client, "cliente_uno")
    with admin() as c:
        c.execute("UPDATE app.sessions SET expires_at = now() + interval '1 minute'")
    assert client.get("/api/auth/me").status_code == 200
    with admin() as c:
        mins = c.execute("SELECT extract(epoch FROM expires_at - now()) / 60 FROM app.sessions").fetchone()[0]
    assert 29 < mins <= 30


def test_session_capped_by_max_lifetime(client):
    login(client, "cliente_uno")
    with admin() as c:
        c.execute("UPDATE app.sessions SET created_at = now() - interval '12 hours' + interval '5 minutes'")
    client.get("/api/auth/me")
    with admin() as c:
        mins = c.execute("SELECT extract(epoch FROM expires_at - now()) / 60 FROM app.sessions").fetchone()[0]
    assert mins <= 5


def test_logout_revokes_session(client):
    login(client, "cliente_uno")
    token = client.cookies.get("session")
    assert client.post("/api/auth/logout", headers=csrf_headers(client)).status_code == 204
    client.cookies.set("session", token)      # reusar el token después del logout
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and error_code(r) == "unauthorized"
    with admin() as c:
        assert c.execute("SELECT reason FROM app.login_events ORDER BY event_id").fetchall() == [("ok",), ("logout",)]


def test_revoked_or_deactivated_user_session_is_401(client):
    login(client, "cliente_uno")
    with admin() as c:
        c.execute("UPDATE app.users SET is_active = false WHERE user_id = 'usr_c1'")
    assert error_code(client.get("/api/auth/me")) == "unauthorized"


# ---------------------------------------------------------------- fuerza bruta
def test_bruteforce_per_user_locks_even_with_right_password(client):
    for _ in range(5):
        assert login(client, "cliente_uno", "mala").status_code == 401
    r = login(client, "cliente_uno", PASSWORD)
    assert r.status_code == 429 and error_code(r) == "rate_limited" and r.headers["Retry-After"]
    assert login(client, "cliente_dos").status_code == 200        # otro usuario desde la misma IP sigue pudiendo
    with admin() as c:
        reasons = [r[0] for r in c.execute("SELECT reason FROM app.login_events ORDER BY event_id")]
    assert reasons == ["bad_credentials"] * 5 + ["locked_user", "ok"]


def test_success_resets_user_counter(client):
    for _ in range(4):
        login(client, "cliente_uno", "mala")
    assert login(client, "cliente_uno").status_code == 200
    for _ in range(4):
        login(client, "cliente_uno", "mala")
    assert login(client, "cliente_uno").status_code == 200


def test_bruteforce_per_ip(clean_auth):
    with TestClient(create_app(make_settings(login_max_failures_ip=3))) as c:
        for i in range(3):
            login(c, f"usuario_{i}", "mala")
        r = login(c, "cliente_uno")
        assert r.status_code == 429
    with admin() as c:
        assert c.execute("SELECT reason FROM app.login_events ORDER BY event_id DESC LIMIT 1").fetchone()[0] == "locked_ip"
