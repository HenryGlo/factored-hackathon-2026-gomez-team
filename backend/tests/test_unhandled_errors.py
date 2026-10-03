"""Un error no previsto responde 500 con el formato del contrato y deja su causa en el log del panel (sin datos)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.observability.logs import MEMORY
from backend.tests.conftest import make_settings


def test_unexpected_error_is_a_contract_500_and_is_logged_with_its_place(clean_auth):
    app = create_app(make_settings())

    @app.get("/api/_boom")
    async def boom():
        raise ValueError("algo raro")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error" and r.json()["error"]["retryable"] is True
    events = [e for e in MEMORY.search(level="error") if e.get("event") == "unhandled_error"]
    assert events and events[-1]["exc_type"] == "ValueError" and events[-1]["path"] == "/api/_boom"
