"""GET /api/demo/info: apagado no dice nada; encendido lista usuarios demo y nunca la contraseña."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.conftest import PASSWORD, make_settings


def test_demo_info_is_empty_when_demo_mode_is_off(clean_auth):
    with TestClient(create_app(make_settings())) as c:
        assert c.get("/api/demo/info").json() == {"demo_mode": False}


def test_demo_info_lists_staff_and_notice_without_any_password(clean_auth):
    with TestClient(create_app(make_settings(demo_mode=True))) as c:
        r = c.get("/api/demo/info")                      # público: sin sesión
        assert r.status_code == 200
        body = r.json()
        assert body["demo_mode"] is True and set(body["notice"]) == {"es", "pt"} and set(body["password_hint"]) == {"es", "pt"}
        roles = {u["role"] for u in body["users"]}
        assert {"analyst"} <= roles
        for u in body["users"]:
            assert set(u) == {"username", "role", "display_name", "scenario", "rank", "description"}
            assert set(u["description"]) == {"es", "pt"}
            assert (u["scenario"] is not None) == (u["role"] == "customer")
        assert PASSWORD not in r.text and "password_hash" not in r.text and "customer_id" not in r.text
