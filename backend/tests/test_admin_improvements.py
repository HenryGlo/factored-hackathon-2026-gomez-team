"""GET /api/admin/improvements (issue #61): solo admin; resume los PR improve/* y sus reportes; si GitHub falla, lo dice."""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.observability import improvements as I
from backend.tests.conftest import make_settings
from backend.tests.conftest import login

PR = {"number": 48, "html_url": "https://github.com/x/y/pull/48", "title": "test(eval): improvement-loop proposal 20261001",
      "state": "open", "draft": True, "merged_at": None, "head": {"ref": "improve/20261001"}}
REPORT = {"conteo": {"feedback_negativo": 5}, "llm": "claude_cli", "analysis": {"patrones": [
    {"titulo": "Coloquial se clasifica como fuera de alcance", "evidencia": ["conv_a", "conv_b"], "accionable": True,
     "casos_propuestos": [{}, {}], "cambio_de_prompt": {"nodo": "intent"}},
    {"titulo": "Manipulación en el comentario", "evidencia": ["conv_c"], "accionable": False, "casos_propuestos": [], "cambio_de_prompt": None}]}}


def test_summary_of_a_report():
    row = I.summarize(PR, REPORT)
    assert row["date"] == "2026-10-01" and row["pr_state"] == "draft" and row["pr_number"] == 48
    assert row["patterns"][0] == {"title": "Coloquial se clasifica como fuera de alcance", "evidence": "2/5", "actionable": True}
    assert row["proposed_cases"] == 2 and row["prompt_changes"] == 1 and row["llm"] == "claude_cli"
    assert row["report_url"].endswith("/blob/improve/20261001/reports/improve-20261001.md")


def test_endpoint_is_admin_only_and_degrades_when_github_fails(clean_auth, monkeypatch):
    async def boom(client):
        raise httpx.ConnectError("sin red")
    monkeypatch.setattr(I, "fetch", boom)
    with TestClient(create_app(make_settings())) as c:
        assert c.get("/api/admin/improvements").status_code == 401
        login(c, "analista_prueba")
        assert c.get("/api/admin/improvements").status_code == 403
        login(c, "admin_prueba")
        body = c.get("/api/admin/improvements").json()
        assert body["reports"] == [] and body["unavailable"] == "github_unreachable"


def test_endpoint_lists_the_reports(clean_auth, monkeypatch):
    async def fake(client):
        return [I.summarize(PR, REPORT)]
    monkeypatch.setattr(I, "fetch", fake)
    with TestClient(create_app(make_settings())) as c:
        login(c, "admin_prueba")
        body = c.get("/api/admin/improvements").json()
        assert body["unavailable"] is None and body["reports"][0]["pr_url"].endswith("/pull/48")
